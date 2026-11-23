# UI roadmap

## Done in the first pass (quick wins)

- Icon system (`static/js/ui-icons.js`): inline SVG, offline. Buttons whose text matches a
  known label become icon buttons automatically, including text set later by other scripts;
  the old text moves to `aria-label` and the tooltip. Unknown labels stay as text.
- Rotary knobs (`static/js/knob.js`) for brightness, color balance, sensitivity, beat sync
  and glitter. The slider stays as the source of truth. Drag up/right to increase,
  double-tap resets, arrow keys / Page keys / wheel work, and it is an ARIA slider.
- Compact layout: icon button rows, icon status line, icon toggles for audio output, and
  help paragraphs turned into (i) buttons next to their label (`static/js/ui-compact.js`).

## Research notes (sources: web search, not all authoritative)

- Touch knobs: circular drag is the familiar model, but straight vertical drag is more
  reliable on phones; GarageBand offers both ("automatic"). Show the value, support keyboard
  and a reset gesture. Gesture-only controls are hard for some users (WCAG 2.5.1 asks for a
  single-pointer alternative), so keep the slider/keyboard path.
- Icon-only buttons: put the accessible name on the button, hide decorative icons, give a
  44x44 px hit area (WCAG 2.2 AA minimum is 24 px), and add a visible label when an icon is
  ambiguous or unfamiliar. Tooltips help on desktop only.

## Verified in a phone-size preview (mock server)

Join, ready/unready, leave, sound-reactive start/stop, song start/pause/resume/seek/jump,
admin login, all eight knobs (keyboard, drag, double-tap reset, saved settings), the
latency measure button and its error path, MP3 upload, rebuild and remove. Not verified on
a real phone, with real touch drags, or with the Pi hardware; the game controller screens
(tutorial, countdown, game, results) were not exercised.

## Icon labels

Icons stand alone when universal (play, pause, stop, skip, home, close, save, lock, trash,
next). Ambiguous ones carry a short label: Join, Arcade, Sound, My mic, Ready/Not ready,
Start, Demo, Rematch, Add, Measure, Rebuild.

## Bigger changes (roadmap, not started)

1. Icon labels for ambiguous actions (measure latency, rebuild show): short label on first
   use, or a coach mark.
2. Knobs: circular-drag option, haptic tick on a vibrating phone, fine-adjust modifier.
   Keep sliders (or steppers with +/-) for exact values such as song latency and seek.
3. Separate "Sound-reactive" and "Song show" into tabs or a bottom navigation bar; move the
   frequency filter and EQ out of the song card.
4. Admin as a bottom sheet instead of a modal dialog; search across settings.
5. Seek bar showing the song's sections (and a waveform) from the show file markers.
6. Live LED strip emulator as a persistent mini-view on every screen.
7. Design tokens (color, spacing, radius) in one place, light theme, reduced-motion and
   high-contrast modes.
8. Accessibility audit with a screen reader; larger touch targets in the game controllers;
   icons for controller buttons.
9. Replace the text-to-icon dictionary with explicit `data-icon` attributes everywhere once
   the UI stops changing.
10. Offline-friendly PWA install (add to home screen).
