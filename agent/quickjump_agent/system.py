"""
Everything that differs between operating systems and Linux desktops:
where files live, where browsers keep their profiles, how this agent is
started, and what the window system lets a client do.

Kept free of Qt imports so the command-line fast path (`--cmd`) stays quick.
"""

import os
import shutil
import sys
from pathlib import Path

APP_ID = 'quickjump-agent'
APP_NAME = 'QuickJump agent'

if sys.platform == 'darwin':
    OS = 'macos'
elif sys.platform.startswith('win'):
    OS = 'windows'
else:
    OS = 'linux'

HOME = Path.home()


# --------------------------------------------------------------- the desktop


def desktop():
    """'kde', 'gnome', 'cinnamon', 'xfce', 'mate', 'budgie', 'other' — Linux only."""
    if OS != 'linux':
        return OS
    names = os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
    for key, ids in (
        ('kde', ('kde',)),
        ('cinnamon', ('x-cinnamon', 'cinnamon')),
        ('budgie', ('budgie', 'budgie-desktop')),
        ('xfce', ('xfce',)),
        ('mate', ('mate',)),
        ('gnome', ('gnome', 'ubuntu', 'unity', 'pop')),
    ):
        if any(n in ids for n in names):
            return key
    return 'other'


def wayland():
    return OS == 'linux' and (os.environ.get('XDG_SESSION_TYPE') == 'wayland'
                              or bool(os.environ.get('WAYLAND_DISPLAY')))


def prepare_qt():
    """
    Must run before QApplication exists.

    Wayland has no way for a client to keep itself above other windows or pick
    its position — only the compositor can. KWin can be told to with a window
    rule (see kwin.py), so KDE stays native. Everywhere else the agent runs
    through XWayland, where the old X11 "keep above" hint and window positions
    are still honoured (GNOME/Mutter included).
    """
    if wayland() and desktop() != 'kde' and 'QT_QPA_PLATFORM' not in os.environ:
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
        os.environ['_QJ_SET_QPA'] = '1'


def pins_with_kwin_rule():
    return OS == 'linux' and desktop() == 'kde'


# ------------------------------------------------------------------ the files


def config_dir():
    if OS == 'macos':
        return HOME / 'Library' / 'Application Support' / 'QuickJump'
    if OS == 'windows':
        return Path(os.environ.get('APPDATA', HOME / 'AppData' / 'Roaming')) / 'QuickJump'
    return Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'quickjump'


def data_dir():
    if OS in ('macos', 'windows'):
        return config_dir()
    return Path(os.environ.get('XDG_DATA_HOME', HOME / '.local' / 'share')) / 'quickjump'


def instance_name():
    """Local socket the running agent listens on for commands."""
    if OS == 'linux':
        runtime = os.environ.get('XDG_RUNTIME_DIR')
        path = str(Path(runtime) / f'{APP_ID}.sock') if runtime else ''
        # sun_path holds 107 bytes.
        if not path or len(path.encode()) > 100:
            path = f'/tmp/{APP_ID}-{os.getuid()}.sock'
        return path
    if OS == 'macos':
        # A full path, so quickjump-cmd can find it (TMPDIR is per user).
        return str(Path(os.environ.get('TMPDIR', '/tmp')) / f'{APP_ID}.sock')
    user = os.environ.get('USERNAME') or os.environ.get('USER') or 'user'
    return f'{APP_ID}-{user}'


# ------------------------------------------------------------- this program


def bundled():
    """True when running from a PyInstaller build (AppImage, .app, .exe)."""
    return bool(getattr(sys, 'frozen', False))


def resource_dir():
    if bundled():
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def icon_file():
    return resource_dir() / 'icons' / '128.png'


def launch_argv():
    """How to start this very agent again — for autostart and menu entries."""
    appimage = os.environ.get('APPIMAGE')
    if appimage:
        return [appimage]
    if bundled():
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / 'quickjump-agent')]


# ---------------------------------------------------------- other programs


