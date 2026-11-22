/* LED Arcade — main client logic: socket, screens, lobby, results. */

(function () {
  "use strict";

  var STORAGE_ID = "led_arcade_player_id";
  var STORAGE_NAME = "led_arcade_player_name";
  var MIC_CLIENT_KEY = "led_arcade_mic_client";
  var micClientId = localStorage.getItem(MIC_CLIENT_KEY);
  if (!micClientId) {
    micClientId = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2));
    localStorage.setItem(MIC_CLIENT_KEY, micClientId);
  }
  var micToken = null;
  var micStream = null;
  var micContext = null;
  var micAnalyser = null;
  var micFrame = 0;
  var micLastSend = 0;
  var micNoiseFloor = 0.008;
  var micLastClap = 0;
  var micRole = "idle";
  var micRequesting = false;
  var micStatusRequestId = 0;
  var micNotice = "";
  var musicVisualizerPending = null;
  var musicVisualizerRequestId = 0;

  var App = {
    socket: null,
    playerId: localStorage.getItem(STORAGE_ID) || null,
    playerName: localStorage.getItem(STORAGE_NAME) || null,
    state: null,
    screen: null,
  };

  function $id(id) { return document.getElementById(id); }

  function showScreen(name) {
    var screens = document.querySelectorAll(".screen");
    for (var i = 0; i < screens.length; i++) screens[i].classList.remove("active");
    var el = $id("screen-" + name);
    if (el) el.classList.add("active");
  }

  function setConn(on) {
    var dot = $id("connection");
    dot.classList.toggle("on", !!on);
    dot.classList.toggle("off", !on);
  }

  function setPlayerName(name) {
    App.playerName = name;
    localStorage.setItem(STORAGE_NAME, name);
  }

  function setPlayerId(id) {
    App.playerId = id;
    if (id) {
      App.screen = null;
      localStorage.setItem(STORAGE_ID, id);
    }
    else localStorage.removeItem(STORAGE_ID);
  }

  // ---- socket -------------------------------------------------------------
  function createPollingSocket() {
    var handlers = {};
    var socket = {
      connected: false,
      on: function (event, callback) {
        (handlers[event] = handlers[event] || []).push(callback);
      },
      emit: function (event, data) {
        var routes = {
          join: "/api/join", rejoin: "/api/rejoin", leave: "/api/leave",
          ready: "/api/ready", select_game: "/api/select_game",
          start_game: "/api/start_game", rematch: "/api/rematch",
          skip_tutorial: "/api/skip_tutorial",
          return_to_idle: "/api/return_to_idle", input: "/api/input",
          ping: "/api/ping",
          music_mode: "/api/music_mode",
        };
        var route = routes[event];
        if (!route) return;
        var payload = Object.assign({}, data || {});
        if (["leave", "ping", "ready", "input"].indexOf(event) >= 0) {
          payload.player_id = App.playerId;
        }
        fetch(route, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok) throw new Error(body.message || "Request failed.");
            return body;
          });
        }).then(function (body) {
          if (event === "join" || event === "rejoin") dispatch("joined", body);
        }).catch(function (error) {
          if (event === "rejoin") {
            setPlayerId(null);
            return;
          }
          dispatch("error", { message: error.message });
        });
      },
    };

    function dispatch(event, data) {
      (handlers[event] || []).forEach(function (callback) { callback(data); });
    }

    function poll() {
      fetch("/api/state", { cache: "no-store" }).then(function (response) {
        if (!response.ok) throw new Error("Arcade server did not respond.");
        return response.json();
      }).then(function (state) {
        if (!socket.connected) {
          socket.connected = true;
          setConn(true);
          dispatch("connect");
        }
        dispatch("state", state);
      }).catch(function () {
        if (socket.connected) {
          socket.connected = false;
          setConn(false);
          dispatch("disconnect");
        }
      });
    }
    poll();
    setInterval(poll, 500);
    return socket;
  }

  function connect() {
    App.socket = createPollingSocket();

    App.socket.on("connect", function () {
      setConn(true);
      if (App.playerId && App.playerName) {
        App.socket.emit("rejoin", { player_id: App.playerId });
      }
    });

    App.socket.on("joined", function (data) {
      setPlayerId(data.player_id);
      setPlayerName(data.player.name);
      $id("home-name").textContent = ", " + App.playerName;
    });

    App.socket.on("error", function (data) {
      var err = $id("join-error");
      err.textContent = data && data.message ? data.message : "Something went wrong.";
      err.hidden = false;
      var musicError = $id("music-message");
      if (musicError) musicError.textContent = err.textContent;
    });

    App.socket.on("state", onState);
    App.socket.on("disconnect", function () { setConn(false); });

    // Heartbeat so the server knows we're still here.
    setInterval(function () {
      if (App.socket && App.socket.connected) App.socket.emit("ping");
    }, 5000);
  }

  function onState(state) {
    App.state = state;

    // If our player id is no longer registered (e.g. returned to idle), reset.
    if (App.playerId && state.players && !state.players.some(function (p) {
      return p.id === App.playerId;
    })) {
      setPlayerId(null);
    }

    render();
    updateMicStatus(state);
  }

  // ---- rendering ----------------------------------------------------------
  function render() {
    var s = App.state;
    if (!s) return;

    $id("idle-animation").textContent = s.idle_animation || "—";
    $id("player-count").textContent = (s.players || []).length;
    $id("lan-url").textContent = window.location.host;
    var musicButton = $id("music-mode-btn");
    var musicMessage = $id("music-message");
    if (musicButton) {
      var musicActive = s.state === "music";
      musicButton.textContent = musicActive ? "STOP MUSIC MODE" : "START FREE MUSIC MODE";
      var audio = s.audio || {};
      musicMessage.textContent = musicActive
        ? (audio.source === "web"
          ? "Listening to the opted-in web microphone; only volume features are sent to the Pi."
          : (audio.status === "listening"
            ? "Using the Pi microphone fallback (" + (audio.device || "default") + ")."
            : (audio.error || "Waiting for a web microphone or Pi input.")))
        : "Web microphone is the default; the Pi's ALSA input is used only as fallback.";
      var visualizer = s.music_visualizer || {};
      var animationNames = {
        center_pulse: "Center pulse", mirror_bars: "Mirror bars",
        rainbow_wave: "Rainbow wave", comet: "Comet",
        retro_vu: "Retro VU meter", inward_diamonds: "Inward diamonds",
        red_shades: "Red shades",
      };
      var visualizerStatus = $id("music-visualizer-status");
      if (visualizerStatus) {
        visualizerStatus.textContent = musicActive
          ? "Animation: " + (animationNames[visualizer.animation] || "Center pulse") + " · Sensitivity: " +
            Number(visualizer.sensitivity || 1).toFixed(2) + "×"
          : "";
      }
      var selection = musicVisualizerPending || visualizer;
      var animationSelect = $id("music-animation-select");
      if (animationSelect) animationSelect.value = selection.animation || "center_pulse";
      $id("music-live-primary").value = selection.primary_color || "#00e5ff";
      $id("music-live-accent").value = selection.accent_color || "#ff2ea6";
      $id("web-mic-controls").hidden = !musicActive;
    }
    var orientation = s.led_orientation || "vertical";
    var orientationLabel = $id("strip-orientation");
    if (orientationLabel) orientationLabel.textContent = orientation;

    if (!App.playerId) {
      // Keep the nickname form open while a visitor is deciding to join.
      showScreen(App.screen === "join" ? "join" : "home");
      if (App.playerName) $id("name-input").value = App.playerName;
      return;
    }

    switch (s.state) {
      case "idle":
        showScreen("home");
        break;
      case "lobby":
        showScreen("lobby");
        renderLobby(s);
        break;
      case "tutorial":
        showScreen("tutorial");
        renderTutorial(s);
        break;
      case "countdown":
        showScreen("countdown");
        renderCountdown(s);
        break;
      case "game":
        showScreen("game");
        renderGame(s);
        break;
      case "results":
        showScreen("results");
        renderResults(s);
        break;
      default:
        showScreen("home");
    }
  }

  function updateMicStatus(state) {
    if (!state || state.state !== "music") {
      micStatusRequestId += 1;
      if (micStream || micContext) stopMicCapture();
      micRequesting = false;
      micToken = null;
      micRole = "idle";
      return;
    }
    var requestId = ++micStatusRequestId;
    fetch("/api/music/mic/state?client_id=" + encodeURIComponent(micClientId), { cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(function (status) {
        // A slow poll must not overwrite a more recent lease response.
        if (requestId !== micStatusRequestId || !App.state || App.state.state !== "music") return;
        var oldRole = micRole;
        micRole = status.role || "idle";
        micToken = status.token || null;
        if (oldRole === "owner" && micRole !== "owner" && !micNotice) {
          micNotice = "Your microphone turn ended. Your browser track has been released.";
        }
        var statusText = $id("web-mic-status");
        var queueButton = $id("mic-queue-btn");
        var startButton = $id("mic-start-btn");
        var secure = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
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
    var token = micToken;
    var shouldLeave = micRole !== "idle" || !!token;
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

  function startMicCapture() {
    var statusText = $id("web-mic-status");
    var startButton = $id("mic-start-btn");
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
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
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
    var mediaRequest;
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
        stopMicCapture();
        statusText.textContent = "Your microphone turn ended before access was granted. Join the queue again for another turn.";
        return;
      }
      micStream = stream;
      micNotice = "";
      statusText.textContent = "Microphone allowed. Visualizing live sound; raw audio stays on this device.";
      stream.getTracks().forEach(function (track) {
        track.addEventListener("ended", releaseMic, { once: true });
      });
      var source = micContext.createMediaStreamSource(stream);
      micAnalyser = micContext.createAnalyser();
      micAnalyser.fftSize = 1024;
      source.connect(micAnalyser);
      var samples = new Float32Array(micAnalyser.fftSize);
      function sample(now) {
        if (!micAnalyser || !micToken || micRole !== "owner") return;
        micAnalyser.getFloatTimeDomainData(samples);
        var squares = 0;
        var peak = 0;
        for (var i = 0; i < samples.length; i++) {
          var value = Math.abs(samples[i]);
          squares += value * value;
          if (value > peak) peak = value;
        }
        var rms = Math.sqrt(squares / samples.length);
        if (rms < micNoiseFloor) micNoiseFloor += (rms - micNoiseFloor) * 0.08;
        else if (rms < micNoiseFloor * 2) micNoiseFloor += (rms - micNoiseFloor) * 0.004;
        var level = Math.max(0, Math.min(1, (rms - micNoiseFloor) / Math.max(0.025, micNoiseFloor * 5)));
        var clap = rms > Math.max(0.018, micNoiseFloor * 1.35) && peak > 0.12 &&
          peak / Math.max(0.001, rms) > 3 && now - micLastClap > 160;
        if (clap) micLastClap = now;
        if (now - micLastSend > 100) {
          micLastSend = now;
          fetch("/api/music/mic/audio", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: micToken, level: level, peak: peak, clap: clap }),
          }).then(function (response) {
            if (response.status === 409) releaseMic();
          }).catch(function () {});
        }
        micFrame = requestAnimationFrame(sample);
      }
      micFrame = requestAnimationFrame(sample);
    }).catch(function (error) {
      micRequesting = false;
      var detail = error && error.name === "NotAllowedError"
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

  function renderLobby(s) {
    var list = $id("player-list");
    var players = s.players || [];
    list.innerHTML = "";

    players.forEach(function (p) {
      var li = document.createElement("li");
      var rgb = "rgb(" + p.color.join(",") + ")";

      var chip = document.createElement("span");
      chip.className = "color-chip";
      chip.style.background = rgb;
      chip.style.color = rgb;

      var name = document.createElement("span");
      name.className = "player-name";
      name.textContent = p.name + (p.id === App.playerId ? " (you)" : "");

      var badge = document.createElement("span");
      badge.className = "ready-badge " + (p.ready ? "ready" : "waiting");
      badge.textContent = p.ready ? "READY" : "WAITING";

      li.appendChild(chip);
      li.appendChild(name);
      li.appendChild(badge);
      list.appendChild(li);
    });

    // Ready button reflects own state.
    var me = players.find(function (p) { return p.id === App.playerId; });
    var readyBtn = $id("ready-btn");
    if (me) {
      readyBtn.textContent = me.ready ? "NOT READY" : "READY";
      readyBtn.className = "btn " + (me.ready ? "btn-ghost" : "btn-primary");
    }

    renderGameList(s);
    updateStartButton(s);
  }

  function renderGameList(s) {
    var container = $id("game-list");
    var games = s.games || [];
    container.innerHTML = "";

    games.forEach(function (g) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "game-option" + (g.slug === s.selected_game ? " selected" : "");

      var name = document.createElement("div");
      name.className = "game-name";
      name.textContent = g.name;
      btn.appendChild(name);

      var desc = document.createElement("div");
      desc.className = "game-desc";
      desc.textContent = g.description;
      btn.appendChild(desc);

      var layouts = document.createElement("div");
      layouts.className = "game-meta";
      layouts.textContent = "Layouts: " + (g.layouts || ["horizontal", "vertical"])
        .map(function (layout) {
          return layout.charAt(0).toUpperCase() + layout.slice(1);
        }).join(" · ");
      btn.appendChild(layouts);

      var meta = document.createElement("div");
      meta.className = "game-meta";
      var players = g.max_players == null
        ? g.min_players + "+ players"
        : (g.min_players === g.max_players
          ? g.min_players + " player" + (g.min_players === 1 ? "" : "s")
          : g.min_players + "–" + g.max_players + " players");
      meta.textContent = players;
      btn.appendChild(meta);

      btn.addEventListener("click", function () {
        App.socket.emit("select_game", { slug: g.slug });
      });

      container.appendChild(btn);
    });
  }

  function updateStartButton(s) {
    var players = s.players || [];
    var startBtn = $id("start-btn");
    var selected = (s.games || []).find(function (g) { return g.slug === s.selected_game; });
    var enough = selected && players.length >= selected.min_players;
    startBtn.disabled = !(s.selected_game && enough);
  }

  function renderCountdown(s) {
    var n = Math.max(1, Math.ceil(s.countdown || 0));
    $id("countdown-number").textContent = n;
    var game = (s.games || []).find(function (g) { return g.slug === s.selected_game; });
    $id("countdown-game").textContent = game ? game.name : "";
  }

  function renderTutorial(s) {
    var game = (s.games || []).find(function (item) { return item.slug === s.selected_game; });
    var tutorial = s.tutorial || {};
    $id("tutorial-game-name").textContent = game ? game.name : "Game tutorial";
    $id("tutorial-title").textContent = tutorial.title || "Get ready";
    $id("tutorial-instruction").textContent = tutorial.instruction || "Watch the LED strip.";
    $id("tutorial-step").textContent = tutorial.count
      ? "Step " + tutorial.index + " of " + tutorial.count
      : "Starting soon";
    var progress = tutorial.count ? (tutorial.index / tutorial.count) * 100 : 100;
    $id("tutorial-progress").style.width = progress + "%";
  }

  function renderGame(s) {
    var game = s.game || {};
    $id("game-title").textContent = game.name || "Game";
    $id("game-subtitle").textContent = "";
    if (typeof renderHud === "function") renderHud(s);
    if (typeof renderController === "function") renderController(s);
  }

  function renderResults(s) {
    var title = $id("results-title");
    var body = $id("results-body");
    var players = s.players || [];
    var game = s.game || {};

    if (game.winner_name) {
      title.textContent = game.winner_name + " wins!";
    } else {
      title.textContent = "Results";
    }

    // Rank players by score (descending).
    var ranked = players.slice().sort(function (a, b) { return b.score - a.score; });
    body.innerHTML = "";

    var list = document.createElement("div");
    list.className = "results-list";

    ranked.forEach(function (p, i) {
      var row = document.createElement("div");
      row.className = "result-row" + (i === 0 ? " winner" : "");

      var place = document.createElement("span");
      place.className = "result-place";
      place.textContent = "#" + (i + 1);
      row.appendChild(place);

      var chip = document.createElement("span");
      chip.className = "color-chip";
      var rgb = "rgb(" + p.color.join(",") + ")";
      chip.style.background = rgb;
      chip.style.color = rgb;
      row.appendChild(chip);

      var name = document.createElement("span");
      name.className = "player-name";
      name.textContent = p.name;
      row.appendChild(name);

      var score = document.createElement("span");
      score.className = "result-score";
      score.textContent = formatScore(p, game, s);
      row.appendChild(score);

      list.appendChild(row);
    });

    body.appendChild(list);

    // Game-specific detail (e.g. reaction times).
    if (typeof renderResultsDetail === "function") {
      renderResultsDetail(s, body);
    }

    // Rematch only makes sense for the joined player.
    $id("rematch-btn").hidden = false;
  }

  function formatScore(p, game, s) {
    if (game && game.slug === "reaction" && game.results && game.results.totals_ms) {
      var total = game.results.totals_ms[p.id];
      if (total != null) return Math.round(total) + " ms";
    }
    return p.score;
  }

  // ---- events -------------------------------------------------------------
  function wireEvents() {
    $id("enter-lobby").addEventListener("click", function () {
      App.screen = "join";
      showScreen("join");
    });

    $id("music-mode-btn").addEventListener("click", function () {
      if (!App.state || App.state.state !== "music") releaseMic();
      App.socket.emit("music_mode", { enabled: !App.state || App.state.state !== "music" });
    });

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

    function submitMusicVisualizer() {
      var requestId = ++musicVisualizerRequestId;
      var selection = {
        animation: $id("music-animation-select").value,
        primary_color: $id("music-live-primary").value,
        accent_color: $id("music-live-accent").value,
      };
      musicVisualizerPending = selection;
      fetch("/api/music/visualizer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(selection),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not switch visualizer.");
          return body;
        });
      }).then(function (body) {
        if (requestId !== musicVisualizerRequestId) return;
        musicVisualizerPending = null;
        $id("music-animation").value = body.animation;
        $id("music-primary-color").value = body.primary_color;
        $id("music-accent-color").value = body.accent_color;
        if (App.state && App.state.music_visualizer) {
          App.state.music_visualizer.animation = body.animation;
          App.state.music_visualizer.primary_color = body.primary_color;
          App.state.music_visualizer.accent_color = body.accent_color;
        }
        render();
      }).catch(function (error) {
        if (requestId !== musicVisualizerRequestId) return;
        musicVisualizerPending = null;
        render();
        $id("music-visualizer-status").textContent = error.message;
      });
    }

    $id("music-animation-select").addEventListener("change", submitMusicVisualizer);
    $id("music-live-primary").addEventListener("change", submitMusicVisualizer);
    $id("music-live-accent").addEventListener("change", submitMusicVisualizer);

    $id("join-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var name = $id("name-input").value.trim();
      if (!name) return;
      $id("join-error").hidden = true;
      setPlayerName(name);
      App.socket.emit("join", { name: name });
    });

    $id("ready-btn").addEventListener("click", function () {
      var me = (App.state.players || []).find(function (p) { return p.id === App.playerId; });
      App.socket.emit("ready", { ready: me ? !me.ready : true });
    });

    $id("leave-btn").addEventListener("click", function () {
      App.socket.emit("leave");
      setPlayerId(null);
    });

    $id("start-btn").addEventListener("click", function () {
      App.socket.emit("start_game");
    });

    $id("skip-tutorial-btn").addEventListener("click", function () {
      App.socket.emit("skip_tutorial");
    });

    $id("back-to-idle").addEventListener("click", function () {
      App.socket.emit("return_to_idle");
      setPlayerId(null);
    });

    $id("rematch-btn").addEventListener("click", function () {
      App.socket.emit("rematch");
    });

    $id("results-idle-btn").addEventListener("click", function () {
      App.socket.emit("return_to_idle");
      setPlayerId(null);
    });

    var loginForm = $id("admin-login-form");
    var settingsForm = $id("admin-settings-form");
    var adminMessage = $id("admin-message");

    function showAdminMessage(message) {
      adminMessage.textContent = message || "";
    }

    function loadAdminSettings() {
      fetch("/api/admin/settings").then(function (response) {
        if (!response.ok) throw new Error("not logged in");
        return response.json();
      }).then(function (data) {
        $id("hidden-start").value = data.hidden_start;
        $id("hidden-end").value = data.hidden_end;
        $id("mic-handoff-seconds").value = data.mic_handoff_seconds;
        $id("music-animation").value = data.music_animation || "center_pulse";
        $id("music-sensitivity").value = data.music_sensitivity || 1;
        $id("music-primary-color").value = data.music_primary_color || "#00e5ff";
        $id("music-accent-color").value = data.music_accent_color || "#ff2ea6";
        ["red", "green", "blue"].forEach(function (channel) {
          var value = data["led_color_" + channel] == null ? 100 : data["led_color_" + channel];
          $id("led-color-" + channel).value = value;
          $id("led-color-" + channel + "-value").textContent = value + "%";
        });
        $id("music-sensitivity-value").textContent = Number($id("music-sensitivity").value).toFixed(2) + "×";
        $id("hidden-start").max = data.led_count;
        $id("hidden-end").max = data.led_count;
        loginForm.hidden = true;
        settingsForm.hidden = false;
        showAdminMessage("Admin access enabled.");
      }).catch(function () {
        loginForm.hidden = false;
        settingsForm.hidden = true;
      });
    }

    loginForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      showAdminMessage("Checking password…");
      fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: $id("admin-password").value }),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Login failed.");
          return body;
        });
      }).then(loadAdminSettings).catch(function (error) {
        showAdminMessage(error.message);
      });
    });

    settingsForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      fetch("/api/admin/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hidden_start: Number($id("hidden-start").value),
          hidden_end: Number($id("hidden-end").value),
          mic_handoff_seconds: Number($id("mic-handoff-seconds").value),
          music_animation: $id("music-animation").value,
          music_sensitivity: Number($id("music-sensitivity").value),
          music_primary_color: $id("music-primary-color").value,
          music_accent_color: $id("music-accent-color").value,
          led_color_red: Number($id("led-color-red").value),
          led_color_green: Number($id("led-color-green").value),
          led_color_blue: Number($id("led-color-blue").value),
        }),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not save settings.");
          return body;
        });
      }).then(function (body) {
        showAdminMessage("Saved. " + body.hidden_start + " hidden at start, " +
          body.hidden_end + " hidden at end; microphone handoff " + body.mic_handoff_seconds +
          " seconds; " + body.music_animation.split("_").join(" ") + " at " +
          Number(body.music_sensitivity).toFixed(2) + "× sensitivity; colors " +
          body.music_primary_color + " / " + body.music_accent_color + "; LED balance R/G/B " +
          body.led_color_red + "% / " + body.led_color_green + "% / " + body.led_color_blue + "%. ");
      }).catch(function (error) {
        showAdminMessage(error.message);
      });
    });

    $id("admin-logout").addEventListener("click", function () {
      fetch("/api/admin/logout", { method: "POST" }).then(function () {
        settingsForm.hidden = true;
        loginForm.hidden = false;
        $id("admin-password").value = "";
        showAdminMessage("Logged out.");
      });
    });

    $id("music-sensitivity").addEventListener("input", function () {
      $id("music-sensitivity-value").textContent = Number(this.value).toFixed(2) + "×";
    });
    ["red", "green", "blue"].forEach(function (channel) {
      $id("led-color-" + channel).addEventListener("input", function () {
        $id("led-color-" + channel + "-value").textContent = this.value + "%";
      });
    });

    loadAdminSettings();
  }

  // Expose a helper for the controller modules.
  window.App = App;

  document.addEventListener("DOMContentLoaded", function () {
    // Pre-fill name and QR.
    if (App.playerName) $id("name-input").value = App.playerName;
    $id("qr-code").innerHTML = '<img src="/qr.svg" width="160" height="160" alt="QR code">';

    wireEvents();
    connect();
  });

  window.addEventListener("pagehide", releaseMic);
})();
