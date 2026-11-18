#!/usr/bin/env bash
# Build a drag-to-install disk image for macOS.
#   bash tools/make_dmg.sh <path/to/GalvaPlot.app> <output.dmg>
# The image shows GalvaPlot.app next to a shortcut to /Applications, on a background that
# explains the first-launch security prompt. The window layout comes from
# assets/dmg/template.dmg (made once with tools/make_dmg_template.sh, which needs Finder);
# here the real app is only copied into a copy of that image, so no Finder scripting is
# needed (works on CI). Without the template a plain image is made.
set -euo pipefail

app="$1"
out="$2"
[ -d "$app" ] || { echo "not found: $app" >&2; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
template="$(dirname "$here")/assets/dmg/template.dmg"

work="$(mktemp -d)"
mnt=""
cleanup() { [ -n "$mnt" ] && hdiutil detach "$mnt" -quiet 2>/dev/null || true; rm -rf "$work"; }
trap cleanup EXIT
rm -f "$out"

# hdiutil occasionally fails with "Resource busy" on CI machines: retry a few times
retry() {
    for attempt in 1 2 3 4; do
        "$@" && return 0
        echo "hdiutil failed (attempt $attempt), retrying..." >&2
        sleep 5
    done
    return 1
}

if [ -f "$template" ]; then
    rw="$work/rw.dmg"
    retry hdiutil convert "$template" -format UDRW -o "$rw" >/dev/null
    # -nobrowse: Finder must not open (and rewrite) the window settings
    mnt="$(retry hdiutil attach -readwrite -noverify -noautoopen -nobrowse "$rw" | awk -F'\t' '/Apple_HFS/ {print $NF}')"
    [ -d "$mnt/.background" ] && [ -f "$mnt/.DS_Store" ] || { echo "template has no layout" >&2; exit 1; }
    rm -rf "$mnt/GalvaPlot.app"
    ditto "$app" "$mnt/GalvaPlot.app"      # ditto keeps the symlinks inside Qt frameworks
    rm -rf "$mnt/.fseventsd" 2>/dev/null || true
    sync
    retry hdiutil detach "$mnt" -quiet
    mnt=""
    retry hdiutil convert "$rw" -format UDZO -imagekey zlib-level=9 -o "$out" >/dev/null
else
    echo "warning: $template not found, making a plain image" >&2
    stage="$work/stage"
    mkdir "$stage"
    ditto "$app" "$stage/$(basename "$app")"
    ln -s /Applications "$stage/Applications"
    retry hdiutil create -volname "GalvaPlot" -srcfolder "$stage" -ov -fs HFS+ -format UDZO "$out"
fi
echo "written: $out"
