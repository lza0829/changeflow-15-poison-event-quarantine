from fastapi import APIRouter, HTTPException

from app.db import connect
from app.engines.poison_rules import POISON_POLICIES
from app.repositories import settings as settings_repo
from app.schemas.entities import SettingPut

router = APIRouter(tags=["settings"])

_ALLOWED_VALUES = {
    "poison_policy": set(POISON_POLICIES),
    "gap_policy": {"stop_quarantine", "skip_gap"},
}


@router.get("/settings")
def list_settings():
    conn = connect()
    try:
        return settings_repo.as_list(conn)
    finally:
        conn.close()


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingPut):
    allowed = _ALLOWED_VALUES.get(key)
    if allowed is not None and body.value not in allowed:
        raise HTTPException(400, f"invalid {key}: {body.value}, allowed={sorted(allowed)}")
    conn = connect()
    try:
        settings_repo.put(conn, key, body.value)
        conn.commit()
        return {"key": key, "value": body.value}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    finally:
        conn.close()
