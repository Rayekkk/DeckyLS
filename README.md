# DeckyLS

Lossless Scaling frame generation on SteamOS, for the game you are playing: open the Quick Access Menu, pick
**2×**, play. A [Decky Loader](https://decky.xyz) plugin built on the official
[lsfg-vk 2.0](https://lsfg-vk.dev) by PancakeTAS.

<img src="docs/screenshots/panel.png" alt="DeckyLS in the Quick Access Menu while Nine Sols runs at 3×" width="320">

- **No launch options, no environment variables.** lsfg-vk recognises the game by its Steam App ID, so nothing
  is added to your games and other launch-option tools keep working.
- **Changes apply while you play.** Turning frame generation off, changing the multiplier, the flow scale or
  performance mode reaches the running game within a second.
- **Tells you what is really happening:** whether lsfg-vk joined the game, lsfg-vk's own health check, a missing
  Lossless Scaling or the wrong Steam branch, and other plugins that also manage lsfg-vk.
- **Official lsfg-vk, unchanged.** It is downloaded from its author's site and checked against a pinned hash;
  removing it deletes exactly the files DeckyLS installed.

## Requirements

- SteamOS (or another Linux with Decky Loader) on an x86_64 handheld or PC.
- [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/) bought and installed from Steam,
  switched to the **lsfg-vk** branch: Lossless Scaling → Properties → Betas → `lsfg-vk`.
- A game that renders through Vulkan, which includes Proton games (DirectX via DXVK / VKD3D). OpenGL games are
  not supported by lsfg-vk.

## Install

1. Download `DeckyLS-<version>.zip` from the latest release.
2. Decky → Settings → Developer → **Install Plugin from ZIP**, choose the file.
3. Open DeckyLS in the Quick Access Menu and press **Install lsfg-vk 2.0.0**.

## Use

Start a game, open the Quick Access Menu → DeckyLS and choose **Frame generation: 2×** (or 3×, 4×). The first time
you turn it on for a game, restart the game: lsfg-vk joins a game when it starts. After that, every change applies
live. **Off** keeps the game's settings for next time.

With no game running, the panel lists the games you have set up so you can change or turn them off.

## How it works

DeckyLS writes one profile per game to lsfg-vk's own configuration file, `~/.config/lsfg-vk/conf.toml`
(`active_in = "<App ID>"`, plus the executable name for non-Steam games). lsfg-vk is a Vulkan layer that reads
this file when a game starts and reloads it when it changes. Profiles and settings that DeckyLS did not create are
kept, and the file you had before is saved once as `conf.toml.bak-deckyls`.

Updating or uninstalling the plugin leaves lsfg-vk and your settings in place; use **Remove lsfg-vk** in the panel
first for a full cleanup.

## Development

```bash
npm ci
npm run typecheck && npm run test:frontend && npm run build
py -3.11 -W error -m unittest discover -s tests -p "test_*.py"
npm run package
```

`tools/device/` has the scripts used to install and drive the plugin on a handheld over SSH.

## Licence

BSD 3-Clause, see [LICENSE](LICENSE) and [NOTICE](NOTICE). lsfg-vk (CC BY-NC-ND 4.0) and Lossless Scaling are not
part of this package. Not affiliated with PancakeTAS, THS or Valve.
