"""채용률을 우리 DB 와 맞춰 돌려준다.

usage_source.py 가 받아온 영문 행과 DB 의 한국어 이름을 잇는 자리다.
받아오기(usage_source.py)와 잇기(여기)를 나눈 이유는, 네트워크가 안 될 때와
DB 에 없을 때가 서로 다른 문제이기 때문이다. 한 일의 두 단계라 이름도
usage 로 맞춰 두고, 받아오는 쪽만 _source 를 붙여 가른다.

── 영문 이름을 그대로 두고 한국어를 곁들인다 ──
  채용률 쪽은 사람이 읽는 표기(Focus Sash), 우리 DB 는 PokeAPI 슬러그
  (focus-sash) 를 쓴다. 소문자로 낮추고 공백을 하이픈으로 바꾸고 기호를
  털면 대부분 맞는다.

  예전에는 한국어로 바꿔 내보내고 못 바꾼 것만 영문을 덧붙였다. 지금은
  반대다 — name 은 늘 영문이고 ko_name 이 곁에 붙는다. 이 결과를 읽는
  것이 LLM 인데, 모델은 Focus Sash 를 기합의띠보다 훨씬 잘 알고, 한국어
  이름은 스스로 번역하지 말고 ko_name 을 글자 그대로 옮겨야 하기
  때문이다. 못 찾으면 ko_name 은 null 이다. 칸을 빼지는 않는다 — 빼면
  모델이 그 칸이 있다는 것 자체를 잊는다.

── 왜 category 를 우리 키로 바꾸나 ──
  move / held_item / stat_alignment / stat_points 를 그대로 내보내면
  화면과 LLM 이 각자 옮긴다. 한 곳에서 바꾼다. 복수형으로 두는 것은
  값이 목록이라서다.
"""

import re

from . import usage_source
from ..db.repositories import lookup_repo

CATEGORY_KEY = {
    "move": "moves",
    "held_item": "items",
    "ability": "abilities",
    "teammate": "teammates",
    "stat_alignment": "natures",
    "stat_points": "spreads",
}

# 채용률 category -> 한국어 이름을 찾을 DB 테이블
CATEGORY_TABLE = {
    "move": "moves",
    "held_item": "items",
    "ability": "abilities",
    "teammate": "pokemons",
    "stat_alignment": "pokemon_natures",
}

SP_COLUMNS = [("hp_points", "hp"), ("attack_points", "atk"),
              ("defense_points", "def"), ("sp_atk_points", "spa"),
              ("sp_def_points", "spd"), ("speed_points", "spe")]

# 성격 보정 칸이 사람 읽는 표기(Sp. Atk)로 온다. 여섯 개뿐이라 표 둘로
# 끝난다. 키 쪽을 배분(spread)과 같은 이름으로 맞춰야, 한 답 안에서
# "atk 에 몰고 atk 를 올린다" 가 같은 낱말로 읽힌다.
STAT_KEY = {"HP": "hp", "Attack": "atk", "Defense": "def",
            "Sp. Atk": "spa", "Sp. Def": "spd", "Speed": "spe"}
STAT_KO = {"HP": "체력", "Attack": "공격", "Defense": "방어",
           "Sp. Atk": "특수공격", "Sp. Def": "특수방어", "Speed": "스피드"}


def slugify(en_display):
    """'Focus Sash' -> 'focus-sash'. 우리 DB 의 name 형식으로 맞춘다."""
    s = en_display.lower().replace("’", "").replace("'", "").replace(".", "")
    s = re.sub(r"[\s_]+", "-", s.strip())
    return re.sub(r"[^a-z0-9-]", "", s)


def _ko_maps(conn):
    maps = {cat: lookup_repo.fetch_ko_map(conn, table)
            for cat, table in CATEGORY_TABLE.items()}
    # 함께 쓰는 포켓몬은 저쪽 표기(Mimikyu, Alolan Raichu)로 온다. 우리
    # 이름은 mimikyu-disguised, raichu-alola 라 슬러그만으로는 안 맞는다.
    maps["_pokemon_alt"] = _pokemon_alt_map(maps["teammate"])
    return maps


def _pokemon_alt_map(ko_by_name):
    """슬러그로 못 찾을 때 쓸 보조 표 둘.

    tokens  이름을 토큰 집합으로. 머리꼬리가 뒤집혀도 맞는다.
              alolan-raichu {alola,raichu} <-> raichu-alola {raichu,alola}
    base    첫 마디만. 저쪽이 폼을 안 나눌 때 쓴다.
              Mimikyu -> mimikyu -> mimikyu-disguised

    base 는 두 번 훑는다. 한 번에 하면 raichu-alola 가 raichu 자리를
    먼저 차지해서 "Raichu" 가 알로라로 잡힌다.
    """
    by_tokens = {usage_source.tokens(name): ko for name, ko in ko_by_name.items()}
    by_base = {}
    for want_plain in (True, False):
        for name, ko in ko_by_name.items():
            plain = "-" not in name
            if want_plain != plain:
                continue
            by_base.setdefault(name.split("-")[0], ko)
    return {"tokens": by_tokens, "base": by_base}


def _pokemon_ko(maps, en_display):
    """저쪽 포켓몬 표기 -> 우리 한국어 이름. 못 찾으면 None."""
    slug = slugify(en_display)
    alt = maps["_pokemon_alt"]
    return (maps["teammate"].get(slug)
            or alt["tokens"].get(usage_source.tokens(slug))
            or alt["base"].get(slug.split("-")[0]))


