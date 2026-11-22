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
        const scores = game.scores || {};
        const vals = [];
        for (const k in scores) vals.push(scores[k]);
        const playerId = window.App && window.App.playerId;
        const assignment = (game.players || []).find(function (player) {
          return player.id === playerId;
        });
        hud.replaceChildren();
        if (assignment) {
          const role = document.createElement("div");
          role.className = "pong-player-role";
          const swatch = document.createElement("span");
          swatch.className = "pong-role-swatch";
          swatch.style.backgroundColor = "rgb(" + assignment.color.join(",") + ")";
          swatch.setAttribute("aria-hidden", "true");
          const label = document.createElement("strong");
          label.textContent = "Your end: " + assignment.side.toUpperCase();
          role.append(swatch, label);
          hud.appendChild(role);
        }
        const score = document.createElement("div");
        score.className = "hud-line";
        score.textContent = (vals[0] || 0) + " — " + (vals[1] || 0);
        hud.appendChild(score);
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

  window.renderHud = renderHud;
  window.renderResultsDetail = renderResultsDetail;
})();
