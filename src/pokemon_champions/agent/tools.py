"""도구 정의 — 모델이 부를 수 있는 함수와 그 스키마.

── 스키마를 손으로 적는 이유 ──
  파이썬 시그니처에서 자동 생성할 수도 있지만, 도구 설명은 모델에게 주는
  프롬프트다. "언제 이걸 부르는가" 를 사람이 써야 한다. 자동 생성하면
  타입만 맞고 판단 근거가 빠져서, 모델이 엉뚱한 도구를 고른다.

── 인자를 적게 ──
  포켓몬 하나를 세우는 데 필요한 것은 이름·SP·성격·특성·도구 다섯이지만,
  대부분의 질문은 "메가갸라도스가 한카리아스를 몇 방에" 처럼 이름 둘과
  기술 하나뿐이다. 나머지는 기본값(SP 0 · 성실 · 첫 특성 · 도구 없음)으로
  두고, 모델이 말한 것만 채우게 한다.

── 모델에게는 영어로 ──
  모델은 Garchomp · Earthquake · Focus Sash 를 한카리아스 · 지진 ·
  기합의띠 보다 훨씬 잘 안다. 한국어 JSON 키에 이르면 아예 거의 본 적이
  없는 모양이라, 키가 한국어면 인자 정확도가 눈에 띄게 떨어진다. 그래서
  주고받는 키와 이름을 전부 영문으로 맞춘다.

── 그런데 번역은 모델이 하면 안 된다 ──
  맡기면 Garchomp 를 "가르촘프" 라고 적고, 틀렸다는 것을 알아챌 방법이
  없다. 계산을 안 맡기는 이유와 똑같다. 그래서 한국어 표시 이름을
  ko_name 으로 나란히 실어 보내고, 모델은 그 글자를 그대로 옮기기만
  한다. 한국어 이름이 없으면 ko_name 을 null 로 둔다 — 칸을 빼 버리면
  모델이 그 칸이 있다는 사실 자체를 잊고 제 맘대로 옮긴다.

  덤이 둘 있다. DB 의 진짜 열쇠가 영문 슬러그라 한국어 이름이 아직 없는
  항목에도 손이 닿고, 같은 내용이 한국어보다 토큰을 2~3배 덜 먹는다.

── 실패는 값으로 ──
  없는 이름을 물으면 예외 대신 {"error": ...} 를 돌려준다. 예외를 올리면
  루프가 죽지만, 값으로 주면 모델이 "그런 포켓몬은 없습니다" 라고 답하거나
  철자를 고쳐 다시 부를 수 있다.
"""

from ..db import connect
from ..db.repositories import (ability_repo, item_repo, lookup_repo, move_repo,
                               pokemon_repo, rules_repo)
from ..domain import STAT_ORDER
from ..services import damage, team, usage
from ..services.damage import BattleContext, Rules
from ..text import normalize

NEUTRAL_NATURE = "성실"

# domain 의 능력치 글자를 모델이 읽을 이름으로. 종족값·실능 dict 의 키가
# 전부 이 여섯이다. 순서는 STAT_ORDER 가 정한다.
STAT_KEYS = {"h": "hp", "a": "atk", "b": "def",
             "c": "spa", "d": "spd", "s": "spe"}

_state = {"conn": None, "rules": None, "rows": {}, "names": {}}


def _conn():
    if _state["conn"] is None:
        _state["conn"] = connect()
    return _state["conn"]


def _rules():
    """상성표 324행. 한 번 읽어 계속 돌려쓴다."""
    if _state["rules"] is None:
        c = _conn()
        _state["rules"] = Rules(
            chart=rules_repo.fetch_type_chart(c),
            weathers=rules_repo.fetch_weathers(c),
            terrains=rules_repo.fetch_terrains(c),
        )
    return _state["rules"]


def close():
    if _state["conn"] is not None:
        _state["conn"].close()
    _state["conn"] = _state["rules"] = None
    _state["rows"], _state["names"] = {}, {}


