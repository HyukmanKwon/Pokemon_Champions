"""로컬 웹으로 내 포켓몬 팀을 보고 필드 단위로 바로 고치는 FastAPI 앱.

CLI(interfaces/cli.py)와 완전히 같은 services 를 쓴다 — 검증/부분수정 로직을
여기서 다시 만들지 않고 services.team, services.stats, repositories 를
호출만 한다. 이 파일에 계산이나 SQL 이 생기면 CLI 와 웹의 동작이 갈라진다.
"""

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from ... import assets
from ...config import IMAGES_DIR
from ...db import connect
from ...db.repositories import (ability_repo, item_repo, move_repo,
                                nature_repo, pokemon_repo, rules_repo)
from ...domain import STAT_LABELS, STAT_ORDER
from ...services import damage, team
from ...services.damage import Rules
from ...services.stats import calc_stats, make_sp
from ...text import normalize
from ...usecases import battle

STATIC_DIR = Path(__file__).resolve().parent / "static"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

state = {"conn": None, "specs": None, "rules": None}


@app.on_event("startup")
def on_startup():
    state["conn"] = connect()
    state["specs"] = team.load_specs()
    # 참조표는 배틀 중에 안 바뀐다. 계산 한 번마다 324행을 다시 읽으면
    # 확정 N타 분석에서 턴 수만큼 쿼리가 나간다. 뜰 때 한 번만 읽는다.
    state["rules"] = Rules(
        chart=rules_repo.fetch_type_chart(state["conn"]),
        weathers=rules_repo.fetch_weathers(state["conn"]),
        terrains=rules_repo.fetch_terrains(state["conn"]),
    )


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


def _type_badges(*names):
    return [{"name": t, "icon": assets.url_type_icon(t)} for t in names if t]


def _mega_view(spec):
    """메가진화 후 모습. 스톤을 안 지녔으면 None 이고, 그때는 힌트만 준다.

    화면 표현(아이콘 URL·스프라이트)만 여기서 붙인다. 무엇이 바뀌는지는
    services.team.resolve_mega 가 정한다.
    """
    conn = state["conn"]
    form = team.resolve_mega(conn, spec)

    # 메가가 아예 없는 포켓몬이면 빈 리스트라 화면에서 아무것도 안 뜬다.
    # 스톤을 이미 지녀 메가가 성립할 때도 목록은 그대로 돌려준다 — 도구
    # 선택 목록에 그 포켓몬의 스톤을 올리려면 이름을 알아야 하기 때문이다.
    # 화면 안내는 megaBar() 가 slot.mega 를 먼저 보므로 겹치지 않는다.
    stones = [s for s in team.mega_hint(conn, spec["ko_name"])
              if s["item_ko_name"]]

    if form is None:
        return None, stones

    return {
        "name": form["ko_name"],
        "sprite": assets.url_pokemon_sprite(form["id"]),
        "types": _type_badges(form["type1"], form["type2"]),
        "base": _stats_dict(form["base"]),
        "stats": {k: form["stats"][k] for k in STAT_ORDER},
        "ability": form["ability"],
    }, stones


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

    types = _type_badges(meta["type1"], meta["type2"])
    mega, mega_stones = _mega_view(spec)
    moves = []
    for m in (spec.get("moves") or []):
        m = normalize(m)
        move_type = move_repo.fetch_type(conn, m)
        moves.append({
            "name": m,
            "type": move_type,
            "icon": assets.url_type_icon(move_type),
        })

    return {
        "index": index,
        "spec": spec,
        "name": normalize(spec["ko_name"]),
        "sprite": assets.url_pokemon_sprite(meta["id"]),
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
        # 고를 수 있는 것들. 포켓몬마다 다르므로 슬롯별로 실어 보낸다.
        # (도구는 포켓몬을 안 가리므로 /api/items 로 따로 한 번만 받는다)
        "selectable_abilities": pokemon_repo.fetch_abilities(
            conn, spec["ko_name"]),
        "learnable_moves": move_repo.fetch_learnable(conn, spec["ko_name"]),
        # 메가스톤을 지녔을 때만 값이 있다. 그때만 화면에 On/Off 버튼이 뜬다.
        "mega": mega,
        # 메가는 가능한데 스톤을 안 지닌 경우의 안내
        "mega_stones": mega_stones,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# 이미지
#
# StaticFiles 로 통째로 걸지 않는다. 아직 안 받은 그림은 404 가 되어,
# 파일이 없는 것과 저장소에 없는 것이 화면에서 똑같아 보이기 때문이다.
# 여기서 받아 저장하고 내주면 첫 요청 때 캐시가 저절로 채워진다.
#
# 그림이 정말 없는 폼(리전폼·메가에 흔하다)은 404 를 준다. 화면은 그
# 자리를 비워두면 되고, 능력치 조회는 애초에 이 경로를 타지 않는다.
#
# 브라우저가 매번 다시 받지 않도록 캐시 헤더를 길게 준다. 스프라이트는
# 한 번 정해지면 안 바뀌는 그림이라 안전하다.
# ─────────────────────────────────────────────────────────────

CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}


