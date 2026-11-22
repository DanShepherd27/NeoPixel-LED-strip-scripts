/* Admin tool: measure and tune song audio latency using the Pi's own microphone. */
(function () {
  "use strict";
  const $id = function (id) { return document.getElementById(id); };
  const CHART_MAX_MS = 1000;

  function setLatency(milliseconds) {
    if (milliseconds == null) return;
    $id("song-latency-ms").value = milliseconds;
    $id("song-latency-value").textContent = milliseconds + " ms";
  }

  function drawCurve(curve, appliedMs) {
    const canvas = $id("song-calibration-chart");
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height, pad = 6;
    ctx.clearRect(0, 0, w, h);
    const x = function (ms) { return pad + (w - 2 * pad) * ms / CHART_MAX_MS; };
    const y = function (score) { return h - pad - (h - 2 * pad) * Math.max(0, score); };
    ctx.strokeStyle = "#00e5ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    curve.forEach(function (point, index) {
      if (index === 0) ctx.moveTo(x(point[0]), y(point[1]));
      else ctx.lineTo(x(point[0]), y(point[1]));
    });
    ctx.stroke();
    if (appliedMs != null) {
      ctx.strokeStyle = "#ff2ea6";
      ctx.beginPath();
      ctx.moveTo(x(appliedMs), 0);
      ctx.lineTo(x(appliedMs), h);
      ctx.stroke();
    }
    canvas.hidden = false;
  }

  function describe(calibration) {
    if (calibration.status === "done") {
      return "Measured " + calibration.applied_ms + " ms (match " + Math.round(calibration.score * 100) +
        "%) and saved it. The pink line marks it on the match-quality curve.";
    }
    if (calibration.message) return calibration.message;
    return "No clear match (best " + Math.round((calibration.score || 0) * 100) +
      "%). Raise the speaker volume, move the microphone closer, or reduce room noise, then retry.";
  }

  function render(state) {
    const calibration = state.song_calibration || { status: "idle" };
    const button = $id("song-calibrate-btn");
    const status = $id("song-calibration-status");
    const running = calibration.status === "running";
    button.disabled = running || (state.state !== "idle");
    if (running && state.song) {
      const seconds = Math.round(state.song.calibration_progress * 18);
      status.textContent = "Playing the intro and listening on the microphone… " + seconds + " / 18 s";
    } else if (calibration.status === "done" || calibration.status === "error") {
      status.textContent = describe(calibration);
      if (calibration.curve) drawCurve(calibration.curve, calibration.applied_ms);
    }
    // Show latency learned on the Pi unless the admin is editing the field.
    if (state.song_latency_ms != null && document.activeElement !== $id("song-latency-ms") &&
        Number($id("song-latency-ms").value) !== state.song_latency_ms) {
      setLatency(state.song_latency_ms);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    $id("song-latency-ms").addEventListener("input", function () {
      $id("song-latency-value").textContent = this.value + " ms";
    });
    $id("song-calibrate-btn").addEventListener("click", function () {
      $id("song-calibration-status").textContent = "Starting…";
      fetch("/api/song/calibrate", { method: "POST" }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not start the measurement.");
        });
      }).catch(function (error) {
        $id("song-calibration-status").textContent = error.message;
      });
    });
    window.App.socket.on("state", render);
  });

  window.SongSync = { setLatency: setLatency };
})();