# ─────────────────────────────────────────────────────────────
# 이름 — 두 방향으로 찾고, 두 벌로 내보낸다
# ─────────────────────────────────────────────────────────────

_LISTS = {
    "pokemons": pokemon_repo.fetch_list,
    "moves": move_repo.fetch_list,
    "items": item_repo.fetch_list,
    "abilities": ability_repo.fetch_list,
}


def _rows_of(table):
    """도감 목록을 한 번만 읽어 영문 이름으로 찾을 수 있게 들고 있는다.

    이름 하나마다 쿼리를 내면 기술 여덟 개짜리 답에 쿼리가 여덟 번 나간다.
    가장 큰 moves 가 498줄이라 전부 들고 있어도 문제가 없다 — 도감 화면도
    같은 함수로 같은 목록을 통째로 받는다.
    """
    if table not in _state["rows"]:
        _state["rows"][table] = {r["name"]: r for r in _LISTS[table](_conn())}
    return _state["rows"][table]


def _maps(table):
    """{영문: 한국어} 와 {한국어: 영문} 두 벌."""
    if table not in _state["names"]:
        if table == "pokemon_natures":
            # 성격만 도감 목록이 없다. 그 테이블은 이름이 ENUM 이라 name
            # 컬럼이 아예 없어서, en_name 을 읽는 lookup_repo 를 쓴다.
            pairs = list(lookup_repo.fetch_ko_map(_conn(), table).items())
        else:
            pairs = [(r["name"], r["ko_name"]) for r in _rows_of(table).values()]
        _state["names"][table] = {
            "ko_by_en": dict(pairs),
            "en_by_ko": {normalize(ko): en for en, ko in pairs if ko},
        }
    return _state["names"][table]


def _resolve(table, name):
    """한국어 이름이든 영문 슬러그든 받아 영문 name 을 돌려준다.

    모델이 한국어 질문을 읽고 그대로 넘기기도 하고, 친절하게 영문으로
    바꿔 넘기기도 한다. 어느 쪽이 오든 걸려야 한다.

    ko_name 을 먼저 본다. 한글과 영문은 문자 집합이 달라 실제로 겹칠 일이
    없지만, 순서를 정해두지 않으면 나중에 겹치는 항목이 생겼을 때 조용히
    갈린다.

    영문은 슬러그로 한 번 더 본다. 모델이 사람 읽는 표기(Focus Sash)로
    주는 일이 잦은데 우리 DB 는 focus-sash 다. 채용률 쪽 이름을 맞출 때
    쓰는 규칙과 같은 것을 쓴다 — 두 벌이 되면 한쪽만 고치게 된다.
    """
    if not name:
        return None
    m = _maps(table)
    key = normalize(str(name))
    hit = m["en_by_ko"].get(key)
    if hit:
        return hit
    if key in m["ko_by_en"]:
        return key
    slug = usage.slugify(key)
    return slug if slug in m["ko_by_en"] else None


def _ko(table, en):
    """영문 name -> 한국어 이름. 아직 없으면 None."""
    return _maps(table)["ko_by_en"].get(en) if en else None


def _named(table, value, key="name"):
    """이름 한 칸을 영문 + 한국어 두 칸으로 편다.

        _named("items", "기합의띠")
            -> {"name": "focus-sash", "ko_name": "기합의띠"}
        _named("abilities", "rough-skin", "ability")
            -> {"ability": "rough-skin", "ability_ko_name": "까칠한피부"}

    칸 이름은 name 일 때만 ko_name 이고 나머지는 <칸>_ko_name 이다. 한
    dict 안에 이름이 여럿 들어가는 자리(공격자의 특성·도구·성격)가 있어서
    ko_name 하나로는 어느 것의 한국어인지 알 수 없다.

    못 찾은 이름은 받은 것을 그대로 둔다. 빈칸으로 만들면 "그런 게 없다"
    로 읽히는데, 실제로는 우리 표에 아직 안 실린 것일 수 있다.
    """
    en = _resolve(table, value)
    ko_key = "ko_name" if key == "name" else f"{key}_ko_name"
    return {key: en or value, ko_key: _ko(table, en)}


