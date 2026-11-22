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

  // Hold-to-repeat button for movement (fires repeatedly while held).
  function makeHoldButton(label, className, action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "control-btn " + (className || "");
    btn.textContent = label;
    let timer = null;

    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
      btn.classList.remove("pressed");
    }

    btn.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      btn.classList.add("pressed");
      sendInput(action);
      timer = setInterval(function () { sendInput(action); }, 90);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach(function (evt) {
      btn.addEventListener(evt, stop);
    });
    return btn;
  }

  function renderReaction(el, game) {
    const label = game.phase === "signal" ? "PRESS!" : "WAIT…";
    const btn = makeButton(label, "hit", "press");
    btn.disabled = false;
    el.appendChild(btn);
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

  function renderController(s) {
    const game = s.game || {};
    const el = document.getElementById("controller");
    el.innerHTML = "";

    switch (game.slug) {
      case "reaction": renderReaction(el, game); break;
      case "dodge": renderDodge(el); break;
      case "shooter": renderShooter(el); break;
      case "pong": renderPong(el, game); break;
      default: break;
    }
  }

  window.renderController = renderController;
})();
