#!/bin/bash
# fps_flow.sh <appid> <name>: turn the FPS counter on, start the game at 3x, read what the counter gets and what the
# label in the Steam UI says, switch to 2x live and read again, then stop the game and put the user's config back.
set -u
appid=$1 name=$2 D=$(dirname "$0")
conf=~/.config/lsfg-vk/conf.toml backup=/tmp/deckyls-fps-backup.toml
cp "$conf" "$backup"
s() { echo "{\"multiplier\": $1, \"flow_scale\": 1.0, \"performance_mode\": true, \"override_present_mode\": true, \"preserve_swapchain_image_count\": false}"; }
bp=$(curl -s http://127.0.0.1:8080/json | python3 -c "import json,sys; print(next(t['title'] for t in json.load(sys.stdin) if 'Big Picture' in t['title']))")
label() { CDP_TARGET="$bp" python3 -I "$D/cdp.py" eval "[...document.querySelectorAll('div')].filter(e => e.style.pointerEvents === 'none' && / FPS\$/.test(e.textContent)).map(e => e.textContent + ' @' + e.getBoundingClientRect().left + ',' + e.getBoundingClientRect().top).join(' | ') || 'no label'"; }
bash "$D/stop_game.sh" "$appid"
bash "$D/lscall.sh" set_fps_counter true 0 '""' >/dev/null
bash "$D/lscall.sh" set_profile "[\"$appid\"]" "\"$name\"" "$(s 3)" 0 '""' >/dev/null
DISPLAY=:0 nohup steam "steam://rungameid/$appid" >/dev/null 2>&1 &
sleep 40
echo "== 3x  get_fps: $(bash "$D/lscall.sh" get_fps "$appid")  label: $(label)"
bash "$D/lscall.sh" set_profile "[\"$appid\"]" "\"$name\"" "$(s 2)" "$appid" "\"$name\"" >/dev/null
sleep 4
echo "== 2x  get_fps: $(bash "$D/lscall.sh" get_fps "$appid")  label: $(label)"
bash "$D/stop_game.sh" "$appid"
sleep 3
echo "== no game  label: $(label)"
cp "$backup" "$conf"
echo "config restored"
