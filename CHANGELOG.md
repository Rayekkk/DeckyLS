# Changelog

All notable changes to DeckyLS, newest first.

## [0.5.1] - 2026-10-25

### Fixed

- The FPS counter showed only while the Quick Access Menu was open. It is now a line in Steam's own
  performance overlay, the one thing gamescope reliably shows over games: at overlay levels 2 to 4 it reads,
  for example, **LSFG 3x - base 48 FPS** next to the FPS on screen, and updates twice a second. Without
  frame generation the overlay is exactly as Steam makes it; level 1 is never changed.
- To add the line, DeckyLS writes `~/.config/MangoHud/presets.conf`, and removes it when the counter is
  turned off. A presets file of your own is never touched; the counter then stays off and says why.

## [0.5.0] - 2026-10-25

### Added

- **All games → FPS counter**: the game's own frame rate and what you see with frame generation, for
  example **48 / 144 FPS**, in the top-left corner while you play. Without frame generation it shows the
  one rate. It reads the frame rate gamescope reports for the screen and shows a base rate only once
  lsfg-vk has really joined the game. It never takes touch or controller input.

## [0.4.0] - 2026-10-25

### Added

- Frame generation up to **8×** (was 4×).
- **Compatibility options** for the running game, folded away by default: **Force V-Sync** (on by
  default; frame generation needs it for even pacing) and **Keep the game's buffer count** (for games
  that crash with frame generation). They apply the next time the game starts.
- **All games → Half precision (FP16)**: on by default and faster on AMD graphics with the same
  image; turn it off only on an old NVIDIA GTX 10 card.

### Fixed

- A profile made by hand or by another tool that leaves a setting out now shows the value lsfg-vk
  really uses (for example performance mode off), not DeckyLS's choice for new games.

## [0.3.0] - 2026-10-25

### Changed

- **Games** is folded away until you press **Show games**, and each game has an **On / Off** switch
  instead of a multiplier. On makes lsfg-vk ready in the game (frame generation stays at 1×); once it
  runs, choose 2×, 3× or 4× at the top of the panel and it applies live. Off keeps lsfg-vk out of the
  game completely.

### Fixed

- Changing a game in the list no longer shows that game's name over the running game for a moment.
- A switch flipped while a slider was still saving is no longer lost.

## [0.2.0] - 2026-10-25

### Added

- **Games**: every installed game, in alphabetical order, with its own Off / 2× / 3× / 4× switch. Set a
  game up before you start it and frame generation runs from its first frame, no restart needed.
  Steam games on every drive and SD card are listed, and non-Steam games together with their
  executable, so lsfg-vk recognises them too.

## [0.1.0] - 2026-10-25

First version.

- Installs the official lsfg-vk 2.0.0 from builds.lsfg-vk.dev (hash-checked) and removes exactly what it installed.
- One menu for the game you are playing: frame generation Off / 2× / 3× / 4×, flow scale and performance mode.
  Changes apply in the running game within a second.
- No launch options and no environment variables: lsfg-vk finds the game by its Steam App ID (non-Steam games
  also by their executable).
- Shows whether lsfg-vk actually joined the game, lsfg-vk's own health check, a missing Lossless Scaling or a
  wrong Steam branch, and other installed plugins that also manage lsfg-vk.
- Keeps other profiles and settings in lsfg-vk's config file and backs the file up before the first change.
