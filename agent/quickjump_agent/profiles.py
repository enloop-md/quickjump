"""
Working out which browser profile a connection belongs to.

An extension cannot read its own profile's name or directory. It can mint a
UUID (`profileId`) and keep it in chrome.storage.local, though — and that
storage lives on disk at
    <browser user data>/<profile dir>/Local Extension Settings/<extension id>/
So the agent finds the directory whose extension storage contains the UUID,
then reads the profile's display name from the browser's `Local State`. No
extra extension permission, and it works for profiles that are not signed in.
"""

import json
from pathlib import Path

from . import system


def locate(profile_id, ext_id):
    """Returns {browser, root, dir, name} or None if the profile is not found."""
    if not profile_id or not ext_id or not ext_id.isalnum():
        return None
    needle = profile_id.encode()
    for browser, root, _ in system.browser_roots():
        if not root.is_dir():
            continue
        for store in root.glob(f'*/Local Extension Settings/{ext_id}'):
            if _contains(store, needle):
                directory = store.parent.parent.name
                return {
                    'browser': browser,
                    'root': str(root),
                    'dir': directory,
                    'name': profile_name(root, directory),
                }
    return None


def _contains(store, needle):
    # LevelDB: recent writes sit verbatim in the .log; compacted tables are
    # snappy-compressed, which leaves a non-repeating string like a UUID intact.
    for f in store.iterdir():
        if f.suffix in ('.log', '.ldb') and f.is_file():
            try:
                if needle in f.read_bytes():
                    return True
            except OSError:
                pass
    return False


def profile_name(root, directory):
    try:
        state = json.loads((Path(root) / 'Local State').read_text(encoding='utf-8'))
        info = state['profile']['info_cache'][directory]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return info.get('name') or info.get('gaia_name') or info.get('user_name') or None


def launch(profile, url):
    """Open `url` in the given (possibly not running) browser profile."""
    root, directory = profile.get('root'), profile.get('dir')
    if root and directory:
        for _, b_root, launcher in system.browser_roots():
            if str(b_root) != root:
                continue
            argv = launcher(directory, url)
            if argv and system.run(argv, detached=True):
                return True
    return system.open_url(url)
