/* Browser microphone queue, capture, and local feature extraction. */
(function () {
  "use strict";
  const MIC_CLIENT_KEY = "led_arcade_mic_client";
  let micClientId = localStorage.getItem(MIC_CLIENT_KEY);
  if (!micClientId) {
    micClientId = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2));
    localStorage.setItem(MIC_CLIENT_KEY, micClientId);
  }
  let App = null;
  function $id(id) { return document.getElementById(id); }
  let micToken = null;
  let micStream = null;
  let micContext = null;
  let micAnalyser = null;
  let micFrame = 0;
  let micLastSend = 0;
  let micNoiseFloor = 0.008;
  let micLastClap = 0;
  let micRttMs = 40;
  let micRole = "idle";
  let micRequesting = false;
  let micStatusRequestId = 0;
  let micNotice = "";
  function updateMicStatus(state) {
    if (!state || state.state !== "music") {
      micStatusRequestId += 1;
      if (micStream || micContext) stopMicCapture();
      micRequesting = false;
      micToken = null;
      micRole = "idle";
      return;
    }
    const requestId = ++micStatusRequestId;
    fetch("/api/music/mic/state?client_id=" + encodeURIComponent(micClientId), { cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(function (status) {
        // A slow poll must not overwrite a more recent lease response.
        if (requestId !== micStatusRequestId || !App.state || App.state.state !== "music") return;
        const oldRole = micRole;
        micRole = status.role || "idle";
        micToken = status.token || null;
        if (oldRole === "owner" && micRole !== "owner" && !micNotice) {
          micNotice = "Your microphone turn ended. Your browser track has been released.";
        }
        const statusText = $id("web-mic-status");
        const queueButton = $id("mic-queue-btn");
        const startButton = $id("mic-start-btn");
        const secure = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
        if (!secure) {
          statusText.textContent = micNotice || "Browser microphone needs HTTPS on this LAN address. Use a trusted HTTPS URL, then allow microphone access.";
          queueButton.disabled = true;
          startButton.hidden = true;
        } else if (micRole === "owner") {
          statusText.textContent = micRequesting
            ? "Requesting microphone permission. Respond to the browser prompt to continue."
            : micNotice || (micStream
            ? "Your microphone is active. The browser track closes automatically when your turn ends. " +
              (status.handoff_in != null ? "Turn ends in about " + status.handoff_in + " seconds. " : "") +
              (status.queued ? status.queued + " user(s) queued." : "")
            : "It is your turn. Start the microphone when you are ready.");
          queueButton.textContent = "RELEASE MICROPHONE";
          queueButton.hidden = false;
          queueButton.disabled = false;
          startButton.hidden = !!micStream;
          startButton.disabled = micRequesting;
          startButton.textContent = micRequesting ? "WAITING FOR MIC…" : "ALLOW MIC AND VISUALIZE";
        } else if (micRole === "queued") {
          statusText.textContent = "You are number " + status.position + " in the microphone queue. " +
            (status.owner ? status.owner + " is using it." : "Waiting for the current turn.");
          queueButton.textContent = "LEAVE MIC QUEUE";
          queueButton.hidden = false;
          queueButton.disabled = false;
          startButton.hidden = true;
        } else {
          statusText.textContent = micNotice || "Join the queue to use this device's microphone.";
          queueButton.textContent = "USE THIS DEVICE'S MIC";
          queueButton.hidden = false;
          queueButton.disabled = false;
          startButton.hidden = true;
        }
        if (micRole !== "owner" && (micStream || micContext)) stopMicCapture();
      }).catch(function () {});
  }

  function stopMicCapture() {
    if (micFrame) cancelAnimationFrame(micFrame);
    micFrame = 0;
    if (micStream) micStream.getTracks().forEach(function (track) { track.stop(); });
    micStream = null;
    if (micContext) micContext.close().catch(function () {});
    micContext = null;
    micAnalyser = null;
  }

  function releaseMic() {
    stopMicCapture();
    const token = micToken;
    const shouldLeave = micRole !== "idle" || !!token;
    micToken = null;
    if (shouldLeave) {
      fetch("/api/music/mic/leave", {
        method: "POST", keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: micClientId, token: token }),
      }).catch(function () {});
    }
    micRole = "idle";
  }

  // Kick (30-150 Hz) and snare (1.5-7 kHz) onset strength: the positive change of the
  // log-compressed spectrum, scaled 0-1 against a slowly decaying recent maximum.
  // ``take`` returns the strongest value since the last call and how long ago it was.
  function createOnsetTracker(analyser, sampleRate) {
    const spectrum = new Float32Array(analyser.frequencyBinCount);
    const previous = new Float32Array(analyser.frequencyBinCount);
    const binHz = sampleRate / analyser.fftSize;
    const ranges = {
      kick: [Math.max(1, Math.floor(30 / binHz)), Math.ceil(150 / binHz)],
      snare: [Math.floor(1500 / binHz), Math.min(spectrum.length - 1, Math.ceil(7000 / binHz))],
    };
    const ceiling = { kick: 0.15, snare: 0.15 };  // about a soft real hit
    const held = { kick: 0, snare: 0, kickAt: 0, snareAt: 0 };
    let primed = false;
    let lastTime = 0;

    function flux(range) {
      let total = 0;
      for (let bin = range[0]; bin <= range[1]; bin++) {
        const rise = spectrum[bin] - previous[bin];
        if (rise > 0) total += rise;
      }
      return total / (range[1] - range[0] + 1);
    }

    function measure(now) {
      analyser.getFloatFrequencyData(spectrum);
      for (let bin = 0; bin < spectrum.length; bin++) {
        const magnitude = Math.pow(10, Math.max(-120, spectrum[bin]) / 20);
        spectrum[bin] = Math.log1p(100 * magnitude);
      }
      if (primed) {
        const decay = Math.exp(-Math.max(0, now - lastTime) / 1000 * 0.25);
        ["kick", "snare"].forEach(function (name) {
          const value = flux(ranges[name]);
          ceiling[name] = Math.max(0.15, ceiling[name] * decay, value);
          const strength = Math.min(1, value / ceiling[name]);
          if (strength > held[name]) {
            held[name] = strength;
            held[name + "At"] = now;
          }
        });
      }
      previous.set(spectrum);
      primed = true;
      lastTime = now;
    }

    function take(now) {
      const result = {
        kick: held.kick, kickAgo: held.kick ? now - held.kickAt : 0,
        snare: held.snare, snareAgo: held.snare ? now - held.snareAt : 0,
      };
      held.kick = held.snare = 0;
      return result;
    }

    return { measure: measure, take: take };
  }

  function startMicCapture() {
    const statusText = $id("web-mic-status");
    const startButton = $id("mic-start-btn");
    if (micRequesting || micStream) return;
    if (micRole !== "owner" || !micToken) {
      micNotice = "Your microphone turn is not ready yet. Wait for the owner status, then tap again.";
      statusText.textContent = micNotice;
      updateMicStatus(App.state);
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      micNotice = "This page cannot request a microphone on HTTP. Open the arcade through trusted HTTPS.";
      statusText.textContent = micNotice;
      return;
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      statusText.textContent = "This browser does not support live audio analysis.";
      return;
    }
    // Invoke getUserMedia directly in the click handler to preserve browser
    // user activation. Do not await a queue/status request before this call.
    micRequesting = true;
    startButton.disabled = true;
    startButton.textContent = "WAITING FOR MIC…";
    statusText.textContent = "Requesting microphone permission from your browser…";
    micNotice = "";
    let mediaRequest;
    try {
      micContext = new AudioContextClass();
      micContext.resume().catch(function () {});
      mediaRequest = navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (error) {
      micRequesting = false;
      stopMicCapture();
      startButton.disabled = false;
      startButton.textContent = "ALLOW MIC AND VISUALIZE";
      statusText.textContent = "Browser could not start microphone access: " + (error.message || error.name || "unknown error");
      return;
    }
    mediaRequest.then(function (stream) {
      micRequesting = false;
      if (micRole !== "owner") {
        stream.getTracks().forEach(function (track) { track.stop(); });
        statusText.textContent = "Your microphone turn ended before access was granted. Join the queue again for another turn.";
        return;
      }
      micStream = stream;
      micNotice = "";
      statusText.textContent = "Microphone allowed. Visualizing live sound; raw audio stays on this device.";
      stream.getTracks().forEach(function (track) {
        track.addEventListener("ended", releaseMic, { once: true });
      });
      const source = micContext.createMediaStreamSource(stream);
      micAnalyser = micContext.createAnalyser();
      micAnalyser.fftSize = 2048;
      micAnalyser.minDecibels = -90;
      micAnalyser.maxDecibels = -20;
      micAnalyser.smoothingTimeConstant = 0.35;
      source.connect(micAnalyser);
      // A second, unsmoothed analyser measures how much the spectrum jumps between
      // frames (spectral flux), the same kick/snare measure the song analyzer uses.
      const fluxAnalyser = micContext.createAnalyser();
      fluxAnalyser.fftSize = 1024;
      fluxAnalyser.smoothingTimeConstant = 0;
      source.connect(fluxAnalyser);
      const onsets = createOnsetTracker(fluxAnalyser, micContext.sampleRate);
      const samples = new Float32Array(micAnalyser.fftSize);
      const frequencyData = new Uint8Array(micAnalyser.frequencyBinCount);
      const frequencyBands = [
        [40, 150], [150, 300], [300, 600],
        [600, 1500], [1500, 4000], [4000, 10000],
      ];
      const bandGains = [1.55, 1.4, 1.15, 1.05, 1.1, 1.25];
      let pendingClap = false;
      let pendingPeak = 0;
      function sample(now) {
        if (!micAnalyser || !micToken || micRole !== "owner") return;
        micAnalyser.getFloatTimeDomainData(samples);
        micAnalyser.getByteFrequencyData(frequencyData);
        let squares = 0;
        let peak = 0;
        for (let i = 0; i < samples.length; i++) {
          const value = Math.abs(samples[i]);
          squares += value * value;
          if (value > peak) peak = value;
        }
        const rms = Math.sqrt(squares / samples.length);
        if (rms < micNoiseFloor) micNoiseFloor += (rms - micNoiseFloor) * 0.08;
        else if (rms < micNoiseFloor * 2) micNoiseFloor += (rms - micNoiseFloor) * 0.004;
        const level = Math.max(0, Math.min(1, (rms - micNoiseFloor) / Math.max(0.025, micNoiseFloor * 5)));
        const binHz = micContext.sampleRate / micAnalyser.fftSize;
        const bands = frequencyBands.map(function (range, bandIndex) {
          const firstBin = Math.max(1, Math.floor(range[0] / binHz));
          const lastBin = Math.min(frequencyData.length - 1, Math.ceil(range[1] / binHz));
          const values = [];
          for (let bin = firstBin; bin <= lastBin; bin++) {
            values.push(frequencyData[bin] / 255);
          }
          if (!values.length) return 0;
          values.sort(function (a, b) { return b - a; });
          const selectedCount = Math.max(1, Math.ceil(values.length * 0.35));
          let power = 0;
          for (let vi = 0; vi < selectedCount; vi++) power += values[vi] * values[vi];
          let bandLevel = Math.sqrt(power / selectedCount);
          bandLevel = Math.max(0, Math.min(1, (bandLevel - 0.18) / 0.42));
          return Math.max(0, Math.min(1, Math.pow(bandLevel, 0.8) * bandGains[bandIndex]));
        });
        const clap = rms > Math.max(0.018, micNoiseFloor * 1.35) && peak > 0.12 &&
          peak / Math.max(0.001, rms) > 3 && now - micLastClap > 160;
        if (clap) micLastClap = now;
        onsets.measure(now);
        // Hold transients until the next send: snapshots taken only every 50 ms
        // would otherwise drop most claps and snare cracks.
        pendingClap = pendingClap || clap;
        pendingPeak = Math.max(pendingPeak, peak);
        if (now - micLastSend > 50) {
          micLastSend = now;
          const hits = onsets.take(now);
          const sentClap = pendingClap;
          const sentPeak = pendingPeak;
          pendingClap = false;
          pendingPeak = 0;
          const requestStarted = performance.now();
          const captureLatency = (micAnalyser.fftSize / micContext.sampleRate) * 500;
          fetch("/api/music/mic/audio", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              token: micToken, level: level, peak: sentPeak, clap: sentClap, bands: bands,
              kick: hits.kick, kick_ago_ms: hits.kickAgo,
              snare: hits.snare, snare_ago_ms: hits.snareAgo,
              latency_ms: captureLatency + micRttMs / 2,
            }),
          }).then(function (response) {
            if (response.status === 409) releaseMic();
            else if (response.ok) {
              const observedRtt = performance.now() - requestStarted;
              micRttMs = micRttMs * 0.8 + observedRtt * 0.2;
            }
          }).catch(function () {});
        }
        micFrame = requestAnimationFrame(sample);
      }
      micFrame = requestAnimationFrame(sample);
    }).catch(function (error) {
      micRequesting = false;
      const detail = error && error.name === "NotAllowedError"
        ? (window.isSecureContext
          ? "The browser blocked microphone access. Allow Microphone for this site in its address-bar/site settings, then join the microphone queue again."
          : "The browser requires HTTPS for microphone access; a private LAN IP over HTTP is not treated as secure.")
        : "Could not open this microphone: " + (error.message || error.name || "unknown error");
      micNotice = detail + " Using the Pi microphone fallback if available.";
      statusText.textContent = micNotice;
      startButton.disabled = false;
      startButton.textContent = "ALLOW MIC AND VISUALIZE";
      releaseMic();
    });
  }

  function bindControls(app) {
    App = app;
    $id("mic-queue-btn").addEventListener("click", function () {
      if (micRole === "queued" || micRole === "owner") {
        releaseMic();
        return;
      }
      fetch("/api/music/mic/request", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: micClientId, name: App.playerName || "Guest" }),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not join microphone queue.");
          return body;
        });
      }).then(function (status) {
        micNotice = "";
        micRole = status.role;
        micToken = status.token;
        updateMicStatus(App.state);
      }).catch(function (error) { $id("web-mic-status").textContent = error.message; });
    });
    $id("mic-start-btn").addEventListener("click", startMicCapture);
  }

  window.WebMic = {
    bindControls: bindControls,
    updateStatus: updateMicStatus,
    release: releaseMic,
  };
})();
