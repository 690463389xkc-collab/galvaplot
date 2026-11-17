"""File readers. ``load_file`` picks the reader from the file extension."""
from __future__ import annotations

import os

SUPPORTED_EXT = (".cex", ".ndax", ".xlsx", ".xlsm", ".xls", ".csv", ".txt")


def load_file(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".cex":
        from .land_cex import read_cex
        return read_cex(path)
    if ext == ".ndax":
        from .neware_ndax import read_ndax
        return read_ndax(path)
    if ext == ".nda":
        raise ValueError("新威旧版 .nda 文件暂不支持。可以在 BTSDA 里另存为 .ndax 或导出 Excel 再拖进来。")
    if ext == ".icex":
        raise ValueError(".icex 是蓝电的索引文件，不含数据。请拖入同名的 .cex 文件。")
    if ext in (".xlsx", ".xlsm", ".xls", ".csv", ".txt"):
        from .tabular import read_table
        return read_table(path)
    raise ValueError(f"不支持的文件类型 {ext}。支持：蓝电 .cex、新威 .ndax，以及导出的 .xlsx/.xls/.csv/.txt")
