/* Sound source switch for the sound-reactive lighting (microphone, Bluetooth audio, ...).
   The sources come from the server, so a new input appears here without UI changes. */
(function () {
  "use strict";
  let pending = null;

  function $id(id) { return document.getElementById(id); }

  function selected(state) {
    return pending || (state.music_input || {}).selected || "microphone";
  }

  function render(state) {
    const sources = (state.music_input || {}).sources || [];
    const select = $id("music-input-select");
    $id("music-input-control").hidden = sources.length < 2;
    if (select.options.length !== sources.length) {
      select.innerHTML = "";
      sources.forEach(function (source) {
        const option = document.createElement("option");
        option.value = source.name;
        option.textContent = source.label;
        select.appendChild(option);
      });
    }
    select.value = selected(state);
  }

  function message(state, active) {
    const audio = state.audio || {};
    if (selected(state) === "bluetooth") {
      if (!active) return "Uses the music your phone streams to the Pi over Bluetooth.";
      return audio.status === "listening"
        ? "Listening to the Bluetooth stream from your phone."
        : (audio.error || "Waiting for a phone to stream Bluetooth audio. An admin can open pairing with the Bluetooth button.");
    }
    if (!active) return "Uses this browser microphone when available, with the Pi microphone as fallback.";
    if (audio.source === "web") return "Listening to this browser microphone; only analyzed sound levels are sent to the Pi.";
    return audio.status === "listening"
      ? "Using the Pi microphone fallback (" + (audio.device || "default") + ")."
      : (audio.error || "Waiting for a web microphone or Pi input.");
  }

  function usesBrowserMicrophone(state) { return selected(state) === "microphone"; }

  function bind(App, rerender) {
    $id("music-input-select").addEventListener("change", function () {
      const choice = this.value;
      pending = choice;
      fetch("/api/music/input", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: choice }),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not switch the sound source.");
          return body;
        });
      }).then(function (body) {
        if (App.state && App.state.music_input) App.state.music_input.selected = body.input;
      }).catch(function (error) {
        $id("music-message").textContent = error.message;
      }).then(function () {
        pending = null;
        rerender();
      });
    });
  }

  window.MusicInput = { render: render, message: message, usesBrowserMicrophone: usesBrowserMicrophone, bind: bind };
})();