def _stats(source):
    """능력치 6칸을 모델이 읽을 키로. Stats 도 dict 행도 같이 받는다."""
    return {STAT_KEYS[k]: source[k] for k in STAT_ORDER}


def _types_of(en):
    """영문 이름 -> 타입 1~2개.

    pokemon_repo.fetch_meta 를 안 쓰는 이유는 그쪽이 ko_name 을 열쇠로
    써서, 한국어 이름이 아직 없는 폼에는 쓸 수 없기 때문이다.
    """
    row = _rows_of("pokemons")[en]
    return tuple(t for t in (row["type1"], row["type2"]) if t)


# ─────────────────────────────────────────────────────────────
# 도감
# ─────────────────────────────────────────────────────────────

def find_pokemon(name):
    """한 마리의 종족값·타입·특성·메가 관계."""
    en = _resolve("pokemons", name)
    if en is None:
        return {"error": f"'{name}' 은(는) 포챔스 목록에 없습니다."}
    row = pokemon_repo.fetch_detail(_conn(), en)
    return {
        "name": row["name"], "ko_name": row["ko_name"],
        "pokemon_id": row["pokemon_id"],
        "types": [t for t in (row["type1"], row["type2"]) if t],
        "base_stats": _stats(row),
        "bst": sum(row[k] for k in STAT_ORDER),
        "abilities": [{"name": a["name"], "ko_name": a["ko_name"],
                       "is_hidden": a["is_hidden"],
                       "description": a["description"]}
                      for a in row["abilities"]],
        "height_m": row["height"], "weight_kg": row["weight"],
        "can_mega": row["can_mega"], "is_mega": row["is_mega"],
        "mega_forms": [{"name": f["mega_name"], "ko_name": f["mega_ko_name"]}
                       for f in row["mega_forms"]],
    }


# 정렬 기준. 모델이 주는 값이라 실능 키와 같은 이름을 쓴다 — 여기만
# 다르면 "spa 로 정렬" 이 조용히 무시된다.
_ORDER_KEYS = {"hp": "h", "atk": "a", "def": "b",
               "spa": "c", "spd": "d", "spe": "s"}


def search_pokemon(type=None, min_total=None, order_by=None, limit=15):
    """조건에 맞는 포켓몬 목록. 비교·후보 추리기용."""
    rows = list(_rows_of("pokemons").values())
    if type:
        t = normalize(type)
        rows = [r for r in rows if t in (r["type1"], r["type2"])]
    if min_total:
        rows = [r for r in rows if sum(r[k] for k in STAT_ORDER) >= min_total]

    key = _ORDER_KEYS.get(order_by or "")
    if key:
        rows.sort(key=lambda r: -r[key])
    elif order_by == "bst":
        rows.sort(key=lambda r: -sum(r[k] for k in STAT_ORDER))

    return {
        "total": len(rows),
        "results": [{"name": r["name"], "ko_name": r["ko_name"],
                     "types": [t for t in (r["type1"], r["type2"]) if t],
                     "base_stats": _stats(r),
                     "bst": sum(r[k] for k in STAT_ORDER)}
                    for r in rows[:limit]],
    }


def type_effectiveness(attack_type, defender):
    """기술 타입이 그 포켓몬에게 몇 배로 들어가는가."""
    en = _resolve("pokemons", defender)
    if en is None:
        return {"error": f"'{defender}' 은(는) 포챔스 목록에 없습니다."}
    at = normalize(attack_type)
    types = _types_of(en)
    return {"attack_type": at,
            "defender": en, "defender_ko_name": _ko("pokemons", en),
            "defender_types": list(types),
            "multiplier": damage.type_multiplier(at, types, _rules().chart)}


