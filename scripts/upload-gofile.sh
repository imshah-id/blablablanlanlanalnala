#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# API flow: https://github.com/Sushrut1101/GoFile-Upload/blob/master/upload.sh
set -euo pipefail
[[ $# == 1 && -f $1 && -s $1 ]] || { echo "Usage: $0 FILE (nonempty regular file)" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
server=$(curl --fail --silent --show-error --connect-timeout 30 --max-time 60 \
    https://api.gofile.io/servers | jq -er 'select(.status == "ok") | .data.servers[0].name')
[[ $server =~ ^[a-zA-Z0-9-]+$ ]] || { echo "Invalid GoFile server response" >&2; exit 1; }
# Quote curl's multipart filename syntax as well as shell arguments.
file=${1//\\/\\\\}
file=${file//\"/\\\"}
link=$(curl --fail --show-error --progress-bar --connect-timeout 30 --max-time 1800 \
    --form "file=@\"$file\"" "https://$server.gofile.io/uploadFile" \
    | jq -er 'select(.status == "ok") | .data.downloadPage')
[[ $link =~ ^https://gofile\.io/d/[a-zA-Z0-9]+$ ]] || { echo "Invalid GoFile download link" >&2; exit 1; }
printf '%s\n' "$link"
