#!/usr/bin/env bash
# Fetch only the files tools/extract.py reads from QuestieDB and Questie:
# a shallow, blobless, sparse clone downloads just these paths at the latest commit.
set -euo pipefail
DEST="${1:-vendor}"
mkdir -p "$DEST"

sparse_clone() {
    local url="$1" dir="$2"; shift 2
    rm -rf "$dir"
    git clone --quiet --depth 1 --filter=blob:none --no-checkout "$url" "$dir"
    git -C "$dir" sparse-checkout set --no-cone "$@"
    git -C "$dir" checkout --quiet
}

sparse_clone https://github.com/Questie/QuestieDB "$DEST/QuestieDB" \
    /src/config.lua \
    /src/meta/questMeta.lua /src/meta/npcMeta.lua /src/meta/objectMeta.lua \
    /src/corrections/enum/ \
    /src/corrections/Forever/ \
    /data/Forever/foreverQuestDB.lua /data/Forever/foreverNpcDB.lua /data/Forever/foreverObjectDB.lua \
    /support/Forever/Zones/areaIdToUiMapId.lua /support/Forever/Zones/subZoneToParentZone.lua

sparse_clone https://github.com/Questie/Questie "$DEST/Questie" \
    /Database/Corrections/QuestieQuestBlacklist.lua

for d in QuestieDB Questie; do
    echo "$d $(git -C "$DEST/$d" rev-parse --short HEAD): $(du -sh "$DEST/$d" | cut -f1) on disk"
done
