import { mountOverlay } from '../overlay/overlay.js';

const root = document.getElementById('root');
const holder = document.getElementById('holder');
const startBtn = document.getElementById('start');
const status = document.getElementById('status');

mountOverlay(root);

if (!('documentPictureInPicture' in window)) {
  startBtn.disabled = true;
  fail('This Chrome build has no Document Picture-in-Picture API (needs Chrome 116+). Use popup-window mode instead.');
}

startBtn.addEventListener('click', async () => {
  const open = window.documentPictureInPicture?.window;
  if (open && !open.closed) {
    open.focus();
    return;
  }
  try {
    // Requires transient user activation — hence the button.
    const pip = await documentPictureInPicture.requestWindow({
      width: 300,
      height: 240,
      disallowReturnToOpener: true,
    });
    adopt(pip);
  } catch (err) {
    fail(`Could not open the floating window: ${err.message}`);
  }
});

/**
 * Move the live overlay DOM into the PiP document. Listeners were attached in
 * this page's realm and keep working after the move, so nothing is re-bound.
 */
function adopt(pip) {
  for (const sheet of document.querySelectorAll('[data-qj-shared]')) {
    pip.document.head.append(sheet.cloneNode(true));
  }
  pip.document.title = 'QuickJump';
  pip.document.body.className = 'qj-pip';
  pip.document.body.append(root);

  setFloating(true);
  pip.addEventListener('pagehide', () => {
    holder.append(root);
    setFloating(false);
  });
}

function setFloating(floating) {
  startBtn.textContent = floating ? 'Bar is floating' : 'Float the bar';
  startBtn.disabled = floating;
  status.classList.remove('is-error');
  status.textContent = floating
    ? 'Floating above other windows. Keep this tab open.'
    : '';
}

function fail(message) {
  status.classList.add('is-error');
  status.textContent = message;
}
