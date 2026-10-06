from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.charts import bar_chart_svg, horizontal_bar_svg
from app.database import get_db
from app.render import render
from app.security import require_user
from app.services.analytics_service import (
    consumption_trend,
    dashboard_metrics,
    laboratory_wise_inventory,
    most_consumed_chemicals,
)
from app.models.user import User

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    metrics = dashboard_metrics(db)
    trend = consumption_trend(db, months=6)
    trend_svg = bar_chart_svg([t["month"][5:] for t in trend], [t["total_used"] for t in trend])

    top_chems = most_consumed_chemicals(db, days=90, limit=6)
    top_chart_svg = horizontal_bar_svg([c["name"] for c in top_chems], [c["total_used"] for c in top_chems])

    lab_inventory = laboratory_wise_inventory(db)

    return render(
        request,
        "dashboard.html",
        {
            "nav_active": "dashboard",
            "metrics": metrics,
            "trend_svg": trend_svg,
            "top_chart_svg": top_chart_svg,
            "lab_inventory": lab_inventory,
        },
    )
