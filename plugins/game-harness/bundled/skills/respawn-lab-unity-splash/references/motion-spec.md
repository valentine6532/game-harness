# Approved Respawn Lab logo intro

The bundled `assets/respawn-lab-wordmark.png` is the exact approved black-on-transparent wordmark. It is 2172 × 724 RGBA. The visible wordmark occupies approximately x=117–2059 and y=239–459. For a dark intro, render the same alpha silhouette in white; do not replace it with a font or redraw it.

- Background: `#111315`, full screen.
- Logo: white, horizontally and vertically centered. Preserve the wordmark's visible aspect ratio of about 8.8:1 and leave comfortable side margins on narrow screens.
- At 0.20 s, `RESPAWN` begins a short fade in; it is fully visible at about 0.75 s.
- `L`, `A`, and `B` arrive individually in that order. Their starts are 0.78 s, 0.98 s, and 1.18 s. Each settles over about 0.65 s with a small upward motion of about 5 display pixels and a fade. Do not expose faint glyph strokes well below the baseline or thin crop lines before a letter appears.
- Hold the completed logo until about 3.2 s. Fade it out over about 0.38 s. Begin the game/title transition at about 3.5 s and finish around 4.15 s.
- Play once on startup. Replaying belongs only to a preview or a user-triggered action.

The source bitmap is wider than its visible content and has transparent padding. When making letter elements, crop based on the actual alpha bounds and inspect the result at the target UI scale. The original web preview achieved the sequence with CSS; the Unity implementation should reproduce the appearance using native assets and animation.
