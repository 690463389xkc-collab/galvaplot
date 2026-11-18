# Changelog

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