def find_move(name):
    en = _resolve("moves", name)
    if en is None:
        return {"error": f"'{name}' 이라는 기술이 없습니다."}
    m = move_repo.fetch_detail(_conn(), en)
    return {"name": m["name"], "ko_name": m["ko_name"], "type": m["type"],
            "category": m["category"], "power": m["power"],
            "accuracy": m["accuracy"], "pp": m["pp"],
            "priority": m["priority"], "description": m["description"]}


def moves_of(pokemon):
    """그 포켓몬이 배울 수 있는 기술 전부.

    move_repo.fetch_learnable 이 아니라 도감 상세를 쓴다. 그쪽은 ko_name
    을 열쇠로 잡고 한국어 이름이 없는 기술을 아예 빼는데, 여기서는 영문
    이름으로 찾고 한국어가 없으면 없다고 밝히면 된다.
    """
    en = _resolve("pokemons", pokemon)
    if en is None:
        return {"error": f"'{pokemon}' 은(는) 포챔스 목록에 없습니다."}
    row = pokemon_repo.fetch_detail(_conn(), en)
    return {"pokemon": en, "ko_name": row["ko_name"],
            "count": len(row["moves"]),
            "moves": [{"name": m["name"], "ko_name": m["ko_name"]}
                      for m in row["moves"]]}


def find_ability(name):
    en = _resolve("abilities", name)
    if en is None:
        return {"error": f"'{name}' 이라는 특성이 없습니다."}
    a = ability_repo.fetch_detail(_conn(), en)
    return {"name": a["name"], "ko_name": a["ko_name"],
            "description": a["description"], "effect_en": a["effect"],
            "pokemon": [{"name": p["name"], "ko_name": p["ko_name"]}
                        for p in a["pokemons"]]}


def find_item(name):
    en = _resolve("items", name)
    if en is None:
        return {"error": f"'{name}' 이라는 도구가 없습니다."}
    i = item_repo.fetch_detail(_conn(), en)
    return {"name": i["name"], "ko_name": i["ko_name"],
            "category": i["category"], "description": i["description"],
            "usable": i["usable"]}


# ─────────────────────────────────────────────────────────────
# 계산
# ─────────────────────────────────────────────────────────────

def _ko_for_build(table, value):
    """모델이 준 이름을 DB 조회에 쓸 한국어로. 못 바꾸면 받은 것 그대로.

    그대로 넘기는 이유는 team.validate_spec 이 이미 "그 포켓몬의 특성이
    아닙니다" 를 사람이 읽을 문장으로 돌려주기 때문이다. 여기서 따로
    막으면 같은 말을 두 곳에서 하게 되고, 문구가 갈린다.
    """
    if not value:
        return None
    return _ko(table, _resolve(table, value)) or normalize(str(value))


def _build(spec, move_ko=None):
    """도구 인자를 Pokemon 으로. 돌려주는 값은 (Pokemon, 영문 이름).

    안 준 것은 기본값으로 채운다.

    ── 왜 다시 한국어로 되돌리나 ──
      모델과는 영문으로 주고받지만, team.build_pokemon 과 그 아래 조회는
      ko_name 을 열쇠로 쓴다. 엔트리 파일을 사람이 한국어로 적기 때문이다.
      그 경계가 여기다. 한국어 이름이 아직 없는 폼은 계산에 못 올리므로
      그렇다고 밝힌다 — 조용히 다른 폼으로 세우면 숫자만 어긋난다.
    """
    en = _resolve("pokemons", spec["name"])
    if en is None:
        raise ValueError(f"'{spec['name']}' 은(는) 포챔스 목록에 없습니다.")
    ko = _ko("pokemons", en)
    if ko is None:
        raise ValueError(f"'{en}' 은(는) 한국어 이름이 아직 없어 "
                         "계산에 올릴 수 없습니다.")

    ability = _ko_for_build("abilities", spec.get("ability"))
    if not ability:
        # 특성을 안 말했으면 1번 특성. 무엇으로 쟀는지는 답에 실어 보낸다.
        cands = pokemon_repo.fetch_abilities(_conn(), ko)
        ability = cands[0] if cands else None

    p = team.build_pokemon(
        _conn(), ko_name=ko,
        sp_values=spec.get("sp") or [0] * 6,
        ko_nature=(_ko_for_build("pokemon_natures", spec.get("nature"))
                   or NEUTRAL_NATURE),
        ability=ability,
        item=_ko_for_build("items", spec.get("item")),
        moves=[move_ko] if move_ko else None,
        rank=spec.get("rank"),
        allow_mega=True,
    )
    return p, en


