/**
 * Connection from this profile's service worker to the QuickJump agent — a
 * desktop app that shows one window for every browser profile, with global
 * hotkeys and a tray icon. See docs/design-multiprofile.md and agent/.
 *
 * The agent listens on ws://127.0.0.1:<agentPort>. This profile reports its
 * whole list (its *shard*) on connect and after every change; the agent asks
 * back to activate or drop entries. When the agent is not running, the
 * extension's own bar is the fallback.
 *
 * An open WebSocket that exchanges messages keeps an MV3 service worker alive
 * (Chrome 116+), so while connected the worker does not sleep. While not, an
 * alarm wakes it to retry.
 */

import {
  getJumps,
  getSettings,
  KEY_PROFILE_ID,
  KEY_AGENT_SEEN,
  KEY_PROFILE_NAME,
  KEY_AGENT_UP,
} from './store.js';

const PROTOCOL = 1;
const PING_MS = 20_000;
const MIN_BACKOFF = 1_000;
const MAX_BACKOFF = 30_000;

let ws = null;
let open = false;
let attempt = null; // Promise<boolean> of the connection in progress
let backoff = MIN_BACKOFF;
let retryTimer = 0;
let pingTimer = 0;
let hooks = {};

/**
 * hooks: { onActivate(id), onDrop(id), onConnected(), onDisconnected() }
 * onDisconnected fires only when an established connection is lost.
 */
export function initAgent(h) {
  hooks = h;
}

export function isAgentConnected() {
  return open;
}

/** Connects unless already connected or connecting. Resolves to "connected?". */
export function connectAgent() {
  if (open) return Promise.resolve(true);
  if (attempt) return attempt;
  clearTimeout(retryTimer);
  const current = (async () => {
    const { agentPort } = await getSettings();
    if (!(await agentListening(agentPort))) {
      scheduleRetry();
      return false;
    }
    let sock;
    try {
      sock = new WebSocket(`ws://127.0.0.1:${agentPort}`);
    } catch {
      return false;
    }
    ws = sock;
    return new Promise((resolve) => {
      sock.onopen = () => {
        open = true;
        backoff = MIN_BACKOFF;
        resolve(true);
        onOpen().catch(() => {});
      };
      sock.onmessage = (event) => onMessage(event.data);
      sock.onclose = () => {
        resolve(false);
        if (ws !== sock) return; // replaced by reconnectAgent()
        const was = open;
        ws = null;
        open = false;
        clearInterval(pingTimer);
        chrome.storage.session.set({ [KEY_AGENT_UP]: false });
        if (was) hooks.onDisconnected?.();
        scheduleRetry();
      };
    });
  })().finally(() => {
    if (attempt === current) attempt = null;
  });
  attempt = current;
  return current;
}

/** Drop the current connection (e.g. the port changed) and connect afresh. */
export function reconnectAgent() {
  if (ws) {
    const old = ws;
    ws = null;
    open = false;
    clearInterval(pingTimer);
    old.close();
    chrome.storage.session.set({ [KEY_AGENT_UP]: false });
  }
  attempt = null;
  backoff = MIN_BACKOFF;
  return connectAgent();
}

/**
 * Is anything listening? Chrome lists every failed WebSocket connection as an
 * error of the extension, which would fill chrome://extensions with
 * "ERR_CONNECTION_REFUSED" whenever the agent is not running. A fetch() that
 * fails and is caught is not logged, so ask over plain HTTP first.
 *
 * `no-cors` on purpose: the answer stays unreadable, but Chrome also logs no
 * CORS error, whoever answers (an older agent, or another program).
 */
async function agentListening(port) {
  try {
    await fetch(`http://127.0.0.1:${port}/quickjump`, {
      mode: 'no-cors',
      cache: 'no-store',
      signal: AbortSignal.timeout(2000),
    });
    return true;
  } catch {
    return false;
  }
}

function scheduleRetry() {
  clearTimeout(retryTimer);
  const delay = backoff * (0.8 + Math.random() * 0.4);
  backoff = Math.min(backoff * 2, MAX_BACKOFF);
  retryTimer = setTimeout(connectAgent, delay);
}

export function sendAgent(message) {
  if (!open) return false;
  ws.send(JSON.stringify(message));
  return true;
}

/**
 * The full list of this profile, always as a snapshot. `reveal` names an entry
 * the agent should show its window for (it was just added).
 */
export async function sendSnapshot(reveal) {
  if (!open) return false;
  const jumps = await getJumps();
  return sendAgent({
    t: 'jumps',
    jumps: jumps.map((j) => ({
      id: j.id,
      url: j.url,
      title: j.title,
      favIconUrl: j.favIconUrl,
      addedAt: j.addedAt,
      alive: j.tabId != null,
    })),
    ...(reveal ? { reveal } : {}),
  });
}

async function onOpen() {
  await chrome.storage.local.set({ [KEY_AGENT_SEEN]: true });
  await chrome.storage.session.set({ [KEY_AGENT_UP]: true });
  const windows = await chrome.windows.getAll().catch(() => []);
  sendAgent({
    t: 'hello',
    v: PROTOCOL,
    profileId: await getProfileId(),
    extId: chrome.runtime.id,
    extVersion: chrome.runtime.getManifest().version,
    brands: (navigator.userAgentData?.brands || []).map((b) => b.brand),
    focused: windows.some((w) => w.focused),
  });
  await sendSnapshot();
  clearInterval(pingTimer);
  pingTimer = setInterval(() => sendAgent({ t: 'ping' }), PING_MS);
  hooks.onConnected?.();
}

function onMessage(data) {
  let msg;
  try {
    msg = JSON.parse(data);
  } catch {
    return;
  }
  switch (msg?.t) {
    case 'welcome':
      chrome.storage.local.set({ [KEY_PROFILE_NAME]: msg.profileName || '' });
      break;
    case 'activate':
      hooks.onActivate?.(msg.id);
      break;
    case 'drop':
      hooks.onDrop?.(msg.id);
      break;
    default:
      break;
  }
}

export async function getProfileId() {
  const stored = await chrome.storage.local.get(KEY_PROFILE_ID);
  if (stored[KEY_PROFILE_ID]) return stored[KEY_PROFILE_ID];
  const id = crypto.randomUUID();
  await chrome.storage.local.set({ [KEY_PROFILE_ID]: id });
  return id;
}
