#!/bin/bash
# fps_flow.sh <appid> <name>: turn the FPS counter on, start the game at 3x, read the counter's label and its overlay
# window, switch to 2x live and read again, then stop the game and put the user's config back.
set -u
appid=$1 name=$2 D=$(dirname "$0")
bash "$D/busy.sh" "$appid" || exit 1
conf=~/.config/lsfg-vk/conf.toml backup=/tmp/deckyls-fps-backup.toml
cp "$conf" "$backup"
s() { echo "{\"multiplier\": $1, \"flow_scale\": 1.0, \"performance_mode\": true, \"override_present_mode\": true, \"preserve_swapchain_image_count\": false}"; }
label() {
  local w state text
  w=$(DISPLAY=:0 xwininfo -root -tree | grep '"DeckyLS FPS counter"' | grep -oE "0x[0-9a-f]+" | head -1)
  state=$([ -n "$w" ] && DISPLAY=:0 xwininfo -id "$w" | grep -o "Map State: [A-Za-z]*" || echo "no window")
  text=$(bash "$D/lscall.sh" get_state 0 '""' | python3 -c "import json,sys; v=json.loads(sys.stdin.read()); s=json.loads(v) if isinstance(v,str) else v; print(s['fps_label'] or '(empty)')")
  echo "$text, window: $state"
}
bash "$D/stop_game.sh" "$appid"
bash "$D/lscall.sh" set_fps_counter true 0 '""' >/dev/null
bash "$D/lscall.sh" set_profile "[\"$appid\"]" "\"$name\"" "$(s 3)" 0 '""' >/dev/null
DISPLAY=:0 nohup steam "steam://rungameid/$appid" >/dev/null 2>&1 &
sleep 40
echo "== 3x  $(label)"
bash "$D/lscall.sh" set_profile "[\"$appid\"]" "\"$name\"" "$(s 2)" "$appid" "\"$name\"" >/dev/null
sleep 4
echo "== 2x  $(label)"
bash "$D/stop_game.sh" "$appid"
sleep 3
echo "== no game  label: $(label)"
cp "$backup" "$conf"
echo "config restored"
