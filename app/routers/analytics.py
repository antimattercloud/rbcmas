from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.charts import bar_chart_svg, horizontal_bar_svg
from app.database import get_db
from app.models.chemical import Chemical
from app.models.user import User
from app.render import render
from app.security import require_user
from app.services.analytics_service import (
    consumption_trend,
    dead_stock_containers,
    laboratory_wise_inventory,
    low_stock_chemicals,
    monthly_average_consumption,
    most_consumed_chemicals,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def analytics_home(request: Request, chemical_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_user)):
    trend = consumption_trend(db, months=12)
    trend_svg = bar_chart_svg([t["month"][5:] for t in trend], [t["total_used"] for t in trend], width=900, height=240)

    top_chems = most_consumed_chemicals(db, days=180, limit=10)
    top_svg = horizontal_bar_svg([c["name"] for c in top_chems], [c["total_used"] for c in top_chems], width=560)

    lab_inventory = laboratory_wise_inventory(db)
    lab_svg = horizontal_bar_svg([r["name"] for r in lab_inventory], [r["total_quantity"] for r in lab_inventory], width=560)

    low_stock = low_stock_chemicals(db)
    dead_stock = dead_stock_containers(db)

    chemicals = list(db.scalars(select(Chemical).where(Chemical.is_archived.is_(False)).order_by(Chemical.name)))
    selected_chemical = db.get(Chemical, chemical_id) if chemical_id else None
    chemical_avg = monthly_average_consumption(db, chemical_id) if chemical_id else None

    return render(
        request,
        "analytics/index.html",
        {
            "nav_active": "analytics",
            "trend_svg": trend_svg,
            "top_svg": top_svg,
            "lab_svg": lab_svg,
            "low_stock": low_stock,
            "dead_stock": dead_stock,
            "chemicals": chemicals,
            "selected_chemical": selected_chemical,
            "chemical_avg": chemical_avg,
        },
    )
