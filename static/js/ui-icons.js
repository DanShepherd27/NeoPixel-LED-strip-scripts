/* Icon system: inline SVG icons (offline, no dependency) and automatic text -> icon
   conversion for buttons. A button whose text matches a known label (including text set
   later by other scripts) becomes an icon button; the old text moves to aria-label and
   the tooltip. Unknown labels are left alone. */
(function () {
  "use strict";
  const ICONS = {
    play: '<polygon points="6 4 20 12 6 20 6 4"/>',
    pause: '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
    stop: '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    rewind: '<polygon points="11 19 2 12 11 5 11 19"/><polygon points="22 19 13 12 22 5 22 19"/>',
    forward: '<polygon points="13 19 22 12 13 5 13 19"/><polygon points="2 19 11 12 2 5 2 19"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    gamepad: '<line x1="6" y1="12" x2="10" y2="12"/><line x1="8" y1="10" x2="8" y2="14"/><line x1="15" y1="13" x2="15.01" y2="13"/><line x1="18" y1="11" x2="18.01" y2="11"/><rect x="2" y="6" width="20" height="12" rx="2"/>',
    wave: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
    micoff: '<line x1="2" y1="2" x2="22" y2="22"/><path d="M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V5a3 3 0 0 0-5.9-.7"/><path d="M19 10v2a7 7 0 0 1-.9 3.4M5 10v2a7 7 0 0 0 11 5.7"/><line x1="12" y1="19" x2="12" y2="22"/>',
    login: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    replay: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
    trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    next: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    plus: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>',
    info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    speaker: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    phone: '<rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>',
    bulb: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',
    spinner: '<path d="M21 12a9 9 0 1 1-6.22-8.56"/>',
  };
  // Button text (lowercase, symbols stripped) -> icon, or [icon, short visible label] for the
  // few icons that are ambiguous on their own. Other scripts set these labels.
  const LABELS = {
    "join": ["login", "Join"], "enter arcade": ["gamepad", "Arcade"],
    "start sound reactive lighting": ["wave", "Sound"], "stop sound reactive lighting": ["stop", "Sound"],
    "play the song show": "play", "stop the song show": "stop",
    "pause": "pause", "resume": "play",
    "use this device's mic": ["mic", "My mic"], "allow mic and visualize": ["mic", "Allow"],
    "waiting for mic…": "spinner", "release microphone": ["micoff", "Release"], "leave mic queue": ["x", "Leave"],
    "ready": ["check", "Ready"], "not ready": ["x", "Not ready"], "leave": "logout", "start game": ["play", "Start"],
    "back to arcade": "home", "next": ["next", "Next"], "start": ["play", "Start"],
    "replay demo": ["replay", "Demo"], "rematch": ["replay", "Rematch"], "close": "x",
    "admin login": "lock", "save settings": "save", "admin logout": "logout",
    "analyze and add": ["upload", "Add"], "measure with speaker + mic": ["target", "Measure"],
    "remove": "trash", "rebuild show": ["refresh", "Rebuild"],
  };

  function sentence(text) {
    const lower = text.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }

  function svg(name) {
    return '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
      (ICONS[name] || "") + "</svg>";
  }

  let applying = false;

  function setIcon(button, name, label, badge, shortLabel) {
    applying = true;
    button.classList.toggle("has-label", Boolean(shortLabel));
    button.dataset.iconName = name;
    button.dataset.label = label;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.classList.add("icon-only");
    button.innerHTML = svg(name) + (badge ? '<span class="icon-badge" aria-hidden="true">' + badge + "</span>" : "") +
      (shortLabel ? '<span class="icon-label" aria-hidden="true">' + shortLabel + "</span>" : "");
    applying = false;
  }

  function normalize(text) {
    return text.replace(/[⏪⏩⏸▶◀▲▼✓]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function convert(button) {
    if (applying || button.closest(".control-btn") || button.classList.contains("keep-text")) return;
    const text = button.textContent.trim();
    if (!text) return;
    const staticName = button.dataset.icon;
    const entry = LABELS[normalize(text)];
    const name = staticName || (Array.isArray(entry) ? entry[0] : entry);
    if (!name) return;
    // A label written in the HTML (aria-label) is kept; otherwise the name follows the text,
    // so a button that changes from "Ready" to "Not ready" announces the new meaning.
    if (button.dataset.fixedLabel === undefined) {
      button.dataset.fixedLabel = button.dataset.label ? "" : (button.getAttribute("aria-label") || "");
    }
    const label = button.dataset.fixedLabel || sentence(normalize(text));
    setIcon(button, name, label, button.dataset.badge, Array.isArray(entry) && !staticName ? entry[1] : "");
  }

  function convertAll(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll("button"), convert);
  }

  function watch() {
    const observer = new MutationObserver(function (mutations) {
      if (applying) return;
      const seen = new Set();
      mutations.forEach(function (mutation) {
        let node = mutation.target.nodeType === 1 ? mutation.target : mutation.target.parentElement;
        const button = node && node.closest("button");
        if (button && !seen.has(button)) { seen.add(button); convert(button); }
        Array.prototype.forEach.call(mutation.addedNodes || [], function (added) {
          if (added.nodeType !== 1) return;
          if (added.tagName === "BUTTON") convert(added);
          else convertAll(added);
        });
      });
      observer.takeRecords();
    });
    observer.observe(document.body, { childList: true, characterData: true, subtree: true });
  }

  function init() {
    convertAll();
    watch();
  }

  window.UI = { icon: svg, setIcon: setIcon, convertAll: convertAll };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
