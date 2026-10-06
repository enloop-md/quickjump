import {
  getSettings,
  setSettings,
  onSettingsChanged,
  getAgentStatus,
  onAgentStatusChanged,
} from '../lib/store.js';
import { agentPitch } from '../overlay/overlay.js';

const topCheck = document.getElementById('newItemsOnTop');
const autoHideCheck = document.getElementById('autoHide');
const portInput = document.getElementById('agentPort');
const agentStatus = document.getElementById('agentStatus');
const agentAlert = document.getElementById('agentAlert');

function show(settings) {
  topCheck.checked = settings.newItemsOnTop;
  autoHideCheck.checked = settings.autoHide;
  if (document.activeElement !== portInput) portInput.value = settings.agentPort;
}

getSettings().then(show);
// Keeps this page honest if settings change from another context.
onSettingsChanged(show);

topCheck.addEventListener('change', () => setSettings({ newItemsOnTop: topCheck.checked }));
autoHideCheck.addEventListener('change', () => setSettings({ autoHide: autoHideCheck.checked }));


portInput.addEventListener('change', () => {
  const port = Number.parseInt(portInput.value, 10);
  if (port >= 1024 && port <= 65535) setSettings({ agentPort: port });
});

/* ------------------------------------------------------------------- agent */

function showAgent({ connected, seen, profileName }) {
  agentStatus.textContent = connected
    ? `Connected. This profile shows in the agent as “${profileName || '…'}”.`
    : seen
      ? 'The agent is not running — using this profile\'s own bar.'
      : 'The agent is not installed (or not running).';
  agentAlert.hidden = connected;
  agentAlert.classList.toggle('is-strong', seen);
  agentAlert.replaceChildren(
    seen
      ? 'Falling back to profile QuickJump. Run the agent for global hotkeys and other improvements.'
      : agentPitch(),
  );
}

getAgentStatus().then(showAgent);
onAgentStatusChanged(showAgent);

// A worker that does not know 'agent-ping' predates the agent: the extension
// files were updated but the extension was not reloaded.
chrome.runtime
  .sendMessage({ type: 'agent-ping' })
  .then((res) => res?.ok)
  .catch(() => false)
  .then((current) => {
    if (current) return;
    agentAlert.hidden = false;
    agentAlert.classList.add('is-strong');
    agentAlert.textContent =
      'QuickJump was updated but not reloaded: open chrome://extensions and click ⟳ on ' +
      'QuickJump, in every Chrome profile.';
    agentStatus.textContent = '';
  });
