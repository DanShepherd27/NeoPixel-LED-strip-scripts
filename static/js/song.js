/* Full-song light show controls and optional playback on this device. */
(function () {
  "use strict";
  const $id = function (id) { return document.getElementById(id); };
  const DRIFT_LIMIT_SECONDS = 0.25;
  const POLL_LATENCY_SECONDS = 0.03;
  let audio = null;

  function selectedSongId() { return $id("song-select").value || null; }

  function loadSongs() {
    fetch("/api/songs").then(function (response) { return response.json(); }).then(function (songs) {
      const select = $id("song-select");
      select.innerHTML = "";
      songs.forEach(function (song) {
        const option = document.createElement("option");
        option.value = song.id;
        option.textContent = song.artist ? song.artist + " — " + song.title : song.title;
        select.appendChild(option);
      });
      select.hidden = songs.length < 2;
      $id("song-description").textContent = "🎄 " + (songs.length === 1 ? select.options[0].textContent : "");
    }).catch(function () {});
  }

  function deviceAudioWanted() { return $id("song-device-audio").checked; }

  let audioUrl = "";

  function ensureAudio(url) {
    const wanted = url || audioUrl;
    if (!wanted) return audio;
    if (!audio || audioUrl !== wanted) {  // a different song: load its audio
      if (audio) audio.pause();
      audioUrl = wanted;
      audio = new Audio(wanted);
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
    const player = ensureAudio(song.audio_url);
    if (song.paused) {  // hold still at the paused position, ready to resume
      player.pause();
      if (Math.abs(player.currentTime - song.position) > 0.05) player.currentTime = song.position;
      return;
    }
    const age = (performance.now() - receivedAt) / 1000 + POLL_LATENCY_SECONDS;
    const expected = Math.min(song.duration, song.position + age);
    if (Math.abs(player.currentTime - expected) > DRIFT_LIMIT_SECONDS) {
      player.currentTime = expected;
    }
    if (player.paused) playDeviceAudio();
  }

  function syncSummary(song) {
    if (!song.sync || !song.sync.enabled) return "";
    const labels = { locked: "in sync", adjusting: "tuning", weak: "listening", off: "starting" };
    return " · latency " + Math.round(song.latency_ms) + " ms (" +
      (labels[song.sync.state] || song.sync.state) + ")";
  }

  const readySongs = new Set();
  let importsSeen = false;

  // Tell every connected browser when a newly analyzed song becomes playable.
  function watchImports(state) {
    let announced = null;
    (state.song_imports || []).forEach(function (job) {
      if (job.status !== "ready" || readySongs.has(job.id)) return;
      readySongs.add(job.id);
      if (importsSeen) announced = job.title;
    });
    importsSeen = true;
    if (announced) {
      loadSongs();
      $id("song-status").textContent = "New song ready to play: " + announced;
    }
  }

  function render(state) {
    watchImports(state);
    const receivedAt = performance.now();
    const song = state.state === "song" ? state.song : null;
    const button = $id("song-btn");
    button.textContent = song ? "STOP THE SONG SHOW" : "PLAY THE SONG SHOW";
    button.disabled = !song && state.state !== "idle";
    if (!song) {
      stopDeviceAudio();
      if (audio) audio.currentTime = 0;
      if (state.state === "idle" && !$id("song-status").dataset.error) {
        $id("song-status").textContent = "";
      }
      return;
    }
    $id("song-status").textContent = song.pi_audio_error || (song.calibrating
      ? "Measuring speaker delay with the microphone…"
      : (song.paused ? "Paused · " : "Now: ") + song.section + syncSummary(song));
    syncDeviceAudio(song, receivedAt);
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(function (response) {
      return response.json().catch(function () {
        throw new Error("The Pi answered with an error (HTTP " + response.status + "); the app may need redeploying.");
      }).then(function (data) {
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
    if (deviceAudioWanted() && selectedSongId()) {
      ensureAudio("/api/songs/" + selectedSongId() + "/audio").play()
        .then(function () { audio.pause(); }).catch(function () {});
    }
    post("/api/song/start", { pi_audio: $id("song-pi-audio").checked, song_id: selectedSongId() }).catch(function (error) {
      status.dataset.error = "1";
      status.textContent = error.message;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadSongs();
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

  // Lets the transport controls move this device's audio immediately.
  window.SongAudio = {
    jump: function (seconds) {
      if (audio && deviceAudioWanted()) audio.currentTime = seconds;
    },
  };
})();
