/* Full-song light show controls and optional playback on this device. */
(function () {
  "use strict";
  const $id = function (id) { return document.getElementById(id); };
  const DRIFT_LIMIT_SECONDS = 0.25;
  const POLL_LATENCY_SECONDS = 0.03;
  let audio = null;

  function deviceAudioWanted() { return $id("song-device-audio").checked; }

  function ensureAudio() {
    if (!audio) {
      audio = new Audio("/api/song/audio");
      audio.preload = "auto";
    }
    return audio;
  }

  function playDeviceAudio() {
    ensureAudio().play().catch(function () {
      $id("song-status").textContent = "Tap the checkbox again to allow audio on this device.";
    });
  }

  function stopDeviceAudio() {
    if (audio) audio.pause();
  }

  function syncDeviceAudio(song, receivedAt) {
    if (!deviceAudioWanted()) return stopDeviceAudio();
    const player = ensureAudio();
    const age = (performance.now() - receivedAt) / 1000 + POLL_LATENCY_SECONDS;
    const expected = Math.min(song.duration, song.position + age);
    if (Math.abs(player.currentTime - expected) > DRIFT_LIMIT_SECONDS) {
      player.currentTime = expected;
    }
    if (player.paused) playDeviceAudio();
  }

  function render(state) {
    const receivedAt = performance.now();
    const song = state.state === "song" ? state.song : null;
    const button = $id("song-btn");
    button.textContent = song ? "STOP THE SONG SHOW" : "PLAY THE SONG SHOW";
    button.disabled = !song && state.state !== "idle";
    $id("song-progress").hidden = !song;
    if (!song) {
      stopDeviceAudio();
      if (audio) audio.currentTime = 0;
      if (state.state === "idle" && !$id("song-status").dataset.error) {
        $id("song-status").textContent = "";
      }
      return;
    }
    $id("song-progress-bar").style.width = (100 * song.position / song.duration) + "%";
    $id("song-status").textContent = song.pi_audio_error || ("Now: " + song.section);
    syncDeviceAudio(song, receivedAt);
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.message || "Request failed.");
        return data;
      });
    });
  }

  function toggle() {
    const status = $id("song-status");
    delete status.dataset.error;
    if (window.App.state && window.App.state.state === "song") {
      post("/api/song/stop").catch(function () {});
      return;
    }
    // Start device audio inside the click so mobile browsers allow it.
    if (deviceAudioWanted()) ensureAudio().play().then(function () { audio.pause(); }).catch(function () {});
    post("/api/song/start", { pi_audio: $id("song-pi-audio").checked }).catch(function (error) {
      status.dataset.error = "1";
      status.textContent = error.message;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    $id("song-btn").addEventListener("click", toggle);
    $id("song-device-audio").addEventListener("change", function () {
      if (this.checked && window.App.state && window.App.state.state === "song") {
        playDeviceAudio();
      } else if (!this.checked) {
        stopDeviceAudio();
      }
    });
    window.App.socket.on("state", render);
  });
})();
