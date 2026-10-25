#!/bin/bash
# lscall.sh <method> [json-args...]: call a DeckyLS backend method like the panel does.
m=$1; shift; args=$(IFS=,; echo "$*")
python3 -I ~/deckyls-test/cdp.py eval "window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit.connect(1, \"DeckyLS\").call(\"$m\"${args:+, $args}).then(r => JSON.stringify(r), e => \"ERR \" + e)"
