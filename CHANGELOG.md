# Changelog

All notable changes to DeckyLS, newest first.

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
