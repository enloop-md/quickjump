"""
KWin window rule for the agent window (KDE Plasma 6).

On Wayland a client cannot keep itself above other windows, put itself on
every virtual desktop or choose its own position — only the compositor can.
So on first run the agent adds one rule, matched on its app id, that does what
the browser bar's rule in kde/install-kwin-rules.sh does for the fallback bar,
plus letting the window take focus when the arm hotkey asks for it.

Written once; if the user edits or deletes the rule afterwards, it is left
alone (the marker key below remembers it was installed).
"""

import shutil

from . import system

RULE_ID = '3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f'
MARKER = ('quickjumprc', 'KWin', 'agentRuleInstalled')


def _read(file, group, key, default=''):
    out = system.run(['kreadconfig6', '--file', file, '--group', group, '--key', key, '--default', default],
                     capture=True)
    return (out or '').strip()


def _write(file, group, key, value):
    system.run(['kwriteconfig6', '--file', file, '--group', group, '--key', key, value])


def _delete(file, group, key):
    system.run(['kwriteconfig6', '--file', file, '--group', group, '--key', key, '--delete'])


def _reconfigure():
    if not system.run(['qdbus6', 'org.kde.KWin', '/KWin', 'reconfigure']):
        system.run(['dbus-send', '--session', '--type=method_call', '--dest=org.kde.KWin', '/KWin',
                    'org.kde.KWin.reconfigure'])


def _available():
    return system.pins_with_kwin_rule() and shutil.which('kwriteconfig6') and shutil.which('kreadconfig6')


def ensure_rule():
    if not _available():
        return False
    if _read(*MARKER) == 'true':
        return False

    g = RULE_ID
    rc = 'kwinrulesrc'
    values = [
        ('Description', 'QuickJump agent window'),
        ('wmclass', system.APP_ID),
        ('wmclassmatch', '1'),      # 1 = exact match (on Wayland: the app id)
        ('wmclasscomplete', 'false'),
        ('types', '1'),
        # SetRule: 2 = force, 4 = remember.
        ('above', 'true'), ('aboverule', '2'),
        ('desktops', ''), ('desktopsrule', '2'),
        ('skiptaskbar', 'true'), ('skiptaskbarrule', '2'),
        ('skippager', 'true'), ('skippagerrule', '2'),
        ('skipswitcher', 'true'), ('skipswitcherrule', '2'),
        ('positionrule', '4'),
        ('sizerule', '4'),
        # The arm hotkey pulls the window forward to read the next digit.
        ('fsplevel', '0'), ('fsplevelrule', '2'),
    ]
    for key, value in values:
        _write(rc, g, key, value)

    rules = [r for r in _read(rc, 'General', 'rules').split(',') if r]
    if g not in rules:
        rules.append(g)
        _write(rc, 'General', 'rules', ','.join(rules))
        _write(rc, 'General', 'count', str(len(rules)))
    _write(*MARKER, 'true')
    _reconfigure()
    return True


# Raises the browser window showing `title` — restoring it if minimised and
# switching to its virtual desktop. Browsers caption their windows
# "<active tab title> - <browser name>".
RAISE_SCRIPT = '''
const title = %(title)s;
const browser = /chrom|brave|vivaldi|edge|opera/i;
const wins = () => workspace.windowList().filter(w => w.normalWindow && browser.test(w.resourceClass));
const exact = w => w.caption.startsWith(title + ' - ');
const loose = w => w.caption.startsWith(title) || (title.length > 8 && w.caption.includes(title));

function raise(w) {
  if (w.minimized) w.minimized = false;
  if (w.desktops.length && !w.desktops.includes(workspace.currentDesktop)) {
    workspace.currentDesktop = w.desktops[0];
  }
  workspace.activeWindow = w;
}

// The browser retitles its window only after switching the tab, and not always
// before this runs: if nothing matches yet, raise whichever window takes on
// the title next (the agent unloads this script after a couple of seconds).
const now = wins().find(exact) || wins().find(loose);
if (now) {
  raise(now);
} else {
  let done = false;
  for (const w of wins()) {
    w.captionChanged.connect(() => {
      if (!done && (exact(w) || loose(w))) {
        done = true;
        raise(w);
      }
    });
  }
}
'''

# Brings this agent's own window forward and gives it keyboard focus, for the
# double-strike hotkey. Qt's own activation request is a Wayland
# xdg-activation request without a token, which KWin may refuse.
ACTIVATE_SELF_SCRIPT = '''
const appId = %(app_id)s;
const w = workspace.windowList().find(w => w.resourceClass === appId || w.desktopFileName === appId);
if (w) {
  if (w.minimized) w.minimized = false;
  workspace.activeWindow = w;
}
'''

_script_count = 0


def run_script(source, keep_ms=2000):
    """Load and run a one-off KWin script; it is unloaded again after `keep_ms`."""
    global _script_count
    if system.desktop() != 'kde':
        return False
    from PyQt6.QtCore import QTimer
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage

    _script_count += 1
    plugin = f'quickjump-{_script_count}'
    path = system.data_dir() / f'{plugin}.js'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')

    bus = QDBusConnection.sessionBus()
    scripting = ('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting')
    load = QDBusMessage.createMethodCall(*scripting, 'loadScript')
    load.setArguments([str(path), plugin])
    reply = bus.call(load)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage or not reply.arguments() \
            or reply.arguments()[0] < 0:
        path.unlink(missing_ok=True)
        return False
    bus.call(QDBusMessage.createMethodCall('org.kde.KWin', f'/Scripting/Script{reply.arguments()[0]}',
                                           'org.kde.kwin.Script', 'run'))

    def unload():
        msg = QDBusMessage.createMethodCall(*scripting, 'unloadScript')
        msg.setArguments([plugin])
        bus.call(msg)
        path.unlink(missing_ok=True)
    QTimer.singleShot(keep_ms, unload)
    return True


def raise_window(title):
    """Ask KWin to bring the browser window whose active tab is `title` forward."""
    import json
    return bool(title) and run_script(RAISE_SCRIPT % {'title': json.dumps(title)})


def activate_self(app_id=system.APP_ID):
    import json
    return run_script(ACTIVATE_SELF_SCRIPT % {'app_id': json.dumps(app_id)}, keep_ms=1000)


RULE_KEYS = ('Description', 'wmclass', 'wmclassmatch', 'wmclasscomplete', 'types', 'above', 'aboverule',
             'desktops', 'desktopsrule', 'skiptaskbar', 'skiptaskbarrule', 'skippager', 'skippagerrule',
             'skipswitcher', 'skipswitcherrule', 'positionrule', 'sizerule', 'fsplevel', 'fsplevelrule')


def remove_rule():
    if not _available():
        return
    rc = 'kwinrulesrc'
    rules = [r for r in _read(rc, 'General', 'rules').split(',') if r]
    if RULE_ID in rules:
        rules.remove(RULE_ID)
        _write(rc, 'General', 'rules', ','.join(rules))
        _write(rc, 'General', 'count', str(len(rules)))
    for key in RULE_KEYS:
        _delete(rc, RULE_ID, key)
    _delete(*MARKER)
    _reconfigure()
