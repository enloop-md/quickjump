"""
quickjump-agent                  start the agent (or bring its window forward)
quickjump-agent --cmd ACTION     tell the running agent to do something; starts
                                 it first if it is not running
    ACTION: show | toggle | newest | arm | slot N | settings | quit
quickjump-agent --uninstall      remove menu entry, autostart, hotkeys, window rule
"""

import sys

ACTIONS = {'show', 'toggle', 'newest', 'arm', 'slot', 'settings', 'quit'}


def _parse(argv):
    if not argv:
        return 'run', ['show']
    if argv[0] in ('-h', '--help'):
        return 'help', []
    if argv[0] == '--uninstall':
        return 'uninstall', []
    if argv[0] == '--cmd' and len(argv) >= 2 and argv[1] in ACTIONS:
        return 'run', argv[1:3]
    if argv[0].startswith('--') and argv[0][2:] in ACTIONS:  # --toggle, --newest, ...
        return 'run', [argv[0][2:], *argv[1:2]]
    return 'help', []


def _send_fast(command):
    """Deliver to a running agent without loading Qt. True if delivered."""
    from . import system
    name = system.instance_name()
    if system.OS == 'windows':
        return False  # named pipe; handled by QLocalSocket below
    import socket
    s = socket.socket(socket.AF_UNIX)
    try:
        s.settimeout(1)
        s.connect(name)
        s.sendall((' '.join(command) + '\n').encode())
        return True
    except OSError:
        return False
    finally:
        s.close()


def _log_uncaught():
    """
    PyQt aborts the process on an exception escaping a slot. Log it instead —
    to stderr and to agent.log next to the state file — and keep running.
    """
    import traceback
    from . import system

    log = system.data_dir() / 'agent.log'

    def hook(kind, value, tb):
        text = ''.join(traceback.format_exception(kind, value, tb))
        sys.stderr.write(text)
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            if log.exists() and log.stat().st_size > 512 * 1024:
                log.unlink()
            with open(log, 'a', encoding='utf-8') as f:
                import time
                f.write(time.strftime('--- %Y-%m-%d %H:%M:%S\n') + text)
        except OSError:
            pass

    sys.excepthook = hook


def main():
    mode, command = _parse(sys.argv[1:])
    if mode == 'help':
        print(__doc__.strip())
        return 0

    if mode == 'run' and _send_fast(command):
        return 0

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    _log_uncaught()

    from . import system
    system.prepare_qt()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    # On Wayland this becomes the window's app id, which the KWin rule matches;
    # on X11 the WM_CLASS. It also names the desktop entry.
    app.setDesktopFileName(system.APP_ID)
    app.setApplicationName(system.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if mode == 'uninstall':
        from .app import uninstall
        uninstall()
        print('QuickJump agent: menu entry, autostart, hotkeys and window rule removed.')
        return 0

    name = system.instance_name()
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):  # Windows path, or a racing second start
        probe.write((' '.join(command) + '\n').encode())
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    if not server.listen(name):
        print(f'quickjump-agent: cannot listen on {name}: {server.errorString()} — '
              'hotkey commands will not reach this instance', file=sys.stderr)

    from .app import Agent
    from .config import load_config

    agent = Agent(load_config())

    def on_connection():
        sock = server.nextPendingConnection()

        def read():
            while sock.canReadLine():
                agent.command(bytes(sock.readLine()).decode(errors='replace').split())
        sock.readyRead.connect(read)
        sock.disconnected.connect(lambda: (read(), sock.deleteLater()))

    server.newConnection.connect(on_connection)
    agent.start()
    if command != ['show']:
        # After the event loop is up — quit() before exec() would be ignored.
        QTimer.singleShot(0, lambda: agent.command(command))
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
