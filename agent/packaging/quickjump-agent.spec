# PyInstaller recipe for every OS:  pyinstaller agent/packaging/quickjump-agent.spec
# Produces dist/quickjump-agent/ (Linux, Windows) or dist/QuickJump Agent.app (macOS).
import sys
from pathlib import Path

HERE = Path(SPECPATH)
AGENT = HERE.parent
REPO = AGENT.parent
sys.path.insert(0, str(AGENT))
from quickjump_agent import __version__  # noqa: E402

ICON_PNG = str(REPO / 'icons' / '128.png')

a = Analysis(
    [str(HERE / 'entry.py')],
    pathex=[str(AGENT)],
    datas=[(str(REPO / 'icons' / name), 'icons') for name in ('16.png', '32.png', '48.png', '128.png')],
    hiddenimports=['PyQt6.QtDBus'] if sys.platform.startswith('linux') else [],
    excludes=['tkinter', 'unittest', 'pydoc', 'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtWebEngineCore',
              'PyQt6.QtMultimedia', 'PyQt6.QtPdf', 'PyQt6.QtOpenGL', 'PyQt6.QtSql', 'PyQt6.QtTest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='quickjump-agent',
    console=False,
    icon=ICON_PNG if sys.platform in ('win32', 'darwin') else None,
    strip=sys.platform.startswith('linux'),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name='quickjump-agent', strip=sys.platform.startswith('linux'), upx=False)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='QuickJump Agent.app',
        icon=ICON_PNG,
        bundle_identifier='app.quickjump.agent',
        version=__version__,
        info_plist={
            'CFBundleShortVersionString': __version__,
            'LSUIElement': True,  # tray (menu bar) app: no Dock icon
            'NSHighResolutionCapable': True,
        },
    )
