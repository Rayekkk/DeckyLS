# Changelog

All notable changes to DeckyLS, newest first.

## [0.5.2] - 2026-10-25

### Added

- When Lossless Scaling is missing, **Open in the Steam Store** takes you to its store page; when it is on the
  wrong branch, **Open Lossless Scaling in the library** takes you to its page, where Properties → Betas is.

### Fixed

- **Games** no longer lists Steam tools such as Ubisoft Connect Services (or Proton and Steam runtimes): only
  games, applications, demos and non-Steam shortcuts, as Steam itself classifies them.

## [0.5.1] - 2026-10-25

### Removed

- The **FPS counter** from 0.5.0. It showed only while the Quick Access Menu was open, and no way to show it
  reliably over games without changing Steam's own performance overlay was found. DeckyLS is back to what
  0.4.0 does; Steam's performance overlay shows the frame rate on screen, generated frames included.

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
