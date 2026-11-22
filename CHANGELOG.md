# Changelog

## 0.4.0 (2026-11-22)

- Voltage vs time for chosen cycles: a "圈数" field on the 电压–时间 tab (empty = whole test, as before). "时间起点" sets the time axis: each cycle from zero (cycles overlaid for comparison), joined from the first chosen cycle, or test time. New arrangement "每圈一个子图" (one panel per cycle, cells compared). A cycle includes its rest steps.
- LAND `.cex`: the active-material mass entered in LAND (file header, offset 0x1C, float32 in g; 0 = not entered) is read and fills the "质量 mg" column unless the user typed a value. Checked on 143 local files: 81 have a mass; in 75 of the 76 with charge/discharge steps, set current ÷ mass is exactly the test plan's 100 or 500 mA/g (apart from a few extra fixed 0.25 mA steps); in the remaining one the set current matches a different mass (probably edited after programming). The 62 files without a mass are mostly symmetric cells.

## 0.3.2 (2026-11-22)

- Fix (Windows in-app update): Setup was started while the app was still quitting; when Restart Manager could not close it, the silent Setup answered its own "could not close applications" question with Abort and rolled back, so the app closed without updating (seen in the CI drill, depending on timing). Setup now waits up to 15 s for GalvaPlot.exe to exit when run silently and force-closes it otherwise (`CloseApplications=force`); the app also passes `/FORCECLOSEAPPLICATIONS`. This also fixes updates started from 0.3.0 / 0.3.1, because the new Setup does the waiting.
- CI: the in-app update drills now install the package just built (`GALVAPLOT_UPDATE_FILE`, same code path as a real update), on Windows twice, and block the release if they fail; "Installation process succeeded" is matched case-sensitively (it used to match "Uninstallation process succeeded" after a rollback).

## 0.3.1 (2026-11-22)

- "保存图片…" (and "保存此子图…") can write EPS. Fonts are embedded as TrueType (Type 42, text stays editable), like in PDF.
- Fix: PDF (since 0.1.0) and EPS with Chinese text on macOS. The Chinese font there (PingFang) has CFF outlines, which cannot be embedded as TrueType: macOS Preview still showed the text, but Ghostscript (and likely Acrobat / Illustrator) showed missing glyphs, and EPS did not open at all. Such figures now embed their fonts as Type 3. Figures without Chinese text, and PDFs on Windows (Microsoft YaHei has TrueType outlines), keep Type 42.
- EPS uses Type 42 only for fonts that have glyph names; Windows Arial and Microsoft YaHei have none, and matplotlib's EPS output then showed no text at all in Ghostscript, so EPS on Windows embeds fonts as Type 3. Found by the Ghostscript test on the Windows CI machine (it stopped the first 0.3.1 build). A test draws the exported PDF/EPS with Ghostscript when available (CI: Windows).
- Windows in-app update: Setup writes a log (`%TEMP%\galvaplot_setup.log`); the CI update drill waits for the app process only.

## 0.3.0 (2026-11-22)

- In-app update: "立即更新" in the update dialog downloads the new package, checks it against the SHA-256 digest GitHub publishes for the release asset, then replaces the installed copy and reopens it. Updates installed this way carry no "downloaded from the internet" mark, so macOS / Windows do not ask for approval again (only the first install does). macOS: copies in a writable folder (also when macOS runs the app translocated); Windows: copies installed with the Setup program (silent update, `/RELAUNCH=1` reopens the app). The portable zip and source checkouts keep the download link.
- Fix: "更多设置" in the preview's right-click menu did nothing (it built the settings panel instead of opening the dialog); GUI regression test added.
- CI: after packaging, an installed copy updates itself to the newest published release on Windows and macOS (non-blocking check).

## 0.2.1 (2026-11-18)

- macOS disk image: the window now has a background with a drag-to-Applications arrow and the first-launch steps (press "Done", not "Move to Trash"; then System Settings → Privacy & Security → Open Anyway). The layout comes from a template image (`assets/dmg/template.dmg`, made once with Finder by `tools/make_dmg_template.sh`), so CI needs no Finder scripting; CI checks the layout files are in the image.
- README: the same steps with a picture.

## 0.2.0 (2026-11-18)

- New arrangement "所有圈+所有电池" for voltage profiles and dQ/dV: every selected cycle of every cell in one panel (colour = cell, line style = cycle; shades of the cell colour when there are more than 4 cycles).
- Right-click menu on the preview: copy one sub-plot's data as tab-separated text (pastes into Excel / Origin), copy or save one sub-plot on its own, show only / hide a sub-plot, plus the whole-figure actions.
- Neware `.ndax`: the active-material mass set in BTS (`Step.xml` → `Head_Info/SCQ`, in µg) is read and fills the "质量 mg" column unless the user typed a value; the file table's right-click menu can restore it.
- "检查更新" (check for updates) in the status bar: asks the GitHub Releases API for the latest version; automatic check at most once a day at start-up, can be switched off; nothing is downloaded or installed automatically.
- Invalid input in the mass column keeps the previous value instead of clearing it.

## 0.1.0 (2026-11-17)

First public version.

- Reads LAND `.cex` and Neware `.ndax` (BTS 8.x, ndc v17) raw files (reverse-engineered readers) and, experimentally, Excel/CSV/TXT exports.
- Four figure types: voltage profiles, cycling metrics, voltage–time, dQ/dV.
- Up to 10 files; editable curve names with `_{}` / `^{}` shortcuts; per-curve colour and line style.
- Capacity in mAh, mAh/g, mAh/cm² or % of a reference cycle; English or Chinese figure text.
- Footnote for test conditions; panel letters; copy to clipboard; PNG/SVG/PDF/TIFF; Excel data export; export-all.
- Last cycle that looks unfinished is left out of cycling plots by default (can be kept).
- Downloads: Windows installer (per-user, no admin rights), portable Windows zip, macOS disk image; CI installs each one and runs a self-test before publishing.