def _side_view(p, en):
    """계산에 실제로 쓰인 한 쪽을 모델이 읽을 모양으로.

    특성·도구·성격을 안 말하면 기본값으로 채워진다. 무엇으로 쟀는지를
    같이 돌려주지 않으면, 모델은 사용자가 말한 조건으로 계산된 줄 안다.
    """
    return {"name": en, "ko_name": p.name,
            **_named("abilities", p.ability, "ability"),
            **_named("items", p.item, "item"),
            **_named("pokemon_natures", p.nature, "nature")}


def calc_damage(attacker, defender, move, weather=None, terrain=None,
                is_critical=False, is_doubles=False):
    """데미지 난수 16개와 확정 N타 판정.

    attacker/defender 는 {"name", "ability", "item", "nature", "sp", "rank"}.
    name 만 필수다.
    """
    en_move = _resolve("moves", move)
    if en_move is None:
        return {"error": f"'{move}' 이라는 기술이 없습니다."}
    m = move_repo.fetch_detail(_conn(), en_move)

    try:
        atk, atk_en = _build(attacker, m["ko_name"] or m["name"])
        dfn, dfn_en = _build(defender)
    except ValueError as e:
        return {"error": str(e)}

    ctx = BattleContext(
        weather=weather or None, terrain=terrain or None,
        attacker_rank=attacker.get("rank") or {},
        defender_rank=defender.get("rank") or {},
        is_critical=is_critical, is_doubles=is_doubles,
    )
    rules = _rules()
    dmg = damage.calc_damage(atk, dfn, m, ctx, rules)
    ko = damage.analyze_ko(atk, dfn, m, ctx, rules)
    lo, hi = dmg.percent(dfn.stats.h)

    return {
        "attacker": {**_side_view(atk, atk_en),
                     "atk": atk.stats.a, "spa": atk.stats.c},
        "defender": {**_side_view(dfn, dfn_en),
                     "hp": dfn.stats.h, "def": dfn.stats.b, "spd": dfn.stats.d},
        "move": {"name": m["name"], "ko_name": m["ko_name"], "type": m["type"],
                 "category": m["category"], "power": m["power"]},
        "type_effect": damage.type_multiplier(m["type"], dfn.types, rules.chart),
        "damage": {"min": dmg.min, "max": dmg.max,
                   "percent": f"{lo:.1f}~{hi:.1f}%", "rolls": dmg.rolls},
        # 판정은 키만 영어다. 값은 사람에게 그대로 보여줄 문장이라 한국어다.
        "verdict": ko["text"],
    }


def power_index(pokemon, moves):
    """결정력 — 공격 실능 × 위력 × 자속. 기술끼리 견주는 데 쓴다."""
    try:
        p, en = _build(pokemon)
    except ValueError as e:
        return {"error": str(e)}

    out = []
    for name in moves:
        en_move = _resolve("moves", name)
        if en_move is None:
            out.append({"name": name, "ko_name": None, "error": "없는 기술"})
            continue
        m = move_repo.fetch_detail(_conn(), en_move)
        out.append({"name": m["name"], "ko_name": m["ko_name"],
                    "type": m["type"], "category": m["category"],
                    "power": m["power"], "stab": m["type"] in p.types,
                    "power_index": damage.power_index(p, m)})
    out.sort(key=lambda x: -x.get("power_index", 0))
    return {"pokemon": en, "ko_name": p.name,
            "atk": p.stats.a, "spa": p.stats.c, "moves": out}


