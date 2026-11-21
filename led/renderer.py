"""The central LED renderer.

Exactly one :class:`Renderer` runs per process. It owns the hardware, drives
the frame loop at a fixed rate, and asks the currently active *scene* to fill
a :class:`~led.frame.Frame` each tick. Scenes are things like idle effects or
games — they only produce pixels, never call ``show()`` themselves.
"""

import threading
import time
import logging

from led.frame import Frame

log = logging.getLogger("led.renderer")


class Renderer(threading.Thread):
    def __init__(self, hardware, fps=40):
        super().__init__(name="renderer", daemon=True)
        self.hardware = hardware
        self.fps = fps
        self.frame = Frame(hardware.count)

        self._scene = None
        self._lock = threading.Lock()
        self._running = False

    # -- scene management ---------------------------------------------------
    def set_scene(self, scene):
        """Swap the active scene. ``scene`` must expose ``render(frame, dt)``."""
        with self._lock:
            self._scene = scene

    def _current_scene(self):
        with self._lock:
            return self._scene

    # -- main loop ----------------------------------------------------------
    def run(self):
        self.hardware.begin()
        self._running = True
        interval = 1.0 / self.fps
        last = time.monotonic()

        log.info("Renderer started at %d FPS (mock=%s)", self.fps,
                 self.hardware.mock)

        while self._running:
            now = time.monotonic()
            dt = now - last
            last = now

            self.frame.clear()

            scene = self._current_scene()
            if scene is not None:
                try:
                    scene.render(self.frame, dt)
                except Exception:
                    log.exception("Scene render failed")

            self.hardware.show_frame(self.frame)

            elapsed = time.monotonic() - now
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        log.info("Renderer stopped")
        self.hardware.clear()

    def stop(self):
        self._running = False
