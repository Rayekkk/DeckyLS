#!/bin/bash
# busy.sh <appid>: fail when a game other than <appid> is running, so a test never starts a game over the user's.
other=$(pgrep -af "[r]eaper SteamLaunch" | grep -oE "AppId=[0-9]+" | grep -vx "AppId=$1" | sort -u)
[ -z "$other" ] && exit 0
echo "another game is running ($other); not testing over it" >&2
exit 1
