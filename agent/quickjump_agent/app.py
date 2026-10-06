"""Wires the pieces together: browser connections, merged list, window, tray, hotkeys."""

import time
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QAction, QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QCheckBox, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, hotkeys, integration, kwin, profiles, system, themes
from .config import save_config
from .settings_dialog import SettingsDialog
from .state import Store
from .window import BarWindow
from .wsserver import WsServer

PROTOCOL = 1
AGENT_VERSION = __version__
PROFILE_COLOURS = ['#6aa8ff', '#f29e4c', '#5fd068', '#e4626f', '#b38cff', '#3cc8c8', '#e0c341', '#ff7fbf']


class Agent(QObject):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.store = Store(newest_on_top=cfg['newItemsOnTop'], parent=self)
        self.clients = {}  # profileId -> WsClient

        self.server = WsServer(self)
        self.server.connected.connect(self._on_client)

        self.window = BarWindow()
        self.window.bare_digits = cfg['bareDigits']
        self.window.set_newest_key(cfg['armNewestKey'])
        self.apply_theme()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self.apply_theme())
        self.window.jump_requested.connect(self.jump)
        self.window.remove_requested.connect(self.remove)
        self.window.order_changed.connect(self.store.reorder)
        self.window.settings_requested.connect(self.open_settings)
        self.window.copy_requested.connect(self._copy_url)
        self.window.hide_requested.connect(self.hide_window)
        self.window.newest_requested.connect(self.jump_newest)

        self.store.changed.connect(self.refresh)
        # Shutting down closes every browser connection; the window may already
        # be gone by then, so stop reacting.
        self._quitting = False
        QApplication.instance().aboutToQuit.connect(lambda: setattr(self, '_quitting', True))

        self.hotkeys = hotkeys.create(self)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self._show_hotkeys()


        self._build_tray()

    # ---------------------------------------------------------------- start

    def start(self):
        if not self.server.listen(self.cfg['port']):
            QMessageBox.critical(
                None, 'QuickJump agent',
                f"Cannot listen on 127.0.0.1:{self.cfg['port']} ({self.server.error()}).\n\n"
                'Another program is using that port. Pick another one in the agent '
                'settings and the same one in each browser\'s QuickJump settings.',
            )
        integration.refresh()
        kwin.ensure_rule()
        self._apply_hotkeys(force=False)
        self._show_hotkeys()  # keys rebound in System Settings were adopted just now
        self.refresh()
        self.window.reveal()
        if not self.cfg.get('setupDone'):
            QTimer.singleShot(400, self._first_run)

    def _first_run(self):
        box = QMessageBox(QMessageBox.Icon.Information, system.APP_NAME, 'QuickJump agent is running.')
        text = ('Add tabs from any browser profile with right-click → “Add to Quick Jump”.\n\n')
        if self.tray.isVisible():
            text += 'Click the tray icon to jump to the newest item.'
        else:
            text += ('This desktop shows no tray icons'
                     + (' — the “AppIndicator and KStatusNotifierItem Support” GNOME extension adds them'
                        if system.desktop() == 'gnome' else '')
                     + '. Use the hotkeys, or start the agent again from the app menu to show its window.')
        box.setInformativeText(text)
        login = QCheckBox('Start the agent when I log in')
        login.setChecked(True)
        box.setCheckBox(login)
        box.exec()
        integration.set_autostart(login.isChecked())
        self.cfg['setupDone'] = True
        save_config(self.cfg)
    def apply_theme(self, theme=None):
        """Paint with `theme` (a preview from the settings dialog) or the saved one."""
        from .window import system_dark
        self.window.apply_palette(themes.resolve(theme or self.cfg.get('theme'), system_dark()))

    def _show_hotkeys(self):
        """What the window header and tooltips say; empty where no hotkey reaches the agent."""
        keys = self.cfg['keys']
        live = self.hotkeys.available and not isinstance(self.hotkeys, hotkeys.ManualShortcuts)
        self.window.set_hotkeys(
            self.cfg['hotkeyStyle'],
            keys.get('arm', '') if live else '',
            keys.get('newest', '') if live else '',
            self.cfg['slotModifier'] if live else '',
        )

    def _apply_hotkeys(self, force):
        keys = self.cfg['keys']
        wanted = {'toggle': keys.get('toggle', ''), 'newest': keys.get('newest', '')}
        if self.cfg['hotkeyStyle'] == 'single':
            for n in range(1, 10):
                wanted[f'slot{n}'] = f"{self.cfg['slotModifier']}+{n}"
        else:
            wanted['arm'] = keys.get('arm', '')
        effective = self.hotkeys.apply(wanted, force=force)
        if not isinstance(self.hotkeys, hotkeys.KGlobalAccelBackend):
            return
        # Adopt rebinds made in System Settings → Shortcuts.
        adopted = False
        for action in ('toggle', 'newest', 'arm'):
            if action in effective and effective[action] and effective[action] != keys.get(action):
                keys[action] = effective[action]
                adopted = True
        if adopted:
            save_config(self.cfg)

    # ------------------------------------------------------------- browsers

    def _on_client(self, client):
        client.pid = None
        client.message.connect(lambda msg, c=client: self._on_message(c, msg))
        client.closed.connect(lambda c=client: self._on_closed(c))

    def _on_message(self, client, msg):
        t = msg.get('t')
        if t == 'hello':
            self._hello(client, msg)
            return
        if t == 'ping':
            client.send({'t': 'pong'})
            return
        if not client.pid:
            return
        if t == 'jumps':
            jumps = msg.get('jumps')
            if not isinstance(jumps, list):
                return
            for jid in self.store.apply_snapshot(client.pid, [j for j in jumps if isinstance(j, dict)]):
                client.send({'t': 'drop', 'id': jid})
            if not self.store.profiles.get(client.pid, {}).get('dir'):
                self._locate(client.pid)
            reveal = msg.get('reveal')
            if reveal and reveal in self.store.jumps:
                self.window.reveal(reveal)
        elif t == 'activated':
            # The browser switched the tab; raising its window is up to us.
            kwin.raise_window(str(msg.get('title') or ''))
        elif t == 'toggle':
            self.toggle_window()
        elif t == 'show':
            self.window.reveal()

    def _hello(self, client, msg):
        pid = msg.get('profileId')
        if not isinstance(pid, str) or not pid or int(msg.get('v') or 0) != PROTOCOL:
            client.send({'t': 'error', 'error': 'unsupported protocol', 'v': PROTOCOL})
            client.close()
            return
        old = self.clients.get(pid)
        if old is not None and old is not client:
            old.pid = None  # a restarted service worker replaces its old socket
            old.close()
        client.pid = pid
        self.clients[pid] = client
        self.store.upsert_profile(pid, {
            'extId': msg.get('extId'),
            'brands': msg.get('brands'),
            'lastSeen': time.time(),
        })
        self._locate(pid)
        client.send(self._welcome(pid))
        self.refresh()

    def _welcome(self, pid):
        return {'t': 'welcome', 'v': PROTOCOL, 'agentVersion': AGENT_VERSION,
                'profileName': self.profile_name(pid)}

    def _locate(self, pid):
        info = self.store.profiles.get(pid, {})
        found = profiles.locate(pid, info.get('extId'))
        if found:
            self.store.upsert_profile(pid, found)

    def _on_closed(self, client):
        if client.pid and self.clients.get(client.pid) is client:
            del self.clients[client.pid]
            self.refresh()

    # ---------------------------------------------------------------- names

    def profile_name(self, pid):
        info = self.store.profiles.get(pid, {})
        name = self.cfg['profileLabels'].get(pid) or info.get('name')
        browser = info.get('browser')
        if not name:
            return f"{browser or 'Browser'} {pid[:4]}"
        browsers = {p.get('browser') for p in self.store.profiles.values() if p.get('browser')}
        if browser and len(browsers) > 1 and browser != 'Chrome':
            return f'{name} ({browser})'
        return name

    def profile_colour(self, pid):
        order = list(self.store.profiles)
        index = order.index(pid) if pid in order else len(order)
        return PROFILE_COLOURS[index % len(PROFILE_COLOURS)]

    # -------------------------------------------------------------- render

    def refresh(self):
        if self._quitting:
            return
        rows = []
        used = []
        for j in self.store.ordered():
            pid = j.get('profileId')
            if pid not in used:
                used.append(pid)
            rows.append({
                'id': j['id'],
                'title': (j.get('title') or '').strip() or _host(j.get('url')) or 'Untitled',
                'url': j.get('url') or '',
                'favIconUrl': j.get('favIconUrl') or '',
                'profileId': pid,
                'profile': self.profile_name(pid),
                'colour': self.profile_colour(pid),
                # Closed tab, or a browser profile that is not running: still
                # clickable, it reopens the URL in that profile.
                'dead': not j.get('alive') or pid not in self.clients,
            })
        chips = [(pid, self.profile_name(pid), self.profile_colour(pid)) for pid in used]
        newest = self.store.newest()
        self.window.newest_id = newest['id'] if newest else None
        self.window.set_content(rows, chips)
        self.tray.setToolTip('QuickJump' + (f"\nClick: {_label(newest)}" if newest else '\nNo items yet'))

    # ------------------------------------------------------------- actions

    def jump(self, jid):
        j = self.store.jumps.get(jid)
        if not j:
            return
        client = self.clients.get(j.get('profileId'))
        if client is not None:
            client.send({'t': 'activate', 'id': jid})
        elif j.get('url'):
            profiles.launch(self.store.profiles.get(j.get('profileId'), {}), j['url'])

    def jump_newest(self):
        newest = self.store.newest()
        if newest:
            self.jump(newest['id'])

    def remove(self, jid):
        jump = self.store.remove(jid)
        client = jump and self.clients.get(jump.get('profileId'))
        if client:
            client.send({'t': 'drop', 'id': jid})

    def _copy_url(self, jid):
        j = self.store.jumps.get(jid)
        if j:
            QGuiApplication.clipboard().setText(j.get('url') or '')

    def command(self, args):
        """From quickjump-cmd / `--cmd` / a second start: ['slot', '3'], ['newest'], ..."""
        if not args:
            return
        action = args[0]
        if action == 'show':
            self.window.reveal()
        elif action == 'settings':
            QTimer.singleShot(0, self.open_settings)
        elif action == 'quit':
            QApplication.quit()
        elif action == 'slot' and len(args) > 1 and args[1].isdigit():
            self._on_hotkey(f'slot{args[1]}')
        elif action in ('toggle', 'newest', 'arm'):
            self._on_hotkey(action)

    def _on_hotkey(self, action):
        if action == 'toggle':
            self.toggle_window()
        elif action == 'newest':
            self.jump_newest()
        elif action == 'arm':
            self.window.arm()
        elif action.startswith('slot'):
            self.window.jump_to_slot(int(action[4:]))

    # -------------------------------------------------------------- window

    def toggle_window(self):
        if self.window.isVisible():
            self.hide_window()
        else:
            self.window.reveal()

    def hide_window(self):
        self.window.disarm()
        self.window.hide()

    # ---------------------------------------------------------------- tray

    def _build_tray(self):
        self.tray = QSystemTrayIcon(QIcon(str(system.icon_file())), self)
        menu = QMenu()
        menu.addAction('Jump to newest item', self.jump_newest)
        menu.addAction('Show / hide window', self.toggle_window)
        menu.addSeparator()
        menu.addAction('Settings…', self.open_settings)
        quit_action = QAction('Quit', menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.jump_newest()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.toggle_window()

    # ------------------------------------------------------------ settings

    def open_settings(self):
        rows = []
        for pid, info in self.store.profiles.items():
            count = sum(1 for j in self.store.jumps.values() if j.get('profileId') == pid)
            rows.append((pid, self.profile_name(pid), info.get('name'), pid in self.clients, count))
        from .window import system_dark
        dialog = SettingsDialog(self.cfg, rows, self.hotkeys, preview=self.apply_theme, system_dark=system_dark())
        if not dialog.exec():
            self.apply_theme()  # drop any preview
            if dialog.uninstall_requested:
                uninstall(self.hotkeys)
                QApplication.quit()
            return
        old_port = self.cfg['port']
        self.cfg = dialog.result_config()
        save_config(self.cfg)
        integration.set_autostart(dialog.autostart_wanted())
        for pid in dialog.forgotten:
            self.store.forget_profile(pid)
        self.store.set_newest_on_top(self.cfg['newItemsOnTop'])
        self.window.bare_digits = self.cfg['bareDigits']
        self.window.set_newest_key(self.cfg['armNewestKey'])
        self.apply_theme()
        self._show_hotkeys()
        self._apply_hotkeys(force=True)
        if self.cfg['port'] != old_port and not self.server.listen(self.cfg['port']):
            QMessageBox.warning(None, 'QuickJump agent',
                                f"Cannot listen on port {self.cfg['port']}: {self.server.error()}")
        for pid, client in self.clients.items():
            client.send(self._welcome(pid))
        self.refresh()


def _host(url):
    try:
        return (urlsplit(url or '').hostname or '').removeprefix('www.')
    except ValueError:
        return ''


def _label(jump):
    title = (jump.get('title') or '').strip() or _host(jump.get('url')) or 'Untitled'
    return title if len(title) <= 60 else title[:59] + '…'


def uninstall(backend=None):
    """Remove everything the agent added to the desktop. Settings and the list stay."""
    (backend or hotkeys.create()).remove_all()
    kwin.remove_rule()
    integration.remove_all()
