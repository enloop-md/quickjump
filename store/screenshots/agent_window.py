"""
Render the agent's real window (agent/quickjump_agent/window.py) offscreen,
filled with the mocked jumps, to a PNG.

    QT_QPA_PLATFORM=offscreen python3 agent_window.py OUT.png [dark|light] [armed]
"""

import base64
import pathlib
import sys

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'agent'))

from quickjump_agent import themes, window  # noqa: E402
from quickjump_agent.app import PROFILE_COLOURS  # noqa: E402

# Same items as mock-data.js.
JUMPS = [
    ('j1', 'Very important call', 'call', 'WORK', False),
    ('j2', 'Q4 roadmap — draft', 'doc', 'WORK', False),
    ('j6', 'Flight check-in', 'plane', 'Personal', False),
    ('j3', 'Production dashboard', 'dash', 'WORK', False),
    ('j4', 'PR #1287: Fix login timeout', 'pr', 'WORK', False),
    ('j7', 'Inbox (3)', 'mail', 'Personal', True),
    ('j5', 'Team chat — #release', 'chat', 'WORK', False),
]
PROFILES = ['WORK', 'Personal']


def data_url(name):
    raw = (HERE / 'favicons' / f'{name}.svg').read_bytes()
    return 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode()


def main():
    out = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else 'dark'
    armed = 'armed' in sys.argv[3:]

    app = QApplication(sys.argv[:1])
    app.setFont(app.font().__class__('Noto Sans', 10))
    win = window.BarWindow()
    win.apply_palette(themes.resolve({'scheme': 'amber', 'mode': mode}, system_dark=mode == 'dark'))
    win.set_newest_key('Q')
    win.set_hotkeys('double', 'Alt+Shift+Q', 'Alt+Shift+R', '')
    rows = [
        {'id': jid, 'title': title, 'url': '', 'favIconUrl': data_url(icon), 'profileId': prof,
         'profile': prof, 'colour': PROFILE_COLOURS[PROFILES.index(prof)], 'dead': dead}
        for jid, title, icon, prof, dead in JUMPS
    ]
    win.newest_id = 'j1'
    win.set_content(rows, [(p, p, PROFILE_COLOURS[i]) for i, p in enumerate(PROFILES)])
    if armed:
        win.armed = True
        win.show_armed_hint(True)
    win.resize(330, win.height())
    win.show()
    app.processEvents()
    win.set_content(win.rows, win.profiles)  # re-fit now that the window has a screen
    app.processEvents()

    pix = win.grab()
    # Rounded corners, like the real window on a compositor.
    rounded = QPixmap(pix.size())
    rounded.setDevicePixelRatio(pix.devicePixelRatio())
    rounded.fill(Qt.GlobalColor.transparent)
    p = QPainter(rounded)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor('white'))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(win.rect().toRectF(), 8, 8)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.drawPixmap(QPoint(0, 0), pix)
    p.end()
    rounded.save(out)


if __name__ == '__main__':
    main()
