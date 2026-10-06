import { mountOverlay } from '../overlay/overlay.js';
import { getAgentStatus, onAgentStatusChanged } from '../lib/store.js';

mountOverlay(document.getElementById('root'));

// With the agent running, its window is the floating bar.
function showAgent({ connected }) {
  document.getElementById('barBtn').textContent = connected ? 'Agent window' : 'Floating bar';
  document.getElementById('pipBtn').hidden = connected;
}
getAgentStatus().then(showAgent);
onAgentStatusChanged(showAgent);

for (const button of document.querySelectorAll('.pop-actions button')) {
  button.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: button.dataset.msg });
    window.close();
  });
}
