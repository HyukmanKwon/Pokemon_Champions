"""도구 본문 — 모델이 부를 수 있는 함수들.

  모델에게 주는 설명(무엇을 언제 부르는가)은 schemas.py 에 있다. 여기는
  그 도구가 실제로 하는 일이다. 두 파일의 열쇠가 어긋나면 아래 HANDLERS
  옆에서 import 때 잡는다.

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

from dataclasses import dataclass

from ..db.repositories import (ability_repo, item_repo, move_repo,
                               pokemon_repo, rules_repo)
from ..domain import STAT_ORDER
from ..services import damage, team, usage
from ..services.damage import Rules
from ..text import normalize
from ..usecases import battle, naming, roster
from . import schemas

# domain 의 능력치 글자를 모델이 읽을 이름으로. 종족값·실능 dict 의 키가
# 전부 이 여섯이다. 순서는 STAT_ORDER 가 정한다.
STAT_KEYS = {"h": "hp", "a": "atk", "b": "def",
             "c": "spa", "d": "spd", "s": "spe"}

@dataclass
class Session:
    """도구 한 벌이 보는 바깥 세상 — 커넥션 · 참조표 · 지금 보는 덱.

    ── 왜 모듈에 안 들고 있나 ──
      예전에는 tools 가 스스로 connect() 해서 모듈 전역에 캐시했다. CLI 는
      진입점이 하나라 그게 맞았지만, 웹에 붙이는 순간 두 가지가 깨진다.

      하나는 커넥션이 두 벌이 되는 것이다. app.py 가 이미 하나 열어뒀는데
      도구가 또 연다. 다른 하나가 더 나쁘다 — FastAPI 는 sync 라우트를
      threadpool 에서 돌리는데, psycopg2 커넥션은 스레드 간 공유가 안전하지
      않다. 모듈 전역이면 동시 요청이 같은 커넥션을 나눠 쓴다.

      그래서 부르는 쪽이 만들어 넘긴다. db/connection.py 첫머리의
      "진입점에서 한 번 열고 인자로 내려보낸다" 가 여기까지 온 것이다.

    ── deck_id ──
      이 대화가 볼 덱. None 이면 활성 덱이다. 모델이 고르는 값이 아니라
      부르는 쪽이 묶는 값이다 — 웹은 화면이 보고 있는 덱을 넣는다.
    """

    conn: object
    rules: object = None
    deck_id: str = None


def load_rules(conn):
    """상성표 324행 + 날씨 + 필드 + 상태이상. 한 번 읽어 세션 내내 돌려쓴다."""
    return Rules(
        chart=rules_repo.fetch_type_chart(conn),
        weathers=rules_repo.fetch_weathers(conn),
        terrains=rules_repo.fetch_terrains(conn),
        conditions=rules_repo.fetch_status_conditions(conn),
    )


def session(conn, deck_id=None, rules=None):
    """도구를 부를 준비가 된 세션. rules 를 이미 들고 있으면 넘겨서 아낀다."""
    return Session(conn=conn, rules=rules or load_rules(conn), deck_id=deck_id)


# ─────────────────────────────────────────────────────────────
# 이름 — usecases/naming 에 conn 을 얹어 부른다
# ─────────────────────────────────────────────────────────────

def _resolve(s, table, name):
    return naming.resolve(s.conn, table, name)


def _ko(s, table, en):
    return naming.ko(s.conn, table, en)


def _types_of(s, en):
    return naming.types_of(s.conn, en)


def _named(s, table, value, key="name"):
    """이름 한 칸을 영문 + 한국어 두 칸으로 편다.

        _named("items", "기합의띠")
            -> {"name": "focus-sash", "ko_name": "기합의띠"}
        _named("abilities", "rough-skin", "ability")
            -> {"ability": "rough-skin", "ability_ko_name": "까칠한피부"}

    칸 이름은 name 일 때만 ko_name 이고 나머지는 <칸>_ko_name 이다. 한
    dict 안에 이름이 여럿 들어가는 자리(공격자의 특성·도구·성격)가 있어서
    ko_name 하나로는 어느 것의 한국어인지 알 수 없다.

    이 모양은 모델에게 주는 것이라 여기 남는다 — naming 은 이름을 찾을
    뿐 누가 읽을 모양인지 모른다.

    못 찾은 이름은 받은 것을 그대로 둔다. 빈칸으로 만들면 "그런 게 없다"
    로 읽히는데, 실제로는 우리 표에 아직 안 실린 것일 수 있다.
    """
    en = _resolve(s, table, value)
    ko_key = "ko_name" if key == "name" else f"{key}_ko_name"
    return {key: en or value, ko_key: _ko(s, table, en)}


def _stats(source):
    """능력치 6칸을 모델이 읽을 키로. Stats 도 dict 행도 같이 받는다."""
    return {STAT_KEYS[k]: source[k] for k in STAT_ORDER}


# ─────────────────────────────────────────────────────────────
# 도감
# ─────────────────────────────────────────────────────────────

def find_pokemon(s, name):
    """한 마리의 종족값·타입·특성·메가 관계."""
    en = _resolve(s, "pokemons", name)
    if en is None:
        return {"error": f"'{name}' 은(는) 포켓몬 목록에 없습니다."}
    row = pokemon_repo.fetch_detail(s.conn, en)
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


def search_pokemon(s, type=None, min_total=None, order_by=None, limit=8):
    """조건에 맞는 포켓몬 목록. 비교·후보 추리기용.

    ── 종족값 여섯 칸을 안 싣는다 ──
      후보를 추릴 때 필요한 건 "누가 있나" 지 여섯 칸 전부가 아니다.
      열다섯 마리에 여섯 칸씩 실으면 이 호출 하나가 천 토큰을 넘고, 그
      뒤로 턴이 이어질수록 그걸 매번 다시 읽는다. 한 마리를 자세히 볼
      때는 find_pokemon 이 있다.

      정렬 기준으로 삼은 칸은 실어 준다. "스피드 빠른 순" 을 물어놓고
      스피드가 안 보이면 다시 물어야 한다.
    """
    rows = list(naming.rows_of(s.conn, "pokemons").values())
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

    def one(r):
        out = {"name": r["name"], "ko_name": r["ko_name"],
               "types": [t for t in (r["type1"], r["type2"]) if t],
               "bst": sum(r[k] for k in STAT_ORDER)}
        if key:
            out[order_by] = r[key]
        return out

    return {"total": len(rows), "shown": min(limit, len(rows)),
            "results": [one(r) for r in rows[:limit]]}


def type_matchup(s, pokemon):
    """그 포켓몬을 칠 때 18타입이 각각 몇 배로 들어가는가 — 한 번에 전부.

    ── 왜 한 타입씩이 아니라 통째로인가 ──
      type_effectiveness 만 있으면 모델이 "뭐에 약해?" 를 타입 하나씩
      찍어보며 푼다. 열여덟 번을 부를 리 없으니 서너 번 찍어보고 멈추고,
      확인 못 한 나머지는 기억으로 채운다. 실제로 리자몽에게 전기가
      2배인데 "중립" 이라고 답하는 일이 있었다.

      빈칸이 있으면 모델은 채운다. 프롬프트로 막을 게 아니라 빈칸이
      생기지 않게 만들어야 한다. 열여덟 개를 한 번에 주면 채울 자리가
      없다.

    배수별로 묶어서 돌려준다. 열여덟 줄을 나열하면 그 자체가 길고,
    모델이 다시 정렬해야 한다.
    """
    en = _resolve(s, "pokemons", pokemon)
    if en is None:
        return {"error": f"'{pokemon}' 은(는) 포켓몬 목록에 없습니다."}

    chart = s.rules.chart
    types = _types_of(s, en)
    grouped = {}
    for atk in sorted({t for (t, _) in chart}):
        mult = damage.type_multiplier(atk, types, chart)
        # 4.0 을 "4" 로. 소수점 없는 정수는 그대로 적어야 읽기 쉽다.
        key = f"{mult:g}"
        grouped.setdefault(key, []).append(atk)

    return {
        "pokemon": en, "ko_name": _ko(s, "pokemons", en),
        "types": list(types),
        # 키가 곧 배수다. "이 타입으로 치면 몇 배" 를 뜻한다.
        "damage_taken": {k: grouped[k]
                         for k in ("4", "2", "1", "0.5", "0.25", "0")
                         if k in grouped},
    }


def type_effectiveness(s, attack_type, defender):
    """기술 타입 하나가 그 포켓몬에게 몇 배로 들어가는가.

    타입을 이미 정해놓고 확인만 할 때 쓴다. "뭐에 약해?" 처럼 열어놓고
    묻는 질문에는 type_matchup 이 맞다.
    """
    en = _resolve(s, "pokemons", defender)
    if en is None:
        return {"error": f"'{defender}' 은(는) 포켓몬 목록에 없습니다."}
    at = normalize(attack_type)
    types = _types_of(s, en)
    return {"attack_type": at,
            "defender": en, "defender_ko_name": _ko(s, "pokemons", en),
            "defender_types": list(types),
            "multiplier": damage.type_multiplier(at, types, s.rules.chart)}


def find_move(s, name):
    en = _resolve(s, "moves", name)
    if en is None:
        return {"error": f"'{name}' 이라는 기술이 없습니다."}
    m = move_repo.fetch_detail(s.conn, en)
    return {"name": m["name"], "ko_name": m["ko_name"], "type": m["type"],
            "category": m["category"], "power": m["power"],
            "accuracy": m["accuracy"], "pp": m["pp"],
            "priority": m["priority"], "description": m["description"]}


def moves_of(s, pokemon, type=None, category=None, min_power=None, limit=40):
    """그 포켓몬이 배울 수 있는 기술. 거르지 않으면 전부.

    move_repo.fetch_learnable 이 아니라 도감 상세를 쓴다. 그쪽은 ko_name
    을 열쇠로 잡고 한국어 이름이 없는 기술을 아예 빼는데, 여기서는 영문
    이름으로 찾고 한국어가 없으면 없다고 밝히면 된다.

    ── 왜 거르는 인자를 두나 ──
      한 마리가 예순 개 넘게 배운다. "불꽃 기술 뭐 배워?" 에 예순 개를
      통째로 돌려주면 그 호출 하나가 천 토큰이고, 모델은 거기서 다시
      골라야 한다. 거르는 일은 여기가 훨씬 잘한다.

    위력을 같이 싣는다. 그게 없으면 "제일 센 거" 를 묻는 순간 기술마다
    find_move 를 다시 부르게 된다.
    """
    en = _resolve(s, "pokemons", pokemon)
    if en is None:
        return {"error": f"'{pokemon}' 은(는) 포켓몬 목록에 없습니다."}

    rows = pokemon_repo.fetch_detail(s.conn, en)["moves"]
    if type:
        t = normalize(type)
        rows = [m for m in rows if m["type"] == t]
    if category:
        c = normalize(category)
        rows = [m for m in rows if m["category"] == c]
    if min_power:
        rows = [m for m in rows if (m["power"] or 0) >= min_power]
    rows.sort(key=lambda m: -(m["power"] or 0))

    return {"pokemon": en, "ko_name": _ko(s, "pokemons", en),
            "total": len(rows), "shown": min(limit, len(rows)),
            "moves": [{"name": m["name"], "ko_name": m["ko_name"],
                       "type": m["type"], "category": m["category"],
                       "power": m["power"]}
                      for m in rows[:limit]]}


def find_ability(s, name):
    en = _resolve(s, "abilities", name)
    if en is None:
        return {"error": f"'{name}' 이라는 특성이 없습니다."}
    a = ability_repo.fetch_detail(s.conn, en)
    return {"name": a["name"], "ko_name": a["ko_name"],
            "description": a["description"], "effect_en": a["effect"],
            "pokemon": [{"name": p["name"], "ko_name": p["ko_name"]}
                        for p in a["pokemons"]]}


def find_item(s, name):
    en = _resolve(s, "items", name)
    if en is None:
        return {"error": f"'{name}' 이라는 도구가 없습니다."}
    i = item_repo.fetch_detail(s.conn, en)
    return {"name": i["name"], "ko_name": i["ko_name"],
            "category": i["category"], "description": i["description"],
            "usable": i["usable"]}


# ─────────────────────────────────────────────────────────────
# 계산
# ─────────────────────────────────────────────────────────────

def _side_view(s, p, en):
    """계산에 실제로 쓰인 한 쪽을 모델이 읽을 모양으로.

    특성·도구·성격을 안 말하면 기본값으로 채워진다. 무엇으로 쟀는지를
    같이 돌려주지 않으면, 모델은 사용자가 말한 조건으로 계산된 줄 안다.
    """
    return {"name": en, "ko_name": p.name,
            **_named(s, "abilities", p.ability, "ability"),
            **_named(s, "items", p.item, "item"),
            **_named(s, "pokemon_natures", p.nature, "nature")}


def calc_damage(s, attacker, defender, move, weather=None, terrain=None,
                is_critical=False, is_doubles=False, toxic_turn=1):
    """데미지 난수 16개와 확정 N타 판정.

    attacker/defender 는 {"name", "ability", "item", "nature", "sp", "rank",
    "condition"}. name 만 필수다.

    ── 웹 계산기보다 받는 칸이 적다 ──
      조립 층은 남은 HP·접지·리플렉터·빛의장막도 받는다. 여기서 안 넘기는
      이유는 스키마에 그 칸이 없어서다. 모델이 채울 수 있게 열어줄지는
      따로 정할 일이라, 지금은 웹만 쓴다.

      상태이상만 열어 뒀다. "맹독 걸고 몇 턴이면 죽나" 는 사람이 실제로
      묻는 질문인데, 맹독은 턴마다 n/16 으로 세져서 모델이 데미지 하나를
      받아 곱셈으로 답할 수가 없다. 열지 않으면 틀린 답이 나온다.
    """
    try:
        shot = battle.one_hit(s.conn, s.rules, attacker, defender, move,
                              weather=weather, terrain=terrain,
                              is_critical=is_critical, is_doubles=is_doubles,
                              toxic_turn=toxic_turn)
    except ValueError as e:
        return {"error": str(e)}

    m, dmg = shot.move, shot.damage
    lo, hi = shot.percent()

    return {
        "attacker": {**_side_view(s, shot.attacker, shot.attacker_en),
                     "atk": shot.attacker.stats.a, "spa": shot.attacker.stats.c},
        "defender": {**_side_view(s, shot.defender, shot.defender_en),
                     "hp": shot.defender.stats.h, "def": shot.defender.stats.b,
                     "spd": shot.defender.stats.d},
        "move": {"name": m["name"], "ko_name": m["ko_name"], "type": m["type"],
                 "category": m["category"], "power": m["power"]},
        "type_effect": shot.effect,
        "damage": {"min": dmg.min, "max": dmg.max,
                   "percent": f"{lo:.1f}~{hi:.1f}%", "rolls": dmg.rolls},
        # 판정은 키만 영어다. 값은 사람에게 그대로 보여줄 문장이라 한국어다.
        "verdict": shot.ko["text"],
        # 턴 끝에 HP 가 움직였을 때만 붙인다. 안 붙이면 모델이 "확정 2턴"
        # 을 보고 두 방이면 죽는다고 옮겨 적는다.
        **_residual_view(shot.ko),
    }


def _residual_view(ko):
    """턴 끝 정산이 있었으면 턴별 한 줄을 붙인다. 없으면 아무것도 안 붙인다."""
    if not ko["residual"]:
        return {}
    return {"residual": [
        {"turn": i, "text": t["tick"].text, "net": t["tick"].net}
        for i, t in enumerate(ko["turns"], 1) if t["tick"]
    ]}


def power_index(s, pokemon, moves):
    """결정력 — 공격 실능 × 위력 × 자속. 기술끼리 견주는 데 쓴다."""
    try:
        got = battle.power(s.conn, pokemon, moves)
    except ValueError as e:
        return {"error": str(e)}

    # 웹은 없는 기술을 404 로 막지만 도구는 그 줄에만 적는다. 모델은 기술
    # 이름을 기억에서 꺼내 오타를 내는데, 넷 중 하나 틀렸다고 전부 막으면
    # 다시 물어보느라 한 바퀴를 더 쓴다.
    out = []
    for sc in got.moves:
        if sc.row is None:
            out.append({"name": sc.asked, "ko_name": None,
                        "error": "없는 기술"})
            continue
        m = sc.row
        out.append({"name": m["name"], "ko_name": m["ko_name"],
                    "type": m["type"], "category": m["category"],
                    "power": m["power"], "stab": sc.stab,
                    "power_index": sc.index})
    p = got.pokemon
    return {"pokemon": got.en, "ko_name": p.name,
            "atk": p.stats.a, "spa": p.stats.c, "moves": out}


def bulk_index(s, pokemon):
    """내구력 — 체력 × 방어 / 0.411, 체력 × 특수방어 / 0.411."""
    try:
        got = battle.bulk(s.conn, pokemon)
    except ValueError as e:
        return {"error": str(e)}
    p = got.pokemon
    return {"pokemon": got.en, "ko_name": p.name, "hp": p.stats.h,
            "def": p.stats.b, "spd": p.stats.d,
            # 소수점 아래는 모델이 읽을 일이 없다. 비교용 값이라 반올림한다.
            "physical_bulk": round(got.physical),
            "special_bulk": round(got.special),
            "divided_by": got.factor}


# ─────────────────────────────────────────────────────────────
# 내 덱
#
# ── 어느 덱인지는 모델이 고르지 않는다 ──
#   덱이 여러 벌이 되면서 "내 팀" 이 모호해졌다. 답은 사용자가 화면에서
#   보고 있는 덱이다. 그래서 기본은 활성 덱이고, 스키마에는 이름으로 부르는
#   선택 인자만 열어둔다 — id 를 노출하면 모델이 짐작해서 고른다.
#
#   웹에 붙일 때는 bind_deck() 으로 요청이 보고 있는 덱을 묶는다. conn 과
#   같은 취급이다.
# ─────────────────────────────────────────────────────────────

def _deck_id(s, deck=None):
    """모델이 이름으로 부른 덱 -> id. 못 찾으면 세션에 묶인 덱(없으면 활성).

    모델이 엉뚱한 이름을 대도 조용히 활성 덱으로 떨어진다. 없는 덱이라고
    되묻는 편이 정확하지만, 그러면 "내 팀 뭐야" 에 되묻는 일이 생긴다 —
    기본값이 사용자가 보고 있는 덱이라 틀릴 일이 거의 없다.
    """
    if deck:
        found = roster.by_name(roster.load(), deck)
        if found:
            return found["id"]
    return s.deck_id


def my_team(s, deck=None):
    """등록해둔 6마리의 실제 스펙과 실능치."""
    try:
        slots = roster.slots(_deck_id(s, deck))
    except LookupError as e:
        return {"error": str(e)}

    out = []
    for spec in slots:
        en = _resolve(s, "pokemons", spec.get("ko_name"))
        try:
            p = team.build_pokemon(s.conn, **spec)
        except ValueError as e:
            out.append({"name": en, "ko_name": spec.get("ko_name"),
                        "error": str(e)})
            continue
        out.append({
            "name": en, "ko_name": p.name, "types": list(p.types),
            **_named(s, "abilities", p.ability, "ability"),
            **_named(s, "items", p.item, "item"),
            **_named(s, "pokemon_natures", p.nature, "nature"),
            "stats": _stats(p.stats),
            "moves": [_named(s, "moves", mv) for mv in (p.moves or [])],
        })
    return {"team": out}


def list_decks(s):
    """저장해둔 덱 목록과 지금 보고 있는 덱."""
    book = roster.summary()
    active = next((d for d in book["decks"] if d["id"] == book["active"]), None)
    return {"active": active["name"] if active else None,
            "decks": [{"name": d["name"], "members": d["members"]}
                      for d in book["decks"]]}


def team_weaknesses(s, deck=None):
    """엔트리 전체의 타입 상성 표. 어느 타입에 몇 마리가 약한가.

    "우리 팀이 뭐에 약해" 를 모델이 상성표를 외워서 답하면 반드시 틀린다.
    18타입 × 6마리를 여기서 곱해준다.

    타입별 목록에는 영문 이름만 담는다. 여섯 마리 이름을 세 칸에 세 번씩
    한국어까지 적으면 표가 배로 불어난다. 한국어는 team 에 한 번 있고,
    모델은 거기서 짝을 찾는다.
    """
    chart = s.rules.chart
    types = sorted({t for (t, _) in chart})

    try:
        slots = roster.slots(_deck_id(s, deck))
    except LookupError as e:
        return {"error": str(e)}

    members = []
    for spec in slots:
        en = _resolve(s, "pokemons", spec["ko_name"])
        if en is None:
            return {"error": f"엔트리의 '{spec['ko_name']}' 을(를) "
                             "포켓몬 목록에서 찾지 못했습니다."}
        members.append((en, _types_of(s, en)))

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
    return {"team": [{"name": n, "ko_name": _ko(s, "pokemons", n)}
                     for n, _ in members],
            "by_type": {t: table[t] for t in order}}


def usage_stats(s, pokemon, format="Singles"):
    """랭크배틀 채용률 — 기술·도구·특성·성격·SP·함께 쓰는 포켓몬."""
    en = _resolve(s, "pokemons", pokemon)
    if en is None:
        return {"error": f"'{pokemon}' 은(는) 포켓몬 목록에 없습니다."}
    return usage.usage_of(s.conn, en, ko_name=_ko(s, "pokemons", en),
                          fmt=format if format in ("Singles", "Doubles")
                          else "Singles")


# ─────────────────────────────────────────────────────────────
# 부르기
# ─────────────────────────────────────────────────────────────

# {도구 이름: 실행할 함수}. 설명은 schemas.TOOLS 에 같은 열쇠로 있다.
HANDLERS = {
    "find_pokemon": find_pokemon,
    "search_pokemon": search_pokemon,
    "type_matchup": type_matchup,
    "type_effectiveness": type_effectiveness,
    "find_move": find_move,
    "moves_of": moves_of,
    "find_ability": find_ability,
    "find_item": find_item,
    "calc_damage": calc_damage,
    "power_index": power_index,
    "bulk_index": bulk_index,
    "my_team": my_team,
    "list_decks": list_decks,
    "team_weaknesses": team_weaknesses,
    "usage_stats": usage_stats,
}

# 함수와 설명이 두 파일로 갈렸으니 한쪽만 고치는 일이 생긴다. 스키마만
# 있고 함수가 없으면 모델이 부를 수 있는 도구가 터지고, 반대면 있는 도구를
# 아무도 모른다. 둘 다 import 할 때 잡는 편이 낫다.
_only_schema = set(schemas.TOOLS) - set(HANDLERS)
_only_handler = set(HANDLERS) - set(schemas.TOOLS)
if _only_schema or _only_handler:
    raise RuntimeError(
        f"도구 짝이 맞지 않습니다 — 설명만 있음: {sorted(_only_schema)}, "
        f"함수만 있음: {sorted(_only_handler)}")


def call(s, name, args):
    """도구 하나를 실행한다. 무엇이 잘못돼도 값으로 돌려준다."""
    fn = HANDLERS.get(name)
    if fn is None:
        return {"error": f"그런 도구가 없습니다: {name}"}
    try:
        return fn(s, **(args or {}))
    except TypeError as e:
        return {"error": f"인자가 맞지 않습니다: {e}"}
    except Exception as e:      # noqa: BLE001 - 루프가 죽으면 안 된다
        return {"error": f"{type(e).__name__}: {e}"}


