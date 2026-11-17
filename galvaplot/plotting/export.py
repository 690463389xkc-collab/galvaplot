"""Export plotted data and per-cycle tables to Excel (for Origin, further analysis, SI)."""
from __future__ import annotations

import re

import numpy as np

CYCLE_COLS = [("cycle", "Cycle"), ("chg_mAh", "Charge capacity (mAh)"), ("dchg_mAh", "Discharge capacity (mAh)"),
              ("chg_mWh", "Charge energy (mWh)"), ("dchg_mWh", "Discharge energy (mWh)"),
              ("CE", "Coulombic efficiency (%)"), ("EE", "Energy efficiency (%)"),
              ("Vavg_chg", "Average charge voltage (V)"), ("Vavg_dchg", "Average discharge voltage (V)"),
              ("dV", "ΔV = Vchg − Vdchg (V)"), ("complete", "Complete cycle")]


def _sheet_name(s, used):
    s = re.sub(r"[\[\]:*?/\\$]", "_", s).strip() or "Sheet"
    s = s[:28]
    base, k = s, 2
    while s.lower() in used:
        s = f"{base[:26]}_{k}"
        k += 1
    used.add(s.lower())
    return s


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if not np.isfinite(f) else f


def export_xlsx(path, result, series, opts):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(write_only=False)
    wb.remove(wb.active)
    used = set()
    bold = Font(bold=True)
    for k, p in enumerate(result.panels):
        title = p.get("title") or f"Panel {k + 1}"
        ws = wb.create_sheet(_sheet_name(f"{'abcdefghijkl'[k]} {title}" if len(result.panels) > 1 else title, used))
        col = 1
        for name, x, y in p["curves"]:
            ws.cell(row=1, column=col, value=name).font = bold
            ws.cell(row=2, column=col, value=re.sub(r"\$|\\mathrm|[{}]", "", p["xlabel"]))
            ws.cell(row=2, column=col + 1, value=re.sub(r"\$|\\mathrm|[{}]", "", p["ylabel"]))
            for i, (a, b) in enumerate(zip(x, y)):
                ws.cell(row=3 + i, column=col, value=_clean(a))
                ws.cell(row=3 + i, column=col + 1, value=_clean(b))
            col += 3
    for s in series:
        ws = wb.create_sheet(_sheet_name("Cycles - " + s.label, used))
        ws.append([h for _, h in CYCLE_COLS])
        for c in ws[1]:
            c.font = bold
        for r in s.table(opts.get("ce_mode", "dchg/chg")):
            ws.append([_clean(r.get(k)) for k, _ in CYCLE_COLS])
    info = wb.create_sheet(_sheet_name("Files", used))
    info.append(["Name", "File", "Source", "Points", "Active mass (mg)", "Warnings"])
    for c in info[1]:
        c.font = bold
    for s in series:
        info.append([s.label, s.cell.path, s.cell.source, s.cell.n_points, s.mass_mg,
                     "; ".join(s.cell.warnings)])
    wb.save(path)
