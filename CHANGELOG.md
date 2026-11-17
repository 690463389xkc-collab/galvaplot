# Changelog

## 0.1.0 (2026-11-17)

First public version.

- Reads LAND `.cex` and Neware `.ndax` (BTS 8.x, ndc v17) raw files (reverse-engineered readers) and, experimentally, Excel/CSV/TXT exports.
- Four figure types: voltage profiles, cycling metrics, voltage–time, dQ/dV.
- Up to 10 files; editable curve names with `_{}` / `^{}` shortcuts; per-curve colour and line style.
- Capacity in mAh, mAh/g, mAh/cm² or % of a reference cycle; English or Chinese figure text.
- Footnote for test conditions; panel letters; copy to clipboard; PNG/SVG/PDF/TIFF; Excel data export; export-all.
- Last cycle that looks unfinished is left out of cycling plots by default (can be kept).
- Downloads: Windows installer (per-user, no admin rights), portable Windows zip, macOS disk image; CI installs each one and runs a self-test before publishing.
