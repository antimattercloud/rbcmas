from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.render import render
from app.security import require_user
from app.services.export_service import rows_to_csv, rows_to_xlsx
from app.services.reports_service import REPORT_DEFS, REPORT_FUNCS

router = APIRouter(prefix="/reports", tags=["reports"])

# Large reports (§46: "do not display thousands of records simultaneously")
# are capped on-screen and rendered in full only via CSV/XLSX export.
SCREEN_ROW_LIMIT = 500


@router.get("")
def reports_index(request: Request, user: User = Depends(require_user)):
    return render(request, "reports/index.html", {"nav_active": "reports", "report_defs": REPORT_DEFS})


@router.get("/{report_key}")
def report_view(request: Request, report_key: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if report_key not in REPORT_FUNCS:
        return render(request, "errors/404.html", {"nav_active": "reports"}, status_code=404)
    headers, rows = REPORT_FUNCS[report_key](db)
    total_rows = len(rows)
    truncated = total_rows > SCREEN_ROW_LIMIT
    return render(
        request,
        "reports/view.html",
        {
            "nav_active": "reports",
            "title": REPORT_DEFS[report_key],
            "report_key": report_key,
            "headers": headers,
            "rows": rows[:SCREEN_ROW_LIMIT] if truncated else rows,
            "total_rows": total_rows,
            "truncated": truncated,
        },
    )


@router.get("/{report_key}/export.csv")
def report_export_csv(report_key: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if report_key not in REPORT_FUNCS:
        return Response(status_code=404)
    headers, rows = REPORT_FUNCS[report_key](db)
    csv_text = rows_to_csv(headers, rows)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{report_key}_report.csv"'},
    )


@router.get("/{report_key}/export.xlsx")
def report_export_xlsx(report_key: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if report_key not in REPORT_FUNCS:
        return Response(status_code=404)
    headers, rows = REPORT_FUNCS[report_key](db)
    xlsx_bytes = rows_to_xlsx(headers, rows, sheet_title=REPORT_DEFS[report_key])
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{report_key}_report.xlsx"'},
    )
