/**
 * Runs on Google Meet and Microsoft Teams pages. Watches the call toolbar's
 * microphone and camera buttons, reports their state to the service worker,
 * and clicks them when the QuickJump bar (or the agent) asks to.
 *
 * Nothing else on the page is read: only the two buttons' attributes.
 *
 * Reported state: { kind: 'meet' | 'teams', mic, cam } with mic/cam being
 *   true   — on (unmuted / camera on)
 *   false  — off (muted / camera off)
 *   null   — a button exists but its state could not be read
 *   absent — no such button on this page right now
 * and `null` as a whole when the page has no call controls at all.
 */

(() => {
  if (globalThis.__qjMeeting) return; // injected twice (reload) — keep one watcher
  globalThis.__qjMeeting = true;

  const host = location.hostname;
  const KIND = host === 'meet.google.com' ? 'meet' : 'teams';

  /* --------------------------------------------------------------- finders */

  /**
   * Google Meet: the two toolbar toggles carry `data-is-muted`. Which is
   * which is read from the Material icon ligature inside, which does not
   * change with the UI language (the aria-label does).
   */
  function findMeet() {
    const result = {};
    for (const button of document.querySelectorAll('button[data-is-muted], [role="button"][data-is-muted]')) {
      const icon = (button.querySelector('i')?.textContent || '').trim();
      const label = button.getAttribute('aria-label') || '';
      let what = null;
      if (/^mic(_off)?$/.test(icon) || /microphone/i.test(label)) what = 'mic';
      else if (/^videocam(_off)?$/.test(icon) || /camera/i.test(label)) what = 'cam';
      if (!what || result[what]) continue;
      result[what] = { el: button, on: button.getAttribute('data-is-muted') !== 'true' };
    }
    return result;
  }

  /**
   * Microsoft Teams (teams.microsoft.com, teams.live.com, teams.cloud.microsoft):
   * the toolbar buttons have stable ids, and a `data-state` attribute that
   * does not depend on the UI language:
   *   #microphone-button  data-state="mic" | "mic-off"
   *   #video-button       data-state="call-video" | "call-video-off"
   * The label text ("Mute mic" ↔ "Unmute mic", "Turn camera on" ↔ "Turn camera
   * off") is the fallback when that attribute is missing.
   */
  const TEAMS_MIC = '#microphone-button, [data-inp="microphone-button"], [data-tid="toggle-mute"]';
  const TEAMS_CAM = '#video-button, [data-inp="video-button"], [data-tid="toggle-video"]';

  // Fallback when the ids change: the toolbar buttons by what they are called.
  const TEAMS_MIC_LABEL = /\b(unmute|mute|microphone|mic)\b/i;
  const TEAMS_CAM_LABEL = /\b(camera|video)\b/i;
  const TEAMS_NOT_TOGGLE = /\b(settings|effects|background|share|device|more|options|preview)\b/i;

  function findTeams() {
    const result = {};
    const mic = document.querySelector(TEAMS_MIC) || teamsByLabel(TEAMS_MIC_LABEL);
    if (mic) result.mic = { el: mic, on: teamsMicOn(mic) };
    const cam = document.querySelector(TEAMS_CAM) || teamsByLabel(TEAMS_CAM_LABEL);
    if (cam && cam !== mic) result.cam = { el: cam, on: teamsCamOn(cam) };
    return result;
  }

  function teamsByLabel(pattern) {
    for (const el of document.querySelectorAll('button[aria-label], [role="button"][aria-label], button[title]')) {
      const text = `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''}`;
      if (pattern.test(text) && !TEAMS_NOT_TOGGLE.test(text)) return el;
    }
    return null;
  }

  function labelOf(el) {
    return `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''} ${el.textContent || ''}`;
  }

  function teamsMicOn(el) {
    const state = el.getAttribute('data-state');
    if (state === 'mic') return true;
    if (state === 'mic-off') return false;
    const text = labelOf(el);
    if (/\bunmute\b/i.test(text)) return false;
    if (/\bmute\b/i.test(text)) return true;
    return pressedState(el);
  }

  function teamsCamOn(el) {
    const state = el.getAttribute('data-state');
    if (state === 'call-video') return true;
    if (state === 'call-video-off') return false;
    const text = labelOf(el);
    if (/\b(turn|switch)\b[^.]*\boff\b/i.test(text) || /\bcamera off\b/i.test(text)) return true;
    if (/\b(turn|switch)\b[^.]*\bon\b/i.test(text) || /\bcamera on\b/i.test(text)) return false;
    return pressedState(el);
  }

  /** aria-pressed="true" on these buttons means "muted" / "camera off". */
  function pressedState(el) {
    const pressed = el.getAttribute('aria-pressed');
    if (pressed === 'true') return false;
    if (pressed === 'false') return true;
    return null;
  }

  const find = KIND === 'meet' ? findMeet : findTeams;

  /* -------------------------------------------------------------- reporting */

  let last = ''; // JSON of the last reported state
  let reportedSomething = false;
  let timer = 0;

  function snapshot() {
    const found = find();
    if (!found.mic && !found.cam) return null;
    const state = { kind: KIND };
    if (found.mic) state.mic = found.mic.on;
    if (found.cam) state.cam = found.cam.on;
    return state;
  }

  function report(force = false) {
    const state = snapshot();
    // A frame that never had controls stays quiet, so it cannot overwrite the
    // report of the frame that has them.
    if (state === null && !reportedSomething) return;
    const key = JSON.stringify(state);
    if (!force && key === last) return;
    last = key;
    reportedSomething = true;
    try {
      chrome.runtime.sendMessage({ type: 'meeting-state', state }).catch(() => {});
    } catch {
      /* extension reloaded underneath this script; nothing to do */
    }
  }

  function scheduleReport() {
    clearTimeout(timer);
    timer = setTimeout(() => report(), 150);
  }

  const observer = new MutationObserver(scheduleReport);
  function observe() {
    if (!document.body) return;
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['aria-label', 'data-is-muted', 'data-state', 'aria-pressed', 'title'],
    });
    report();
  }
  if (document.body) observe();
  else document.addEventListener('DOMContentLoaded', observe, { once: true });
  // Safety net for changes the observer cannot see (e.g. a replaced shadow tree).
  setInterval(() => report(), 3000);

  /* ---------------------------------------------------------------- control */

  // The service worker messages every frame of the tab and takes the first
  // answer, so a frame without the controls does not answer at all: the one
  // that has them does, and with no answer the tab is not in a call.
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type === 'meeting-query') {
      const state = snapshot();
      if (state) sendResponse({ state });
      return false;
    }
    if (msg?.type !== 'meeting-toggle') return false;
    const found = find();
    const target = found[msg.what];
    if (!target) return false;
    target.el.click();
    // The page updates the button's attributes a moment later; the observer
    // reports that. Make sure it does even if nothing visibly mutates.
    setTimeout(() => report(true), 400);
    sendResponse({ ok: true });
    return false;
  });
})();
