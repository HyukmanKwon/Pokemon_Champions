"""도구가 돌려줄 값을 모델이 읽을 모양으로.

tools.py 는 "이름을 찾고 아래층을 부른다" 만 한다. 무엇을 어느 칸에 담을지는
여기가 정한다.

── 여기 있는 함수는 전부 s(Session)를 안 받는다 ──
  받는 순간 조회가 섞였다는 뜻이다. 한국어 이름을 붙이는 일은 conn 이
  필요하므로 tools.py 에 남고(_named), 여기는 이미 붙은 값을 담기만 한다.

── 모양의 원칙 두 가지 ──
  1. 영문과 한국어를 짝으로 준다. 모델이 다음 호출에 이름을 되짚어 넣어야
     하는데, 한국어만 주면 우리 DB 의 영문 키를 모른다. 반대로 영문만 주면
     사용자에게 옮겨 적을 말이 없다.

  2. 안 물어본 칸은 싣지 않는다. 목록을 주는 도구(search_pokemon ·
     moves_of)는 종족값 여섯 칸을 빼고 요약만 준다. 열다섯 줄에 여섯 칸씩
     실으면 그 호출 하나가 천 토큰이고, 뒤로 턴이 이어질수록 매번 다시
     읽힌다. 자세히 볼 때 쓰는 도구가 따로 있다.

── interfaces/api/views.py 와 왜 따로인가 ──
  같은 자료를 담지만 겹치는 칸이 사실상 없다. 계산 결과의 한 쪽을 보면

      화면용   name · types(아이콘 URL) · stats · rank · condition
      모델용   name(영문) · ko_name · ability+ability_ko_name · item+… · nature+…

  공통은 name 하나다. 화면은 아이콘이 필요하고 모델에게는 쓸모없다.
  모델은 영·한 짝이 필요하고 화면은 한국어만 쓴다. 한 함수로 만들면
  "누가 부르는가" 를 인자로 넘기게 되고, 그때부터 칸 하나를 고칠 때마다
  양쪽을 다 확인해야 한다.
"""

from ..domain import STAT_ORDER

# 능력치 키를 모델이 아는 말로. 우리 DB 는 h·a·b·c·d·s 지만 모델은
# 영어권 약어로 학습돼 있어서 spa/spd 를 그대로 이해한다.
STAT_KEYS = {"h": "hp", "a": "atk", "b": "def",
             "c": "spa", "d": "spd", "s": "spe"}


def stats(source):
    """능력치 6칸. Stats 도 dict 행도 같이 받는다."""
    return {STAT_KEYS[k]: source[k] for k in STAT_ORDER}


def bst(row):
    return sum(row[k] for k in STAT_ORDER)


# ─────────────────────────────────────────────────────────────
# 도감
# ─────────────────────────────────────────────────────────────

def pokemon_detail(row):
    """한 마리의 종족값·타입·특성·메가 관계."""
    return {
        "name": row["name"], "ko_name": row["ko_name"],
        "pokemon_id": row["pokemon_id"],
        "types": [t for t in (row["type1"], row["type2"]) if t],
        "base_stats": stats(row),
        "bst": bst(row),
        "abilities": [{"name": a["name"], "ko_name": a["ko_name"],
                       "is_hidden": a["is_hidden"],
                       "description": a["description"]}
                      for a in row["abilities"]],
        "height_m": row["height"], "weight_kg": row["weight"],
        "can_mega": row["can_mega"], "is_mega": row["is_mega"],
        "mega_forms": [{"name": f["mega_name"], "ko_name": f["mega_ko_name"]}
                       for f in row["mega_forms"]],
    }


def pokemon_brief(row, order_by=None, order_key=None):
    """목록 한 줄. 종족값 여섯 칸 대신 총합만 싣는다.

    정렬 기준으로 삼은 칸은 실어 준다 — "스피드 빠른 순" 을 물어놓고
    스피드가 안 보이면 다시 물어야 한다.
    """
    out = {"name": row["name"], "ko_name": row["ko_name"],
           "types": [t for t in (row["type1"], row["type2"]) if t],
           "bst": bst(row)}
    if order_key:
        out[order_by] = row[order_key]
    return out


