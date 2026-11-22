/* LED Arcade — per-game controller (touch controls). */

(function () {
  "use strict";

  function sendInput(action) {
    if (window.App && window.App.socket) {
      window.App.socket.emit("input", { action: action });
    }
  }

  function makeButton(label, className, action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "control-btn " + (className || "");
    btn.textContent = label;
    btn.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      btn.classList.add("pressed");
      sendInput(action);
    });
    btn.addEventListener("pointerup", function () {
      btn.classList.remove("pressed");
      if (action === "left" || action === "right") sendInput("stop");
    });
    btn.addEventListener("pointerleave", function () {
      btn.classList.remove("pressed");
      if (action === "left" || action === "right") sendInput("stop");
    });
    return btn;
  }

  // Hold-to-repeat button for movement (repeats while the finger stays down).
  const activeHolds = new Set();

  function releaseAllHolds() {
    activeHolds.forEach(function (stop) { stop(); });
  }

  function makeHoldButton(label, className, action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "control-btn control-hold " + (className || "");
    btn.textContent = label;
    let timer = null;

    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
      activeHolds.delete(stop);
      btn.classList.remove("pressed");
    }

    btn.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      stop();
      // Capture keeps the hold alive if the finger drifts off the button.
      if (btn.setPointerCapture) btn.setPointerCapture(ev.pointerId);
      btn.classList.add("pressed");
      sendInput(action);
      timer = setInterval(function () { sendInput(action); }, 90);
      activeHolds.add(stop);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (evt) {
      btn.addEventListener(evt, stop);
    });
    btn.addEventListener("contextmenu", function (ev) { ev.preventDefault(); });
    return btn;
  }

  function renderReaction(el) {
    el.appendChild(makeButton("WAIT…", "hit", "press"));
  }

  function updateReaction(el, game) {
    el.firstChild.textContent = game.phase === "signal" ? "PRESS!" : "WAIT…";
  }

  function renderDodge(el) {
    const row = document.createElement("div");
    row.className = "control-row";
    row.appendChild(makeHoldButton("← LEFT", "", "left"));
    row.appendChild(makeHoldButton("RIGHT →", "", "right"));
    el.appendChild(row);

    const hint = document.createElement("div");
    hint.className = "control-hint";
    hint.textContent = "Hold to move your avatar";
    el.appendChild(hint);
  }

  function renderShooter(el) {
    el.appendChild(makeButton("FIRE", "fire", "fire"));

    const row = document.createElement("div");
    row.className = "control-row";
    row.appendChild(makeHoldButton("←", "", "left"));
    row.appendChild(makeHoldButton("→", "", "right"));
    el.appendChild(row);
  }

  function renderPong(el, game) {
    const playerId = window.App && window.App.playerId;
    const assignment = (game.players || []).find(function (player) {
      return player.id === playerId;
    });
    if (assignment) {
      const role = document.createElement("div");
      role.className = "pong-controller-role";
      const swatch = document.createElement("span");
      swatch.className = "pong-role-swatch";
      swatch.style.backgroundColor = "rgb(" + assignment.color.join(",") + ")";
      swatch.setAttribute("aria-hidden", "true");
      const label = document.createElement("strong");
      label.textContent = "You guard the " + assignment.side.toUpperCase() + " end";
      role.append(swatch, label);
      el.appendChild(role);
    }
    const hitButton = makeButton("HIT YOUR END", "hit pong-hit", "hit");
    if (assignment) hitButton.style.borderColor = "rgb(" + assignment.color.join(",") + ")";
    el.appendChild(hitButton);
  }

  // The controller is rebuilt only when the game (or this player's role)
  // changes. Rebuilding on every state poll would detach a button the player
  // is holding, so its pointerup would never arrive.
  let builtKey = null;

  function controllerKey(game) {
    const playerId = window.App && window.App.playerId;
    const mine = (game.players || []).find(function (player) { return player.id === playerId; });
    return [game.slug, mine ? mine.side : ""].join(":");
  }

  function renderController(s) {
    const game = s.game || {};
    const el = document.getElementById("controller");
    const key = controllerKey(game);

    if (key === builtKey && el.firstChild) {
      if (game.slug === "reaction") updateReaction(el, game);
      return;
    }
    releaseAllHolds();
    builtKey = key;
    el.innerHTML = "";

    switch (game.slug) {
      case "reaction": renderReaction(el); break;
      case "dodge": renderDodge(el); break;
      case "shooter": renderShooter(el); break;
      case "pong": renderPong(el, game); break;
      default: break;
    }
  }

  window.resetController = function () {
    releaseAllHolds();
    builtKey = null;
  };
  window.renderController = renderController;
})();
