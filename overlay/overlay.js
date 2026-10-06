import {
  getJumps,
  onJumpsChanged,
  labelFor,
  getAgentStatus,
  onAgentStatusChanged,
} from '../lib/store.js';

/** Where the agent can be downloaded. */
const AGENT_URL = 'https://github.com/enloop-md/quickjump/releases/latest';

/**
 * Renders the QuickJump list into `root` and keeps it in sync with storage.
 *
 * The same mount is used by three hosts: the standalone popup window, the
 * Picture-in-Picture window, and the toolbar popup. In PiP mode `root` is
 * physically moved into the PiP document, but this code keeps running in the
 * host page's realm — which is exactly why every listener is attached here and
 * nothing relies on `document` or `window` after mount.
 */
export function mountOverlay(root, { onRender, showClose = false } = {}) {
  root.classList.add('qj');
  root.replaceChildren();

  const head = el('header', 'qj-head');
  const brand = el('span', 'qj-brand');
  brand.textContent = 'QuickJump';
  const spacer = el('span', 'qj-spacer');
  const infoBtn = iconButton('i', 'Get the QuickJump agent');
  infoBtn.classList.add('qj-info-btn');
  infoBtn.hidden = true;
  const addBtn = iconButton('+', 'Add the current tab');
  const settingsBtn = iconButton('⚙', 'QuickJump settings');
  settingsBtn.addEventListener('click', () => send('open-settings'));
  head.append(brand, spacer, infoBtn, addBtn, settingsBtn);
  if (showClose) {
    const closeBtn = iconButton('×', 'Hide the bar');
    closeBtn.classList.add('qj-close');
    closeBtn.addEventListener('click', () => send('close-overlay'));
    head.append(closeBtn);
  }

  const list = el('ul', 'qj-list');
  const empty = el('div', 'qj-empty');
  empty.textContent = 'Right-click any page → “Add to Quick Jump”';

  // Agent notices: a quiet (i) until the agent has ever been seen, a loud
  // alert once it has been and is not running now.
  const info = el('div', 'qj-info');
  info.hidden = true;
  info.append(agentPitch());
  const alert = el('div', 'qj-alert');
  alert.hidden = true;
  alert.textContent =
    'Falling back to profile QuickJump. Run the agent for global hotkeys and other improvements.';
  const note = el('div', 'qj-note');
  note.hidden = true;
  note.textContent = 'Shown in the QuickJump agent window, together with your other profiles.';

  infoBtn.addEventListener('click', () => {
    info.hidden = !info.hidden;
    onRender?.();
  });

  root.append(head, info, alert, note, list, empty);

  addBtn.addEventListener('click', () => send('add-active-tab'));

  /* --------------------------------------------------------------- render */

  function render(jumps) {
    list.replaceChildren();
    empty.hidden = jumps.length > 0;

    for (const jump of jumps) {
      const item = el('li', 'qj-item');
      item.dataset.id = jump.id;
      item.draggable = true;
      const dead = jump.tabId == null;
      if (dead) item.classList.add('qj-dead');

      const icon = el('span', 'qj-fav');
      if (jump.favIconUrl) {
        const img = document.createElement('img');
        img.src = jump.favIconUrl;
        img.alt = '';
        img.addEventListener('error', () => icon.replaceChildren(fallbackGlyph(jump)));
        icon.append(img);
      } else {
        icon.append(fallbackGlyph(jump));
      }

      const label = labelFor(jump);
      const title = el('span', 'qj-title');
      title.textContent = label;

      const remove = iconButton('×', 'Remove from QuickJump');
      remove.classList.add('qj-remove');

      item.title = dead ? `${label}\n(tab was closed — click to reopen)` : `${label}\n${jump.url}`;
      item.append(icon, title, remove);

      item.addEventListener('click', (event) => {
        if (event.target.closest('.qj-remove')) {
          event.stopPropagation();
          send('remove', { id: jump.id });
          return;
        }
        send('jump', { id: jump.id });
      });
      // Middle-click removes, matching the tab-strip gesture.
      item.addEventListener('auxclick', (event) => {
        if (event.button === 1) {
          event.preventDefault();
          send('remove', { id: jump.id });
        }
      });

      list.append(item);
    }

    onRender?.();
  }

  /* ------------------------------------------------------- drag to reorder */

  let dragging = null;

  list.addEventListener('dragstart', (event) => {
    const item = event.target.closest('.qj-item');
    if (!item) return;
    dragging = item;
    item.classList.add('qj-dragging');
    event.dataTransfer.effectAllowed = 'move';
    // Firefox/Chrome both need *something* set for the drag to start.
    event.dataTransfer.setData('text/plain', item.dataset.id);
  });

  list.addEventListener('dragover', (event) => {
    if (!dragging) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const over = event.target.closest('.qj-item');
    if (!over || over === dragging) return;
    const rect = over.getBoundingClientRect();
    const after = event.clientY > rect.top + rect.height / 2;
    over.parentNode.insertBefore(dragging, after ? over.nextSibling : over);
  });

  list.addEventListener('drop', (event) => event.preventDefault());

  list.addEventListener('dragend', () => {
    if (!dragging) return;
    dragging.classList.remove('qj-dragging');
    dragging = null;
    const ids = [...list.querySelectorAll('.qj-item')].map((li) => li.dataset.id);
    send('reorder', { ids });
  });

  /* ------------------------------------------------------------- lifecycle */

  onJumpsChanged(render);
  getJumps().then(render);

  function showAgent({ connected, seen, profileName }) {
    brand.textContent = profileName ? `QuickJump · ${profileName}` : 'QuickJump';
    infoBtn.hidden = connected || seen;
    if (infoBtn.hidden) info.hidden = true;
    alert.hidden = connected || !seen;
    note.hidden = !connected;
    onRender?.();
  }
  onAgentStatusChanged(showAgent);
  getAgentStatus().then(showAgent);

  return { render };
}

/* -------------------------------------------------------------- utilities */

/** "Install the agent" text, shared with the settings page. */
export function agentPitch() {
  const frag = document.createDocumentFragment();
  const text = document.createElement('span');
  text.textContent =
    'Install the QuickJump agent app for global hotkeys, a tray icon and a single window ' +
    'for all your browser profiles. ';
  frag.append(text);
  if (AGENT_URL) {
    const link = document.createElement('a');
    link.href = AGENT_URL;
    link.target = '_blank';
    link.textContent = 'Get the agent';
    frag.append(link);
  } else {
    const soon = document.createElement('em');
    soon.textContent = '(Download link coming soon — see agent/ in the repository.)';
    frag.append(soon);
  }
  return frag;
}

function el(tag, className) {
  const node = document.createElement(tag);
  node.className = className;
  return node;
}

function iconButton(glyph, title) {
  const button = document.createElement('button');
  button.className = 'qj-btn';
  button.type = 'button';
  button.textContent = glyph;
  button.title = title;
  return button;
}

function fallbackGlyph(jump) {
  const span = el('span', 'qj-fav-letter');
  span.textContent = labelFor(jump).trim().charAt(0).toUpperCase() || '?';
  return span;
}

function send(type, payload = {}) {
  chrome.runtime.sendMessage({ type, ...payload }).catch(() => {
    /* Service worker restarting; the next storage change will resync the UI. */
  });
}
