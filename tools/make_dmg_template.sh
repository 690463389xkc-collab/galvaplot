#!/usr/bin/env bash
# One-off, on a Mac (needs Finder): build assets/dmg/template.dmg, an almost empty
# "GalvaPlot" volume whose Finder window shows the background picture with the
# first-launch instructions, a placeholder GalvaPlot.app on the left and the Applications
# shortcut on the right. tools/make_dmg.sh copies the real app into a copy of this image,
# so CI never has to script Finder. Re-run after changing tools/make_dmg_art.py:
#   python tools/make_dmg_art.py && bash tools/make_dmg_template.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
art="$(dirname "$here")/assets/dmg"
tiffutil -cathidpicheck "$art/background.png" "$art/background@2x.png" -out "$art/background.tiff" >/dev/null

work="$(mktemp -d)"
mnt=""
cleanup() { [ -n "$mnt" ] && hdiutil detach "$mnt" -quiet 2>/dev/null || true; rm -rf "$work"; }
trap cleanup EXIT

rw="$work/template_rw.dmg"
hdiutil create -size 400m -fs HFS+ -volname GalvaPlot -ov "$rw" >/dev/null   # room for the app (~120 MB)
mnt="$(hdiutil attach -readwrite -noverify -noautoopen "$rw" | awk -F'\t' '/Apple_HFS/ {print $NF}')"
echo "mounted at $mnt"
mkdir "$mnt/.background"
cp "$art/background.tiff" "$mnt/.background/background.tiff"
ln -s /Applications "$mnt/Applications"
mkdir "$mnt/GalvaPlot.app"        # placeholder: Finder stores icon positions by file name

osascript - "$mnt" <<'APPLESCRIPT'
on run argv
    set mnt to POSIX file (item 1 of argv) as alias
    tell application "Finder"
        set d to item mnt
        open d
        set w to container window of d
        set current view of w to icon view
        set toolbar visible of w to false
        set statusbar visible of w to false
        set the bounds of w to {200, 120, 840, 628}
        set opts to icon view options of w
        set arrangement of opts to not arranged
        set icon size of opts to 112
        set text size of opts to 13
        set background picture of opts to file ".background:background.tiff" of d
        set position of item "GalvaPlot.app" of d to {160, 140}
        set position of item "Applications" of d to {480, 140}
        close w
        open d
        update d without registering applications
        delay 2
        close container window of d
    end tell
end run
APPLESCRIPT

sync
sleep 2
[ -f "$mnt/.DS_Store" ] || { echo "Finder did not write .DS_Store" >&2; exit 1; }
rm -rf "$mnt/.fseventsd" "$mnt/.Trashes" 2>/dev/null || true
hdiutil detach "$mnt" -quiet
mnt=""
hdiutil convert "$rw" -format UDZO -imagekey zlib-level=9 -ov -o "$art/template.dmg" >/dev/null
echo "written: $art/template.dmg ($(du -h "$art/template.dmg" | cut -f1))"
