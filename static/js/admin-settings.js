/* Admin login and runtime settings UI. */
(function () {
  "use strict";
  function $id(id) { return document.getElementById(id); }
  function init(App) {
    const adminDialog = $id("admin-dialog");
    $id("open-admin").addEventListener("click", function () {
      if (!adminDialog.open) adminDialog.showModal();
    });
    $id("close-admin").addEventListener("click", function () { adminDialog.close(); });
    const loginForm = $id("admin-login-form");
    const settingsForm = $id("admin-settings-form");
    const adminMessage = $id("admin-message");

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
        $id("music-beat-lead-ms").value = data.music_beat_lead_ms || 0;
        $id("music-beat-lead-value").textContent = (data.music_beat_lead_ms || 0) + " ms";
        $id("music-animation").value = data.music_animation || "center_pulse";
        window.MusicPreview.configurePatternControls(
          "admin", $id("music-animation").value, data.music_band_colors,
        );
        $id("music-sensitivity").value = data.music_sensitivity || 1;
        $id("music-sound-profile").value = data.music_sound_profile || "small_speakers";
        $id("music-glitter-brightness").value = data.music_glitter_brightness == null ? 255 : data.music_glitter_brightness;
        $id("music-glitter-brightness-value").textContent = $id("music-glitter-brightness").value;
        $id("christmas-glitter-control").hidden = $id("music-animation").value !== "christmas_glitter";
        $id("music-primary-color").value = data.music_primary_color || "#00e5ff";
        $id("music-accent-color").value = data.music_accent_color || "#ff2ea6";
        window.MusicPreview.updateColors();
        ["red", "green", "blue"].forEach(function (channel) {
          const value = data["led_color_" + channel] == null ? 100 : data["led_color_" + channel];
          $id("led-color-" + channel).value = value;
          $id("led-color-" + channel + "-value").textContent = value + "%";
        });
        $id("led-brightness").value = data.led_brightness == null ? 40 : data.led_brightness;
        $id("led-brightness-value").textContent = $id("led-brightness").value;
        App.previewInvertOrder = data.preview_invert_order === true;
        $id("preview-invert-order").checked = App.previewInvertOrder;
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
          music_sound_profile: $id("music-sound-profile").value,
          music_glitter_brightness: Number($id("music-glitter-brightness").value),
          music_beat_lead_ms: Number($id("music-beat-lead-ms").value),
          music_primary_color: $id("music-primary-color").value,
          music_accent_color: $id("music-accent-color").value,
          music_band_colors: window.MusicPreview.getBandColors("admin"),
          led_color_red: Number($id("led-color-red").value),
          led_color_green: Number($id("led-color-green").value),
          led_color_blue: Number($id("led-color-blue").value),
          led_brightness: Number($id("led-brightness").value),
          preview_invert_order: $id("preview-invert-order").checked,
        }),
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.message || "Could not save settings.");
          return body;
        });
      }).then(function (body) {
        showAdminMessage("Saved. " + body.hidden_start + " hidden at start, " +
          body.hidden_end + " hidden at end; microphone handoff " + body.mic_handoff_seconds +
          " seconds; " + window.MusicPreview.patternLabel(body.music_animation) + " at " +
          Number(body.music_sensitivity).toFixed(2) + "× sensitivity; speaker profile " +
          $id("music-sound-profile").selectedOptions[0].textContent + "; glitter burst " +
          body.music_glitter_brightness + "/255; colors " +
          body.music_primary_color + " / " + body.music_accent_color + "; LED balance R/G/B " +
          body.led_color_red + "% / " + body.led_color_green + "% / " + body.led_color_blue + "%. ");
        App.previewInvertOrder = body.preview_invert_order === true;
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
    $id("music-glitter-brightness").addEventListener("input", function () {
      $id("music-glitter-brightness-value").textContent = this.value;
    });
    ["red", "green", "blue"].forEach(function (channel) {
      $id("led-color-" + channel).addEventListener("input", function () {
        $id("led-color-" + channel + "-value").textContent = this.value + "%";
      });
    });
    $id("led-brightness").addEventListener("input", function () {
      $id("led-brightness-value").textContent = this.value;
    });
    ["music-primary-color", "music-accent-color"].forEach(function (id) {
      $id(id).addEventListener("input", window.MusicPreview.updateColors);
      $id(id).addEventListener("change", window.MusicPreview.updateColors);
    });
    $id("music-animation").addEventListener("change", function () {
      $id("christmas-glitter-control").hidden = this.value !== "christmas_glitter";
      window.MusicPreview.configurePatternControls(
        "admin", this.value, window.MusicPreview.getBandColors("admin"),
      );
    });

    $id("music-beat-lead-ms").addEventListener("input", function () {
      $id("music-beat-lead-value").textContent = this.value + " ms";
    });

    Array.prototype.forEach.call(document.querySelectorAll('#admin-settings-form input[type="range"]'), function (slider) {
      slider.addEventListener("dblclick", function (event) {
        event.preventDefault();
        this.value = this.defaultValue;
        this.dispatchEvent(new Event("input", { bubbles: true }));
        this.dispatchEvent(new Event("change", { bubbles: true }));
      });
      const row = document.createElement("div");
      row.className = "range-input-row";
      slider.parentNode.insertBefore(row, slider);
      row.appendChild(slider);

      const reset = document.createElement("button");
      const label = slider.id && document.querySelector('label[for="' + slider.id + '"]');
      reset.type = "button";
      reset.className = "range-reset";
      reset.setAttribute("aria-label", "Reset " + (label ? label.textContent.trim() : "slider") + " to default");
      reset.title = "Reset to default";
      reset.textContent = "↺";
      reset.addEventListener("click", function () {
        slider.value = slider.defaultValue;
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        slider.dispatchEvent(new Event("change", { bubbles: true }));
      });
      row.appendChild(reset);
    });

    loadAdminSettings();
  }
  window.AdminSettings = { init: init };
})();