def bulk_index(pokemon):
    """내구력 — 체력 × 방어, 체력 × 특수방어."""
    try:
        p, en = _build(pokemon)
    except ValueError as e:
        return {"error": str(e)}
    b = damage.bulk_index(p)
    return {"pokemon": en, "ko_name": p.name, "hp": p.stats.h,
            "def": p.stats.b, "spd": p.stats.d,
            "physical_bulk": b["physical"], "special_bulk": b["special"]}


# ─────────────────────────────────────────────────────────────
# 내 엔트리
# ─────────────────────────────────────────────────────────────

def my_team():
    """등록해둔 6마리의 실제 스펙과 실능치."""
    out = []
    for spec in team.load_specs():
        en = _resolve("pokemons", spec.get("ko_name"))
        try:
            p = team.build_pokemon(_conn(), **spec)
        except ValueError as e:
            out.append({"name": en, "ko_name": spec.get("ko_name"),
                        "error": str(e)})
            continue
        out.append({
            "name": en, "ko_name": p.name, "types": list(p.types),
            **_named("abilities", p.ability, "ability"),
            **_named("items", p.item, "item"),
            **_named("pokemon_natures", p.nature, "nature"),
            "stats": _stats(p.stats),
            "moves": [_named("moves", mv) for mv in (p.moves or [])],
        })
    return {"team": out}


def team_weaknesses():
    """엔트리 전체의 타입 상성 표. 어느 타입에 몇 마리가 약한가.

    "우리 팀이 뭐에 약해" 를 모델이 상성표를 외워서 답하면 반드시 틀린다.
    18타입 × 6마리를 여기서 곱해준다.

    타입별 목록에는 영문 이름만 담는다. 여섯 마리 이름을 세 칸에 세 번씩
    한국어까지 적으면 표가 배로 불어난다. 한국어는 team 에 한 번 있고,
    모델은 거기서 짝을 찾는다.
    """
    chart = _rules().chart
    types = sorted({t for (t, _) in chart})

    members = []
    for spec in team.load_specs():
        en = _resolve("pokemons", spec["ko_name"])
        if en is None:
            return {"error": f"엔트리의 '{spec['ko_name']}' 을(를) "
                             "포챔스 목록에서 찾지 못했습니다."}
        members.append((en, _types_of(en)))

    table = {}
    for t in types:
        hit = {name: damage.type_multiplier(t, tt, chart) for name, tt in members}
        table[t] = {
            "weak_to": [n for n, m in hit.items() if m >= 2],
            "resists": [n for n, m in hit.items() if 0 < m <= 0.5],
            "immune": [n for n, m in hit.items() if m == 0],
        }
    # 위험한 순서로. 2배 이상 맞는 머릿수가 많은 타입이 곧 팀의 구멍이다.
    order = sorted(types, key=lambda t: -len(table[t]["weak_to"]))
    return {"team": [{"name": n, "ko_name": _ko("pokemons", n)}
                     for n, _ in members],
            "by_type": {t: table[t] for t in order}}


def usage_stats(pokemon, format="Singles"):
    """랭크배틀 채용률 — 기술·도구·특성·성격·SP·함께 쓰는 포켓몬."""
    en = _resolve("pokemons", pokemon)
    if en is None:
        return {"error": f"'{pokemon}' 은(는) 포챔스 목록에 없습니다."}
    return usage.usage_of(_conn(), en, ko_name=_ko("pokemons", en),
                          fmt=format if format in ("Singles", "Doubles")
                          else "Singles")


# ─────────────────────────────────────────────────────────────
# 스키마 — 모델에게 주는 설명이다. 타입만 맞추면 도구를 잘못 고른다.
# ─────────────────────────────────────────────────────────────

