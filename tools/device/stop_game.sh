#!/bin/bash
# stop_game.sh <appid>: end every process of a Steam game (they all carry SteamAppId=<appid>), so Steam sees it exit.
appid=$1
pids=$(grep -lzx "SteamAppId=$appid" /proc/[0-9]*/environ 2>/dev/null | cut -d/ -f3 | grep -vx "$$")
[ -n "$pids" ] && kill $pids 2>/dev/null
for i in $(seq 1 15); do
  grep -qzx "SteamAppId=$appid" /proc/[0-9]*/environ 2>/dev/null || exit 0
  sleep 1
done
pids=$(grep -lzx "SteamAppId=$appid" /proc/[0-9]*/environ 2>/dev/null | cut -d/ -f3 | grep -vx "$$")
[ -n "$pids" ] && kill -9 $pids 2>/dev/null
sleep 2
