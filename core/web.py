"""
로컬 웹으로 내 포켓몬 팀을 보고 필드 단위로 바로 고치는 FastAPI 앱.

CLI(main.py)와 데이터 계층(my_pokemons.py)을 그대로 공유한다 — 검증/부분수정
로직을 여기서 다시 만들지 않고 stat_calculator의 fetch_*/calc_stats, my_pokemons의
edit_spec()을 그대로 호출만 한다.
"""
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assets, my_pokemons
from .database import db
from .pokemons import STAT_LABELS, STAT_ORDER
from .stat_calculator import (
    calc_stats, fetch_ability_effect, fetch_base, fetch_move_type, fetch_nature,
    fetch_pokemon_meta, make_sp, normalize,
)

STATIC_DIR = Path(__file__).resolve().parent / "web_static"

assets.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/images", StaticFiles(directory=assets.IMAGES_DIR), name="images")

state = {"conn": None, "specs": None}


@app.on_event("startup")
def on_startup():
    state["conn"] = db.connect()
    state["specs"] = my_pokemons.load_specs()


@app.on_event("shutdown")
def on_shutdown():
    state["conn"].close()


class SlotEdit(BaseModel):
    ko_name: Optional[str] = None
    sp_values: Optional[List[int]] = None
    ko_nature: Optional[str] = None
    ability: Optional[str] = None
    item: Optional[str] = None
    moves: Optional[List[str]] = None


def _stats_dict(stats):
    d = {k: stats[k] for k in STAT_ORDER}
    d["total"] = stats.total()
    return d


def _slot_view(index):
    spec = state["specs"][index]
    conn = state["conn"]

    base = fetch_base(conn, spec["ko_name"])
    sp = make_sp(spec["sp_values"])
    nature_mods = fetch_nature(conn, spec["ko_nature"])
    stats = calc_stats(base, sp, nature_mods)
    effect = fetch_ability_effect(conn, spec["ability"])
    meta = fetch_pokemon_meta(conn, spec["ko_name"])

    up = next((k for k, v in nature_mods.items() if v == 1.1), None)
    down = next((k for k, v in nature_mods.items() if v == 0.9), None)

    types = [
        {"name": t, "icon": assets.ensure_type_icon(t)}
        for t in (meta["type1"], meta["type2"]) if t
    ]
    moves = []
    for m in (spec.get("moves") or []):
        m = normalize(m)
        move_type = fetch_move_type(conn, m)
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
    my_pokemons.edit_spec(specs, index, **fields)
    try:
        view = _slot_view(index)
    except ValueError as e:
        specs[index] = before
        raise HTTPException(400, str(e))

    my_pokemons.save_specs(specs)
    return view