# 이름 인자는 전부 양방향이다. 모델이 한국어 질문을 그대로 옮겨 적기도
# 하고 영문으로 바꿔 주기도 하는데, 둘 중 하나만 받으면 나머지 절반이
# "그런 포켓몬은 없습니다" 가 된다.
_NAME_DESC = "한국어 이름 또는 영문 슬러그. 한카리아스 / garchomp 둘 다 된다"
_MOVE_DESC = "한국어 이름 또는 영문 슬러그. 지진 / earthquake 둘 다 된다"

_SIDE = {
    "type": "object",
    "description": "포켓몬 한 마리. name 만 필수이고 나머지는 기본값"
                   "(SP 0 · 성실 · 1번 특성 · 도구 없음)으로 채워진다.",
    "properties": {
        "name": {"type": "string",
                 "description": f"{_NAME_DESC}. 메가폼도 된다"},
        "ability": {"type": "string", "description":
                    "특성 이름. 까칠한피부 / rough-skin 둘 다 된다"},
        "item": {"type": "string", "description":
                 "도구 이름. 기합의띠 / focus-sash 둘 다 된다"},
        "nature": {"type": "string", "description":
                   "성격 이름. 고집 / adamant 둘 다 된다. 기본 성실"},
        "sp": {"type": "array", "items": {"type": "integer"},
               "description": "hp, atk, def, spa, spd, spe 순 6개. 총 66"},
        "rank": {"type": "object",
                 "description": '랭크 변화. 예: {"a": 2} 는 공격 2랭크업'},
    },
    "required": ["name"],
}

_STR = {"type": "string"}

