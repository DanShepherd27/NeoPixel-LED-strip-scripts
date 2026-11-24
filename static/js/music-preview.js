(function () {
  "use strict";
  function $id(id) { return document.getElementById(id); }
  function updateColorPreview(inputId, previewId, valueId) {
    const input = $id(inputId);
    const preview = $id(previewId);
    const value = $id(valueId);
    if (!input || !preview || !value) return;
    const hex = input.value;
    const channels = [1, 3, 5].map(function (offset) {
      const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
      // Approximate the extra apparent brightness of an emissive LED against
      // the dark page. This changes only the preview, never the sent RGB.
      return Math.round(Math.pow(channel, 0.68) * 255);
    });
    const cssColor = "rgb(" + channels.join(", ") + ")";
    preview.style.backgroundColor = cssColor;
    preview.style.boxShadow = "0 0 16px rgba(" + channels.join(", ") + ", 0.68), " +
      "inset 0 0 8px rgba(255, 255, 255, 0.24)";
    value.textContent = hex.toUpperCase();
  }

  function updateColors() {
    updateColorPreview("music-live-primary", "music-live-primary-preview", "music-live-primary-value");
    updateColorPreview("music-live-accent", "music-live-accent-preview", "music-live-accent-value");
    updateColorPreview("music-primary-color", "music-primary-preview", "music-primary-value");
    updateColorPreview("music-accent-color", "music-accent-preview", "music-accent-value");
  }

  const twoColorPatterns = new Set(["center_pulse", "mirror_bars", "comet", "inward_diamonds"]);
  const bandNames = ["Sub-bass", "Bass", "Low mids", "Mids", "High mids", "Treble"];
  const defaultBandColors = ["#FF2C0C", "#FF7A00", "#FFDC00", "#24FF20", "#00CDFF", "#AA20FF"];
  const bandColorCache = {};
  const patternLabels = {
    center_pulse: "Center glow", mirror_bars: "Mirrored blocks",
    rainbow_wave: "Rainbow sweep", comet: "Comet tail", retro_vu: "Retro VU meter",
    live_band: "Six band spectrum", bpm_trace: "Beat timing trace",
    laser_dance: "Laser dance", kitt_scanner: "Red scanner",
    inward_diamonds: "Inward diamonds", red_shades: "Red pulse",
    christmas_glitter: "Christmas glitter", club: "Club (kick, snare, lead)",
    genesys: "Genesys (Anyma style)", holo: "Holo (Eric Prydz style)",
    paradise: "Paradise (Swedish House Mafia style)", rave: "Rave (Fred again.. style)",
  };

  function configurePatternControls(scope, pattern, bandColors) {
    const standard = $id(scope + "-standard-colors");
    const bandContainer = $id(scope + "-band-color-controls");
    if (!standard || !bandContainer) return;
    if (Array.isArray(bandColors) && bandColors.length === 6) {
      bandColorCache[scope] = bandColors.map(function (color) { return color.toUpperCase(); });
    }
    if (!bandColorCache[scope]) bandColorCache[scope] = defaultBandColors.slice();
    if (bandContainer.dataset.pattern === pattern) return;
    standard.hidden = !twoColorPatterns.has(pattern);
    bandContainer.hidden = pattern !== "live_band";
    bandContainer.dataset.pattern = pattern;
    bandContainer.replaceChildren();
    if (pattern !== "live_band") return;

    const colors = bandColorCache[scope];
    bandNames.forEach(function (name, index) {
      const label = document.createElement("label");
      label.append(document.createTextNode(name));
      const input = document.createElement("input");
      input.type = "color";
      input.id = scope + "-band-color-" + index;
      input.value = colors[index];
      const value = document.createElement("code");
      value.id = input.id + "-value";
      value.textContent = input.value.toUpperCase();
      input.addEventListener("input", function () {
        value.textContent = input.value.toUpperCase();
        bandColorCache[scope][index] = input.value.toUpperCase();
      });
      label.append(input, value);
      bandContainer.appendChild(label);
    });
  }

  function getBandColors(scope) {
    if (!bandColorCache[scope]) bandColorCache[scope] = defaultBandColors.slice();
    bandNames.forEach(function (_, index) {
      const input = $id(scope + "-band-color-" + index);
      if (input) bandColorCache[scope][index] = input.value.toUpperCase();
    });
    return bandColorCache[scope].slice();
  }

  let previewAnimation = 0;
  let previewLastDraw = 0;
  let currentApp = null;
  function drawMusicPreviews() {
    previewAnimation = requestAnimationFrame(drawMusicPreviews);
    const now = performance.now();
    // State arrives at 2 Hz; redraw at a modest rate between updates without
    // repeatedly allocating paths and repainting both canvases at display Hz.
    if (now - previewLastDraw < 50) return;
    previewLastDraw = now;
    const audio = currentApp.state && currentApp.state.audio || {};
    let bands = Array.isArray(audio.bands) && audio.bands.length === 6
      ? audio.bands.map(function (value) { return Math.max(0, Math.min(1, Number(value) || 0)); })
      : [0, 0, 0, 0, 0, 0];
    const overallLevel = Math.max(0, Math.min(1, Number(audio.level) || 0));
    // Older or partially available audio sources may provide overall level
    // without usable frequency bands. Keep the graphic EQ visibly responsive
    // instead of presenting a blank chart while audio is reaching the server.
    if (overallLevel > 0.015 && !bands.some(function (value) { return value > 0.015; })) {
      bands = bands.map(function () { return overallLevel; });
    }
    const selected = Array.prototype.map.call(document.querySelectorAll("#live-band-controls [data-band]"),
      function (input) { return input.checked; });
    const colors = ["#ff2c0c", "#ff7a00", "#ffdc00", "#24ff20", "#00cdff", "#aa20ff"];
    const eq = $id("music-eq-preview");
    if (eq) {
      const ctx = eq.getContext("2d");
      const width = eq.clientWidth || 360, height = eq.clientHeight || 130;
      ctx.clearRect(0, 0, width, height);
      ctx.strokeStyle = "rgba(180,190,220,.16)";
      for (let row = 1; row <= 4; row++) {
        const y = height - row * height / 5;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
      }
      const gap = 7, barWidth = (width - gap * 7) / 6;
      bands.forEach(function (level, index) {
        const x = gap + index * (barWidth + gap);
        const barHeight = Math.max(2, (selected[index] ? level : 0) * (height - 9));
        ctx.globalAlpha = selected[index] ? 1 : 0.2;
        ctx.fillStyle = colors[index];
        ctx.fillRect(x, height - barHeight, barWidth, barHeight);
        ctx.globalAlpha = 1;
        ctx.fillStyle = "#9a9ab0";
        ctx.fillRect(x, height - barHeight - 3, barWidth, 2);
      });
    }
    const strip = $id("music-led-preview");
    if (strip) {
      const ctx2 = strip.getContext("2d");
      const sw = strip.clientWidth || 360, sh = strip.clientHeight || 130;
      const dpr = window.devicePixelRatio || 1;
      if (strip.width !== Math.round(sw * dpr) || strip.height !== Math.round(sh * dpr)) {
        strip.width = Math.round(sw * dpr);
        strip.height = Math.round(sh * dpr);
      }
      ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx2.clearRect(0, 0, sw, sh);
      const frame = currentApp.state && currentApp.state.music_led_frame;
      const vertical = window.matchMedia("(orientation: portrait)").matches;
      const reverse = currentApp.previewInvertOrder;
      const ledCount = frame && frame.length === 60 ? frame.length : 60;
      const pitch = (vertical ? sh : sw) / ledCount;
      const radius = Math.max(1, Math.min(vertical ? sw : sh, pitch) * 0.38);
      ctx2.lineWidth = 1;
      for (let led = 0; led < 60; led++) {
        const rgb = frame && frame[led] || [0, 0, 0];
        const lit = rgb.some(function (channel) { return channel > 0; });
        const position = (reverse ? 59 - led : led) + 0.5;
        const x = vertical ? sw / 2 : pitch * position;
        const y = vertical ? sh - pitch * position : sh / 2;
        ctx2.beginPath();
        ctx2.arc(x, y, radius, 0, Math.PI * 2);
        const displayRgb = rgb.map(function (channel) {
          return Math.max(0, Math.min(255, Math.round(channel)));
        });
        const color = "rgb(" + displayRgb.join(",") + ")";
        ctx2.fillStyle = lit ? color : "#252532";
        ctx2.globalAlpha = lit ? 1 : 0.86;
        ctx2.shadowColor = lit ? color : "transparent";
        ctx2.shadowBlur = 0;
        ctx2.fill();
      }
      ctx2.globalAlpha = 1; ctx2.shadowBlur = 0;
    }
    const source = $id("music-preview-source");
    if (source) {
      const state = currentApp.state || {};
      const visualizer = state.music_visualizer || {};
      const pattern = visualizer.animation || "center_pulse";
      const scene = state.state === "music" ? (patternLabels[pattern] || "Sound reactive") :
        (state.game && state.game.name ? state.game.name : (state.idle_animation || state.state || "idle"));
      source.textContent = "Showing " + scene.toString().replace(/_/g, " ");
    }
  }

  window.MusicPreview = {
    updateColors: updateColors,
    configurePatternControls: configurePatternControls,
    getBandColors: getBandColors,
    patternLabel: function (pattern) { return patternLabels[pattern] || "Sound reactive pattern"; },
    start: function (app) {
      currentApp = app;
      if (!previewAnimation) previewAnimation = requestAnimationFrame(drawMusicPreviews);
    },
  };
})();