def _sprite(path):
    if path is None:
        raise HTTPException(404, "이미지가 없습니다.")
    return FileResponse(path, media_type="image/png", headers=CACHE_HEADERS)


@app.get("/sprite/type/{type_name}")
def sprite_type(type_name: str):
    return _sprite(assets.ensure_type_icon(type_name))


@app.get("/sprite/pokemon/{pokemon_id}")
def sprite_pokemon(pokemon_id: int):
    """상세용 큰 그림(official-artwork)."""
    return _sprite(assets.ensure_pokemon_sprite(pokemon_id))


@app.get("/sprite/pokemon/{pokemon_id}/icon")
def sprite_pokemon_icon(pokemon_id: int):
    """목록용 96px 도트. 큰 그림을 313개 깔면 화면이 안 뜬다."""
    return _sprite(assets.ensure_pokemon_icon(pokemon_id))


@app.get("/sprite/item/{item_name}")
def sprite_item(item_name: str):
    """도구 아이콘. 저장소 파일명이 영문 슬러그라 items.name 으로 찾는다."""
    return _sprite(assets.ensure_item_sprite(item_name))


# ─────────────────────────────────────────────────────────────
# 도감 — DB 에 있는 것을 그대로 열람한다
#
# 팀 화면(/api/team)과 성격이 다르다. 저쪽은 내 엔트리 6칸을 계산해서
# 보여주고 고치는 곳이고, 이쪽은 DB 내용을 있는 그대로 읽기만 한다.
# 그래서 services 를 거치지 않고 repositories 를 바로 부른다 — 중간에
# 낄 규칙이 없는데 계층만 늘리면 무엇이 어디 있는지 흐려진다.
#
# 목록은 전부 한 번에 보낸다. 가장 큰 moves 가 498줄이라, 검색·정렬은
# 브라우저가 메모리에서 하는 편이 왕복보다 빠르다.
# ─────────────────────────────────────────────────────────────

def _decorate_pokemon(row):
    """포켓몬 행에 화면용 그림 주소를 붙인다. 여기서만 붙이는 이유는,
    repositories 가 화면 사정(어떤 크기의 그림을 쓰는지)을 모르게 하려는 것."""
    row["types"] = _type_badges(row.get("type1"), row.get("type2"))
    row["icon"] = assets.url_pokemon_icon(row.get("id"))
    row["sprite"] = assets.url_pokemon_sprite(row.get("id"))
    return row


def _found(fetch, *args):
    """repositories 의 ValueError('존재하지 않는 …') 를 404 로 바꾼다."""
    try:
        return fetch(*args)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/dex/pokemons")
def dex_pokemons():
    return [_decorate_pokemon(r)
            for r in pokemon_repo.fetch_list(state["conn"])]


@app.get("/api/dex/pokemons/{name}")
def dex_pokemon(name: str):
    row = _found(pokemon_repo.fetch_detail, state["conn"], name)
    _decorate_pokemon(row)
    for m in row["moves"]:
        m["icon"] = assets.url_type_icon(m["type"])
    for f in row["mega_forms"]:
        f["item_icon"] = assets.url_item_sprite(f["item_name"])
    if row["mega_of"]:
        row["mega_of"]["item_icon"] = assets.url_item_sprite(
            row["mega_of"]["item_name"])
    return row


@app.get("/api/dex/moves")
def dex_moves():
    rows = move_repo.fetch_list(state["conn"])
    for r in rows:
        r["icon"] = assets.url_type_icon(r["type"])
    return rows


@app.get("/api/dex/moves/{name}")
def dex_move(name: str):
    row = _found(move_repo.fetch_detail, state["conn"], name)
    row["icon"] = assets.url_type_icon(row["type"])
    row["learners"] = [_decorate_pokemon(p) for p in row["learners"]]
    return row


