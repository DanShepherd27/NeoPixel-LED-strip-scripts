/* LED Arcade — game-specific HUD and results detail rendering. */

(function () {
  "use strict";

  function reactionPhaseLabel(phase) {
    switch (phase) {
      case "waiting": return "Wait for the flash…";
      case "signal": return "PRESS NOW!";
      case "round_over": return "Round over";
      default: return "";
    }
  }

  // Plain-language name of a player color (their LED end), from its hue.
  function colorName(rgb) {
    const max = Math.max.apply(null, rgb);
    const min = Math.min.apply(null, rgb);
    if (max === 0 || (max - min) / max < 0.2) return "white";
    const d = max - min;
    let hue;
    if (max === rgb[0]) hue = ((rgb[1] - rgb[2]) / d + 6) % 6;
    else if (max === rgb[1]) hue = (rgb[2] - rgb[0]) / d + 2;
    else hue = (rgb[0] - rgb[1]) / d + 4;
    hue *= 60;
    const names = [[15, "red"], [40, "orange"], [70, "yellow"], [165, "green"], [200, "cyan"],
      [255, "blue"], [290, "purple"], [345, "pink"], [361, "red"]];
    return names.find(function (entry) { return hue < entry[0]; })[1];
  }

  function swatch(rgb) {
    const dot = document.createElement("span");
    dot.className = "pong-role-swatch";
    dot.style.backgroundColor = "rgb(" + rgb.join(",") + ")";
    dot.setAttribute("aria-hidden", "true");
    return dot;
  }

  let lastPongSpeed = 0;

  function renderPongHud(hud, game) {
    hud.replaceChildren();
    const seats = game.seats || [];
    const level = document.createElement("div");
    level.className = "hud-line";
    level.textContent = "Level " + game.level + " of " + game.levels;
    hud.appendChild(level);

    const score = document.createElement("div");
    score.className = "pong-scoreboard";
    seats.forEach(function (seat, index) {
      if (index) score.appendChild(document.createTextNode(" — "));
      const cell = document.createElement("span");
      cell.className = "pong-score-cell";
      cell.append(swatch(seat.color), document.createTextNode(String(seat.points)));
      cell.title = seat.name + ": " + seat.points + " points, " + seat.wins + " levels won";
      score.appendChild(cell);
    });
    hud.appendChild(score);

    const wins = document.createElement("div");
    wins.className = "pong-subline";
    wins.textContent = "First to " + game.level_points + " clears a level · levels won " +
      seats.map(function (seat) { return seat.wins; }).join(" — ");
    hud.appendChild(wins);

    const meter = document.createElement("div");
    meter.className = "pong-speed";
    const bump = game.phase === "play" && game.speed > lastPongSpeed + 0.1;
    lastPongSpeed = game.speed;
    meter.classList.toggle("bump", bump);
    const label = document.createElement("span");
    label.textContent = "Ball speed";
    const bar = document.createElement("span");
    bar.className = "pong-speed-bar";
    const fill = document.createElement("span");
    fill.style.width = Math.max(6, Math.round((game.speed_ratio || 0) * 100)) + "%";
    bar.appendChild(fill);
    meter.append(label, bar);
    hud.appendChild(meter);
  }

  function renderHud(s) {
    const game = s.game || {};
    const hud = document.getElementById("game-hud");
    let html = "";

    switch (game.slug) {
      case "reaction":
        html = "<div class='hud-line'>Round " + game.round + " / " +
          game.rounds + "</div>" +
          "<div class='hud-line'>" + reactionPhaseLabel(game.phase) + "</div>";
        break;
      case "dodge":
        html = "<div class='hud-line'>Lives: " + game.lives + "</div>" +
          "<div class='hud-line'>" + game.score + "s</div>";
        break;
      case "shooter":
        html = "<div class='hud-line'>Health: " + game.health + "</div>" +
          "<div class='hud-line'>Enemies: " + game.enemies + "</div>";
        break;
      case "pong":
        renderPongHud(hud, game);
        return;
    }

    hud.innerHTML = html;
  }

  function renderResultsDetail(s, body) {
    const game = s.game || {};
    if (game.slug !== "reaction" || !game.results) return;

    const players = s.players || [];
    const detail = document.createElement("div");
    detail.className = "muted";
    detail.style.marginTop = "8px";

    let html = "";
    players.forEach(function (p) {
      const times = (game.results.reaction_times_ms || {})[p.id] || [];
      const total = (game.results.totals_ms || {})[p.id];
      const falseStarts = (game.results.false_starts || {})[p.id] || 0;
      html += "<div>" + p.name + ": " +
        times.map(function (t) { return Math.round(t) + "ms"; }).join(", ") +
        (falseStarts ? " · " + falseStarts + " false start" +
          (falseStarts === 1 ? "" : "s") : "") +
        (total != null ? " · total " + Math.round(total) + "ms" : "") +
        "</div>";
    });
    detail.innerHTML = html;
    body.appendChild(detail);
  }

  window.colorName = colorName;
  window.renderHud = renderHud;
  window.renderResultsDetail = renderResultsDetail;
})();
