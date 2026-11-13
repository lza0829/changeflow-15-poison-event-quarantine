from fastapi import APIRouter

from app.db import connect
from app.repositories import quarantine as quarantine_repo

router = APIRouter(tags=["quarantine"])


@router.get("/quarantine")
def list_quarantine(kind: str | None = None):
    """隔离区列表。kind=poison 只看毒丸，kind=gap 只看缺口，缺省返回全部。"""
    conn = connect()
    try:
        if kind not in (None, "poison", "gap"):
            kind = None
        return quarantine_repo.list_quarantine(conn, kind)
    finally:
        conn.close()
