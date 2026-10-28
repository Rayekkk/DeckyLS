#!/bin/bash
# list_flow.sh <appid> <name>: the games-list flow. Switch the game On (1x) while it is closed, start it, choose 2x
# live, stop it, switch it Off again. Prints lsfg-vk's log and the panel's view of the game at each step.
set -u
appid=$1 name=$2 D=$(dirname "$0")
bash "$D/busy.sh" "$appid" || exit 1
stop() { bash "$D/stop_game.sh" "$appid"; sleep 3; }
s() { echo "{\"multiplier\": $1, \"flow_scale\": 1.0, \"performance_mode\": true, \"override_present_mode\": true, \"preserve_swapchain_image_count\": false}"; }
call() { bash "$D/lscall.sh" "$@" | python3 -c "import json,sys; v=json.loads(sys.stdin.read()); r=json.loads(v) if isinstance(v,str) else v; s=r['state']; g=s['game']; e=[x for x in s['games'] if x['appid']==$appid]; print(' error:', s['error'] or '-', '| list:', e and e[0]['settings'] and e[0]['settings']['multiplier'], '| running:', g and (g['settings'] and g['settings']['multiplier'], g['attached']))"; }
stop
echo "== switch On in the list"; call set_profile "[\"$appid\"]" "\"$name\"" "$(s 1)" 0 '""'
DISPLAY=:0 nohup steam "steam://rungameid/$appid" >/dev/null 2>&1 &
sleep 40
echo "== started"; journalctl --user --since "-45s" --no-pager -o cat | grep "(lsfg-vk)" | grep -E "Using|Disabled" | sort | uniq -c
call get_state "$appid" "\"$name\""
since=$(date "+%F %T")
echo "== 2x in the game"; call set_profile "[\"$appid\"]" "\"$name\"" "$(s 2)" "$appid" "\"$name\""
sleep 5; journalctl --user --since "$since" --no-pager -o cat | grep "(lsfg-vk)"
stop
echo "== switch Off in the list"; call remove_profile "[\"$appid\"]" 0 '""'