TOOLS = {
    "find_pokemon": (find_pokemon, {
        "description": "포켓몬 한 마리의 종족값·타입·특성·메가 관계를 본다. "
                       "특정 포켓몬을 물었을 때 가장 먼저 부른다.",
        "properties": {"name": {**_STR, "description": _NAME_DESC}},
        "required": ["name"]}),

    "search_pokemon": (search_pokemon, {
        "description": "조건으로 포켓몬을 추린다. '불꽃 타입 중 스피드가 빠른' "
                       "처럼 한 마리가 아니라 후보를 찾을 때 쓴다.",
        "properties": {
            "type": {**_STR, "description": "영문 타입. fire, water, dragon …"},
            "min_total": {"type": "integer", "description": "종족값 합 하한"},
            "order_by": {**_STR, "description":
                         "정렬 기준. hp/atk/def/spa/spd/spe/bst"},
            "limit": {"type": "integer", "description": "최대 개수. 기본 15"}},
        "required": []}),

    "type_effectiveness": (type_effectiveness, {
        "description": "어떤 타입 기술이 그 포켓몬에게 몇 배로 들어가는지. "
                       "상성을 외워서 답하지 말고 반드시 이걸 부른다.",
        "properties": {
            "attack_type": {**_STR, "description": "영문 타입. fire, ground …"},
            "defender": {**_STR, "description":
                         f"방어하는 포켓몬. {_NAME_DESC}"}},
        "required": ["attack_type", "defender"]}),

    "find_move": (find_move, {
        "description": "기술 하나의 위력·타입·분류·효과.",
        "properties": {"name": {**_STR, "description": _MOVE_DESC}},
        "required": ["name"]}),

    "moves_of": (moves_of, {
        "description": "그 포켓몬이 배울 수 있는 기술 전부. "
                       "'이 기술 배울 수 있어?' 를 추측하지 말고 이걸로 확인한다.",
        "properties": {"pokemon": {**_STR, "description": _NAME_DESC}},
        "required": ["pokemon"]}),

    "find_ability": (find_ability, {
        "description": "특성 하나의 효과와 그 특성을 가진 포켓몬들.",
        "properties": {"name": {**_STR, "description":
                                "특성 이름. 까칠한피부 / rough-skin 둘 다 된다"}},
        "required": ["name"]}),

    "find_item": (find_item, {
        "description": "도구 하나의 효과와 분류.",
        "properties": {"name": {**_STR, "description":
                                "도구 이름. 기합의띠 / focus-sash 둘 다 된다"}},
        "required": ["name"]}),

    "calc_damage": (calc_damage, {
        "description": "데미지와 확정 N타 판정. '몇 방에 죽나', '버티나', "
                       "'원킬 나나' 류의 질문은 전부 이걸 부른다. "
                       "직접 곱셈하지 말 것 — 본가 공식은 반올림이 특이해서 "
                       "손으로 계산하면 확정/난수 판정이 뒤집힌다.",
        "properties": {
            "attacker": _SIDE, "defender": _SIDE,
            "move": {**_STR, "description": _MOVE_DESC},
            "weather": {**_STR, "description": "sun rain sandstorm snow 중 하나"},
            "terrain": {**_STR, "description":
                        "electric grassy misty psychic 중 하나"},
            "is_critical": {"type": "boolean", "description": "급소 여부"},
            "is_doubles": {"type": "boolean", "description": "더블 배틀 여부"}},
        "required": ["attacker", "defender", "move"]}),

    "power_index": (power_index, {
        "description": "결정력. 한 포켓몬의 기술들을 화력 순으로 견준다. "
                       "상대가 정해지지 않은 '뭘 넣는 게 세?' 에 쓴다.",
        "properties": {
            "pokemon": _SIDE,
            "moves": {"type": "array", "items": _STR,
                      "description": f"기술 이름들. {_MOVE_DESC}"}},
        "required": ["pokemon", "moves"]}),

    "bulk_index": (bulk_index, {
        "description": "내구력. 체력 × 방어, 체력 × 특수방어. "
                       "포켓몬끼리 얼마나 단단한지 견줄 때 쓴다.",
        "properties": {"pokemon": _SIDE},
        "required": ["pokemon"]}),

    "my_team": (my_team, {
        "description": "사용자가 등록해둔 엔트리 6마리의 스펙과 실능치. "
                       "'내 팀', '내 엔트리' 가 나오면 먼저 부른다.",
        "properties": {}, "required": []}),

    "team_weaknesses": (team_weaknesses, {
        "description": "엔트리 6마리의 타입 상성 표. 어느 타입에 몇 마리가 "
                       "약한지 전부 계산해 돌려준다. 팀의 약점을 물으면 "
                       "상성표를 외워서 답하지 말고 이걸 부른다.",
        "properties": {}, "required": []}),

    "usage_stats": (usage_stats, {
        "description": "랭크배틀 채용률. 그 포켓몬이 실제로 어떤 기술·도구·"
                       "특성·성격·SP 를 들고 나오는지, 누구와 같이 쓰이는지. "
                       "'요즘 뭐 들어?', '유행하는 배분', '어떤 도구 껴?' "
                       "류의 질문에 쓴다. 기억으로 답하지 말 것 — 메타는 "
                       "매일 바뀌고 이 수치는 게임 안 배틀 데이터에서 온다.",
        "properties": {
            "pokemon": {**_STR, "description": _NAME_DESC},
            "format": {**_STR, "description": "Singles 또는 Doubles. 기본 Singles"}},
        "required": ["pokemon"]}),
}


def schemas():
    """Ollama·OpenAI 형식의 tools 배열."""
    return [{"type": "function",
             "function": {"name": name,
                          "description": spec["description"],
                          "parameters": {"type": "object",
                                         "properties": spec["properties"],
                                         "required": spec["required"]}}}
            for name, (_, spec) in TOOLS.items()]


def call(name, args):
    """도구 하나를 실행한다. 무엇이 잘못돼도 값으로 돌려준다."""
    entry = TOOLS.get(name)
    if entry is None:
        return {"error": f"그런 도구가 없습니다: {name}"}
    try:
        return entry[0](**(args or {}))
    except TypeError as e:
        return {"error": f"인자가 맞지 않습니다: {e}"}
    except Exception as e:      # noqa: BLE001 - 루프가 죽으면 안 된다
        return {"error": f"{type(e).__name__}: {e}"}
