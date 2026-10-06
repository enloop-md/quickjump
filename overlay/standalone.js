import { mountOverlay } from './overlay.js';

const MIN_HEIGHT = 40;
const MAX_HEIGHT = 900;

/** Set once the user resizes the bar by hand; auto-fit then stays out of the way. */
const KEY_USER_SIZED = 'overlayUserSized';

mountOverlay(document.getElementById('root'), {
  showClose: true,
  onRender: fitHeight,
});

/*
 * Auto-fit yields to the user: the first manual resize is remembered and turns
 * shrink-wrapping off, so the bar can be kept as small (or large) as wanted.
 * Double-clicking empty chrome (the header, or below the list) shrink-wraps
 * again and re-enables auto-fit.
 */
let userSized = false;
chrome.storage.local.get(KEY_USER_SIZED).then((st) => {
  userSized = Boolean(st[KEY_USER_SIZED]);
});

// Resize events also fire while the window is being created/placed by the WM
// and when fitHeight() itself resizes — ignore those windows of time.
let squelchUntil = performance.now() + 1500;

window.addEventListener('resize', () => {
  if (performance.now() < squelchUntil || userSized) return;
  userSized = true;
  chrome.storage.local.set({ [KEY_USER_SIZED]: true });
});

document.addEventListener('dblclick', (event) => {
  if (event.target.closest('.qj-item, .qj-btn')) return;
  userSized = false;
  chrome.storage.local.remove(KEY_USER_SIZED);
  fitHeight();
});

/**
 * Shrink-wrap the popup window around its content. Chrome's popup frame adds a
 * slim title strip, so measure it rather than guessing a constant.
 */
async function fitHeight() {
  if (userSized) return;
  // Let layout settle before measuring.
  await new Promise(requestAnimationFrame);
  if (userSized) return;
  const frame = window.outerHeight - window.innerHeight;
  const content = document.documentElement.scrollHeight;
  const height = Math.round(clamp(content + frame, MIN_HEIGHT, MAX_HEIGHT));
  if (Math.abs(height - window.outerHeight) < 4) return;
  squelchUntil = performance.now() + 600;
  try {
    const win = await chrome.windows.getCurrent();
    await chrome.windows.update(win.id, { height });
    squelchUntil = performance.now() + 600;
  } catch {
    /* Window is closing, or the compositor refused the resize. */
  }
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
