/* Header button that opens a temporary Bluetooth pairing window, and the admin panel button that
   forgets every pairing. Admin only: the header button is shown after admin login (see the
   "admin-state" event) and the server enforces the same rule for both. */
(function () {
  "use strict";
  const button = document.getElementById("bluetooth-pair");
  const adminMessage = document.getElementById("admin-message");
  let timer = null;

  function announce(message) {
    if (adminMessage) adminMessage.textContent = message;
    button.title = message;
  }

  function finish() {
    button.classList.remove("working");
    button.disabled = false;
  }

  document.addEventListener("admin-state", function (event) {
    button.hidden = !event.detail.isAdmin;
  });

  button.addEventListener("click", function () {
    button.disabled = true;
    fetch("/api/admin/bluetooth/discoverable", { method: "POST" }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.message || "Bluetooth pairing failed.");
        return body;
      });
    }).then(function (body) {
      const kicked = body.kicked.length ? " Disconnected " + body.kicked.join(", ") + "." : "";
      announce("Pi is discoverable for " + body.seconds + " seconds." + kicked);
      button.classList.add("working");
      clearTimeout(timer);
      timer = setTimeout(function () {
        finish();
        button.title = "Bluetooth pairing";
      }, body.seconds * 1000);
      button.disabled = false;
    }).catch(function (error) {
      finish();
      announce(error.message);
      window.alert(error.message);
    });
  });

  const resetButton = document.getElementById("bluetooth-reset");
  resetButton.addEventListener("click", function () {
    if (!window.confirm("Forget all Bluetooth devices? Phones must pair again.")) return;
    resetButton.disabled = true;
    fetch("/api/admin/bluetooth/reset", { method: "POST" }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.message || "Bluetooth reset failed.");
        return body;
      });
    }).then(function (body) {
      announce(body.forgotten.length
        ? "Forgot " + body.forgotten.join(", ") + ". Forget the Pi on the phone too, then pair again."
        : "No Bluetooth devices were paired.");
    }).catch(function (error) {
      announce(error.message);
    }).then(function () {
      resetButton.disabled = false;
    });
  });
})();
