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
    var game = s.game || {};
    var hud = document.getElementById("game-hud");
    var html = "";

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
        var scores = game.scores || {};
        var vals = [];
        for (var k in scores) vals.push(scores[k]);
        html = "<div class='hud-line'>" + (vals[0] || 0) + " — " + (vals[1] || 0) + "</div>";
        break;
    }

    hud.innerHTML = html;
  }

  function renderResultsDetail(s, body) {
    var game = s.game || {};
    if (game.slug !== "reaction" || !game.results) return;

    var players = s.players || [];
    var detail = document.createElement("div");
    detail.className = "muted";
    detail.style.marginTop = "8px";

    var html = "";
    players.forEach(function (p) {
      var times = (game.results.reaction_times_ms || {})[p.id] || [];
      var total = (game.results.totals_ms || {})[p.id];
      var falseStarts = (game.results.false_starts || {})[p.id] || 0;
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
