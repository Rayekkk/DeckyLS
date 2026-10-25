#!/bin/bash
# compat_flow.sh <appid> <name>: start a game at 3x with "Keep the game's buffer count" on and FP16 off, check that
# lsfg-vk accepts the file and uses both, screenshot the panel with the compatibility options open, then put the
# user's config file back exactly as it was.
set -u
appid=$1 name=$2 D=$(dirname "$0")
bash "$D/busy.sh" "$appid" || exit 1
conf=~/.config/lsfg-vk/conf.toml backup=/tmp/deckyls-compat-backup.toml
cp "$conf" "$backup"
q() { CDP_TARGET=QuickAccess_uid2 python3 -I "$D/cdp.py" "$@"; }
bash "$D/stop_game.sh" "$appid"
bash "$D/lscall.sh" set_profile "[\"$appid\"]" "\"$name\"" '{"multiplier": 3, "flow_scale": 0.8, "performance_mode": true, "override_present_mode": true, "preserve_swapchain_image_count": true}' 0 '""' >/dev/null
bash "$D/lscall.sh" set_fp16 false 0 '""' >/dev/null
~/.local/bin/lsfg-vk-cli validate | sed -n 2p
DISPLAY=:0 nohup steam "steam://rungameid/$appid" >/dev/null 2>&1 &
sleep 40
journalctl --user --since "-45s" --no-pager -o cat | grep "(lsfg-vk)" | grep -E "Using|Multiplier|half precision" | sort | uniq -c
python3 -I "$D/cdp.py" eval "DFL.Navigation.OpenQuickAccessMenu(999), DeckyPluginLoader.deckyState.setActivePlugin(\"DeckyLS\"), 1" >/dev/null
sleep 3
q eval "(() => { const b=[...document.querySelectorAll(\"button, .DialogButton\")].find(e=>e.innerText.trim()===\"Compatibility options\"); b&&b.click(); return !!b; })()"
sleep 1
q shot /tmp/ls-compat-top.png 0 0 375 695 >/dev/null
q eval "(() => { const h=[...document.querySelectorAll(\"*\")].find(e=>e.childElementCount===0&&e.textContent.trim()===\"Status\"); h&&h.scrollIntoView({block:\"start\"}); return !!h; })()"
sleep 1
q shot /tmp/ls-compat.png 0 0 375 695 >/dev/null
python3 -I "$D/cdp.py" eval "DFL.Navigation.CloseSideMenus(), 1" >/dev/null
bash "$D/stop_game.sh" "$appid"
cp "$backup" "$conf"
echo "config restored"
