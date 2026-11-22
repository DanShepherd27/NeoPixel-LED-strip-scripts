/* Admin: upload an MP3, watch its analysis, and remove songs added this way. */
(function () {
  "use strict";
  const $id = function (id) { return document.getElementById(id); };
  let lastReadyKey = "";

  function renderJobs(jobs) {
    const container = $id("song-import-jobs");
    container.innerHTML = "";
    jobs.filter(function (job) { return job.status !== "ready"; }).forEach(function (job) {
      const row = document.createElement("div");
      row.className = "song-import-job" + (job.status === "error" ? " error" : "");
      const label = document.createElement("div");
      label.textContent = job.title + " — " + (job.status === "error"
        ? "failed: " + job.message
        : job.stage + " " + Math.round(job.progress * 100) + "%");
      row.appendChild(label);
      if (job.status !== "error") {
        const track = document.createElement("div");
        track.className = "song-progress";
        const bar = document.createElement("span");
        bar.style.width = Math.round(job.progress * 100) + "%";
        track.appendChild(bar);
        row.appendChild(track);
      }
      container.appendChild(row);
    });
  }

  function renderLibrary(songs) {
    const container = $id("song-import-library");
    container.innerHTML = "";
    songs.filter(function (song) { return song.user; }).forEach(function (song) {
      const row = document.createElement("div");
      row.className = "song-library-row";
      const name = document.createElement("span");
      name.textContent = song.artist ? song.artist + " — " + song.title : song.title;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn";
      remove.textContent = "Remove";
      remove.addEventListener("click", function () {
        if (!window.confirm("Remove “" + song.title + "” from the Pi?")) return;
        fetch("/api/songs/" + encodeURIComponent(song.id), { method: "DELETE" }).then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok) throw new Error(body.message || "Could not remove the song.");
            refreshLibrary();
          });
        }).catch(function (error) { $id("song-import-message").textContent = error.message; });
      });
      const rebuild = document.createElement("button");
      rebuild.type = "button";
      rebuild.className = "btn";
      rebuild.textContent = "Rebuild show";
      rebuild.addEventListener("click", function () {
        if (!window.confirm("Rebuild the light show for “" + song.title + "” with the “" +
          $id("song-import-look").selectedOptions[0].textContent.split(":")[0] + "” look? Hand edits to its show file are replaced.")) return;
        fetch("/api/songs/" + encodeURIComponent(song.id) + "/regenerate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ look: $id("song-import-look").value }),
        }).then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok) throw new Error(body.message || "Could not rebuild the show.");
            $id("song-import-message").textContent = "Rebuilt the show for " + song.title + ".";
          });
        }).catch(function (error) { $id("song-import-message").textContent = error.message; });
      });
      row.appendChild(name);
      row.appendChild(rebuild);
      row.appendChild(remove);
      container.appendChild(row);
    });
  }

  function refreshLibrary() {
    fetch("/api/songs").then(function (response) { return response.json(); }).then(renderLibrary)
      .catch(function () {});
  }

  function onState(state) {
    const jobs = state.song_imports || [];
    renderJobs(jobs);
    const readyKey = jobs.filter(function (job) { return job.status === "ready"; })
      .map(function (job) { return job.id; }).join(",");
    if (readyKey !== lastReadyKey) {
      lastReadyKey = readyKey;
      refreshLibrary();
    }
  }

  function upload() {
    const file = $id("song-import-file").files[0];
    const message = $id("song-import-message");
    if (!file) { message.textContent = "Choose an MP3 file first."; return; }
    const form = new FormData();
    form.append("file", file);
    form.append("title", $id("song-import-title").value);
    form.append("artist", $id("song-import-artist").value);
    form.append("look", $id("song-import-look").value);
    message.textContent = "Uploading " + file.name + "…";
    $id("song-import-btn").disabled = true;
    fetch("/api/songs/import", { method: "POST", body: form }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.message || "Upload failed.");
        message.textContent = "Uploaded. Analysis started; this page shows the progress.";
        $id("song-import-file").value = "";
        $id("song-import-title").value = "";
        $id("song-import-artist").value = "";
      });
    }).catch(function (error) {
      message.textContent = error.message;
    }).then(function () { $id("song-import-btn").disabled = false; });
  }

  document.addEventListener("DOMContentLoaded", function () {
    $id("song-import-btn").addEventListener("click", upload);
    window.App.socket.on("state", onState);
    refreshLibrary();
  });
})();
