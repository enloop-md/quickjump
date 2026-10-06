"""
Global hotkeys, one backend per desktop:

- KDE                    KGlobalAccel over D-Bus (Wayland and X11). Instant,
                         editable under System Settings → Shortcuts.
- GNOME, Budgie,         custom shortcuts written into the desktop's own
  Cinnamon, Xfce         keyboard settings, each running `quickjump-cmd …`
                         (see integration.py). Works on Wayland and X11 and on
                         every version of those desktops; the user sees and can
                         edit them in the desktop's keyboard settings.
- anything else          nothing is registered; the settings dialog shows the
                         `quickjump-cmd` lines to bind in the window manager
                         (Sway, Hyprland, i3, …).
- macOS, Windows         not yet.

Every backend has the same face: apply(wanted, force) registers exactly the
actions in `wanted` ({action: 'Alt+Shift+Q'}) and returns what is in effect;
remove_all() takes everything back out. Desktop-shortcut backends deliver key
presses through the command socket; KGlobalAccel through its `triggered`.
"""

import ast
import json
import shutil

from PyQt6.QtCore import QMetaType, QObject, QVariant, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeySequence

try:  # not shipped in every PyQt6 build (Windows)
    from PyQt6.QtDBus import QDBusArgument, QDBusConnection, QDBusMessage
except ImportError:
    QDBusArgument = QDBusConnection = QDBusMessage = None

from . import integration, system
from .config import write_private

LABELS = {
    'toggle': 'Show / hide the QuickJump window',
    'newest': 'Jump to the newest QuickJump item',
    'arm': 'Arm QuickJump item hotkeys (then press 1-9)',
    **{f'slot{n}': f'Jump to QuickJump item {n}' for n in range(1, 10)},
}


def key_code(text):
    seq = QKeySequence(text)
    return seq[0].toCombined() if not seq.isEmpty() else 0


def key_text(code):
    return QKeySequence(code).toString() if code else ''


def command_args(action):
    """'slot3' -> ['slot', '3']"""
    if action.startswith('slot'):
        return ['slot', action[4:]]
    return [action]


class Backend(QObject):
    triggered = pyqtSignal(str)
    available = False
    # Shown in the settings dialog: where else the user can change the keys.
    where = ''
    # Whether "arm, then press a digit" can work: the window must get focus.
    can_arm = True

    def apply(self, wanted, force=False):
        return {}

    def remove_all(self):
        pass


# ---------------------------------------------------------------- KDE


class KGlobalAccelBackend(Backend):
    SERVICE = 'org.kde.kglobalaccel'
    COMPONENT = 'quickjump'
    COMPONENT_NAME = 'QuickJump'
    SET_PRESENT = 2
    NO_AUTOLOADING = 4
    where = 'System Settings → Keyboard → Shortcuts → QuickJump'

    def __init__(self, parent=None):
        super().__init__(parent)
        if QDBusConnection is None:
            return
        self.bus = QDBusConnection.sessionBus()
        self.available = self.bus.isConnected() and self.bus.interface().isServiceRegistered(self.SERVICE).value()
        self.registered = set()
        self._listening = False

    def _call(self, method, *args):
        msg = QDBusMessage.createMethodCall(self.SERVICE, '/kglobalaccel', 'org.kde.KGlobalAccel', method)
        msg.setArguments(list(args))
        reply = self.bus.call(msg)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return None
        return reply.arguments()

    @staticmethod
    def _array(values, type_):
        arg = QDBusArgument()
        arg.beginArray(QMetaType(type_.value))
        for v in values:
            arg.add(v, type_.value)
        arg.endArray()
        return arg

    def _action_id(self, action):
        return self._array([self.COMPONENT, action, self.COMPONENT_NAME, LABELS[action]], QMetaType.Type.QString)

    def apply(self, wanted, force=False):
        if not self.available:
            return {}
        flags = QVariant(self.SET_PRESENT | (self.NO_AUTOLOADING if force else 0))
        flags.convert(QMetaType(QMetaType.Type.UInt.value))
        effective = {}
        for action, text in wanted.items():
            aid = self._action_id(action)
            self._call('doRegister', aid)
            code = key_code(text)
            res = self._call('setShortcut', aid, self._array([code] if code else [], QMetaType.Type.Int), flags)
            got = res[0] if res and res[0] else []
            effective[action] = key_text(got[0]) if got else ''
            self.registered.add(action)
        for action in list(self.registered - set(wanted)):
            self._call('unregister', self.COMPONENT, action)
            self.registered.discard(action)
        self._listen()
        return effective

    def remove_all(self):
        if self.available:
            for action in LABELS:
                self._call('unregister', self.COMPONENT, action)
            self.registered.clear()

    def _listen(self):
        if self._listening:
            return
        res = self._call('getComponent', self.COMPONENT)
        if not res:
            return
        path = res[0].path() if hasattr(res[0], 'path') else str(res[0])
        self._listening = self.bus.connect(
            self.SERVICE, path, 'org.kde.kglobalaccel.Component', 'globalShortcutPressed', self._on_pressed
        )

    if QDBusMessage is not None:
        @pyqtSlot(QDBusMessage)
        def _on_pressed(self, msg):
            self._pressed(msg)

    def _pressed(self, msg):
        args = msg.arguments()
        if len(args) >= 2 and args[0] == self.COMPONENT:
            self.triggered.emit(args[1])


