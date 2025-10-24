from fastapi import APIRouter
import time
from ops.flatten import flatten_all_safe
import os, json


router = APIRouter(tags=["ops"])


@router.post("/flatten")
def flatten():
    count = flatten_all_safe(reason="MANUAL")
    return {"flattened_positions": count}


@router.get("/healthz")
def healthz():
    return {"ok": True, "ts": time.time()}


@router.get("/runtime_json")
def runtime_json():
    path = os.getenv("ACCOUNT_RUNTIME_PATH", "runtime/account_runtime.json")
    if not os.path.exists(path):
        return {"status": "missing"}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data
