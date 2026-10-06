"""Agent settings (agent.json) and on-disk locations — see system.py for where."""

import json
import os

from . import system

CONFIG_FILE = system.config_dir() / 'agent.json'
STATE_FILE = system.data_dir() / 'state.json'

DEFAULT_PORT = 8787

DEFAULTS = {
    # Must match the port in each extension's settings.
    'port': DEFAULT_PORT,
    # 'double': press the arm key, then 1-9 (or R for the newest item).
    # 'single': one chord per slot, <slotModifier>+1..9.
    'hotkeyStyle': 'single' if system.desktop() not in ('kde', 'windows', 'macos') else 'double',
    'keys': {
        'arm': 'Alt+Shift+Q',
        'newest': 'Alt+Shift+R',
        'toggle': 'Alt+Shift+J',
    },
    'slotModifier': 'Meta+Alt',
    # Double strike: after the arm key, this letter opens the newest item. The
    # arm key's own letter by default — Alt+Shift+Q, Q.
    'armNewestKey': 'Q',
    # Bare 1-9 jump while the agent window itself is focused.
    'bareDigits': True,
    'newItemsOnTop': True,
    # profileId -> name the user typed; wins over the browser's profile name.
    'profileLabels': {},
    # Colours: a scheme from themes.py plus the user's own overrides.
    'theme': {'scheme': 'amber', 'mode': 'system', 'custom': {'dark': {}, 'light': {}}},
    # The first-run "start at login?" question was answered.
    'setupDone': False,
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        stored = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        stored = {}
    if isinstance(stored, dict):
        for key, value in stored.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def save_config(cfg):
    write_private(CONFIG_FILE, json.dumps(cfg, indent=2))


def write_private(path, text):
    """Atomic write, readable only by the user."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)
