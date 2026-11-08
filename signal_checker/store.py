"""部位與狀態都存成 JSON 檔，放在 data/ 資料夾，由 GitHub Actions 自動 commit 回專案。"""
import json
import os
from datetime import date, datetime

DATA_DIR = os.environ.get("SC_DATA_DIR", "data")
POSITIONS = "positions.json"
STATE = "state.json"


def _path(name):
    return os.path.join(DATA_DIR, name)


def _default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"無法序列化 {type(o)}")


def load(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(name, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_default)
        f.write("\n")
    os.replace(tmp, _path(name))


def load_positions():
    p = load(POSITIONS, {"open": {}, "closed": []})
    p.setdefault("open", {})
    p.setdefault("closed", [])
    return p


def save_positions(p):
    save(POSITIONS, p)


def load_state():
    return load(STATE, {})


def save_state(s):
    save(STATE, s)


def key(symbol, side):
    return f"{symbol}:{side}"
