/* Compact UI helpers: long explanatory paragraphs become an (i) button next to the label
   they explain (tap to read, hidden by default), and accordion headers get icons. */
(function () {
  "use strict";
  const HINT_SELECTOR = [
    ".admin-section-body p.muted:not([role]):not([id])",
    "#song-card p.muted:not([role]):not([id])",
    ".music-live-effect-controls p.muted",
    "#web-mic-controls p.muted:not([role]):not([id])",
  ].join(",");
  const ANCHORS = "label, h2, h3, h4, legend, .knob-cell";

  function findAnchor(paragraph) {
    let node = paragraph.previousElementSibling;
    while (node) {
      if (node.matches(ANCHORS)) return node;
      if (node.querySelector && node.querySelector(ANCHORS) && node.matches(".range-input-row, #christmas-glitter-control, div")) {
        const inner = node.querySelectorAll(ANCHORS);
        return inner[inner.length - 1];
      }
      node = node.previousElementSibling;
    }
    return null;
  }

  function addHint(paragraph) {
    const anchor = findAnchor(paragraph);
    if (!anchor || paragraph.dataset.hinted) return;
    paragraph.dataset.hinted = "1";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "hint-btn keep-text";
    button.setAttribute("aria-label", "More information");
    button.setAttribute("aria-expanded", "false");
    button.title = paragraph.textContent.trim();
    button.innerHTML = window.UI ? window.UI.icon("info") : "i";
    paragraph.hidden = true;
    paragraph.classList.add("hint-text");
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      paragraph.hidden = !paragraph.hidden;
      button.setAttribute("aria-expanded", String(!paragraph.hidden));
    });
    if (anchor.classList.contains("knob-cell")) anchor.appendChild(button);
    else anchor.appendChild(button);
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll(HINT_SELECTOR), addHint);
    Array.prototype.forEach.call(document.querySelectorAll("summary[data-icon]"), function (summary) {
      if (window.UI && !summary.querySelector(".icon")) {
        summary.insertAdjacentHTML("afterbegin", window.UI.icon(summary.dataset.icon));
      }
    });
  }

  // Runs after ui-icons.js has defined window.UI (both are deferred to DOMContentLoaded's end).
  window.addEventListener("load", init);
})();
