from __future__ import annotations

import csv
import io

from openpyxl import Workbook


def rows_to_csv(headers: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue()


def rows_to_xlsx(headers: list[str], rows: list[list], sheet_title: str = "Export") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31] or "Export"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    for col_idx, header in enumerate(headers, start=1):
        width = max(len(str(header)) + 2, 12)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(width, 40)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
