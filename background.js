import {
  getJumps,
  setJumps,
  getSettings,
  onJumpsChanged,
  onSettingsChanged,
  KEY_AGENT_UP,
} from './lib/store.js';
import {
  initAgent,
  connectAgent,
  reconnectAgent,
  isAgentConnected,
  sendAgent,
  sendSnapshot,
  getProfileId,
} from './lib/agent.js';

const OVERLAY_WIN = 'overlayWindowId';
const OVERLAY_GEOM = 'overlayGeom';
const LAST_WIN = 'lastNormalWindowId';

const OVERLAY_URL = chrome.runtime.getURL('overlay/overlay.html');
const HUB_URL = chrome.runtime.getURL('hub/hub.html');
const SELF_PREFIX = chrome.runtime.getURL('');

// Wayland ignores requested window positions, so `left`/`top` mostly matter on
// X11 and Windows. On KDE the supplied KWin rule remembers the position instead.
const DEFAULT_GEOM = { left: 60, top: 60, width: 280, height: 200 };

const MENU_ADD = 'qj-add';
const MENU_ADD_LINK = 'qj-add-link';
const MENU_SHOW = 'qj-show';
const AGENT_ALARM = 'qj-agent';

/* ------------------------------------------------------------------ menus */

function buildMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_ADD,
      title: 'Add to Quick Jump',
      contexts: ['page', 'selection', 'image', 'video', 'audio', 'editable'],
    });
    chrome.contextMenus.create({
      id: MENU_ADD_LINK,
      title: 'Add link to Quick Jump',
      contexts: ['link'],
    });
    chrome.contextMenus.create({ id: 'qj-sep', type: 'separator', contexts: ['all'] });
    chrome.contextMenus.create({
      id: MENU_SHOW,
      title: 'Show Quick Jump bar',
      contexts: ['all'],
    });
  });
}

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  buildMenus();
  if (reason !== 'install') return;
  await getProfileId();
  // First run: without the agent, say what it would add.
  if (!(await connectAgent())) chrome.runtime.openOptionsPage();
});
chrome.runtime.onStartup.addListener(buildMenus);

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === MENU_ADD && tab) {
    await showAdded(await addTab(tab));
  } else if (info.menuItemId === MENU_ADD_LINK && info.linkUrl) {
    await showAdded(await addLink(info.linkUrl, info.selectionText));
  } else if (info.menuItemId === MENU_SHOW) {
    await showBar();
  }
});

/* ------------------------------------------------------------ adding jumps */

/** Returns the id of the added (or re-added) jump. */
async function addTab(tab) {
  if (!tab.url || tab.url.startsWith(SELF_PREFIX)) return null;
  const jumps = await getJumps();
  const existing = jumps.find((j) => j.tabId === tab.id);
  if (existing) {
    // Already tracked — adding it again makes it the newest entry rather
    // than a duplicate.
    jumps.splice(jumps.indexOf(existing), 1);
    await insertJump(jumps, {
      ...existing,
      url: tab.url,
      title: tab.title || existing.title,
      favIconUrl: tab.favIconUrl || existing.favIconUrl,
      addedAt: Date.now(),
    });
    return existing.id;
  }
  const id = crypto.randomUUID();
  await insertJump(jumps, {
    id,
    tabId: tab.id,
    windowId: tab.windowId,
    url: tab.url,
    title: tab.title || tab.url,
    favIconUrl: tab.favIconUrl || '',
    addedAt: Date.now(),
  });
  return id;
}

async function insertJump(jumps, jump) {
  const { newItemsOnTop } = await getSettings();
  if (newItemsOnTop) jumps.unshift(jump);
  else jumps.push(jump);
  await setJumps(jumps);
}

/** A link that is not open yet: clicking it later opens a fresh tab. */
async function addLink(url, selectionText) {
  const jumps = await getJumps();
  const known = jumps.find((j) => j.url === url);
  if (known) return known.id;
  let title = (selectionText || '').trim();
  if (!title) {
    try {
      title = new URL(url).hostname.replace(/^www\./, '');
    } catch {
      title = url;
    }
  }
  const id = crypto.randomUUID();
  await insertJump(jumps, {
    id,
    tabId: null,
    windowId: null,
    url,
    title,
    favIconUrl: '',
    addedAt: Date.now(),
  });
  return id;
}

