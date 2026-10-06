"""
The merged jump list.

Ownership follows docs/design-multiprofile.md §3: each browser profile owns its
*shard* (which jumps exist, their tab, title and favicon) and reports it as a
full snapshot; the agent owns what only it can know — the merged order, which
profiles exist, and which jumps the user removed from the agent window.

A jump here is the extension's record plus `profileId`:
  { id, profileId, url, title, favIconUrl, addedAt, alive }
"""

import json
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .config import STATE_FILE, write_private

# A removed jump stays tombstoned this long, so a profile that was offline when
# it was removed drops it on reconnect instead of bringing it back.
TOMBSTONE_TTL = 60 * 60 * 24 * 30

JUMP_FIELDS = ('url', 'title', 'favIconUrl', 'addedAt', 'alive')


class Store(QObject):
    changed = pyqtSignal()

    def __init__(self, newest_on_top=True, parent=None):
        super().__init__(parent)
        self.newest_on_top = newest_on_top
        self.jumps = {}       # id -> jump
        self.order = []       # ids, as shown
        self.profiles = {}    # profileId -> {browser, root, dir, name, extId, lastSeen}
        self.tombstones = {}  # id -> removal time
        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(self.save)
        self._load()

    # ------------------------------------------------------------ persistence

    def _load(self):
        try:
            data = json.loads(STATE_FILE.read_text())
        except (OSError, ValueError):
            return
        self.jumps = {j['id']: j for j in data.get('jumps', []) if isinstance(j, dict) and j.get('id')}
        self.order = [i for i in data.get('order', []) if i in self.jumps]
        self.order += [i for i in self.jumps if i not in self.order]
        self.profiles = data.get('profiles', {})
        now = time.time()
        self.tombstones = {k: v for k, v in data.get('tombstones', {}).items() if now - v < TOMBSTONE_TTL}

    def save(self):
        data = {
            'jumps': [self.jumps[i] for i in self.order],
            'order': self.order,
            'profiles': self.profiles,
            'tombstones': self.tombstones,
        }
        write_private(STATE_FILE, json.dumps(data, indent=1))

    def _touch(self):
        self._save_timer.start()
        self.changed.emit()

    # ----------------------------------------------------------------- reads

    def ordered(self):
        return [self.jumps[i] for i in self.order]

    def newest(self):
        """Most recently added, wherever it sits in the list."""
        if not self.jumps:
            return None
        return max(self.jumps.values(), key=lambda j: j.get('addedAt', 0))

    # ---------------------------------------------------------------- writes

    def apply_snapshot(self, profile_id, incoming):
        """
        Replace one profile's shard. New jumps are merged into the list by
        their add time — this is also how the fallback lists of every profile
        get folded together the first time the agent sees them.

        Returns the ids the profile should drop (removed here while it was
        away).
        """
        drops = []
        seen = set()
        changed = False
        for raw in incoming:
            jid = raw.get('id')
            if not isinstance(jid, str) or not jid:
                continue
            if jid in self.tombstones:
                drops.append(jid)
                continue
            seen.add(jid)
            fresh = {k: raw.get(k) for k in JUMP_FIELDS}
            fresh['addedAt'] = fresh['addedAt'] or 0
            fresh['alive'] = bool(fresh['alive'])
            old = self.jumps.get(jid)
            if old is None:
                self.jumps[jid] = {'id': jid, 'profileId': profile_id, **fresh}
                self._insert_by_time(jid)
                changed = True
                continue
            re_added = fresh['addedAt'] > old.get('addedAt', 0)
            if any(old.get(k) != fresh[k] for k in JUMP_FIELDS) or old.get('profileId') != profile_id:
                old.update(fresh, profileId=profile_id)
                changed = True
            if re_added:
                # Adding an entry that is already listed puts it back on top.
                self.order.remove(jid)
                self._insert_by_time(jid)

        # Anything this profile no longer reports was removed in its fallback bar.
        for jid in [i for i in self.order if self.jumps[i].get('profileId') == profile_id and i not in seen]:
            self.order.remove(jid)
            del self.jumps[jid]
            changed = True

        if changed:
            self._touch()
        return drops

    def _insert_by_time(self, jid):
        t = self.jumps[jid].get('addedAt', 0)
        for index, other in enumerate(self.order):
            ot = self.jumps[other].get('addedAt', 0)
            if (t > ot) if self.newest_on_top else (t < ot):
                self.order.insert(index, jid)
                return
        self.order.append(jid)

    def remove(self, jid):
        jump = self.jumps.pop(jid, None)
        if jump is None:
            return None
        self.order.remove(jid)
        self.tombstones[jid] = time.time()
        self._touch()
        return jump

    def reorder(self, ids):
        known = [i for i in ids if i in self.jumps]
        rest = [i for i in self.order if i not in known]
        if known + rest != self.order:
            self.order = known + rest
            self._touch()

    def upsert_profile(self, profile_id, info):
        current = self.profiles.get(profile_id, {})
        merged = {**current, **{k: v for k, v in info.items() if v is not None}}
        if merged != current:
            self.profiles[profile_id] = merged
            self._touch()

    def forget_profile(self, profile_id):
        self.profiles.pop(profile_id, None)
        for jid in [i for i in self.order if self.jumps[i].get('profileId') == profile_id]:
            self.order.remove(jid)
            del self.jumps[jid]
        self._touch()

    def set_newest_on_top(self, value):
        self.newest_on_top = value
