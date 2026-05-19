# state_manager.py
import json
import os
from pathlib import Path

def load_state(path):
    if not os.path.exists(path):
        return {"items": {}}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {"items": {}}

def save_state(path, state):
    Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")

def has_changed(state, item):
    sid = str(item["id"])
    prev = state["items"].get(sid)
    current = {
        "next_ep_date": item["next_ep_date"],
        "next_ep_number": item["next_ep_number"],
        "status": item["status"],
    }
    if prev == current:
        return False
    state["items"][sid] = current
    return True
