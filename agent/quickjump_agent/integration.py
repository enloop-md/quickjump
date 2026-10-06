"""
Making the agent a citizen of the desktop: app-menu entry, start at login,
the `quickjump-cmd` helper that hotkeys call, and undoing all of it.

Linux:   ~/.local/share/applications/quickjump-agent.desktop (+ icon), and the
         same entry in ~/.config/autostart. Both point at wherever the agent
         runs from — for an AppImage that is the AppImage file, refreshed on
         every start so a moved or updated AppImage keeps working.
macOS:   ~/Library/LaunchAgents/<id>.plist
Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
"""

import os
import plistlib
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

from . import system

XDG_DATA = Path(os.environ.get('XDG_DATA_HOME', system.HOME / '.local' / 'share'))
XDG_CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', system.HOME / '.config'))
DESKTOP_FILE = XDG_DATA / 'applications' / f'{system.APP_ID}.desktop'
AUTOSTART_FILE = XDG_CONFIG / 'autostart' / f'{system.APP_ID}.desktop'
ICON_TARGET = XDG_DATA / 'icons' / 'hicolor' / '128x128' / 'apps' / f'{system.APP_ID}.png'

MAC_AGENT_ID = 'app.quickjump.agent'
MAC_PLIST = system.HOME / 'Library' / 'LaunchAgents' / f'{MAC_AGENT_ID}.plist'
WIN_RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
WIN_RUN_VALUE = 'QuickJump agent'

HELPER = system.data_dir() / 'quickjump-cmd'


# ------------------------------------------------------------------ helpers


def _exec_line(extra=()):
    return ' '.join(shlex.quote(a) for a in [*system.launch_argv(), *extra])


def _desktop_entry(autostart=False):
    lines = [
        '[Desktop Entry]',
        'Type=Application',
        f'Name={system.APP_NAME}',
        'Comment=One floating QuickJump window for every browser profile, with global hotkeys and a tray icon',
        f'Exec={_exec_line()}',
        f'Icon={system.APP_ID}',
        'Terminal=false',
        'Categories=Utility;',
        'StartupNotify=false',
        'Actions=newest;toggle;settings;',
    ]
    if autostart:
        lines += ['X-GNOME-Autostart-enabled=true', 'X-KDE-autostart-after=panel']
    for action, name in (('newest', 'Jump to the newest item'), ('toggle', 'Show / hide the window'),
                         ('settings', 'Settings')):
        lines += ['', f'[Desktop Action {action}]', f'Name={name}', f"Exec={_exec_line(['--cmd', action])}"]
    return '\n'.join(lines) + '\n'


def _write_if_changed(path, text, mode=None):
    try:
        if path.exists() and path.read_text(encoding='utf-8') == text:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        if mode:
            path.chmod(mode)
    except OSError:
        pass


# ----------------------------------------------------------------- refresh


def refresh():
    """
    Runs on every start. Keeps the menu entry, the autostart entry (if the user
    enabled it) and the hotkey helper pointing at this copy of the agent.
    """
    write_helper()
    if system.OS == 'linux':
        _write_if_changed(DESKTOP_FILE, _desktop_entry())
        try:
            if not ICON_TARGET.exists() or ICON_TARGET.stat().st_size != system.icon_file().stat().st_size:
                ICON_TARGET.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(system.icon_file(), ICON_TARGET)
        except OSError:
            pass
        if AUTOSTART_FILE.exists():
            _write_if_changed(AUTOSTART_FILE, _desktop_entry(autostart=True))
    elif autostart_enabled():
        set_autostart(True)  # re-point at a moved app


def write_helper():
    """
    `quickjump-cmd <action> [n]` — what desktop hotkeys and window-manager
    bindings run. It talks to the running agent's socket directly with the
    system python3 (tens of milliseconds); when the agent is not running, or
    there is no python3, it runs the agent binary itself, which starts the
    agent if needed and then carries out the command.
    """
    if system.OS == 'windows':
        return
    sock = system.instance_name()
    fallback = _exec_line(['--cmd'])
    script = f"""#!/bin/sh
# QuickJump agent: send a command to the running agent.
# Usage: quickjump-cmd newest | toggle | show | arm | slot N | settings
if command -v python3 >/dev/null 2>&1; then
  python3 -c '
import socket, sys
s = socket.socket(socket.AF_UNIX)
try:
    s.connect(sys.argv[1])
except OSError:
    sys.exit(3)
s.sendall((" ".join(sys.argv[2:]) + "\\n").encode())
' {shlex.quote(sock)} "$@" && exit 0
fi
# Not running (or no python3): the agent starts and runs the command itself.
exec {fallback} "$@"
"""
    _write_if_changed(HELPER, script, mode=stat.S_IRWXU)


def helper_command(*args):
    if system.OS == 'windows':
        return _exec_line(['--cmd', *args])
    return ' '.join(shlex.quote(a) for a in [str(HELPER), *args])


# ---------------------------------------------------------------- autostart


def autostart_enabled():
    if system.OS == 'linux':
        return AUTOSTART_FILE.exists()
    if system.OS == 'macos':
        return MAC_PLIST.exists()
    if system.OS == 'windows':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
                winreg.QueryValueEx(key, WIN_RUN_VALUE)
            return True
        except OSError:
            return False
    return False


def set_autostart(on):
    if system.OS == 'linux':
        if on:
            _write_if_changed(AUTOSTART_FILE, _desktop_entry(autostart=True))
        elif AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()
    elif system.OS == 'macos':
        if on:
            MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
            with open(MAC_PLIST, 'wb') as f:
                plistlib.dump({
                    'Label': MAC_AGENT_ID,
                    'ProgramArguments': system.launch_argv(),
                    'RunAtLoad': True,
                    'ProcessType': 'Interactive',
                }, f)
        elif MAC_PLIST.exists():
            MAC_PLIST.unlink()
    elif system.OS == 'windows':
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                command = subprocess.list2cmdline(system.launch_argv())
                winreg.SetValueEx(key, WIN_RUN_VALUE, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, WIN_RUN_VALUE)
                except OSError:
                    pass


# ---------------------------------------------------------------- uninstall


def remove_all():
    """Undo refresh() and autostart. Hotkeys and the KWin rule are removed by their owners."""
    set_autostart(False)
    for path in (DESKTOP_FILE, ICON_TARGET, HELPER):
        try:
            path.unlink()
        except OSError:
            pass
