# Changelog

All notable changes to DeckyLS, newest first.

## [Unreleased]

### Added

- **DeckyLS updates:** a new **About** page (last row of the panel) shows the version, author, license and
  credits for lsfg-vk and Lossless Scaling, and at the bottom **Check for updates**. A newer DeckyLS release can be
  downloaded to your Downloads folder (checked against GitHub's size and SHA-256 first) and installed from Decky
  settings → Developer → Install plugin from ZIP. DeckyLS never checks on its own.

### Changed

- **Remove lsfg-vk** now asks in a dialog ("Remove lsfg-vk?") instead of needing a second press, and says when it
  is done. Installing, updating and removing lsfg-vk stay on the main page, in a new **lsfg-vk** section.
- **Panel:** if DeckyLS cannot start, the menu says "DeckyLS unavailable" with a **Try again** button, and DeckyLS
  can still be updated from there. If the panel loses contact for a moment, the last values stay with a
  "Last read … ago · Retrying…" note.
- **Panel:** a change that cannot be saved now also shows a notification, besides the message in the panel.
  Colors follow the other plugins.

### Fixed

- **Panel:** when DeckyLS cannot read its state, the menu shows why instead of a loading spinner that never ends,
  and keeps trying.
- **Remove lsfg-vk:** a file that cannot be deleted is reported in the panel and stays on DeckyLS's list, so
  pressing the button again finishes the job.
- **Install lsfg-vk:** an install cut short (full disk, plugin restarted) no longer forgets the files it already
  wrote; they can be removed from the panel or the install finished.
- **Error messages:** the panel no longer shows full file paths (which contain your user name); the full error
  is in the Decky log.
- **Panel:** a change that cannot reach DeckyLS at all (for example while the plugin restarts) now says so in a
  notification instead of quietly going back to the saved value.

### Changed

- **Panel:** with the menu open, the game library is read again only when a game or shortcut is added or removed,
  not every 5 seconds.

## [0.5.5] - 2026-10-26

### Fixed

- When a change cannot be saved, the panel no longer keeps showing it as if it were: it goes back to the
  saved value and shows why.
- A game name with a character TOML does not allow as-is (DEL) is written escaped instead of failing the
  save; any other text that cannot be written is reported in the panel, and nothing is left half-written.

## [0.5.4] - 2026-10-26

### Fixed

- With the menu open, DeckyLS no longer fills Decky's log: it read every installed plugin's manifest every
  5 seconds (Decky logs each file opened in its plugin folder in developer mode). It now looks again only
  when a plugin is added or removed.
- Reopening the menu right after closing it could show the loading spinner for up to 5 seconds.

### Changed

- The system journal is read only for a running game set to 2× or more; games without frame generation
  cost nothing while the menu is open.

## [0.5.3] - 2026-10-26

### Fixed

- A **Flow scale** change made just before closing the menu was lost; it is now saved when the menu closes.
- Right after a change, the panel could show the previous value again for up to 5 seconds.

### Changed

- The panel is lighter while it is open: lsfg-vk's health check runs again only when lsfg-vk changes, and
  the system journal is read only until lsfg-vk has joined the running game, not every 5 seconds for the
  whole session. A slow refresh is no longer stacked with the next one.

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
