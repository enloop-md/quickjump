/**
 * Shared access to the QuickJump list.
 *
 * A jump is: { id, tabId, windowId, url, title, favIconUrl, addedAt }
 * `tabId` is null once the tab it pointed at is gone — the jump survives and
 * reopens `url` on the next click.
 */

export const KEY_JUMPS = 'jumps';
export const KEY_SETTINGS = 'settings';

export const DEFAULT_SETTINGS = {
  newItemsOnTop: true,
  autoHide: true, // hide the bar while Chrome is focused, show it when it isn't
  agentPort: 8787, // must match the QuickJump agent's port
};

/* ------------------------------------------------------------------ agent */

/** This profile's id towards the agent, minted once (storage.local). */
export const KEY_PROFILE_ID = 'profileId';
/** The agent has been reachable at least once (storage.local). */
export const KEY_AGENT_SEEN = 'agentSeen';
/** This profile's name as the agent knows it (storage.local). */
export const KEY_PROFILE_NAME = 'profileName';
/** The service worker is connected to the agent right now (storage.session). */
export const KEY_AGENT_UP = 'agentConnected';

/** { connected, seen, profileName } */
export async function getAgentStatus() {
  const [local, session] = await Promise.all([
    chrome.storage.local.get([KEY_AGENT_SEEN, KEY_PROFILE_NAME]),
    chrome.storage.session.get(KEY_AGENT_UP),
  ]);
  return {
    connected: Boolean(session[KEY_AGENT_UP]),
    seen: Boolean(local[KEY_AGENT_SEEN]),
    profileName: local[KEY_PROFILE_NAME] || '',
  };
}

/** Calls `cb(status)` whenever the agent connection or its details change. */
export function onAgentStatusChanged(cb) {
  chrome.storage.onChanged.addListener((changes, area) => {
    const keys = area === 'session' ? [KEY_AGENT_UP] : [KEY_AGENT_SEEN, KEY_PROFILE_NAME];
    if (keys.some((k) => k in changes)) getAgentStatus().then(cb);
  });
}

export async function getSettings() {
  const stored = await chrome.storage.local.get(KEY_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...(stored[KEY_SETTINGS] || {}) };
}

export async function setSettings(patch) {
  const next = { ...(await getSettings()), ...patch };
  await chrome.storage.local.set({ [KEY_SETTINGS]: next });
  return next;
}

/** Calls `cb(settings)` whenever settings change in any extension context. */
export function onSettingsChanged(cb) {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes[KEY_SETTINGS]) {
      cb({ ...DEFAULT_SETTINGS, ...(changes[KEY_SETTINGS].newValue || {}) });
    }
  });
}

export async function getJumps() {
  const stored = await chrome.storage.local.get(KEY_JUMPS);
  const jumps = stored[KEY_JUMPS];
  return Array.isArray(jumps) ? jumps : [];
}

export async function setJumps(jumps) {
  await chrome.storage.local.set({ [KEY_JUMPS]: jumps });
}

/** Calls `cb(jumps)` whenever the list changes in any extension context. */
export function onJumpsChanged(cb) {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes[KEY_JUMPS]) cb(changes[KEY_JUMPS].newValue || []);
  });
}

/** Short, human-scannable label for a jump. */
export function labelFor(jump) {
  const title = (jump.title || '').trim();
  if (title) return title;
  try {
    return new URL(jump.url).hostname.replace(/^www\./, '');
  } catch {
    return jump.url || 'Untitled';
  }
}
