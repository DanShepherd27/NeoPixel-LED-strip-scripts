/* LED Arcade — main client logic: socket, screens, lobby, results. */

(function () {
  "use strict";

  const STORAGE_ID = "led_arcade_player_id";
  const STORAGE_NAME = "led_arcade_player_name";
  let musicVisualizerPending = null;
  let musicVisualizerDraft = null;
  let musicVisualizerRequestId = 0;

  const App = {
    socket: null,
    playerId: localStorage.getItem(STORAGE_ID) || null,
    playerName: localStorage.getItem(STORAGE_NAME) || null,
    state: null,
    screen: null,
    previewInvertOrder: false,
  };

  function $id(id) { return document.getElementById(id); }

  function showScreen(name) {
    const screens = document.querySelectorAll(".screen");
    for (let i = 0; i < screens.length; i++) screens[i].classList.remove("active");
    const el = $id("screen-" + name);
    if (el) el.classList.add("active");
  }

  function setConn(on) {
    const dot = $id("connection");
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
    const handlers = {};
    const socket = {
      connected: false,
      on: function (event, callback) {
        (handlers[event] = handlers[event] || []).push(callback);
      },
      emit: function (event, data) {
        const routes = {
          join: "/api/join", rejoin: "/api/rejoin", leave: "/api/leave",
          ready: "/api/ready", select_game: "/api/select_game",
          start_game: "/api/start_game", rematch: "/api/rematch",
          skip_tutorial: "/api/skip_tutorial",
          return_to_idle: "/api/return_to_idle", input: "/api/input",
          ping: "/api/ping",
          music_mode: "/api/music_mode",
        };
        const route = routes[event];
        if (!route) return;
        const payload = Object.assign({}, data || {});
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
        setPollDelay(state.state === "music" || state.state === "song" ? 125 : 500);
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
    let pollDelay = 500;
    let pollTimer = setInterval(poll, pollDelay);
    function setPollDelay(delay) {
      if (pollDelay === delay) return;
      pollDelay = delay;
      clearInterval(pollTimer);
      pollTimer = setInterval(poll, pollDelay);
    }
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
      const err = $id("join-error");
      err.textContent = data && data.message ? data.message : "Something went wrong.";
      err.hidden = false;
      const musicError = $id("music-message");
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
    window.WebMic.updateStatus(state);
  }

  // ---- rendering ----------------------------------------------------------
  function render() {
    const s = App.state;
    if (!s) return;
    document.body.dataset.arcadeState = s.state || "";
    if (s.preview_invert_order != null) App.previewInvertOrder = s.preview_invert_order === true;

    $id("idle-animation").textContent = s.idle_animation || "—";
    $id("player-count").textContent = (s.players || []).length;
    $id("lan-url").textContent = window.location.host;
    const musicButton = $id("music-mode-btn");
    const musicMessage = $id("music-message");
    if (musicButton) {
      const musicActive = s.state === "music";
      musicButton.textContent = musicActive ? "STOP SOUND REACTIVE LIGHTING" : "START SOUND REACTIVE LIGHTING";
      const audio = s.audio || {};
      musicMessage.textContent = musicActive
        ? (audio.source === "web"
          ? "Listening to this browser microphone; only analyzed sound levels are sent to the Pi."
          : (audio.status === "listening"
            ? "Using the Pi microphone fallback (" + (audio.device || "default") + ")."
            : (audio.error || "Waiting for a web microphone or Pi input.")))
        : "Uses this browser microphone when available, with the Pi microphone as fallback.";
      const visualizer = s.music_visualizer || {};
      const visualizerStatus = $id("music-visualizer-status");
      if (visualizerStatus) {
        visualizerStatus.textContent = musicActive
          ? "Pattern: " + window.MusicPreview.patternLabel(visualizer.animation) + " · Sensitivity: " +
            Number(visualizer.sensitivity || 1).toFixed(2) + "×"
          : "";
      }
      if (musicActive && visualizer.bpm && visualizerStatus) {
        visualizerStatus.textContent += " | Beat sync: " + visualizer.bpm + " BPM";
      }
      const selection = musicVisualizerPending || musicVisualizerDraft || visualizer;
      const animationSelect = $id("music-animation-select");
      const selectedPattern = selection.animation || "center_pulse";
      if (animationSelect) animationSelect.value = selectedPattern;
      $id("music-live-effect-controls").hidden = !musicActive || selectedPattern !== "christmas_glitter";
      $id("music-live-glitter-brightness").value = selection.glitter_brightness == null
        ? 255 : selection.glitter_brightness;
      $id("music-live-glitter-brightness-value").textContent = $id("music-live-glitter-brightness").value;
      window.MusicPreview.configurePatternControls("music", selectedPattern, selection.band_colors);
      $id("music-live-primary").value = selection.primary_color || "#00e5ff";
      $id("music-live-accent").value = selection.accent_color || "#ff2ea6";
      const enabledBands = selection.enabled_bands || [true, true, true, true, true, true];
      document.querySelectorAll("#live-band-controls [data-band]").forEach(function (input) {
        input.checked = enabledBands[Number(input.dataset.band)] !== false;
      });
      window.MusicPreview.updateColors();
      $id("web-mic-controls").hidden = !musicActive;
    }
    const orientation = s.led_orientation || "vertical";
    const orientationLabel = $id("strip-orientation");
    if (orientationLabel) orientationLabel.textContent = orientation;

    if (!App.playerId) {
      // Keep the nickname form open while a visitor is deciding to join.
      showScreen(App.screen === "join" ? "join" : "home");
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

  function renderLobby(s) {
    const list = $id("player-list");
    const players = s.players || [];
    list.innerHTML = "";

    players.forEach(function (p) {
      const li = document.createElement("li");
      const rgb = "rgb(" + p.color.join(",") + ")";

      const chip = document.createElement("span");
      chip.className = "color-chip";
      chip.style.background = rgb;
      chip.style.color = rgb;

      const name = document.createElement("span");
      name.className = "player-name";
      name.textContent = p.name + (p.id === App.playerId ? " (you)" : "");

      const badge = document.createElement("span");
      badge.className = "ready-badge " + (p.ready ? "ready" : "waiting");
      badge.textContent = p.ready ? "READY" : "WAITING";

      li.appendChild(chip);
      li.appendChild(name);
      li.appendChild(badge);
      list.appendChild(li);
    });

    // Ready button reflects own state.
    const me = players.find(function (p) { return p.id === App.playerId; });
    const readyBtn = $id("ready-btn");
    if (me) {
      readyBtn.textContent = me.ready ? "NOT READY" : "READY";
      readyBtn.className = "btn " + (me.ready ? "btn-ghost" : "btn-primary");
    }
    const readyCount = players.filter(function (player) { return player.connected && player.ready; }).length;
    const connectedCount = players.filter(function (player) { return player.connected; }).length;
    $id("lobby-ready-status").textContent = readyCount + " of " + connectedCount + " players ready. Everyone must be ready to start.";

    renderGameList(s);
    updateStartButton(s);
  }

  function renderGameList(s) {
    const container = $id("game-list");
    const games = s.games || [];
    container.innerHTML = "";

    games.forEach(function (g) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "game-option" + (g.slug === s.selected_game ? " selected" : "");

      const name = document.createElement("div");
      name.className = "game-name";
      name.textContent = g.name;
      btn.appendChild(name);

      const desc = document.createElement("div");
      desc.className = "game-desc";
      desc.textContent = g.description;
      btn.appendChild(desc);

      const layouts = document.createElement("div");
      layouts.className = "game-meta";
      layouts.textContent = "Layouts: " + (g.layouts || ["horizontal", "vertical"])
        .map(function (layout) {
          return layout.charAt(0).toUpperCase() + layout.slice(1);
        }).join(" · ");
      btn.appendChild(layouts);

      const meta = document.createElement("div");
      meta.className = "game-meta";
      const players = g.max_players == null
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
    const players = s.players || [];
    const startBtn = $id("start-btn");
    const selected = (s.games || []).find(function (g) { return g.slug === s.selected_game; });
    const connected = players.filter(function (player) { return player.connected; });
    const enough = selected && connected.length >= selected.min_players;
    const everyoneReady = connected.length > 0 && connected.every(function (player) { return player.ready; });
    startBtn.disabled = !(s.selected_game && enough && everyoneReady);
  }

  function renderCountdown(s) {
    const n = Math.max(1, Math.ceil(s.countdown || 0));
    $id("countdown-number").textContent = n;
    const game = (s.games || []).find(function (g) { return g.slug === s.selected_game; });
    $id("countdown-game").textContent = game ? game.name : "";
  }

  function renderTutorial(s) {
    const game = (s.games || []).find(function (item) { return item.slug === s.selected_game; });
    const tutorial = s.tutorial || {};
    $id("tutorial-game-name").textContent = game ? game.name : "Game tutorial";
    $id("tutorial-title").textContent = tutorial.title || "Get ready";
    $id("tutorial-instruction").textContent = tutorial.instruction || "Watch the LED strip.";
    $id("tutorial-step").textContent = tutorial.count
      ? "Step " + tutorial.index + " of " + tutorial.count
      : "Starting soon";
    const progress = tutorial.count ? (tutorial.index / tutorial.count) * 100 : 100;
    $id("tutorial-progress").style.width = progress + "%";
    const players = s.players || [];
    const connected = players.filter(function (player) { return player.connected; });
    const readyCount = connected.filter(function (player) { return player.ready; }).length;
    const waiting = !!tutorial.waiting_ready;
    const me = connected.find(function (player) { return player.id === App.playerId; });
    const readyButton = $id("tutorial-ready-btn");
    readyButton.disabled = !waiting || !me;
    readyButton.textContent = me && me.ready ? "NOT READY" : "READY";
    readyButton.className = "btn btn-block " + (me && me.ready ? "btn-ghost" : "btn-primary");
    $id("tutorial-ready-status").textContent = waiting
      ? readyCount + " of " + connected.length + " players ready. " + (readyCount === connected.length ? "Starting countdown…" : "Waiting for everyone.")
      : "Read the instructions, then watch the LED demo. You can replay it before marking ready.";
    $id("replay-tutorial-btn").hidden = !waiting;
  }

  function renderGame(s) {
    const game = s.game || {};
    $id("game-title").textContent = game.name || "Game";
    $id("game-subtitle").textContent = "";
    if (typeof renderHud === "function") renderHud(s);
    if (typeof renderController === "function") renderController(s);
  }

  function renderResults(s) {
    const title = $id("results-title");
    const body = $id("results-body");
    const players = s.players || [];
    const game = s.game || {};

    if (game.winner_name) {
      title.textContent = game.winner_name + " wins!";
    } else {
      title.textContent = "Results";
    }

    // Rank players by score (descending).
    const ranked = players.slice().sort(function (a, b) { return b.score - a.score; });
    body.innerHTML = "";

    const list = document.createElement("div");
    list.className = "results-list";

    ranked.forEach(function (p, i) {
      const row = document.createElement("div");
      row.className = "result-row" + (i === 0 ? " winner" : "");

      const place = document.createElement("span");
      place.className = "result-place";
      place.textContent = "#" + (i + 1);
      row.appendChild(place);

      const chip = document.createElement("span");
      chip.className = "color-chip";
      const rgb = "rgb(" + p.color.join(",") + ")";
      chip.style.background = rgb;
      chip.style.color = rgb;
      row.appendChild(chip);

      const name = document.createElement("span");
      name.className = "player-name";
      name.textContent = p.name;
      row.appendChild(name);

      const score = document.createElement("span");
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
      const total = game.results.totals_ms[p.id];
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
      if (!App.state || App.state.state !== "music") window.WebMic.release();
      App.socket.emit("music_mode", { enabled: !App.state || App.state.state !== "music" });
    });

    window.WebMic.bindControls(App);

    function submitMusicVisualizer() {
      const requestId = ++musicVisualizerRequestId;
      const selection = {
        animation: $id("music-animation-select").value,
        primary_color: $id("music-live-primary").value,
        accent_color: $id("music-live-accent").value,
        band_colors: window.MusicPreview.getBandColors("music"),
        enabled_bands: Array.prototype.map.call(
          document.querySelectorAll("#live-band-controls [data-band]"), function (input) { return input.checked; }),
        glitter_brightness: Number($id("music-live-glitter-brightness").value),
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
        musicVisualizerDraft = null;
        $id("music-animation").value = body.animation;
        $id("music-primary-color").value = body.primary_color;
        $id("music-accent-color").value = body.accent_color;
        if (App.state && App.state.music_visualizer) {
          App.state.music_visualizer.animation = body.animation;
          App.state.music_visualizer.primary_color = body.primary_color;
          App.state.music_visualizer.accent_color = body.accent_color;
          App.state.music_visualizer.enabled_bands = body.enabled_bands;
          App.state.music_visualizer.band_colors = body.band_colors;
          App.state.music_visualizer.glitter_brightness = body.glitter_brightness;
        }
        render();
      }).catch(function (error) {
        if (requestId !== musicVisualizerRequestId) return;
        musicVisualizerPending = null;
        musicVisualizerDraft = null;
        render();
        $id("music-visualizer-status").textContent = error.message;
      });
    }

    function rememberMusicVisualizerDraft() {
      musicVisualizerDraft = {
        animation: $id("music-animation-select").value,
        primary_color: $id("music-live-primary").value,
        accent_color: $id("music-live-accent").value,
        band_colors: window.MusicPreview.getBandColors("music"),
        enabled_bands: Array.prototype.map.call(
          document.querySelectorAll("#live-band-controls [data-band]"), function (input) { return input.checked; }),
        glitter_brightness: Number($id("music-live-glitter-brightness").value),
      };
    }

    $id("music-animation-select").addEventListener("change", function () {
      const pattern = this.value;
      window.MusicPreview.configurePatternControls(
        "music", pattern, App.state.music_visualizer.band_colors,
      );
      submitMusicVisualizer();
    });
    $id("music-band-color-controls").addEventListener("change", submitMusicVisualizer);
    $id("music-live-glitter-brightness").addEventListener("input", function () {
      $id("music-live-glitter-brightness-value").textContent = this.value;
      rememberMusicVisualizerDraft();
    });
    $id("music-live-glitter-brightness").addEventListener("change", submitMusicVisualizer);
    document.querySelectorAll("#live-band-controls [data-band]").forEach(function (input) {
      input.addEventListener("change", submitMusicVisualizer);
    });
    ["music-live-primary", "music-live-accent"].forEach(function (id) {
      const picker = $id(id);
      picker.addEventListener("focus", rememberMusicVisualizerDraft);
      picker.addEventListener("input", rememberMusicVisualizerDraft);
      picker.addEventListener("change", function () {
        rememberMusicVisualizerDraft();
        submitMusicVisualizer();
      });
      picker.addEventListener("blur", function () {
        window.setTimeout(function () {
          if (!musicVisualizerPending) {
            const visualizer = App.state && App.state.music_visualizer || {};
            const stateKey = id === "music-live-primary" ? "primary_color" : "accent_color";
            const committedColor = visualizer[stateKey] || (stateKey === "primary_color" ? "#00e5ff" : "#ff2ea6");
            if (picker.value.toLowerCase() !== committedColor.toLowerCase()) {
              submitMusicVisualizer();
            } else {
              musicVisualizerDraft = null;
              render();
            }
          }
        }, 0);
      });
      picker.addEventListener("input", window.MusicPreview.updateColors);
      picker.addEventListener("change", window.MusicPreview.updateColors);
    });

    $id("join-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      const name = $id("name-input").value.trim();
      if (!name) return;
      $id("join-error").hidden = true;
      setPlayerName(name);
      App.socket.emit("join", { name: name });
    });

    $id("ready-btn").addEventListener("click", function () {
      const me = (App.state.players || []).find(function (p) { return p.id === App.playerId; });
      App.socket.emit("ready", { ready: me ? !me.ready : true });
    });

    $id("leave-btn").addEventListener("click", function () {
      App.socket.emit("leave");
      setPlayerId(null);
    });

    $id("start-btn").addEventListener("click", function () {
      App.socket.emit("start_game");
    });

    $id("tutorial-ready-btn").addEventListener("click", function () {
      const me = (App.state.players || []).find(function (p) { return p.id === App.playerId; });
      App.socket.emit("ready", { ready: me ? !me.ready : true });
    });

    $id("replay-tutorial-btn").addEventListener("click", function () {
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

    window.AdminSettings.init(App);
  }

  // Expose a helper for the controller modules.
  window.App = App;

  document.addEventListener("DOMContentLoaded", function () {
    // Pre-fill name and QR.
    if (App.playerName) $id("name-input").value = App.playerName;
    $id("qr-code").innerHTML = '<img src="/qr.svg" width="160" height="160" alt="QR code">';

    wireEvents();
    connect();
    window.MusicPreview.start(App);
  });

  window.addEventListener("pagehide", window.WebMic.release);
})();
