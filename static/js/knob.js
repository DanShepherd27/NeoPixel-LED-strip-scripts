/* Rotary knobs: turns <input type="range" data-knob> into a compact knob that keeps the
   input as the source of truth (other scripts keep reading .value and listening to
   input/change events).

   Interaction (researched pattern for touch knobs): drag up or right to increase and
   down or left to decrease (a straight drag is more reliable on a phone than tracing a
   circle); shift or a slow drag is not needed because a full sweep is ~200 px; double-tap
   or double-click resets to the default; arrow keys, Page Up/Down, Home/End and the
   mouse wheel work too, and the control is a real ARIA slider with a visible value. */
(function () {
  "use strict";
  const SWEEP_PIXELS = 200;      // one full range of drag
  const DOUBLE_TAP_MS = 350;
  const START_ANGLE = -135;      // degrees; the arc spans 270 degrees
  const ARC_SPAN = 270;
  const valueDescriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");

  function polar(angle, radius) {
    const radians = (angle - 90) * Math.PI / 180;
    return [32 + radius * Math.cos(radians), 32 + radius * Math.sin(radians)];
  }

  function arc(from, to) {
    const [x1, y1] = polar(from, 26);
    const [x2, y2] = polar(to, 26);
    return "M" + x1.toFixed(2) + " " + y1.toFixed(2) + " A26 26 0 " + (to - from > 180 ? 1 : 0) +
      " 1 " + x2.toFixed(2) + " " + y2.toFixed(2);
  }

  function upgrade(input) {
    const min = Number(input.min || 0), max = Number(input.max || 100);
    const step = Number(input.step) || 1;
    const label = input.id && document.querySelector('label[for="' + input.id + '"]');
    const output = label && label.querySelector("output");
    let name = input.getAttribute("aria-label") || "";
    if (label) {
      const clone = label.cloneNode(true);
      Array.prototype.forEach.call(clone.querySelectorAll("output"), function (node) { node.remove(); });
      name = clone.textContent.trim() || name;
      label.hidden = true;
    }

    const cell = document.createElement("div");
    cell.className = "knob-cell";
    cell.innerHTML =
      '<div class="knob" role="slider" tabindex="0">' +
      '<svg viewBox="0 0 64 64" aria-hidden="true"><path class="knob-track"/><path class="knob-fill"/>' +
      '<circle class="knob-dot" r="3.2"/></svg><span class="knob-value"></span></div>' +
      '<span class="knob-label"></span>';
    const knob = cell.querySelector(".knob");
    cell.querySelector(".knob-label").textContent = name;
    knob.setAttribute("aria-label", name);
    knob.setAttribute("aria-valuemin", min);
    knob.setAttribute("aria-valuemax", max);
    knob.title = name;
    cell.querySelector(".knob-track").setAttribute("d", arc(START_ANGLE, START_ANGLE + ARC_SPAN));
    input.parentNode.insertBefore(cell, input);
    input.hidden = true;

    function current() { return Number(valueDescriptor.get.call(input)); }

    function refresh() {
      const value = current();
      const fraction = max === min ? 0 : (value - min) / (max - min);
      const end = START_ANGLE + ARC_SPAN * fraction;
      cell.querySelector(".knob-fill").setAttribute("d", fraction <= 0 ? "" : arc(START_ANGLE, Math.max(end, START_ANGLE + 0.5)));
      const [x, y] = polar(end, 26);
      const dot = cell.querySelector(".knob-dot");
      dot.setAttribute("cx", x.toFixed(2));
      dot.setAttribute("cy", y.toFixed(2));
      const text = output && output.textContent.trim() ? output.textContent.trim() : String(value);
      cell.querySelector(".knob-value").textContent = text;
      knob.setAttribute("aria-valuenow", value);
      knob.setAttribute("aria-valuetext", text);
    }

    // Scripts that assign input.value programmatically (loading saved settings) update the knob too.
    Object.defineProperty(input, "value", {
      get: function () { return valueDescriptor.get.call(this); },
      set: function (next) { valueDescriptor.set.call(this, next); refresh(); },
    });

    function commit(next) {
      const stepped = Math.round((next - min) / step) * step + min;
      const clamped = Math.max(min, Math.min(max, Number(stepped.toFixed(6))));
      if (clamped === current()) return;
      valueDescriptor.set.call(input, clamped);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      refresh();
    }

    function reset() { commit(Number(input.defaultValue)); }

    let drag = null, lastTap = 0;
    knob.addEventListener("pointerdown", function (event) {
      knob.setPointerCapture(event.pointerId);
      drag = { x: event.clientX, y: event.clientY, value: current(), moved: false };
      knob.classList.add("active");
    });
    knob.addEventListener("pointermove", function (event) {
      if (!drag) return;
      const travel = (event.clientX - drag.x) - (event.clientY - drag.y);
      if (Math.abs(travel) > 3) drag.moved = true;
      commit(drag.value + travel / SWEEP_PIXELS * (max - min));
    });
    function release(event) {
      if (!drag) return;
      const wasTap = !drag.moved;
      drag = null;
      knob.classList.remove("active");
      if (wasTap && event.type === "pointerup") {
        const now = Date.now();
        if (now - lastTap < DOUBLE_TAP_MS) { reset(); lastTap = 0; } else { lastTap = now; }
      }
    }
    knob.addEventListener("pointerup", release);
    knob.addEventListener("pointercancel", release);
    knob.addEventListener("dblclick", function (event) { event.preventDefault(); });
    knob.addEventListener("keydown", function (event) {
      const keys = { ArrowUp: step, ArrowRight: step, ArrowDown: -step, ArrowLeft: -step,
                     PageUp: (max - min) / 10, PageDown: -(max - min) / 10 };
      if (event.key in keys) commit(current() + keys[event.key]);
      else if (event.key === "Home") commit(min);
      else if (event.key === "End") commit(max);
      else if (event.key === "Backspace" || event.key === "Delete") reset();
      else return;
      event.preventDefault();
    });
    knob.addEventListener("wheel", function (event) {
      if (document.activeElement !== knob) return;
      commit(current() + (event.deltaY < 0 ? step : -step));
      event.preventDefault();
    }, { passive: false });
    if (output) new MutationObserver(refresh).observe(output, { childList: true, characterData: true, subtree: true });
    refresh();
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll('input[type="range"][data-knob]'), upgrade);
  });
  window.Knob = { upgrade: upgrade };
})();