@app.get("/api/dex/abilities")
def dex_abilities():
    return ability_repo.fetch_list(state["conn"])


@app.get("/api/dex/abilities/{name}")
def dex_ability(name: str):
    row = _found(ability_repo.fetch_detail, state["conn"], name)
    row["pokemons"] = [_decorate_pokemon(p) for p in row["pokemons"]]
    return row


@app.get("/api/dex/items")
def dex_items():
    rows = item_repo.fetch_list(state["conn"])
    for r in rows:
        r["icon"] = assets.url_item_sprite(r["name"])
    return rows


@app.get("/api/dex/items/{name}")
def dex_item(name: str):
    row = _found(item_repo.fetch_detail, state["conn"], name)
    row["icon"] = assets.url_item_sprite(row["name"])
    if row["mega"]:
        row["mega"]["base_icon"] = assets.url_pokemon_icon(
            row["mega"]["base_id"])
        row["mega"]["mega_icon"] = assets.url_pokemon_icon(
            row["mega"]["mega_id"])
    return row


@app.get("/api/team")
def get_team():
    return [_slot_view(i) for i in range(len(state["specs"]))]


@app.get("/api/pokemon/{ko_name}/options")
def get_pokemon_options(ko_name: str):
    """아직 등록하지 않은 포켓몬의 특성·기술 목록.

    검증은 스펙 전체를 보므로, 이름만 바꾸면 특성과 기술이 새 포켓몬 것이
    아니라서 반드시 거부된다. 화면은 이 목록을 먼저 받아 특성을 채우고
    기술을 비운 뒤 한 번의 PATCH 로 보낸다. 초기화는 화면 사정이므로
    services 에 두지 않고 여기서 한다.
    """
    conn = state["conn"]
    try:
        meta = pokemon_repo.fetch_meta(conn, ko_name)   # 없는 이름이면 여기서 걸린다
    except ValueError as e:
        raise HTTPException(404, str(e))

    # 메가폼이면 지닐 도구가 정해져 있다. 메가스톤이 없으면 그 폼 자체가
    # 성립하지 않으므로, 고를 여지가 없는 것을 고르게 두지 않는다.
    # (계산기 전용이다 — 엔트리에는 메가폼을 올릴 수 없다)
    forced_item = None
    if meta["is_mega"]:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT i.ko_name
            FROM mega_evolutions me
            JOIN pokemons p   ON p.name = me.mega_name
            LEFT JOIN items i ON i.name = me.item_name
            WHERE p.ko_name = %s
            """,
            (normalize(ko_name),),
        )
        row = cur.fetchone()
        forced_item = row[0] if row else None

    return {
        "selectable_abilities": pokemon_repo.fetch_abilities(conn, ko_name),
        "learnable_moves": move_repo.fetch_learnable(conn, ko_name),
        "is_mega": meta["is_mega"],
        "forced_item": forced_item,
    }


@app.get("/api/pokemons")
def get_pokemons():
    """엔트리에 올릴 수 있는 포켓몬 이름. 메가폼은 빠져 있다."""
    return pokemon_repo.fetch_selectable(state["conn"])


@app.get("/api/items")
def get_items():
    """지닐 수 있는 도구 전역 목록.

    도구는 포켓몬마다 다르지 않으므로 슬롯마다 실어 보내지 않는다. 한 번
    받아서 여섯 카드가 같이 쓴다. 포켓몬을 가리는 것은 메가스톤뿐이고,
    그건 슬롯의 mega_stones 에 따로 들어 있다.
    """
    return item_repo.fetch_usable(state["conn"])


@app.get("/api/natures")
def get_natures():
    """성격 21종. 이것도 포켓몬을 가리지 않으므로 전역으로 한 번만 준다.

    이름만 주면 화면에서 무엇이 오르고 내리는지 알 수 없으니 능력치 이름을
    같이 붙인다. 성실은 둘 다 None 이다.
    """
    return [
        {
            "name": n["ko_name"],
            "up": STAT_LABELS.get(n["up"]),
            "down": STAT_LABELS.get(n["down"]),
        }
        for n in nature_repo.fetch_all(state["conn"])
    ]


@app.patch("/api/team/{index}")
def patch_team(index: int, edit: SlotEdit):
    specs = state["specs"]
    if not 0 <= index < len(specs):
        raise HTTPException(404, f"슬롯 {index}는 존재하지 않습니다.")

    fields = edit.dict(exclude_unset=True)
    before = dict(specs[index])
    team.edit_spec(specs, index, **fields)
    try:
        # _slot_view 는 repositories 를 직접 부르므로 build_pokemon 을 거치지
        # 않는다. 여기서 부르지 않으면 CLI 만 검증되고 웹은 무엇이든 통과한다.
        team.validate_spec(state["conn"], specs[index])
        view = _slot_view(index)
    except ValueError as e:
        specs[index] = before
        raise HTTPException(400, str(e))

    team.save_specs(specs)
    return view


# ─────────────────────────────────────────────────────────────
# 데미지 계산기
#
# services/damage.py 는 DB 를 안 본다. 여기서 조회해서 숫자만 넘긴다.
# 그 경계 덕에 CLI(scripts/check_damage.py)와 이 라우트가 같은 함수를
# 쓰고, 값이 갈라지지 않는다.
# ─────────────────────────────────────────────────────────────

# 무보정 성격·SP 기본값·메가 허용은 usecases/battle.py 가 한 벌로 들고 있다.
# 여기서 다시 적으면 도구 쪽과 갈린다 — 실제로 갈렸던 자리다.
NEUTRAL_NATURE = battle.NEUTRAL_NATURE


class CalcSide(BaseModel):
    """계산에 올릴 한쪽. ko_name 과 ability 만 필수다."""

    ko_name: str
    ability: str
    item: Optional[str] = None
    ko_nature: str = NEUTRAL_NATURE
    # 안 보내면 조립 층이 무보정(0 여섯 칸)으로 채운다
    sp_values: Optional[List[int]] = None
    # {"a": 2, "s": -1} — 안 적힌 능력치는 0
    rank: Dict[str, int] = Field(default_factory=dict)
    condition: Optional[str] = None
    # 남은 HP. None 이면 만피. 멀티스케일·궁지 특성이 이걸 본다
    hp: Optional[int] = None
    grounded: bool = True


class CalcRequest(BaseModel):
    attacker: CalcSide
    defender: CalcSide
    move: str                    # 한국어 기술 이름
    weather: Optional[str] = None
    terrain: Optional[str] = None
    is_critical: bool = False
    reflect: bool = False
    light_screen: bool = False
    is_doubles: bool = False
    max_turns: int = 4


def _spec(side: CalcSide):
    """CalcSide 를 조립 층이 받는 느슨한 스펙으로.

    칸 이름이 다른 것은 화면이 한국어를 그대로 보내기 때문이다(ko_name,
    ko_nature, sp_values). 요청 모양은 그대로 두고 여기서만 옮긴다 —
    화면 코드를 건드리지 않으려는 것이다.
    """
    return {"name": side.ko_name, "ability": side.ability, "item": side.item,
            "nature": side.ko_nature, "sp": side.sp_values, "rank": side.rank,
            "condition": side.condition, "hp": side.hp,
            "grounded": side.grounded}


def _side_pokemon(side: CalcSide, move=None):
    """CalcSide 를 Pokemon 으로. 기술을 주면 그것까지 검증한다."""
    return battle.build_side(state["conn"], _spec(side), move)[0]


def _side_view(p, side: CalcSide):
    return {
        "name": p.name,
        "types": _type_badges(*p.types),
        "stats": {k: p.stats[k] for k in STAT_ORDER},
        "ability": p.ability,
        "item": p.item,
        "nature": p.nature,
        "rank": side.rank,
        "condition": side.condition,
    }


@app.get("/api/calc/rules")
def calc_rules():
    """날씨·필드·상태이상 선택지. 화면의 드롭다운을 이걸로 채운다.

    코드에 목록을 적어두면 DB 에 새 날씨가 생겼을 때 조용히 빠진다.
    """
    conn = state["conn"]
    def pairs(rows):
        return [{"name": k, "ko_name": v["ko_name"]} for k, v in rows.items()]

    return {
        "weathers": pairs(state["rules"].weathers),
        "terrains": pairs(state["rules"].terrains),
        "conditions": pairs(rules_repo.fetch_status_conditions(conn)),
        "stat_order": list(STAT_ORDER),
        "stat_labels": {k: STAT_LABELS[k] for k in STAT_ORDER},
    }


class IndexRequest(BaseModel):
    """결정력·내구력용. 상대도 판도 없이 한쪽만 본다."""

    side: CalcSide
    moves: List[str] = Field(default_factory=list)


@app.post("/api/calc/power")
def calc_power(req: IndexRequest):
    """결정력 — 공격 실능 × 위력 × 자속. 기술별로 준다.

    상성·랭크·날씨는 상대와 판이 있어야 정해지므로 빠진다. 절대값에는
    의미가 없고 기술끼리·포켓몬끼리 비교하는 데만 쓴다.
    """
    conn = state["conn"]
    try:
        p = _side_pokemon(req.side)
    except ValueError as e:
        raise HTTPException(400, str(e))

    out = []
    for ko in req.moves:
        if not ko:
            continue
        en = move_repo.fetch_en_name(conn, normalize(ko))
        if en is None:
            raise HTTPException(404, f"없는 기술입니다: {ko}")
        move = move_repo.fetch_detail(conn, en)
        out.append({
            "name": move["ko_name"] or move["name"],
            "type": move["type"],
            "icon": assets.url_type_icon(move["type"]),
            "category": move["category"],
            "power": move["power"],
            "stab": move["type"] in p.types,
            "index": damage.power_index(p, move),
        })
    out.sort(key=lambda m: -m["index"])
    return {"side": _side_view(p, req.side), "moves": out}


@app.post("/api/calc/bulk")
def calc_bulk(req: IndexRequest):
    """내구력 — HP × 방어, HP × 특수방어.

    HP 만 봐도 방어만 봐도 몇 방 버티는지가 안 나온다. 받는 데미지가
    방어에 반비례하고 남은 턴이 HP 에 비례하므로 곱이 기준이 된다.
    """
    try:
        p = _side_pokemon(req.side)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"side": _side_view(p, req.side), "bulk": damage.bulk_index(p)}


@app.post("/api/calc/damage")
def calc_damage(req: CalcRequest):
    # 없는 기술은 404, 세울 수 없는 포켓몬은 400. 조립 층은 둘 다
    # ValueError 로 올리므로 기술만 먼저 확인해 갈래를 나눈다.
    if battle.move_row(state["conn"], req.move) is None:
        raise HTTPException(404, f"없는 기술입니다: {req.move}")

    try:
        shot = battle.one_hit(
            state["conn"], state["rules"],
            _spec(req.attacker), _spec(req.defender), req.move,
            max_turns=req.max_turns,
            weather=req.weather, terrain=req.terrain,
            is_critical=req.is_critical, reflect=req.reflect,
            light_screen=req.light_screen, is_doubles=req.is_doubles,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    attacker, defender = shot.attacker, shot.defender
    move, ctx, dmg, ko = shot.move, shot.ctx, shot.damage, shot.ko
    max_hp = defender.stats.h
    lo, hi = shot.percent()

    return {
        "attacker": _side_view(attacker, req.attacker),
        "defender": _side_view(defender, req.defender),
        "move": {
            "name": move["ko_name"] or move["name"],
            "type": move["type"],
            "icon": assets.url_type_icon(move["type"]),
            "category": move["category"],
            "power": move["power"],
            "accuracy": move["accuracy"],
        },
        "type_effect": shot.effect,
        # 실제로 계산에 들어간 판 상황을 그대로 돌려준다. 화면이 보낸 것을
        # 화면이 다시 그리면 "보냈다고 믿는 것" 을 보게 되어, 서버가 못 받은
        # 경우와 구별이 안 된다.
        "context": {
            "weather": ctx.weather,
            "terrain": ctx.terrain,
            "attacker_rank": ctx.attacker_rank,
            "defender_rank": ctx.defender_rank,
            "is_critical": ctx.is_critical,
            "reflect": ctx.reflect,
            "light_screen": ctx.light_screen,
            "is_doubles": ctx.is_doubles,
            "attacker_hp": ctx.attacker_hp,
            "defender_hp": ctx.defender_hp,
        },
        "damage": {
            "min": dmg.min,
            "max": dmg.max,
            "rolls": dmg.rolls,
            "percent_min": lo,
            "percent_max": hi,
            "defender_hp": max_hp,
        },
        "ko": {
            "text": ko["text"],
            "guaranteed": ko["guaranteed"],
            "possible": ko["possible"],
            "turns": [
                {"damage_min": t["damage"].min,
                 "damage_max": t["damage"].max,
                 "hp_before": t["hp_before"]}
                for t in ko["turns"]
            ],
        },
    }