async function addActiveTab() {
  const lastWin = await getLastNormalWindow();
  let tabs = [];
  if (lastWin != null) {
    try {
      tabs = await chrome.tabs.query({ active: true, windowId: lastWin });
    } catch { /* window closed since */ }
  }
  if (!tabs.length) tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const tab = tabs.find((t) => t.url && !t.url.startsWith(SELF_PREFIX));
  return tab ? addTab(tab) : null;
}

/** After an add: the agent's window if it is running, otherwise this profile's bar. */
async function showAdded(id) {
  if (id && isAgentConnected()) {
    await sendSnapshot(id);
    return;
  }
  await openOverlay({ focus: false });
}

async function showBar() {
  if (!sendAgent({ t: 'show' })) await openOverlay({ focus: true });
}

async function toggleBar() {
  if (!sendAgent({ t: 'toggle' })) await toggleOverlay();
}

async function removeJump(id) {
  await setJumps((await getJumps()).filter((j) => j.id !== id));
}

/** Reorders to match `ids`; anything not listed keeps its relative place at the end. */
async function reorder(ids) {
  const jumps = await getJumps();
  const byId = new Map(jumps.map((j) => [j.id, j]));
  const next = [];
  for (const id of ids) {
    if (byId.has(id)) {
      next.push(byId.get(id));
      byId.delete(id);
    }
  }
  await setJumps([...next, ...byId.values()]);
}

/* ------------------------------------------------------------------ jumping */

/** Activates the jump's tab (reopening it if needed); returns that tab. */
async function jump(id) {
  const jumps = await getJumps();
  const j = jumps.find((x) => x.id === id);
  if (!j) return null;

  let tab = null;
  if (j.tabId != null) {
    try {
      tab = await chrome.tabs.get(j.tabId);
    } catch { /* tab is gone */ }
  }
  if (!tab && j.url) tab = await findTabByUrl(j.url);

  if (tab) {
    await chrome.tabs.update(tab.id, { active: true });
  } else {
    const opts = { url: j.url, active: true };
    const lastWin = await getLastNormalWindow();
    if (lastWin != null) opts.windowId = lastWin;
    try {
      tab = await chrome.tabs.create(opts);
    } catch {
      tab = await chrome.tabs.create({ url: j.url, active: true });
    }
  }

  // Raising the browser window is what actually gets the user back on the call.
  try {
    const win = await chrome.windows.get(tab.windowId);
    if (win.state === 'minimized') {
      await chrome.windows.update(win.id, { state: 'normal' });
    }
    await chrome.windows.update(win.id, { focused: true });
  } catch { /* window vanished mid-jump */ }

  j.tabId = tab.id;
  j.windowId = tab.windowId;
  if (tab.title) j.title = tab.title;
  if (tab.favIconUrl) j.favIconUrl = tab.favIconUrl;
  await setJumps(jumps);
  return tab;
}

/**
 * On Wayland the browser may switch the tab but is not allowed to raise its
 * own window, let alone switch virtual desktops. The agent can ask the window
 * manager to; it finds the window by its caption, which is the active tab's
 * title — so report that once the browser has had a moment to update it.
 */
async function reportActivated(id, tab) {
  if (!tab) return;
  await new Promise((resolve) => setTimeout(resolve, 150));
  const fresh = await chrome.tabs.get(tab.id).catch(() => tab);
  sendAgent({ t: 'activated', id, title: fresh.title || '', url: fresh.url || '' });
}

async function findTabByUrl(url) {
  const tabs = await chrome.tabs.query({});
  const exact = tabs.find((t) => t.url === url);
  if (exact) return exact;
  // Fall back to same origin + path, ignoring query/hash drift.
  try {
    const want = new URL(url);
    return (
      tabs.find((t) => {
        if (!t.url) return false;
        try {
          const got = new URL(t.url);
          return got.origin === want.origin && got.pathname === want.pathname;
        } catch {
          return false;
        }
      }) || null
    );
  } catch {
    return null;
  }
}

/* -------------------------------------------------------- overlay window */

