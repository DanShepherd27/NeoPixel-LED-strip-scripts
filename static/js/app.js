/* LED Arcade — main client logic: socket, screens, lobby, results. */

(function () {
  "use strict";

  var STORAGE_ID = "led_arcade_player_id";
  var STORAGE_NAME = "led_arcade_player_name";

  var App = {
    socket: null,
    playerId: localStorage.getItem(STORAGE_ID) || null,
    playerName: localStorage.getItem(STORAGE_NAME) || null,
    state: null,
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
    if (id) localStorage.setItem(STORAGE_ID, id);
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
          return_to_idle: "/api/return_to_idle", input: "/api/input",
          ping: "/api/ping",
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
  }

  // ---- rendering ----------------------------------------------------------
  function render() {
    var s = App.state;
    if (!s) return;

    $id("idle-animation").textContent = s.idle_animation || "—";
    $id("player-count").textContent = (s.players || []).length;
    $id("lan-url").textContent = window.location.host;
    var orientation = s.led_orientation || "vertical";
    var orientationLabel = $id("strip-orientation");
    if (orientationLabel) orientationLabel.textContent = orientation;

    if (!App.playerId) {
      // Spectator: show attract screen.
      showScreen("home");
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
      showScreen("join");
    });

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
        }),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not save settings.");
          return body;
        });
      }).then(function (body) {
        showAdminMessage("Saved. " + body.hidden_start + " hidden at start, " +
          body.hidden_end + " hidden at end.");
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
})();