def search_results(rows, limit, order_by=None, order_key=None):
    return {"total": len(rows), "shown": min(limit, len(rows)),
            "results": [pokemon_brief(r, order_by, order_key)
                        for r in rows[:limit]]}


def move_detail(row):
    return {"name": row["name"], "ko_name": row["ko_name"],
            "type": row["type"], "category": row["category"],
            "power": row["power"], "accuracy": row["accuracy"],
            "pp": row["pp"], "priority": row["priority"],
            "description": row["description"]}


def move_brief(row):
    return {"name": row["name"], "ko_name": row["ko_name"],
            "type": row["type"], "category": row["category"],
            "power": row["power"]}


def moves_of(en, ko_name, rows, limit):
    return {"pokemon": en, "ko_name": ko_name,
            "total": len(rows), "shown": min(limit, len(rows)),
            "moves": [move_brief(m) for m in rows[:limit]]}


def ability_detail(row):
    return {"name": row["name"], "ko_name": row["ko_name"],
            "description": row["description"], "effect_en": row["effect"],
            "pokemon": [{"name": p["name"], "ko_name": p["ko_name"]}
                        for p in row["pokemons"]]}


def item_detail(row):
    return {"name": row["name"], "ko_name": row["ko_name"],
            "category": row["category"], "description": row["description"]}


# ─────────────────────────────────────────────────────────────
# 타입 상성
# ─────────────────────────────────────────────────────────────

# 배수를 나열하는 순서. 큰 것부터 — 모델이 먼저 읽는 줄이 약점이어야 한다.
_MULT_ORDER = ("4", "2", "1", "0.5", "0.25", "0")


def type_matchup(en, ko_name, types, grouped):
    """배수별로 묶어서. 열여덟 줄을 나열하면 모델이 다시 정렬해야 한다."""
    return {
        "pokemon": en, "ko_name": ko_name,
        "types": list(types),
        # 키가 곧 배수다. "이 타입으로 치면 몇 배" 를 뜻한다.
        "damage_taken": {k: grouped[k] for k in _MULT_ORDER if k in grouped},
    }


def type_effectiveness(attack_type, en, ko_name, types, multiplier):
    return {"attack_type": attack_type,
            "defender": en, "defender_ko_name": ko_name,
            "defender_types": list(types),
            "multiplier": multiplier}


def team_weaknesses(members, table, order, ko_of):
    """타입별로 몇 마리가 약한가. 위험한 순서로 늘어놓는다.

    타입별 목록에는 영문 이름만 담는다. 여섯 마리를 세 칸에 세 번씩
    한국어까지 적으면 표가 배로 불어난다 — 한국어는 team 에 한 번 있고
    모델은 거기서 짝을 찾는다.
    """
    return {"team": [{"name": n, "ko_name": ko_of[n]} for n, _ in members],
            "by_type": {t: table[t] for t in order}}


# ─────────────────────────────────────────────────────────────
# 계산
# ─────────────────────────────────────────────────────────────

def residual(ko):
    """턴 끝 정산이 있었을 때만 턴별 한 줄을 붙인다. 없으면 빈 dict.

    안 붙이면 모델이 "확정 2턴" 을 보고 두 방이면 죽는다고 옮겨 적는다.
    """
    if not ko["residual"]:
        return {}
    return {"residual": [
        {"turn": i, "text": t["tick"].text, "net": t["tick"].net}
        for i, t in enumerate(ko["turns"], 1) if t["tick"]
    ]}


def damage(shot, attacker_side, defender_side):
    """데미지 난수 16개와 확정 N타 판정.

    양쪽 side 는 tools 가 만들어 넘긴다 — 한국어 이름을 붙이는 데 conn 이
    필요해서 여기서 만들 수 없다.
    """
    m, dmg = shot.move, shot.damage
    lo, hi = shot.percent()

    return {
        "attacker": {**attacker_side,
                     "atk": shot.attacker.stats.a,
                     "spa": shot.attacker.stats.c},
        "defender": {**defender_side,
                     "hp": shot.defender.stats.h,
                     "def": shot.defender.stats.b,
                     "spd": shot.defender.stats.d},
        "move": {"name": m["name"], "ko_name": m["ko_name"], "type": m["type"],
                 "category": m["category"], "power": m["power"]},
        "type_effect": shot.effect,
        "damage": {"min": dmg.min, "max": dmg.max,
                   "percent": f"{lo:.1f}~{hi:.1f}%", "rolls": dmg.rolls},
        # 판정은 키만 영어다. 값은 사람에게 그대로 보여줄 문장이라 한국어다.
        "verdict": shot.ko["text"],
        **residual(shot.ko),
        **usage_note(shot.attacker_usage or shot.defender_usage),
    }