async function openOverlay({ focus = true } = {}) {
  const st = await chrome.storage.local.get([OVERLAY_WIN, OVERLAY_GEOM]);
  const existing = st[OVERLAY_WIN];
  if (existing != null) {
    try {
      await chrome.windows.get(existing);
      if (focus) await chrome.windows.update(existing, { focused: true });
      return existing;
    } catch { /* stale id, fall through and recreate */ }
  }

  const geom = { ...DEFAULT_GEOM, ...(st[OVERLAY_GEOM] || {}) };
  const win = await chrome.windows.create({
    url: OVERLAY_URL,
    type: 'popup',
    focused: focus,
    left: Math.round(geom.left),
    top: Math.round(geom.top),
    width: Math.round(geom.width),
    height: Math.round(geom.height),
  });
  await chrome.storage.local.set({ [OVERLAY_WIN]: win.id });
  return win.id;
}

async function closeOverlay({ manual = true } = {}) {
  // A manual close of a focused bar hands focus to another app, which looks
  // exactly like "left Chrome" to auto-show — don't reopen what was just
  // deliberately closed.
  if (manual) suppressAutoShowUntil = Date.now() + 1000;
  const st = await chrome.storage.local.get(OVERLAY_WIN);
  if (st[OVERLAY_WIN] == null) return;
  try {
    await chrome.windows.remove(st[OVERLAY_WIN]);
  } catch { /* already closed */ }
  await chrome.storage.local.remove(OVERLAY_WIN);
}

async function toggleOverlay() {
  const st = await chrome.storage.local.get(OVERLAY_WIN);
  if (st[OVERLAY_WIN] != null) {
    try {
      await chrome.windows.get(st[OVERLAY_WIN]);
      await closeOverlay();
      return;
    } catch { /* stale */ }
  }
  await openOverlay({ focus: true });
}

chrome.windows.onRemoved.addListener(async (windowId) => {
  const st = await chrome.storage.local.get(OVERLAY_WIN);
  if (st[OVERLAY_WIN] === windowId) await chrome.storage.local.remove(OVERLAY_WIN);
});

if (chrome.windows.onBoundsChanged) {
  chrome.windows.onBoundsChanged.addListener(async (win) => {
    const st = await chrome.storage.local.get(OVERLAY_WIN);
    if (st[OVERLAY_WIN] !== win.id) return;
    await chrome.storage.local.set({
      [OVERLAY_GEOM]: { left: win.left, top: win.top, width: win.width, height: win.height },
    });
  });
}

/* ------------------------------------------------------------- PiP host tab */

async function openHub() {
  const tabs = await chrome.tabs.query({ url: HUB_URL });
  if (tabs.length) {
    await chrome.tabs.update(tabs[0].id, { active: true });
    await chrome.windows.update(tabs[0].windowId, { focused: true });
    return;
  }
  await chrome.tabs.create({ url: HUB_URL, pinned: true, active: true });
}

/* ------------------------------------------------------- keeping data fresh */

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!('title' in changeInfo) && !('url' in changeInfo) && !('favIconUrl' in changeInfo)) return;
  const jumps = await getJumps();
  let dirty = false;
  for (const j of jumps) {
    if (j.tabId !== tabId) continue;
    if (tab.url) j.url = tab.url;
    if (tab.title) j.title = tab.title;
    if (tab.favIconUrl) j.favIconUrl = tab.favIconUrl;
    dirty = true;
  }
  if (dirty) await setJumps(jumps);
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const jumps = await getJumps();
  let dirty = false;
  for (const j of jumps) {
    if (j.tabId === tabId) {
      j.tabId = null;
      j.windowId = null;
      dirty = true;
    }
  }
  if (dirty) await setJumps(jumps);
});

chrome.tabs.onAttached.addListener(async (tabId, info) => {
  const jumps = await getJumps();
  let dirty = false;
  for (const j of jumps) {
    if (j.tabId === tabId) {
      j.windowId = info.newWindowId;
      dirty = true;
    }
  }
  if (dirty) await setJumps(jumps);
});

