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
      const wasHeld = timer !== null;
      if (timer) { clearInterval(timer); timer = null; }
      activeHolds.delete(stop);
      btn.classList.remove("pressed");
      // Dodge keeps drifting until told to stop; other games ignore it.
      if (wasHeld) sendInput("stop");
    }

    btn.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      if (timer) { clearInterval(timer); timer = null; }
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
    const color = assignment ? "rgb(" + assignment.color.join(",") + ")" : null;
    if (assignment) {
      const role = document.createElement("div");
      role.className = "pong-controller-role";
      const swatch = document.createElement("span");
      swatch.className = "pong-role-swatch";
      swatch.style.backgroundColor = color;
      swatch.setAttribute("aria-hidden", "true");
      const label = document.createElement("strong");
      label.textContent = "You guard the " + window.colorName(assignment.color).toUpperCase() + " end";
      role.append(swatch, label);
      el.appendChild(role);
    }
    const hitButton = makeButton("HIT", "hit pong-hit", "hit");
    if (color) hitButton.style.borderColor = color;
    el.appendChild(hitButton);

    const panel = document.createElement("div");
    panel.className = "pong-break card";
    panel.hidden = true;
    el.appendChild(panel);
  }

  let breakLevel = null;

  // Between levels the strip waits: the phone says what happened and holds the start button.
  function updatePong(el, game) {
    const hit = el.querySelector(".pong-hit");
    const panel = el.querySelector(".pong-break");
    if (!hit || !panel) return;
    const onBreak = game.phase === "break";
    hit.hidden = onBreak;
    panel.hidden = !onBreak;
    if (!onBreak) { breakLevel = null; return; }

    const seats = game.seats || [];
    const playerId = window.App && window.App.playerId;
    const ready = game.break_ready || [];
    const humans = (window.App.state.players || []).filter(function (p) { return !p.queued && p.connected; });
    if (breakLevel !== game.level) {
      breakLevel = game.level;
      if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
      panel.replaceChildren();
      const title = document.createElement("h3");
      title.textContent = "Level " + game.level + " cleared!";
      const winner = document.createElement("p");
      winner.textContent = (game.level_winner_name || "Someone") + " won the level. Levels won: " +
        seats.map(function (seat) { return seat.name + " " + seat.wins; }).join(" · ") + ".";
      const faster = document.createElement("p");
      faster.className = "muted";
      const factor = (game.next_level_speed / game.level_speed).toFixed(1);
      faster.textContent = "Level " + game.next_level + " of " + game.levels + " starts " + factor +
        "× faster. Watch your end, then start when you are ready.";
      const button = makeButton("START LEVEL " + game.next_level, "start-level", "next_level");
      const status = document.createElement("p");
      status.className = "muted pong-break-status";
      panel.append(title, winner, faster, button, status);
    }
    const button = panel.querySelector(".start-level");
    const mineReady = ready.indexOf(playerId) >= 0;
    button.disabled = mineReady;
    button.classList.toggle("done", mineReady);
    panel.querySelector(".pong-break-status").textContent = mineReady
      ? "Ready. Waiting for the other player (" + ready.length + " of " + humans.length + ")…"
      : (humans.length > 1 ? ready.length + " of " + humans.length + " players ready." : "");
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
      if (game.slug === "pong") updatePong(el, game);
      return;
    }
    releaseAllHolds();
    builtKey = key;
    el.innerHTML = "";

    switch (game.slug) {
      case "reaction": renderReaction(el); break;
      case "dodge": renderDodge(el); break;
      case "shooter": renderShooter(el); break;
      case "pong": renderPong(el, game); updatePong(el, game); break;
      default: break;
    }
  }

  window.resetController = function () {
    releaseAllHolds();
    builtKey = null;
    breakLevel = null;
  };
  window.renderController = renderController;
})();
