from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.render import render
from app.security import require_user
from app.services.search_service import smart_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search_view(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(require_user)):
    results = smart_search(db, q) if q else None
    return render(request, "search/results.html", {"nav_active": "", "q": q, "results": results})