# ─────────────────────────────────────────────────────────────
# 저쪽 이름 -> 우리 pokemons.name
#
# usage_of() 가 쓰는 usage_source.battle_name() 과 방향이 반대다. 저쪽은
# 우리보다 폼을 덜 나누므로(우리 317 : 저쪽 236) 이 방향은 1:N 이고,
# 후보 중 하나를 골라야 한다. 기록을 쌓을 때만 필요하다.
# ─────────────────────────────────────────────────────────────


def pokemon_index(rows):
    """pokemons 행들을 이름 맞추기용으로 한 번 접어 둔다.

    236번 부르는 자리라 매번 317줄을 토큰으로 쪼개지 않게 미리 만든다.
    """
    return [(r["name"], r.get("id"), usage_source.tokens(r["name"]))
            for r in rows]


def _default_form(candidates):
    """후보가 여럿이면 기본 폼을 고른다.

    PokeAPI 는 폼 변이에 10000번대 id 를 준다. 그래서 가장 작은 id 가
    기본 폼이다 — castform(351) 이 castform-sunny(10013) 를 이긴다.
    저쪽이 폼을 안 나누는 경우(Gourgeist, Morpeko)에 여기서 갈린다.
    """
    return min(candidates, key=lambda c: (c[1] if c[1] is not None else 10 ** 9))[0]


def resolve_pokemon(index, battle_name):
    """저쪽 battleName -> 우리 pokemons.name. 못 붙이면 None.

    세 번 시도한다. 앞의 것이 걸리면 뒤는 보지 않는다.

      1. 토큰이 똑같은 것        Alolan Raichu -> raichu-alola
         메가는 여기서 저절로 걸러진다. 우리 charizard-mega-x 는 토큰이
         하나 더 많아 Charizard 와 같지 않다.
      2. 우리 토큰이 저쪽에 다 들어 있는 것 중 가장 많이 겹치는 것
         Fan Rotom -> rotom-fan (rotom 도 걸리지만 겹치는 토큰이 적다)
      3. 첫 낱말이 같은 것       Gourgeist -> gourgeist-average
         저쪽이 폼을 안 나눠서 우리 이름이 모두 두 낱말인 경우다.
    """
    want = tokens = usage_source.tokens(battle_name)

    exact = [c for c in index if c[2] == want]
    if exact:
        return _default_form(exact)

    subset = [c for c in index if c[2] and c[2] <= tokens]
    if subset:
        widest = max(len(c[2]) for c in subset)
        return _default_form([c for c in subset if len(c[2]) == widest])

    head = slugify(battle_name).split("-")[0]
    base = [c for c in index if c[0].split("-")[0] == head]
    return _default_form(base) if base else None


def usage_of(conn, en_name, ko_name=None, fmt="Singles", top=8):
    """한 마리의 채용률. 못 받으면 {"error": ...}.

    en_name 은 우리 DB 의 pokemons.name (PokeAPI 슬러그) 이다.
    """
    who = ko_name or en_name
    name, was_mega = usage_source.battle_name(en_name)
    if name is None:
        return {"error": f"채용률 자료에 '{who}' 가 없습니다. "
                         "랭크배틀 표본이 적거나 아직 안 실린 폼일 수 있습니다."}

    data = usage_source.fetch_battle(name, fmt)
    if data is None:
        return {"error": f"'{who}' 의 {fmt} 자료를 못 받았습니다. "
                         "채용률 서버에 연결하지 못했고 캐시도 없습니다."}

    maps = _ko_maps(conn)
    out = {}
    for row in data.get("rows", []):
        cat = row.get("category")
        if cat not in CATEGORY_KEY:
            continue
        bucket = out.setdefault(CATEGORY_KEY[cat], [])
        if len(bucket) >= top:
            continue

        if cat == "stat_points":
            bucket.append({
                "spread": {key: row.get(col) or 0 for col, key in SP_COLUMNS},
                "percent": row.get("percentage_value"),
            })
            continue

        en = row.get("name") or ""
        ko = (_pokemon_ko(maps, en) if cat == "teammate"
              else maps.get(cat, {}).get(slugify(en)))
        # name 은 찾았든 못 찾았든 받은 영문 그대로다. 예전처럼 못 찾은
        # 것만 영문으로 두면 한 목록 안에 두 모양이 섞여, 읽는 쪽이
        # 어느 칸이 이름인지 매번 다시 판단해야 한다.
        entry = {"name": en, "ko_name": ko,
                 "percent": row.get("percentage_value")}
        if cat == "stat_alignment":
            up, down = row.get("stat_up"), row.get("stat_down")
            entry["up"] = STAT_KEY.get(up)
            entry["up_ko_name"] = STAT_KO.get(up)
            entry["down"] = STAT_KEY.get(down)
            entry["down_ko_name"] = STAT_KO.get(down)
        bucket.append(entry)

    result = {
        "pokemon": en_name,
        "ko_name": ko_name,
        "counted_as": data.get("pokemon"),
        "format": fmt,
        "season": data.get("season"),
        "source": "championsbattledata.com (게임 내 배틀 데이터를 옮긴 팬 사이트)",
    }
    if was_mega:
        # 밝히지 않으면 "메가갸라도스 채용률" 로 읽힌다. 실제로는 원종 통계다.
        result["note"] = ("메가는 배틀 중 상태라 채용률이 원종으로 집계됩니다. "
                          "아래는 원종 기준이고, 메가로 가는 비율은 "
                          "items 항목의 메가스톤 비율로 보세요.")
    result.update(out)
    return result
