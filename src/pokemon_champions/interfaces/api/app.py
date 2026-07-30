"""로컬 웹으로 내 포켓몬 팀을 보고 필드 단위로 바로 고치는 FastAPI 앱.

CLI(interfaces/cli.py)와 완전히 같은 services 를 쓴다 — 검증/부분수정 로직을
여기서 다시 만들지 않고 services.team, services.stats, repositories 를
호출만 한다. 이 파일에 계산이나 SQL 이 생기면 CLI 와 웹의 동작이 갈라진다.
"""

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ... import assets
from ...config import IMAGES_DIR
from ...db import connect
from ...db.repositories import ability_repo, move_repo, nature_repo, pokemon_repo
from ...domain import STAT_LABELS, STAT_ORDER
from ...services import team
from ...services.stats import calc_stats, make_sp
from ...text import normalize

STATIC_DIR = Path(__file__).resolve().parent / "static"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

state = {"conn": None, "specs": None}


@app.on_event("startup")
def on_startup():
    state["conn"] = connect()
    state["specs"] = team.load_specs()


@app.on_event("shutdown")
def on_shutdown():
    if state["conn"] is not None:
        state["conn"].close()


class SlotEdit(BaseModel):
    ko_name: Optional[str] = None
    sp_values: Optional[List[int]] = None
    ko_nature: Optional[str] = None
    ability: Optional[str] = None
    item: Optional[str] = None
    moves: Optional[List[str]] = None


def _stats_dict(stats):
    d = stats.as_dict()
    d["total"] = stats.total()
    return d


def _slot_view(index):
    spec = state["specs"][index]
    conn = state["conn"]

    base = pokemon_repo.fetch_base(conn, spec["ko_name"])
    sp = make_sp(spec["sp_values"])
    nature_mods = nature_repo.fetch_modifiers(conn, spec["ko_nature"])
    stats = calc_stats(base, sp, nature_mods)
    effect = ability_repo.fetch_effect(conn, spec["ability"])
    meta = pokemon_repo.fetch_meta(conn, spec["ko_name"])

    up = next((k for k, v in nature_mods.items() if v == 1.1), None)
    down = next((k for k, v in nature_mods.items() if v == 0.9), None)

    types = [
        {"name": t, "icon": assets.ensure_type_icon(t)}
        for t in (meta["type1"], meta["type2"]) if t
    ]
    moves = []
    for m in (spec.get("moves") or []):
        m = normalize(m)
        move_type = move_repo.fetch_type(conn, m)
        moves.append({
            "name": m,
            "type": move_type,
            "icon": assets.ensure_type_icon(move_type),
        })

    return {
        "index": index,
        "spec": spec,
        "name": normalize(spec["ko_name"]),
        "sprite": assets.ensure_pokemon_sprite(meta["id"]),
        "types": types,
        "base": _stats_dict(base),
        "sp": _stats_dict(sp),
        "stats": {k: stats[k] for k in STAT_ORDER},
        "nature": {
            "name": normalize(spec["ko_nature"]),
            "up": STAT_LABELS.get(up),
            "down": STAT_LABELS.get(down),
        },
        "ability": {"name": spec["ability"], "effect": effect},
        "item": (normalize(spec["item"]) if spec.get("item") else None) or "없음",
        "condition": spec.get("condition") or "정상",
        "moves": moves,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/team")
def get_team():
    return [_slot_view(i) for i in range(len(state["specs"]))]


@app.patch("/api/team/{index}")
def patch_team(index: int, edit: SlotEdit):
    specs = state["specs"]
    if not 0 <= index < len(specs):
        raise HTTPException(404, f"슬롯 {index}는 존재하지 않습니다.")

    fields = edit.dict(exclude_unset=True)
    before = dict(specs[index])
    team.edit_spec(specs, index, **fields)
    try:
        view = _slot_view(index)
    except ValueError as e:
        specs[index] = before
        raise HTTPException(400, str(e))

    team.save_specs(specs)
    return view
