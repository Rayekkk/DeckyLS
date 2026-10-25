#!/bin/bash
# off_start.sh <appid> <name>: start a game whose profile is Off, then turn it on live; prints lsfg-vk's log.
set -u
appid=$1 name=$2 D=$(dirname "$0")
bash "$D/busy.sh" "$appid" || exit 1
stop() { bash "$D/stop_game.sh" "$appid"; sleep 3; }
call() { bash "$D/lscall.sh" set_profile "[\"$appid\"]" "\"$name\"" "{\"multiplier\": $1, \"flow_scale\": 1.0, \"performance_mode\": true, \"override_present_mode\": true, \"preserve_swapchain_image_count\": false}" "$2" >/dev/null; }
stop
call 1 0
DISPLAY=:0 nohup steam "steam://rungameid/$appid" >/dev/null 2>&1 &
sleep 40
echo "== at start (profile Off)"
journalctl --user --since "-45s" --no-pager -o cat | grep "(lsfg-vk)" | grep -E "Using|Disabled" | sort | uniq -c
since=$(date "+%F %T")
call 2 "$appid"
sleep 5
echo "== after turning it on"
journalctl --user --since "$since" --no-pager -o cat | grep "(lsfg-vk)"
stop
