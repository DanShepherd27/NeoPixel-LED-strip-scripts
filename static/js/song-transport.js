/* Pause, resume and seek controls for the song show. */
(function () {
  "use strict";
  const $id = function (id) { return document.getElementById(id); };
  const SKIP_SECONDS = 10;
  const SETTLE_MS = 1200;  // ignore server positions briefly after our own seek
  let dragging = false;
  let settleUntil = 0;
  let sectionsShown = 0;
  let latestSong = null;

  function clock(seconds) {
    const whole = Math.max(0, Math.floor(seconds));
    return Math.floor(whole / 60) + ":" + String(whole % 60).padStart(2, "0");
  }

  function control(action, position) {
    const body = { action: action };
    if (position != null) body.position = position;
    return fetch("/api/song/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function seekTo(seconds) {
    if (!latestSong) return;
    const target = Math.max(0, Math.min(latestSong.duration - 1, seconds));
    settleUntil = performance.now() + SETTLE_MS;
    $id("song-seek").value = target;
    $id("song-time").textContent = clock(target);
    window.SongAudio.jump(target);
    control("seek", target);
  }

  function fillSections(sections) {
    if (sectionsShown === sections.length) return;
    const select = $id("song-section-select");
    select.length = 1;
    sections.forEach(function (section, index) {
      const option = document.createElement("option");
      option.value = section.start;
      option.textContent = clock(section.start) + "  " + section.name;
      select.appendChild(option);
    });
    sectionsShown = sections.length;
  }

  function render(state) {
    const song = state.state === "song" && state.song && !state.song.calibrating ? state.song : null;
    if (song && !latestSong) $id("song-card").open = true;   // show the controls when a song starts
    latestSong = song;
    $id("song-player").hidden = !song;
    if (!song) return;
    fillSections(song.sections || []);
    $id("song-pause").textContent = song.paused ? "▶ RESUME" : "⏸ PAUSE";
    $id("song-seek").max = Math.floor(song.duration);
    $id("song-total").textContent = clock(song.duration);
    if (!dragging && performance.now() > settleUntil) {
      $id("song-seek").value = song.position;
      $id("song-time").textContent = clock(song.position);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const seek = $id("song-seek");
    seek.addEventListener("pointerdown", function () { dragging = true; });
    seek.addEventListener("input", function () { $id("song-time").textContent = clock(Number(seek.value)); });
    seek.addEventListener("change", function () {
      dragging = false;
      seekTo(Number(seek.value));
    });
    $id("song-pause").addEventListener("click", function () {
      control(latestSong && latestSong.paused ? "resume" : "pause");
    });
    $id("song-back").addEventListener("click", function () {
      if (latestSong) seekTo(Number(seek.value) - SKIP_SECONDS);
    });
    $id("song-forward").addEventListener("click", function () {
      if (latestSong) seekTo(Number(seek.value) + SKIP_SECONDS);
    });
    $id("song-section-select").addEventListener("change", function () {
      if (this.value !== "") seekTo(Number(this.value));
      this.value = "";
    });
    window.App.socket.on("state", render);
  });
})();
