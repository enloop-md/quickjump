"""The agent's settings dialog."""

import json
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QColorDialog, QGridLayout, QKeySequenceEdit, QLabel, QPushButton, QRadioButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QColor, QKeySequence

from . import hotkeys, integration, system, themes

def _page(group):
    """A tab holding one settings group, pushed to the top."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(group)
    layout.addStretch(1)
    return page


SLOT_MODIFIERS = ['Meta+Alt', 'Ctrl+Alt', 'Meta+Ctrl', 'Meta+Shift', 'Ctrl+Shift', 'Alt+Shift']


class SettingsDialog(QDialog):
    def __init__(self, cfg, profiles, backend, preview=None, system_dark=True, parent=None):
        """
        profiles: [(pid, label shown now, browser profile name, online, item count)]
        """
        super().__init__(parent)
        self.setWindowTitle('QuickJump agent settings')
        self.cfg = cfg
        self.forgotten = set()
        self.uninstall_requested = False
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)
        general = QWidget()
        general_layout = QVBoxLayout(general)
        tabs.addTab(general, 'General')

        # --- connection
        conn = QGroupBox('Browser connection')
        cf = QFormLayout(conn)
        self.port = QSpinBox(minimum=1024, maximum=65535, value=cfg['port'])
        cf.addRow('Port:', self.port)
        cf.addRow(QLabel('Every browser profile must use the same port\n(QuickJump extension → settings).'))
        general_layout.addWidget(conn)

        # --- hotkeys
        hk = QGroupBox('Global hotkeys')
        hf = QFormLayout(hk)
        self.style_double = QRadioButton('Double strike — arm key, then 1–9 or the newest-item key')
        self.style_single = QRadioButton('Single strike — one chord per item')
        group = QButtonGroup(self)
        group.addButton(self.style_double)
        group.addButton(self.style_single)
        (self.style_single if cfg['hotkeyStyle'] == 'single' else self.style_double).setChecked(True)
        hf.addRow(self.style_double)
        self.arm_key = QKeySequenceEdit(QKeySequence(cfg['keys'].get('arm', '')))
        self.arm_key.setMaximumSequenceLength(1)
        hf.addRow('    Arm key:', self.arm_key)
        self.newest_letter = QComboBox()
        self.newest_letter.addItems(list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        self.newest_letter.setCurrentText(cfg.get('armNewestKey', 'Q'))
        self.newest_letter.setToolTip('Pressed after the arm key. Matched by its place on the keyboard, '
                                      'so it works on any layout.')
        hf.addRow('    Then, for the newest item:', self.newest_letter)
        hf.addRow(self.style_single)
        self.slot_mod = QComboBox()
        self.slot_mod.addItems(SLOT_MODIFIERS)
        if cfg['slotModifier'] not in SLOT_MODIFIERS:
            self.slot_mod.addItem(cfg['slotModifier'])
        self.slot_mod.setCurrentText(cfg['slotModifier'])
        hf.addRow('    Modifier + 1–9:', self.slot_mod)
        self.newest_key = QKeySequenceEdit(QKeySequence(cfg['keys'].get('newest', '')))
        self.newest_key.setMaximumSequenceLength(1)
        hf.addRow('Jump to newest item:', self.newest_key)
        self.toggle_key = QKeySequenceEdit(QKeySequence(cfg['keys'].get('toggle', '')))
        self.toggle_key.setMaximumSequenceLength(1)
        hf.addRow('Show / hide window:', self.toggle_key)
        self.bare = QCheckBox('Bare 1–9 also jump while the QuickJump window is focused')
        self.bare.setChecked(cfg['bareDigits'])
        hf.addRow(self.bare)
        if isinstance(backend, hotkeys.ManualShortcuts) or not backend.available:
            note = QLabel(
                'This desktop gets no automatic global hotkeys. Bind these commands in\n'
                f'{backend.where}:\n\n'
                f"    {integration.helper_command('newest')}\n"
                f"    {integration.helper_command('toggle')}\n"
                f"    {integration.helper_command('slot', '1')}   … slot 9\n"
                f"    {integration.helper_command('arm')}")
            note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            hf.addRow(note)
        else:
            hf.addRow(QLabel(f'Also editable in {backend.where}.'))
        if not backend.can_arm:
            warn = QLabel('Double strike needs the window to take keyboard focus, which this\n'
                          'desktop may refuse — single strike is the reliable choice here.')
            warn.setStyleSheet('color: #d08a2c')
            hf.addRow(warn)
        tabs.addTab(_page(hk), 'Hotkeys')

        # --- window
        win = QGroupBox('Window')
        wl = QVBoxLayout(win)
        self.on_top = QCheckBox('Put new items at the top of the list')
        self.on_top.setChecked(cfg['newItemsOnTop'])
        self.login = QCheckBox('Start the agent when I log in')
        self.login.setChecked(integration.autostart_enabled())
        for w in (self.on_top, self.login):
            wl.addWidget(w)
        general_layout.addWidget(win)
        general_layout.addStretch(1)

        # --- appearance
        self.preview = preview or (lambda theme: None)
        self.system_dark = system_dark
        self.theme = themes.normalise(json.loads(json.dumps(cfg.get('theme') or {})))
        look = QGroupBox('Appearance')
        lf = QFormLayout(look)
        self.scheme = QComboBox()
        for key, scheme in themes.SCHEMES.items():
            self.scheme.addItem(scheme['name'], key)
        self.scheme.setCurrentIndex(self.scheme.findData(self.theme['scheme']))
        self.scheme.currentIndexChanged.connect(self._scheme_changed)
        lf.addRow('Colour scheme:', self.scheme)
        self.mode = QComboBox()
        for key, label in (('system', 'Follow the desktop'), ('dark', 'Dark'), ('light', 'Light')):
            self.mode.addItem(label, key)
        self.mode.setCurrentIndex(self.mode.findData(self.theme['mode']))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        lf.addRow('Variant:', self.mode)
        self.colours_title = QLabel()
        lf.addRow(self.colours_title)
        grid = QGridLayout()
        self.swatches = {}
        for i, (key, label) in enumerate(themes.KEYS.items()):
            button = QPushButton()
            button.setFixedWidth(150)
            button.clicked.connect(lambda _=False, k=key: self._pick(k))
            grid.addWidget(QLabel(label + ':'), i // 2, (i % 2) * 2)
            grid.addWidget(button, i // 2, (i % 2) * 2 + 1)
            self.swatches[key] = button
        lf.addRow(grid)
        reset = QPushButton('Reset colours to the scheme')
        reset.clicked.connect(self._reset_colours)
        lf.addRow(reset)
        tabs.addTab(_page(look), 'Appearance')
        self._show_swatches()

        # --- profiles
        prof = QGroupBox('Browser profiles')
        pl = QVBoxLayout(prof)
        self.table = QTableWidget(len(profiles), 4)
        self.table.setHorizontalHeaderLabels(['Label (editable)', 'Browser profile', 'Status', ''])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.pids = []
        for row, (pid, label, name, online, count) in enumerate(profiles):
            self.pids.append(pid)
            self.table.setItem(row, 0, QTableWidgetItem(cfg['profileLabels'].get(pid, '')))
            self.table.item(row, 0).setToolTip(f'Empty = use “{name or label}”')
            for col, text in ((1, name or '(not found)'), (2, f"{'online' if online else 'offline'}, {count} items")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
            forget = QPushButton('Forget')
            forget.setToolTip('Remove this profile and its items from the agent')
            forget.setEnabled(not online)
            forget.clicked.connect(lambda _=False, r=row, b=forget: self._forget(r, b))
            self.table.setCellWidget(row, 3, forget)
        self.table.resizeColumnsToContents()
        self.table.setMinimumWidth(460)
        pl.addWidget(self.table)
        if not profiles:
            pl.addWidget(QLabel('No browser has connected yet.'))
        tabs.addTab(_page(prof), 'Browser profiles')

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        remove = buttons.addButton('Uninstall…', QDialogButtonBox.ButtonRole.DestructiveRole)
        remove.setToolTip('Remove the menu entry, autostart, hotkeys and window rule, then quit')
        remove.clicked.connect(self._uninstall)
        root.addWidget(buttons)

    def _uninstall(self):
        from PyQt6.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            self, system.APP_NAME,
            'Remove the QuickJump agent from this desktop and quit?\n\n'
            'This takes out its menu entry, autostart, global hotkeys and window rule. '
            'Your list and settings stay, in case you come back. '
            + ('Delete the AppImage file afterwards to remove the program itself.'
               if os.environ.get('APPIMAGE') else ''))
        if answer == QMessageBox.StandardButton.Yes:
            self.uninstall_requested = True
            self.reject()

    # ------------------------------------------------------------- colours

    def _variant(self):
        return themes.variant(self.theme, self.system_dark)

    def _show_swatches(self):
        variant = self._variant()
        colours = themes.resolve(self.theme, self.system_dark)
        custom = self.theme['custom'][variant]
        self.colours_title.setText(f'Colours ({variant} variant) — click one to change it:')
        for key, button in self.swatches.items():
            colour = QColor(colours[key])
            text = '#000000' if colour.lightnessF() > 0.55 else '#ffffff'
            button.setText(colours[key] + ('  · custom' if key in custom else ''))
            button.setStyleSheet(f'QPushButton {{ background: {colours[key]}; color: {text}; '
                                 f'border: 1px solid #888; padding: 3px; }}')

    def _pick(self, key):
        variant = self._variant()
        current = QColor(themes.resolve(self.theme, self.system_dark)[key])
        colour = QColorDialog.getColor(current, self, themes.KEYS[key])
        if colour.isValid():
            self.theme['custom'][variant][key] = colour.name()
            self._changed()

    def _scheme_changed(self):
        # A new scheme starts clean; customise it from there.
        self.theme['scheme'] = self.scheme.currentData()
        self.theme['custom'] = {'dark': {}, 'light': {}}
        self._changed()

    def _mode_changed(self):
        self.theme['mode'] = self.mode.currentData()
        self._changed()

    def _reset_colours(self):
        self.theme['custom'][self._variant()] = {}
        self._changed()

    def _changed(self):
        self._show_swatches()
        self.preview(self.theme)

    def _forget(self, row, button):
        self.forgotten.add(self.pids[row])
        button.setEnabled(False)
        button.setText('Forgotten')
        for col in range(3):
            item = self.table.item(row, col)
            if item:
                f = item.font()
                f.setStrikeOut(True)
                item.setFont(f)

    def result_config(self):
        cfg = dict(self.cfg)
        cfg['port'] = self.port.value()
        cfg['hotkeyStyle'] = 'single' if self.style_single.isChecked() else 'double'
        cfg['keys'] = {
            'arm': self.arm_key.keySequence().toString(),
            'newest': self.newest_key.keySequence().toString(),
            'toggle': self.toggle_key.keySequence().toString(),
        }
        cfg['slotModifier'] = self.slot_mod.currentText()
        cfg['armNewestKey'] = self.newest_letter.currentText()
        cfg['theme'] = self.theme
        cfg['bareDigits'] = self.bare.isChecked()
        cfg['newItemsOnTop'] = self.on_top.isChecked()
        labels = {}
        for row, pid in enumerate(self.pids):
            text = (self.table.item(row, 0).text() or '').strip()
            if text and pid not in self.forgotten:
                labels[pid] = text
        cfg['profileLabels'] = labels
        return cfg

    def autostart_wanted(self):
        return self.login.isChecked()