def host_env():
    """
    Environment for programs that are not part of this agent. A PyInstaller
    build points LD_LIBRARY_PATH at its bundled libraries (keeping the old
    value in LD_LIBRARY_PATH_ORIG); a host program such as gsettings, a browser
    or xdg-open must not load those.
    """
    env = dict(os.environ)
    if bundled():
        for var in ('LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH'):
            orig = env.pop(f'{var}_ORIG', None)
            if orig is not None:
                env[var] = orig
            else:
                env.pop(var, None)
        for var in ('QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'PYTHONHOME', 'PYTHONPATH'):
            env.pop(var, None)
    # Set by prepare_qt() for this process only.
    if env.get('QT_QPA_PLATFORM') == 'xcb' and wayland() and os.environ.get('_QJ_SET_QPA'):
        env.pop('QT_QPA_PLATFORM', None)
    env.pop('_QJ_SET_QPA', None)
    return env


def run(argv, capture=False, detached=False):
    """Run a host program; returns its stdout when `capture`, else success."""
    import subprocess
    kwargs = dict(env=host_env(), stdin=subprocess.DEVNULL)
    if OS == 'windows':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        if detached:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=OS != 'windows', **kwargs)
            return True
        out = subprocess.run(argv, capture_output=True, text=True, timeout=10, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None if capture else False
    if capture:
        return out.stdout if out.returncode == 0 else None
    return out.returncode == 0


def open_url(url):
    """Default browser, without leaking bundled libraries into it."""
    if OS == 'linux':
        return run(['xdg-open', url], detached=True)
    if OS == 'macos':
        return run(['open', url], detached=True)
    os.startfile(url)  # noqa: S606 — Windows
    return True


# -------------------------------------------------------------------- browsers


def _local_app_data():
    return Path(os.environ.get('LOCALAPPDATA', HOME / 'AppData' / 'Local'))


def _program_dirs():
    return [Path(os.environ[v]) for v in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA') if os.environ.get(v)]


def browser_roots():
    """
    [(display name, user-data dir, launcher)] for every Chromium browser this
    OS might have. `launcher(profile_dir, url)` returns an argv or None.
    """
    def which(*names):
        def launch(profile_dir, url):
            for n in names:
                exe = shutil.which(n)
                if exe:
                    return [exe, f'--profile-directory={profile_dir}', url]
            return None
        return launch

    def flatpak(app):
        def launch(profile_dir, url):
            exe = shutil.which('flatpak')
            return [exe, 'run', app, f'--profile-directory={profile_dir}', url] if exe else None
        return launch

    def mac_app(app):
        def launch(profile_dir, url):
            return ['open', '-na', app, '--args', f'--profile-directory={profile_dir}', url]
        return launch

    def win_exe(*rel):
        def launch(profile_dir, url):
            for base in _program_dirs():
                for r in rel:
                    exe = base / r
                    if exe.exists():
                        return [str(exe), f'--profile-directory={profile_dir}', url]
            return None
        return launch

    if OS == 'macos':
        sup = HOME / 'Library' / 'Application Support'
        return [
            ('Chrome', sup / 'Google' / 'Chrome', mac_app('Google Chrome')),
            ('Chrome Beta', sup / 'Google' / 'Chrome Beta', mac_app('Google Chrome Beta')),
            ('Chromium', sup / 'Chromium', mac_app('Chromium')),
            ('Brave', sup / 'BraveSoftware' / 'Brave-Browser', mac_app('Brave Browser')),
            ('Edge', sup / 'Microsoft Edge', mac_app('Microsoft Edge')),
            ('Vivaldi', sup / 'Vivaldi', mac_app('Vivaldi')),
        ]
    if OS == 'windows':
        lad = _local_app_data()
        return [
            ('Chrome', lad / 'Google' / 'Chrome' / 'User Data',
             win_exe(r'Google\Chrome\Application\chrome.exe')),
            ('Chromium', lad / 'Chromium' / 'User Data', win_exe(r'Chromium\Application\chrome.exe')),
            ('Brave', lad / 'BraveSoftware' / 'Brave-Browser' / 'User Data',
             win_exe(r'BraveSoftware\Brave-Browser\Application\brave.exe')),
            ('Edge', lad / 'Microsoft' / 'Edge' / 'User Data',
             win_exe(r'Microsoft\Edge\Application\msedge.exe')),
            ('Vivaldi', lad / 'Vivaldi' / 'User Data', win_exe(r'Vivaldi\Application\vivaldi.exe')),
        ]
    cfg = HOME / '.config'
    var = HOME / '.var' / 'app'
    return [
        ('Chrome', cfg / 'google-chrome', which('google-chrome', 'google-chrome-stable')),
        ('Chrome Beta', cfg / 'google-chrome-beta', which('google-chrome-beta')),
        ('Chrome Dev', cfg / 'google-chrome-unstable', which('google-chrome-unstable')),
        ('Chromium', cfg / 'chromium', which('chromium', 'chromium-browser')),
        ('Chromium', HOME / 'snap' / 'chromium' / 'common' / 'chromium', which('chromium')),
        ('Brave', cfg / 'BraveSoftware' / 'Brave-Browser', which('brave-browser', 'brave')),
        ('Edge', cfg / 'microsoft-edge', which('microsoft-edge', 'microsoft-edge-stable')),
        ('Vivaldi', cfg / 'vivaldi', which('vivaldi', 'vivaldi-stable')),
        ('Chrome', var / 'com.google.Chrome' / 'config' / 'google-chrome', flatpak('com.google.Chrome')),
        ('Chromium', var / 'org.chromium.Chromium' / 'config' / 'chromium', flatpak('org.chromium.Chromium')),
        ('Brave', var / 'com.brave.Browser' / 'config' / 'BraveSoftware' / 'Brave-Browser',
         flatpak('com.brave.Browser')),
        ('Edge', var / 'com.microsoft.Edge' / 'config' / 'microsoft-edge', flatpak('com.microsoft.Edge')),
    ]
