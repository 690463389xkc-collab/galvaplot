#!/usr/bin/env bash
# Build a drag-to-install disk image for macOS.
#   bash tools/make_dmg.sh <path/to/GalvaPlot.app> <output.dmg>
# The image shows GalvaPlot.app next to a shortcut to /Applications.
set -euo pipefail

app="$1"
out="$2"
[ -d "$app" ] || { echo "not found: $app" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
ditto "$app" "$stage/$(basename "$app")"      # ditto keeps the symlinks inside Qt frameworks
ln -s /Applications "$stage/Applications"

rm -f "$out"
# hdiutil occasionally fails with "Resource busy" on CI machines: retry a few times
for attempt in 1 2 3 4; do
    if hdiutil create -volname "GalvaPlot" -srcfolder "$stage" -ov -fs HFS+ -format UDZO "$out"; then
        echo "written: $out"
        exit 0
    fi
    echo "hdiutil failed (attempt $attempt), retrying..." >&2
    sleep 5
done
exit 1
