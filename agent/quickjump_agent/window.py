"""
The agent's floating window: the same bar as the browser one, holding every
profile's jumps, with a profile filter on top.
"""

import base64

from PyQt6.QtCore import QByteArray, QObject, QPoint, QRect, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
    QSizePolicy, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget,
)

from . import system, themes

ARM_TIMEOUT_MS = 4000

# XKB keycodes (evdev + 8) of the letter keys, by their position on a US
# layout — so the armed "newest" key is found by where it is on the keyboard,
# whatever the active layout types there.
LETTER_KEYCODES = dict(zip('QWERTYUIOP', range(24, 34))) | dict(zip('ASDFGHJKL', range(38, 47))) \
    | dict(zip('ZXCVBNM', range(52, 59)))
ROW_H = 26
DEFAULT_WIDTH = 300
EDGE = 5
REMOVE_W = 22


ROLE = Qt.ItemDataRole.UserRole


def _dot(colour):
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(colour))
    p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QIcon(pix)


# The colours in use (see themes.py); the agent sets them via apply_palette().
_palette = themes.resolve(None, system_dark=True)


def palette():
    return _palette


def system_dark():
    return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light


# ------------------------------------------------------------------ favicons


class Favicons(QObject):
    """Fetches and caches favicons by URL. Unreachable ones get a letter tile."""

    updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._net = QNetworkAccessManager(self)
        self._cache = {}  # url -> QPixmap | None (None = failed or pending)

    def get(self, url):
        if not url:
            return None
        if url in self._cache:
            return self._cache[url]
        self._cache[url] = None
        if url.startswith('data:'):
            self._cache[url] = self._from_data_url(url)
        elif url.startswith(('http://', 'https://')):
            reply = self._net.get(QNetworkRequest(QUrl(url)))
            reply.finished.connect(lambda r=reply, u=url: self._done(u, r))
        return self._cache[url]

    def _from_data_url(self, url):
        head, _, body = url.partition(',')
        try:
            raw = base64.b64decode(body) if head.endswith(';base64') else body.encode()
        except ValueError:
            return None
        pix = QPixmap()
        return pix if pix.loadFromData(QByteArray(raw)) else None

    def _done(self, url, reply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix = QPixmap()
            if pix.loadFromData(reply.readAll()):
                self._cache[url] = pix
                self.updated.emit()
        reply.deleteLater()


# ---------------------------------------------------------------- list rows


class RowDelegate(QStyledItemDelegate):
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, p, option, index):
        row = index.data(ROLE)
        if not row:
            return
        c = palette()
        r = option.rect.adjusted(3, 1, -3, -1)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if row['id'] == self.bar.flash_id:
            bg = QColor(c['accent'])
            bg.setAlpha(60)
            p.setBrush(bg)
            p.drawRoundedRect(r, 6, 6)
        elif hovered:
            p.setBrush(QColor(c['hover']))
            p.drawRoundedRect(r, 6, 6)

        dim = 0.5 if row['dead'] else 1.0
        x = r.left() + 6

        # Slot number — what 1-9 jumps to.
        slot = row['slot']
        f = QFont(option.font)
        f.setPointSizeF(max(6.0, f.pointSizeF() * 0.8))
        if self.bar.armed:
            f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(c['accent'] if self.bar.armed else c['muted']))
        p.drawText(QRect(x, r.top(), 10, r.height()), Qt.AlignmentFlag.AlignCenter, str(slot) if slot else '')
        x += 17

        # Favicon or letter tile.
        icon_rect = QRect(x, r.center().y() - 8, 16, 16)
        p.setOpacity(dim)
        pix = self.bar.favicons.get(row['favIconUrl'])
        if pix:
            p.drawPixmap(icon_rect, pix)
        else:
            p.setBrush(QColor(c['active']))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(icon_rect, 3, 3)
            lf = QFont(option.font)
            lf.setPointSizeF(max(6.0, lf.pointSizeF() * 0.75))
            lf.setBold(True)
            p.setFont(lf)
            p.setPen(QColor(c['muted']))
            p.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, (row['title'][:1] or '?').upper())
        x += 23

        right = r.right() - 4
        if hovered:
            right -= REMOVE_W

        # Profile badge: coloured dot + name, only when several profiles exist.
        if row['profile'] and self.bar.show_profiles:
            bf = QFont(option.font)
            bf.setPointSizeF(max(6.0, bf.pointSizeF() * 0.78))
            p.setFont(bf)
            name = p.fontMetrics().elidedText(row['profile'], Qt.TextElideMode.ElideRight, 90)
            w = p.fontMetrics().horizontalAdvance(name)
            p.setPen(QColor(c['muted']))
            p.drawText(QRect(right - w, r.top(), w, r.height()), Qt.AlignmentFlag.AlignVCenter, name)
            right -= w + 6
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(row['colour']))
            p.drawEllipse(QPoint(right - 2, r.center().y() + 1), 3, 3)
            right -= 12

        # Title.
        tf = QFont(option.font)
        tf.setItalic(row['dead'])
        p.setFont(tf)
        p.setPen(QColor(c['fg']))
        title = p.fontMetrics().elidedText(row['title'], Qt.TextElideMode.ElideRight, max(0, right - x))
        p.drawText(QRect(x, r.top(), right - x, r.height()), Qt.AlignmentFlag.AlignVCenter, title)

        p.setOpacity(1.0)
        if hovered:
            p.setPen(QColor(c['muted']))
            p.setFont(option.font)
            p.drawText(self.remove_rect(option.rect), Qt.AlignmentFlag.AlignCenter, '×')
        p.restore()

    @staticmethod
    def remove_rect(rect):
        return QRect(rect.right() - REMOVE_W - 3, rect.top(), REMOVE_W, rect.height())