// Remember the last real browser window so "add current tab" and reopened
// links land somewhere sensible even when the overlay had focus.
chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) {
    try {
      const win = await chrome.windows.get(windowId);
      if (win.type === 'normal') await chrome.storage.session.set({ [LAST_WIN]: windowId });
    } catch { /* ignore */ }
  }
  // The agent's window does not auto-hide; only the fallback bar does.
  if (!isAgentConnected()) await autoHideOnFocusChange(windowId);
});

/* ---------------------------------------------------------------- auto-hide */

/**
 * With the autoHide setting on, the bar behaves like a HUD for the rest of
 * the desktop: it hides while any Chrome window is focused (the tabs are
 * right there) and reappears once focus moves to another application.
 * Switching between two Chrome windows briefly reports WINDOW_ID_NONE, so
 * showing waits a beat and re-checks that focus really left Chrome.
 */
let autoShowTimer = null;
let suppressAutoShowUntil = 0;

async function autoHideOnFocusChange(windowId) {
  const { autoHide } = await getSettings();
  if (!autoHide) return;

  clearTimeout(autoShowTimer);

  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    autoShowTimer = setTimeout(async () => {
      if (Date.now() < suppressAutoShowUntil) return;
      const wins = await chrome.windows.getAll().catch(() => []);
      if (wins.some((w) => w.focused)) return; // it was just a window switch
      await openOverlay({ focus: false });
    }, 300);
    return;
  }

  // The bar taking focus itself (clicks) must not hide it.
  const st = await chrome.storage.local.get(OVERLAY_WIN);
  if (st[OVERLAY_WIN] === windowId) return;
  await closeOverlay({ manual: false });
}

async function getLastNormalWindow() {
  const st = await chrome.storage.session.get(LAST_WIN);
  const id = st[LAST_WIN];
  if (id == null) return null;
  try {
    const win = await chrome.windows.get(id);
    return win.type === 'normal' ? id : null;
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------------- messages */

const handlers = {
  jump: (msg) => jump(msg.id),
  remove: (msg) => removeJump(msg.id),
  reorder: (msg) => reorder(msg.ids),
  clear: () => setJumps([]),
  'add-active-tab': async () => showAdded(await addActiveTab()),
  'open-overlay': () => showBar(),
  'close-overlay': () => closeOverlay(),
  'toggle-overlay': () => toggleBar(),
  'open-hub': () => openHub(),
  'open-settings': () => chrome.runtime.openOptionsPage(),
  // Pages ask this to tell a current worker from one left over from before
  // the agent existed (an unpacked extension's pages update without a reload,
  // its worker does not).
  'agent-ping': () => connectAgent(),
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const handler = handlers[msg?.type];
  if (!handler) return false;
  Promise.resolve(handler(msg))
    .then(() => sendResponse({ ok: true }))
    .catch((err) => sendResponse({ ok: false, error: String(err) }));
  return true;
});

/* ------------------------------------------------------------------- agent */

initAgent({
  onActivate: async (id) => reportActivated(id, await jump(id)),
  onDrop: (id) => removeJump(id),
  // The agent's window replaces this profile's bar while it runs…
  onConnected: () => closeOverlay({ manual: false }),
  // …and the bar comes back, with its "run the agent" alert, when it stops.
  onDisconnected: () => openOverlay({ focus: false }),
});

// Every change to this profile's list goes to the agent as a fresh snapshot.
onJumpsChanged(() => sendSnapshot());

let agentPort = null;
getSettings().then((s) => {
  agentPort = s.agentPort;
});
onSettingsChanged((s) => {
  if (agentPort !== null && s.agentPort !== agentPort) reconnectAgent();
  agentPort = s.agentPort;
});

// A sleeping service worker has no timers; the alarm wakes it to retry.
// (Guarded: without the permission the rest of the worker must still run.)
chrome.alarms?.get(AGENT_ALARM).then((alarm) => {
  if (!alarm) chrome.alarms.create(AGENT_ALARM, { periodInMinutes: 0.5 });
});
chrome.alarms?.onAlarm.addListener((alarm) => {
  if (alarm.name === AGENT_ALARM) connectAgent();
});

// Every worker start: a flag left over from a worker that died while connected
// is stale.
chrome.storage.session.set({ [KEY_AGENT_UP]: false }).then(() => connectAgent());
