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

── 실패는 값으로 ──
  없는 이름을 물으면 예외 대신 {"error": ...} 를 돌려준다. 예외를 올리면
  루프가 죽지만, 값으로 주면 모델이 "그런 포켓몬은 없습니다" 라고 답하거나
  철자를 고쳐 다시 부를 수 있다.
"""

from ..db import connect
from ..db.repositories import (ability_repo, item_repo, move_repo,
                               pokemon_repo, rules_repo)
from ..domain import STAT_LABELS, STAT_ORDER
from ..services import damage, meta, team
from ..services.damage import BattleContext, Rules
from ..text import normalize

NEUTRAL_NATURE = "성실"

_state = {"conn": None, "rules": None}


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


# ─────────────────────────────────────────────────────────────
# 도감
# ─────────────────────────────────────────────────────────────

def _en_of(ko_name):
    """한국어 이름 -> 영문 name. 도감 조회가 영문 키를 쓴다."""
    cur = _conn().cursor()
    cur.execute("SELECT name FROM pokemons WHERE ko_name = %s",
                (normalize(ko_name),))
    row = cur.fetchone()
    return row[0] if row else None


def find_pokemon(name):
    """한 마리의 종족값·타입·특성·메가 관계."""
    en = _en_of(name)
    if en is None:
        return {"error": f"'{name}' 은(는) 포챔스 목록에 없습니다."}
    row = pokemon_repo.fetch_detail(_conn(), en)
    return {
        "이름": row["ko_name"], "영문": row["name"], "도감번호": row["pokemon_id"],
        "타입": [t for t in (row["type1"], row["type2"]) if t],
        "종족값": {STAT_LABELS[k]: row[k] for k in STAT_ORDER},
        "종족값합": sum(row[k] for k in STAT_ORDER),
        "특성": [{"이름": a["ko_name"] or a["name"],
                  "숨은특성": a["is_hidden"], "효과": a["description"]}
                 for a in row["abilities"]],
        "신장_m": row["height"], "체중_kg": row["weight"],
        "메가가능": row["can_mega"], "메가폼여부": row["is_mega"],
        "메가폼": [f["mega_ko_name"] for f in row["mega_forms"]],
    }


def search_pokemon(type=None, min_total=None, order_by=None, limit=15):
    """조건에 맞는 포켓몬 목록. 비교·후보 추리기용."""
    rows = pokemon_repo.fetch_list(_conn())
    if type:
        t = normalize(type)
        rows = [r for r in rows if t in (r["type1"], r["type2"])]
    if min_total:
        rows = [r for r in rows if sum(r[k] for k in STAT_ORDER) >= min_total]

    key = {"체력": "h", "공격": "a", "방어": "b", "특수공격": "c",
           "특수방어": "d", "스피드": "s"}.get(order_by or "")
    if key:
        rows.sort(key=lambda r: -r[key])
    elif order_by == "종족값합":
        rows.sort(key=lambda r: -sum(r[k] for k in STAT_ORDER))

    return {
        "총": len(rows),
        "목록": [{"이름": r["ko_name"],
                  "타입": [t for t in (r["type1"], r["type2"]) if t],
                  "종족값": {STAT_LABELS[k]: r[k] for k in STAT_ORDER},
                  "종족값합": sum(r[k] for k in STAT_ORDER)}
                 for r in rows[:limit]],
    }


def type_effectiveness(attack_type, defender):
    """기술 타입이 그 포켓몬에게 몇 배로 들어가는가."""
    en = _en_of(defender)
    if en is None:
        return {"error": f"'{defender}' 은(는) 포챔스 목록에 없습니다."}
    meta = pokemon_repo.fetch_meta(_conn(), normalize(defender))
    types = tuple(t for t in (meta["type1"], meta["type2"]) if t)
    mult = damage.type_multiplier(normalize(attack_type), types, _rules().chart)
    return {"공격타입": attack_type, "방어자": defender,
            "방어타입": list(types), "배수": mult}


def find_move(name):
    en = move_repo.fetch_en_name(_conn(), name)
    if en is None:
        return {"error": f"'{name}' 이라는 기술이 없습니다."}
    m = move_repo.fetch_detail(_conn(), en)
    return {"이름": m["ko_name"], "타입": m["type"], "분류": m["category"],
            "위력": m["power"], "명중": m["accuracy"], "PP": m["pp"],
            "우선도": m["priority"], "설명": m["description"]}


def moves_of(pokemon):
    """그 포켓몬이 배울 수 있는 기술 전부."""
    if _en_of(pokemon) is None:
        return {"error": f"'{pokemon}' 은(는) 포챔스 목록에 없습니다."}
    names = move_repo.fetch_learnable(_conn(), normalize(pokemon))
    return {"포켓몬": pokemon, "개수": len(names), "기술": names}


def find_ability(name):
    rows = [a for a in ability_repo.fetch_list(_conn())
            if normalize(a["ko_name"] or "") == normalize(name)]
    if not rows:
        return {"error": f"'{name}' 이라는 특성이 없습니다."}
    a = ability_repo.fetch_detail(_conn(), rows[0]["name"])
    return {"이름": a["ko_name"], "효과": a["description"],
            "영문효과": a["effect"],
            "가진포켓몬": [p["ko_name"] for p in a["pokemons"]]}


def find_item(name):
    rows = [i for i in item_repo.fetch_list(_conn())
            if normalize(i["ko_name"] or "") == normalize(name)]
    if not rows:
        return {"error": f"'{name}' 이라는 도구가 없습니다."}
    i = item_repo.fetch_detail(_conn(), rows[0]["name"])
    return {"이름": i["ko_name"], "분류": i["category"],
            "설명": i["description"], "대전사용": i["usable"]}


# ─────────────────────────────────────────────────────────────
# 계산
# ─────────────────────────────────────────────────────────────

def _build(spec, move_ko=None):
    """도구 인자를 Pokemon 으로. 안 준 것은 기본값으로 채운다."""
    ko = normalize(spec["name"])
    ability = spec.get("ability")
    if not ability:
        # 특성을 안 말했으면 1번 특성. 무엇으로 쟀는지는 답에 실어 보낸다.
        cands = pokemon_repo.fetch_abilities(_conn(), ko)
        ability = cands[0] if cands else None
    return team.build_pokemon(
        _conn(), ko_name=ko,
        sp_values=spec.get("sp") or [0] * 6,
        ko_nature=spec.get("nature") or NEUTRAL_NATURE,
        ability=ability,
        item=spec.get("item"),
        moves=[move_ko] if move_ko else None,
        rank=spec.get("rank"),
        allow_mega=True,
    )


def calc_damage(attacker, defender, move, weather=None, terrain=None,
                is_critical=False, is_doubles=False):
    """데미지 난수 16개와 확정 N타 판정.

    attacker/defender 는 {"name", "ability", "item", "nature", "sp", "rank"}.
    name 만 필수다.
    """
    en = move_repo.fetch_en_name(_conn(), normalize(move))
    if en is None:
        return {"error": f"'{move}' 이라는 기술이 없습니다."}
    m = move_repo.fetch_detail(_conn(), en)

    try:
        atk = _build(attacker, move)
        dfn = _build(defender)
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
        "공격자": {"이름": atk.name, "특성": atk.ability, "도구": atk.item,
                   "성격": atk.nature,
                   "공격": atk.stats.a, "특수공격": atk.stats.c},
        "방어자": {"이름": dfn.name, "특성": dfn.ability, "도구": dfn.item,
                   "성격": dfn.nature, "체력": dfn.stats.h,
                   "방어": dfn.stats.b, "특수방어": dfn.stats.d},
        "기술": {"이름": m["ko_name"], "타입": m["type"],
                 "분류": m["category"], "위력": m["power"]},
        "상성배수": damage.type_multiplier(m["type"], dfn.types, rules.chart),
        "데미지": {"최소": dmg.min, "최대": dmg.max,
                   "비율": f"{lo:.1f}~{hi:.1f}%", "난수16": dmg.rolls},
        "판정": ko["text"],
    }


def power_index(pokemon, moves):
    """결정력 — 공격 실능 × 위력 × 자속. 기술끼리 견주는 데 쓴다."""
    try:
        p = _build(pokemon)
    except ValueError as e:
        return {"error": str(e)}

    out = []
    for ko in moves:
        en = move_repo.fetch_en_name(_conn(), normalize(ko))
        if en is None:
            out.append({"기술": ko, "error": "없는 기술"})
            continue
        m = move_repo.fetch_detail(_conn(), en)
        out.append({"기술": m["ko_name"], "타입": m["type"],
                    "분류": m["category"], "위력": m["power"],
                    "자속": m["type"] in p.types,
                    "결정력": damage.power_index(p, m)})
    out.sort(key=lambda x: -x.get("결정력", 0))
    return {"포켓몬": p.name, "공격": p.stats.a, "특수공격": p.stats.c,
            "기술별": out}


def bulk_index(pokemon):
    """내구력 — 체력 × 방어, 체력 × 특수방어."""
    try:
        p = _build(pokemon)
    except ValueError as e:
        return {"error": str(e)}
    b = damage.bulk_index(p)
    return {"포켓몬": p.name, "체력": p.stats.h,
            "방어": p.stats.b, "특수방어": p.stats.d,
            "물리내구": b["physical"], "특수내구": b["special"]}


# ─────────────────────────────────────────────────────────────
# 내 엔트리
# ─────────────────────────────────────────────────────────────

def my_team():
    """등록해둔 6마리의 실제 스펙과 실능치."""
    out = []
    for spec in team.load_specs():
        try:
            p = team.build_pokemon(_conn(), **spec)
        except ValueError as e:
            out.append({"이름": spec.get("ko_name"), "error": str(e)})
            continue
        out.append({
            "이름": p.name, "타입": list(p.types), "특성": p.ability,
            "도구": p.item, "성격": p.nature,
            "실능": {STAT_LABELS[k]: p.stats[k] for k in STAT_ORDER},
            "기술": p.moves,
        })
    return {"엔트리": out}


def team_weaknesses():
    """엔트리 전체의 타입 상성 표. 어느 타입에 몇 마리가 약한가.

    "우리 팀이 뭐에 약해" 를 모델이 상성표를 외워서 답하면 반드시 틀린다.
    18타입 × 6마리를 여기서 곱해준다.
    """
    chart = _rules().chart
    types = sorted({t for (t, _) in chart})
    members = []
    for spec in team.load_specs():
        meta = pokemon_repo.fetch_meta(_conn(), normalize(spec["ko_name"]))
        members.append((normalize(spec["ko_name"]),
                        tuple(t for t in (meta["type1"], meta["type2"]) if t)))

    table = {}
    for t in types:
        hit = {name: damage.type_multiplier(t, tt, chart) for name, tt in members}
        table[t] = {
            "2배이상": [n for n, m in hit.items() if m >= 2],
            "반감이하": [n for n, m in hit.items() if 0 < m <= 0.5],
            "무효": [n for n, m in hit.items() if m == 0],
        }
    # 위험한 순서로. 2배 이상 맞는 머릿수가 많은 타입이 곧 팀의 구멍이다.
    order = sorted(types, key=lambda t: -len(table[t]["2배이상"]))
    return {"엔트리": [n for n, _ in members],
            "타입별": {t: table[t] for t in order}}


def usage_stats(pokemon, format="Singles"):
    """랭크배틀 채용률 — 기술·도구·특성·성격·SP·함께 쓰는 포켓몬."""
    en = _en_of(pokemon)
    if en is None:
        return {"error": f"'{pokemon}' 은(는) 포챔스 목록에 없습니다."}
    return meta.usage_of(_conn(), en, ko_name=normalize(pokemon),
                         fmt=format if format in ("Singles", "Doubles")
                         else "Singles")


# ─────────────────────────────────────────────────────────────
# 스키마 — 모델에게 주는 설명이다. 타입만 맞추면 도구를 잘못 고른다.
# ─────────────────────────────────────────────────────────────

_SIDE = {
    "type": "object",
    "description": "포켓몬 한 마리. name 만 필수이고 나머지는 기본값"
                   "(SP 0 · 성실 · 1번 특성 · 도구 없음)으로 채워진다.",
    "properties": {
        "name": {"type": "string", "description": "한국어 이름. 메가폼도 된다"},
        "ability": {"type": "string", "description": "한국어 특성 이름"},
        "item": {"type": "string", "description": "한국어 도구 이름"},
        "nature": {"type": "string", "description": "한국어 성격. 기본 성실"},
        "sp": {"type": "array", "items": {"type": "integer"},
               "description": "체력·공격·방어·특공·특방·스피드 순 6개. 총 66"},
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
        "properties": {"name": {**_STR, "description": "한국어 이름"}},
        "required": ["name"]}),

    "search_pokemon": (search_pokemon, {
        "description": "조건으로 포켓몬을 추린다. '불꽃 타입 중 스피드가 빠른' "
                       "처럼 한 마리가 아니라 후보를 찾을 때 쓴다.",
        "properties": {
            "type": {**_STR, "description": "영문 타입. fire, water, dragon …"},
            "min_total": {"type": "integer", "description": "종족값 합 하한"},
            "order_by": {**_STR, "description":
                         "정렬 기준. 체력/공격/방어/특수공격/특수방어/스피드/종족값합"},
            "limit": {"type": "integer", "description": "최대 개수. 기본 15"}},
        "required": []}),

    "type_effectiveness": (type_effectiveness, {
        "description": "어떤 타입 기술이 그 포켓몬에게 몇 배로 들어가는지. "
                       "상성을 외워서 답하지 말고 반드시 이걸 부른다.",
        "properties": {
            "attack_type": {**_STR, "description": "영문 타입. fire, ground …"},
            "defender": {**_STR, "description": "방어하는 포켓몬의 한국어 이름"}},
        "required": ["attack_type", "defender"]}),

    "find_move": (find_move, {
        "description": "기술 하나의 위력·타입·분류·효과.",
        "properties": {"name": {**_STR, "description": "한국어 기술 이름"}},
        "required": ["name"]}),

    "moves_of": (moves_of, {
        "description": "그 포켓몬이 배울 수 있는 기술 전부. "
                       "'이 기술 배울 수 있어?' 를 추측하지 말고 이걸로 확인한다.",
        "properties": {"pokemon": {**_STR, "description": "한국어 이름"}},
        "required": ["pokemon"]}),

    "find_ability": (find_ability, {
        "description": "특성 하나의 효과와 그 특성을 가진 포켓몬들.",
        "properties": {"name": {**_STR, "description": "한국어 특성 이름"}},
        "required": ["name"]}),

    "find_item": (find_item, {
        "description": "도구 하나의 효과와 분류.",
        "properties": {"name": {**_STR, "description": "한국어 도구 이름"}},
        "required": ["name"]}),

    "calc_damage": (calc_damage, {
        "description": "데미지와 확정 N타 판정. '몇 방에 죽나', '버티나', "
                       "'원킬 나나' 류의 질문은 전부 이걸 부른다. "
                       "직접 곱셈하지 말 것 — 본가 공식은 반올림이 특이해서 "
                       "손으로 계산하면 확정/난수 판정이 뒤집힌다.",
        "properties": {
            "attacker": _SIDE, "defender": _SIDE,
            "move": {**_STR, "description": "한국어 기술 이름"},
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
                      "description": "한국어 기술 이름들"}},
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
            "pokemon": {**_STR, "description": "한국어 이름"},
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