class JumpList(QListWidget):
    """
    Click jumps, × or middle-click removes, dragging a row reorders.

    Reordering is plain mouse tracking inside the list rather than Qt's
    drag-and-drop: that goes through the Wayland data-device protocol, which
    is heavier than a list reorder needs and needs a selected row to start.
    """

    activated_id = pyqtSignal(str)
    remove_id = pyqtSignal(str)
    context_id = pyqtSignal(str, QPoint)
    moved = pyqtSignal(int, int)  # from row, to row (as rows read after the move)

    DRAG_START = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context)
        self._press = None      # where the left button went down
        self._drag_row = None   # row being dragged, once past DRAG_START
        self._gap = None        # insertion gap 0..count the row would drop into

    def _id_at(self, pos):
        item = self.itemAt(pos)
        return item.data(ROLE)['id'] if item else None

    def _gap_at(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return 0 if pos.y() < 0 else self.count()
        rect = self.visualItemRect(item)
        row = self.row(item)
        return row + 1 if pos.y() > rect.center().y() else row

    @property
    def dragging(self):
        return self._drag_row is not None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._press is not None and not self.dragging \
                and (pos - self._press).manhattanLength() >= self.DRAG_START:
            item = self.itemAt(self._press)
            if item is not None and self.count() > 1:
                self._drag_row = self.row(item)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self.dragging:
            self._gap = self._gap_at(pos)
            self.viewport().update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        pos = e.position().toPoint()
        if self.dragging and e.button() == Qt.MouseButton.LeftButton:
            src, gap = self._drag_row, self._gap
            self._end_drag()
            if gap is not None:
                dst = gap - 1 if gap > src else gap
                if dst != src:
                    self.moved.emit(src, dst)
            return
        jid = self._id_at(pos)
        # A left press that travelled is neither a click nor (one row) a drag.
        travelled = e.button() == Qt.MouseButton.LeftButton and (
            self._press is None or (pos - self._press).manhattanLength() >= self.DRAG_START)
        self._press = None
        super().mouseReleaseEvent(e)
        if not jid or travelled:
            return
        if e.button() == Qt.MouseButton.MiddleButton:
            self.remove_id.emit(jid)
        elif e.button() == Qt.MouseButton.LeftButton:
            item_rect = self.visualItemRect(self.itemAt(pos))
            if RowDelegate.remove_rect(item_rect).contains(pos):
                self.remove_id.emit(jid)
            else:
                self.activated_id.emit(jid)

    def _end_drag(self):
        self._press = self._drag_row = self._gap = None
        self.unsetCursor()
        self.viewport().update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.dragging or self._gap is None:
            return
        # Dim the row being moved and draw where it would land.
        p = QPainter(self.viewport())
        c = palette()
        dragged = self.visualItemRect(self.item(self._drag_row))
        shade = QColor(c['bg'])
        shade.setAlpha(150)
        p.fillRect(dragged, shade)
        if self._gap < self.count():
            y = self.visualItemRect(self.item(self._gap)).top()
        else:
            y = self.visualItemRect(self.item(self.count() - 1)).bottom() + 1
        p.fillRect(QRect(4, max(0, y - 1), self.viewport().width() - 8, 2), QColor(c['accent']))
        p.end()

    def _context(self, pos):
        jid = self._id_at(pos)
        if jid:
            self.context_id.emit(jid, self.viewport().mapToGlobal(pos))

    def leaveEvent(self, e):
        self.viewport().update()
        super().leaveEvent(e)


class _Frame(QWidget):
    """Inner border drawn above the content, so it adds no layout space."""

    WIDTH = 2

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Resize:
            self.setGeometry(obj.rect())
            self.raise_()
        return False

    def paintEvent(self, _e):
        p = QPainter(self)
        pen = p.pen()
        pen.setColor(QColor(palette()['border']))
        pen.setWidth(self.WIDTH)
        p.setPen(pen)
        half = self.WIDTH // 2
        p.drawRect(self.rect().adjusted(half, half, -half, -half))
        p.end()


# --------------------------------------------------------------------- window


class BarWindow(QWidget):
    jump_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    order_changed = pyqtSignal(list)
    settings_requested = pyqtSignal()
    copy_requested = pyqtSignal(str)
    hide_requested = pyqtSignal()
    newest_requested = pyqtSignal()

    def __init__(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        # Off KDE/Wayland (where a KWin rule does it) a tool window is what keeps
        # it out of the taskbar and the window switcher.
        flags |= Qt.WindowType.Window if system.pins_with_kwin_rule() else Qt.WindowType.Tool
        super().__init__(None, flags)
        # macOS hides tool windows whenever the app is not active; this one must not.
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle('QuickJump')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.resize(DEFAULT_WIDTH, 120)

        self.favicons = Favicons(self)
        self.armed = False
        self.flash_id = None
        self.show_profiles = False
        self.bare_digits = True
        self.newest_key = 'Q'  # second stroke for the newest item, see set_newest_key()
        self.hotkey_style, self.arm_hotkey, self.slot_modifier = 'double', '', ''
        self.newest_hotkey = ''
        self.newest_id = None  # set by the agent; its row's tooltip names the newest hotkey
        self.filter_pid = None
        self.rows = []
        self.profiles = []  # [(pid, name, colour)]
        self.hidden_before_arm = False

        self._arm_timer = QTimer(self, singleShot=True, interval=ARM_TIMEOUT_MS)
        self._arm_timer.timeout.connect(self.cancel_arm)
        self._flash_timer = QTimer(self, singleShot=True, interval=1600)
        self._flash_timer.timeout.connect(self._end_flash)

        # Header
        self.header = QWidget(objectName='head')
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(9, 4, 4, 4)
        hl.setSpacing(4)
        self.brand = QLabel('QUICKJUMP', objectName='brand')
        self.hint = QLabel('', objectName='hint')
        self.hint.hide()
        # The newest item's hotkey, always in view (replaced by `hint` while armed).
        self.keys = QLabel('', objectName='keys')
        # Neither label, nor the chips row below, may widen the window: the
        # width is the user's. They get clipped instead.
        for label in (self.hint, self.keys):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setMinimumWidth(0)
        settings_btn = self._button('⚙\ufe0e', 'QuickJump agent settings', self.settings_requested.emit)
        close_btn = self._button('×', 'Hide the window (it stays in the tray)', self.hide_requested.emit)
        hl.addWidget(self.brand)
        hl.addWidget(self.hint, 1)
        hl.addWidget(self.keys, 1)
        hl.addWidget(settings_btn)
        hl.addWidget(close_btn)

        # Profile filter chips
        self.chips = QWidget(objectName='chips')
        self.chips.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.chips.setMinimumWidth(0)
        self.chips_layout = QHBoxLayout(self.chips)
        self.chips_layout.setContentsMargins(6, 4, 6, 4)
        self.chips_layout.setSpacing(4)

        self.list = JumpList()
        self.list.setItemDelegate(RowDelegate(self))
        self.list.activated_id.connect(self._jump)
        self.list.remove_id.connect(self.remove_requested.emit)
        self.list.context_id.connect(self._context_menu)
        self.list.moved.connect(self._move_row)
        self.favicons.updated.connect(self.list.viewport().update)

        self.frame = _Frame(self)
        self.empty = QLabel('Right-click any page → “Add to Quick Jump”', objectName='empty')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(EDGE, 1, EDGE, 1)
        root.setSpacing(0)
        root.addWidget(self.header)
        root.addWidget(self.chips)
        root.addWidget(self.list)
        root.addWidget(self.empty)

        self._style()

    def _button(self, glyph, tip, slot):
        b = QToolButton(text=glyph, toolTip=tip, objectName='btn')
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        return b

    def apply_palette(self, colours):
        global _palette
        _palette = dict(colours)
        self._style()
        self._build_chips()
        self.list.viewport().update()
        self.frame.update()

    def _style(self):
        c = palette()
        self.setStyleSheet(f"""
            BarWindow {{ background: {c['bg']}; }}
            QWidget {{ color: {c['fg']}; }}
            #head {{ background: {c['head']}; border-bottom: 1px solid {c['line']}; }}
            #brand {{ font-size: 8pt; font-weight: 700; letter-spacing: 1px; color: {c['accent']}; }}
            #hint {{ font-size: 8pt; font-weight: 600; color: {c['accent']}; }}
            #keys {{ font-size: 8pt; color: {c['muted']}; }}
            #btn {{ border: none; border-radius: 5px; padding: 0 5px; color: {c['muted']}; }}
            #btn:hover {{ background: {c['hover']}; color: {c['fg']}; }}
            #chips {{ background: {c['head']}; border-bottom: 1px solid {c['line']}; }}
            #chip {{ border: 1px solid {c['line']}; border-radius: 9px; padding: 1px 8px;
                     font-size: 8pt; color: {c['muted']}; background: transparent; }}
            #chip:hover {{ background: {c['hover']}; }}
            #chip:checked {{ background: {c['active']}; color: {c['fg']}; border-color: {c['accent']}; }}
            #empty {{ color: {c['muted']}; padding: 14px 12px; }}
            QListWidget {{ background: {c['bg']}; outline: none; padding: 2px 0; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {c['active']}; border-radius: 3px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)

    # ------------------------------------------------------------- content

    def set_content(self, rows, profiles):
        """
        rows: [{id, title, url, favIconUrl, profileId, profile, colour, dead}]
        profiles: [(pid, name, colour)] — those that have rows.
        """
        self.rows = rows
        self.profiles = profiles
        self.show_profiles = len(profiles) > 1
        if self.filter_pid and self.filter_pid not in {p[0] for p in profiles}:
            self.filter_pid = None
        self._build_chips()
        self._fill()

    def _build_chips(self):
        while self.chips_layout.count():
            w = self.chips_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.show_profiles:
            self.chips.hide()
            return
        for pid, name, colour in [(None, 'All', None)] + self.profiles:
            chip = QToolButton(text=name, objectName='chip', checkable=True)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.setChecked(pid == self.filter_pid)
            if colour:
                chip.setIcon(_dot(colour))
                chip.setIconSize(QSize(8, 8))
                chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            chip.clicked.connect(lambda _=False, p=pid: self.set_filter(p))
            self.chips_layout.addWidget(chip)
        self.chips_layout.addStretch(1)
        self.chips.show()

    def set_filter(self, pid):
        self.filter_pid = pid
        self._build_chips()
        self._fill()

    def cycle_filter(self, step):
        options = [None] + [p[0] for p in self.profiles]
        if len(options) < 2:
            return
        i = options.index(self.filter_pid) if self.filter_pid in options else 0
        self.set_filter(options[(i + step) % len(options)])

    def visible_rows(self):
        if self.filter_pid is None:
            return self.rows
        return [r for r in self.rows if r['profileId'] == self.filter_pid]

    def _fill(self):
        self.list.clear()
        rows = self.visible_rows()
        for n, row in enumerate(rows, 1):
            item = QListWidgetItem()
            tip = f"{row['title']}\n{row['url']}"
            if row['profile']:
                tip += f"\nProfile: {row['profile']}"
            if row['dead']:
                tip += '\n(tab closed — click to reopen)'
            hotkey = self._slot_hotkey(n)
            if hotkey:
                tip += f'\nHotkey: {hotkey}'
            if row['id'] == self.newest_id and self.newest_hotkey:
                tip += f'\nNewest item: {self.newest_hotkey}'
            item.setToolTip(tip)
            item.setData(ROLE, {**row, 'slot': n if n <= 9 else 0})
            item.setSizeHint(QSize(0, ROW_H))
            self.list.addItem(item)
        self.empty.setVisible(not rows)
        self.list.setVisible(bool(rows))
        self._fit()

    def _fit(self):
        n = len(self.visible_rows())
        screen = self.screen().availableGeometry() if self.screen() else None
        max_list = int(screen.height() * 0.6) if screen else 600
        self.list.setFixedHeight(min(n * ROW_H + 6, max_list))
        self.layout().activate()
        self.resize(self.width(), self.layout().sizeHint().height())

    def _move_row(self, src, dst):
        """A row of the visible list was dragged from `src` to `dst`."""
        visible = [r['id'] for r in self.visible_rows()]
        visible.insert(dst, visible.pop(src))
        if self.filter_pid is None:
            ids = visible
        else:
            # Filtered: only this profile's rows moved; the others keep their
            # places in the full list.
            it = iter(visible)
            ids = [next(it) if r['profileId'] == self.filter_pid else r['id'] for r in self.rows]
        self.order_changed.emit(ids)

    def _context_menu(self, jid, global_pos):
        menu = QMenu(self)
        menu.addAction('Jump', lambda: self._jump(jid))
        menu.addAction('Copy URL', lambda: self.copy_requested.emit(jid))
        menu.addSeparator()
        menu.addAction('Remove', lambda: self.remove_requested.emit(jid))
        menu.exec(global_pos)

    def _jump(self, jid):
        self.disarm()
        self.jump_requested.emit(jid)

    # -------------------------------------------------------------- showing

    def reveal(self, jid=None):
        """Show without taking focus, highlighting a just-added item."""
        if jid and self.filter_pid and not any(r['id'] == jid for r in self.visible_rows()):
            self.set_filter(None)
        self.show()
        self.raise_()
        if jid:
            self.flash_id = jid
            self._flash_timer.start()
            self.list.viewport().update()

    def _end_flash(self):
        self.flash_id = None
        self.list.viewport().update()

    # -------------------------------------------------------------- hotkeys

    def show_armed_hint(self, armed):
        self.hint.setVisible(armed)
        self.keys.setVisible(not armed and bool(self.keys.text()))

    def arm(self):
        """Double-strike: bring the window forward and wait for a digit."""
        self.hidden_before_arm = not self.isVisible()
        self.armed = True
        self.show_armed_hint(True)
        self.show()
        self.raise_()
        self.activateWindow()
        if self.windowHandle():
            self.windowHandle().requestActivate()
        if system.pins_with_kwin_rule():
            from . import kwin
            kwin.activate_self()
        self._arm_timer.start()
        self.list.viewport().update()

    def disarm(self):
        if not self.armed:
            return
        self.armed = False
        self._arm_timer.stop()
        self.show_armed_hint(False)
        self.list.viewport().update()

    def cancel_arm(self):
        if not self.armed:
            return
        self.disarm()
        if self.hidden_before_arm:
            self.hide()

    def jump_to_slot(self, slot):
        rows = self.visible_rows()
        if 0 < slot <= len(rows):
            self._jump(rows[slot - 1]['id'])

    def set_newest_key(self, letter):
        self.newest_key = letter if letter in LETTER_KEYCODES else 'Q'
        self.hint.setText(f'press 1–9 · {self.newest_key} = newest')

    def set_hotkeys(self, style, arm, newest, slot_modifier):
        """Hotkeys to show: next to the title (newest item) and in row tooltips."""
        self.hotkey_style, self.arm_hotkey, self.slot_modifier = style, arm, slot_modifier
        if style == 'double' and arm:
            self.newest_hotkey = f'{arm}, {self.newest_key}'
        else:
            self.newest_hotkey = newest
        self.keys.setText(self.newest_hotkey)
        self.keys.setToolTip(f'Newest item: {self.newest_hotkey}' if self.newest_hotkey else '')
        self.show_armed_hint(self.armed)
        self._fill()

    def _slot_hotkey(self, n):
        if n > 9:
            return ''
        if self.hotkey_style == 'double':
            return f'{self.arm_hotkey}, {n}' if self.arm_hotkey else ''
        return f'{self.slot_modifier}+{n}' if self.slot_modifier else ''

    def _physical(self, e):
        """
        (digit 1-9 or 0, is the newest key) from the physical key where
        possible: with the arm chord's Alt+Shift still held, or on a non-Latin
        layout, the key *text* of the "1" or "Q" key is something else entirely.
        """
        code = e.nativeScanCode()
        if system.OS == 'linux' and code:
            # XKB keycodes: 10-18 are the 1-9 row.
            return (code - 9 if 10 <= code <= 18 else 0), code == LETTER_KEYCODES[self.newest_key]
        key = e.key()
        digit = key - Qt.Key.Key_0 if Qt.Key.Key_1 <= key <= Qt.Key.Key_9 else 0
        if not digit and e.text():
            digit = '!@#$%^&*('.find(e.text()) + 1
        return digit, key == Qt.Key.Key_A + ord(self.newest_key) - ord('A')

    def keyPressEvent(self, e):
        key = e.key()
        if self.armed:
            # Only a digit, the newest key or Esc ends the wait. Auto-repeat of
            # the arm key (still held when focus arrives) and stray keys are
            # ignored; the timeout cancels.
            if e.isAutoRepeat():
                return
            if key == Qt.Key.Key_Escape:
                self.cancel_arm()
                return
            digit, is_newest = self._physical(e)
            if digit:
                self.disarm()
                self.jump_to_slot(digit)
            elif is_newest:
                self.disarm()
                self.newest_requested.emit()
            else:
                return
            # The arm key brought a hidden window up just to read this key.
            if self.hidden_before_arm:
                self.hide()
            return
        digit = key - Qt.Key.Key_0 if Qt.Key.Key_1 <= key <= Qt.Key.Key_9 else 0
        mods = e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                                | Qt.KeyboardModifier.MetaModifier)
        if digit and self.bare_digits and not mods:
            self.jump_to_slot(digit)
        elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Right):
            self.cycle_filter(1)
        elif key in (Qt.Key.Key_Backtab, Qt.Key.Key_Left):
            self.cycle_filter(-1)
        elif key in (Qt.Key.Key_0, Qt.Key.Key_QuoteLeft):
            self.set_filter(None)
        elif key == Qt.Key.Key_Escape:
            self.hide_requested.emit()
        else:
            super().keyPressEvent(e)

    def focusNextPrevChild(self, _next):
        return False  # keep Tab for cycling the profile filter

    def focusOutEvent(self, e):
        self.cancel_arm()
        super().focusOutEvent(e)

    # ------------------------------------------------- moving and resizing

    def _edges(self, pos):
        # Height always fits the content; only the width is the user's.
        edges = Qt.Edge(0)
        if pos.x() <= EDGE:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - EDGE:
            edges |= Qt.Edge.RightEdge
        return edges

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.windowHandle():
            return
        pos = e.position().toPoint()
        edges = self._edges(pos)
        if edges:
            self.windowHandle().startSystemResize(edges)
        elif self.header.geometry().contains(pos) or self.chips.geometry().contains(pos):
            self.windowHandle().startSystemMove()

    def mouseMoveEvent(self, e):
        if self._edges(e.position().toPoint()):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()

    def mouseDoubleClickEvent(self, e):
        # Shrink-wrap again, like the browser bar.
        self._fit()