# ------------------------------------------------- desktop keyboard settings


def gtk_accel(text):
    """'Alt+Shift+R' -> '<Alt><Shift>r' (GNOME, Cinnamon, Xfce notation)."""
    parts = [p for p in text.split('+') if p]
    if not parts:
        return ''
    *mods, key = parts
    names = {'Ctrl': '<Control>', 'Alt': '<Alt>', 'Shift': '<Shift>', 'Meta': '<Super>'}
    key = key if len(key) > 1 else key.lower()
    return ''.join(names.get(m, f'<{m}>') for m in mods) + key


def _gv_str(s):
    return "'" + s.replace('\\', '\\\\').replace("'", "\\'") + "'"


def _gv_list(items):
    return '[' + ', '.join(_gv_str(i) for i in items) + ']'


class DesktopShortcutsBackend(Backend):
    """Writes custom shortcuts that run quickjump-cmd. Remembers what it wrote."""

    available = True
    can_arm = False  # the window cannot reliably take focus from a shortcut here
    RECORD = system.data_dir() / 'desktop-shortcuts.json'

    def _written(self):
        try:
            return json.loads(self.RECORD.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _remember(self, written):
        write_private(self.RECORD, json.dumps(written))

    def apply(self, wanted, force=False):
        written = self._written()
        for action in [a for a in written if a not in wanted]:
            self._remove(action, written[action])
            del written[action]
        for action, text in wanted.items():
            accel = gtk_accel(text)
            if written.get(action) != accel or force:
                if action in written:
                    self._remove(action, written[action])
                if accel:
                    self._add(action, accel, integration.helper_command(*command_args(action)))
                    written[action] = accel
                else:
                    written.pop(action, None)
        self._remember(written)
        return {a: t for a, t in wanted.items()}

    def remove_all(self):
        written = self._written()
        for action, accel in written.items():
            self._remove(action, accel)
        self._remember({})

    def _add(self, action, accel, command):
        raise NotImplementedError

    def _remove(self, action, accel):
        raise NotImplementedError


class GsettingsList:
    """Shared plumbing for GNOME and Cinnamon: a list key + relocatable entries."""

    @staticmethod
    def get(schema, key):
        out = system.run(['gsettings', 'get', schema, key], capture=True)
        text = (out or '').strip().removeprefix('@as ')
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return []
        return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

    @staticmethod
    def has_schema(schema):
        return schema in (system.run(['gsettings', 'list-schemas'], capture=True) or '').split()

    @staticmethod
    def set(schema, key, value):
        system.run(['gsettings', 'set', schema, key, value])


class GnomeShortcuts(DesktopShortcutsBackend):
    LIST_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys'
    ENTRY_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
    BASE = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/'
    where = 'Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts'

    def _path(self, action):
        return f'{self.BASE}quickjump-{action}/'

    def _add(self, action, accel, command):
        path = self._path(action)
        entry = f'{self.ENTRY_SCHEMA}:{path}'
        GsettingsList.set(entry, 'name', _gv_str(LABELS[action]))
        GsettingsList.set(entry, 'command', _gv_str(command))
        GsettingsList.set(entry, 'binding', _gv_str(accel))
        paths = GsettingsList.get(self.LIST_SCHEMA, 'custom-keybindings')
        if path not in paths:
            GsettingsList.set(self.LIST_SCHEMA, 'custom-keybindings', _gv_list(paths + [path]))

    def _remove(self, action, accel):
        path = self._path(action)
        paths = GsettingsList.get(self.LIST_SCHEMA, 'custom-keybindings')
        if path in paths:
            GsettingsList.set(self.LIST_SCHEMA, 'custom-keybindings', _gv_list([p for p in paths if p != path]))
        entry = f'{self.ENTRY_SCHEMA}:{path}'
        for key in ('name', 'command', 'binding'):
            system.run(['gsettings', 'reset', entry, key])


class CinnamonShortcuts(DesktopShortcutsBackend):
    LIST_SCHEMA = 'org.cinnamon.desktop.keybindings'
    ENTRY_SCHEMA = 'org.cinnamon.desktop.keybindings.custom-keybinding'
    BASE = '/org/cinnamon/desktop/keybindings/custom-keybindings/'
    where = 'System Settings → Keyboard → Shortcuts → Custom Shortcuts'

    def _add(self, action, accel, command):
        name = f'quickjump-{action}'
        entry = f'{self.ENTRY_SCHEMA}:{self.BASE}{name}/'
        GsettingsList.set(entry, 'name', _gv_str(LABELS[action]))
        GsettingsList.set(entry, 'command', _gv_str(command))
        GsettingsList.set(entry, 'binding', _gv_list([accel]))
        names = GsettingsList.get(self.LIST_SCHEMA, 'custom-list')
        if name not in names:
            GsettingsList.set(self.LIST_SCHEMA, 'custom-list', _gv_list(names + [name]))

    def _remove(self, action, accel):
        name = f'quickjump-{action}'
        names = GsettingsList.get(self.LIST_SCHEMA, 'custom-list')
        if name in names:
            GsettingsList.set(self.LIST_SCHEMA, 'custom-list', _gv_list([n for n in names if n != name]))
        entry = f'{self.ENTRY_SCHEMA}:{self.BASE}{name}/'
        for key in ('name', 'command', 'binding'):
            system.run(['gsettings', 'reset', entry, key])


class XfceShortcuts(DesktopShortcutsBackend):
    where = 'Settings → Keyboard → Application Shortcuts'

    def _add(self, action, accel, command):
        system.run(['xfconf-query', '-c', 'xfce4-keyboard-shortcuts', '-p', f'/commands/custom/{accel}',
                    '-n', '-t', 'string', '-s', command])

    def _remove(self, action, accel):
        system.run(['xfconf-query', '-c', 'xfce4-keyboard-shortcuts', '-p', f'/commands/custom/{accel}', '-r'])


class ManualShortcuts(Backend):
    """Nothing to register; the user binds quickjump-cmd in their window manager."""

    where = 'your window manager’s key bindings'


def create(parent=None):
    d = system.desktop()
    if d == 'kde':
        kga = KGlobalAccelBackend(parent)
        if kga.available:
            return kga
    if d in ('gnome', 'budgie') and shutil.which('gsettings') and GsettingsList.has_schema(
            GnomeShortcuts.LIST_SCHEMA):
        return GnomeShortcuts(parent)
    if d == 'cinnamon' and shutil.which('gsettings') and GsettingsList.has_schema(CinnamonShortcuts.LIST_SCHEMA):
        return CinnamonShortcuts(parent)
    if d == 'xfce' and shutil.which('xfconf-query'):
        return XfceShortcuts(parent)
    return ManualShortcuts(parent)