def usage_note(usage):
    """채용률로 채운 칸이 있으면 한 줄로. 없으면 빈 dict.

    percent 를 그대로 주지 않고 날짜와 채운 칸만 준다. 모델에게는 "언제
    자료로 무엇을 채웠나" 면 충분하고, 칸마다 %를 실으면 답마다 길어진다.
    자세한 채용률은 usage_stats 도구가 따로 있다.
    """
    if not usage:
        return {}
    return {"filled_from_usage": {
        "date": usage["date"],
        "format": usage["format"],
        "fields": sorted(usage["percent"]),
    }}


def power(got):
    """결정력. 없는 기술은 그 줄에만 적는다 — 웹처럼 전부 막지 않는다.

    모델은 기술 이름을 기억에서 꺼내 오타를 내는데, 넷 중 하나 틀렸다고
    전부 막으면 다시 물어보느라 한 바퀴를 더 쓴다.
    """
    moves = []
    for sc in got.moves:
        if sc.row is None:
            moves.append({"name": sc.asked, "ko_name": None,
                          "error": "없는 기술"})
            continue
        moves.append({**move_brief(sc.row),
                      "stab": sc.stab, "power_index": sc.index})

    p = got.pokemon
    return {"pokemon": got.en, "ko_name": p.name,
            "atk": p.stats.a, "spa": p.stats.c, "moves": moves,
            **usage_note(got.usage)}


def bulk(got):
    p = got.pokemon
    return {"pokemon": got.en, "ko_name": p.name, "hp": p.stats.h,
            "def": p.stats.b, "spd": p.stats.d,
            # 소수점 아래는 모델이 읽을 일이 없다. 비교용 값이라 반올림한다.
            "physical_bulk": round(got.physical),
            "special_bulk": round(got.special),
            "divided_by": got.factor,
            **usage_note(got.usage)}


# ─────────────────────────────────────────────────────────────
# 채용률
# ─────────────────────────────────────────────────────────────

def ranking(rows, fmt):
    """메타 순위 목록. 1위부터.

    percent 를 안 싣는다 — 저쪽이 포켓몬별 사용률 %를 안 주고 순위만 준다.
    없는 숫자를 자리만 만들어 두면 모델이 채운다.
    """
    if not rows:
        return {"error": "순위 자료가 아직 없습니다. "
                         "python -m scripts.etl.sync.usage --rankings-only"}
    return {
        "format": fmt,
        "date": rows[0]["taken_on"].isoformat(),
        "note": "순위만 있고 사용률 %는 저쪽이 주지 않습니다.",
        "ranking": [{"position": r["position"],
                     "name": r["pokemon_name"] or r["battle_name"],
                     "ko_name": r["ko_name"]}
                    for r in rows],
    }


def rank_note(row, total_key="total"):
    """그 포켓몬의 메타 순위 한 줄. 없으면 빈 dict.

    usage_stats 에 같이 실어, 모델이 기술 채용률(지진 99.3%)을 포켓몬
    사용률로 오해하지 않게 한다. 실제로 그 오해가 있었다 — 답할 자료가
    없으면 모델은 옆에 있는 숫자로 채운다.
    """
    if not row:
        return {}
    return {"meta_rank": {"position": row["position"],
                          "of": row[total_key],
                          "date": row["taken_on"].isoformat()}}


# ─────────────────────────────────────────────────────────────
# 덱
# ─────────────────────────────────────────────────────────────

def decks(book):
    active = next((d for d in book["decks"] if d["id"] == book["active"]), None)
    return {"active": active["name"] if active else None,
            "decks": [{"name": d["name"], "members": d["members"]}
                      for d in book["decks"]]}
