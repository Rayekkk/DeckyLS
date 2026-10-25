# Changelog

All notable changes to DeckyLS, newest first.

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
