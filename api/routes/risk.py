from typing import Any, Dict
from fastapi import APIRouter
from risk.engine import RiskEngine
from utils.config import reload_risk_cfg

router = APIRouter(prefix="/risk", tags=["risk"])
_eng = RiskEngine()


@router.get("/status")
def risk_status() -> Dict[str, Any]:
    return _eng.status()


@router.post("/kill_switch/on")
def kill_on() -> Dict[str, Any]:
    _eng.set_kill_switch(True)
    return _eng.status()


@router.post("/kill_switch/off")
def kill_off() -> Dict[str, Any]:
    _eng.set_kill_switch(False)
    return _eng.status()


@router.post("/reset")
def reset_breakers() -> Dict[str, Any]:
    _eng.reset_breakers()
    return _eng.status()


@router.post("/reload")
def risk_reload() -> Dict[str, Any]:
    reload_risk_cfg()
    return _eng.status()
