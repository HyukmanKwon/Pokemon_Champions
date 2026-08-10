"""채용률을 우리 DB 와 맞춰 한국어로 돌려준다.

usage.py 가 받아온 영문 행과 DB 의 한국어 이름을 잇는 자리다.
받아오기(usage.py)와 잇기(여기)를 나눈 이유는, 네트워크가 안 될 때와
DB 에 없을 때가 서로 다른 문제이기 때문이다.

── 영문 -> 우리 이름 ──
  채용률 쪽은 사람이 읽는 표기(Focus Sash), 우리 DB 는 PokeAPI 슬러그
  (focus-sash) 를 쓴다. 소문자로 낮추고 공백을 하이픈으로 바꾸고 기호를
  털면 대부분 맞는다. 안 맞는 것은 한국어로 못 바꾸고 영문 그대로 둔다 —
  빈칸으로 두면 "그런 기술이 없다" 로 오해된다.

── 왜 category 를 우리 말로 바꾸나 ──
  move / held_item / stat_alignment / stat_points 를 그대로 내보내면
  화면과 LLM 이 각자 번역하게 된다. 한 곳에서 바꾼다.
"""

import re

from .. import usage
from ..db.repositories import lookup_repo

CATEGORY_KO = {
    "move": "기술",
    "held_item": "도구",
    "ability": "특성",
    "teammate": "함께쓰는포켓몬",
    "stat_alignment": "성격",
    "stat_points": "SP배분",
}

# 채용률 category -> 한국어 이름을 찾을 DB 테이블
CATEGORY_TABLE = {
    "move": "moves",
    "held_item": "items",
    "ability": "abilities",
    "teammate": "pokemons",
    "stat_alignment": "pokemon_natures",
}

SP_COLUMNS = [("hp_points", "체력"), ("attack_points", "공격"),
              ("defense_points", "방어"), ("sp_atk_points", "특수공격"),
              ("sp_def_points", "특수방어"), ("speed_points", "스피드")]

# 성격 보정 칸이 영문으로 온다. 여섯 개뿐이라 표 하나로 끝난다.
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
    by_tokens = {usage.tokens(name): ko for name, ko in ko_by_name.items()}
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
            or alt["tokens"].get(usage.tokens(slug))
            or alt["base"].get(slug.split("-")[0]))


def usage_of(conn, en_name, ko_name=None, fmt="Singles", top=8):
    """한 마리의 채용률. 못 받으면 {"error": ...}.

    en_name 은 우리 DB 의 pokemons.name (PokeAPI 슬러그) 이다.
    """
    who = ko_name or en_name
    name, was_mega = usage.battle_name(en_name)
    if name is None:
        return {"error": f"채용률 자료에 '{who}' 가 없습니다. "
                         "랭크배틀 표본이 적거나 아직 안 실린 폼일 수 있습니다."}

    data = usage.fetch_battle(name, fmt)
    if data is None:
        return {"error": f"'{who}' 의 {fmt} 자료를 못 받았습니다. "
                         "채용률 서버에 연결하지 못했고 캐시도 없습니다."}

    maps = _ko_maps(conn)
    out = {}
    for row in data.get("rows", []):
        cat = row.get("category")
        if cat not in CATEGORY_KO:
            continue
        bucket = out.setdefault(CATEGORY_KO[cat], [])
        if len(bucket) >= top:
            continue

        if cat == "stat_points":
            bucket.append({
                "배분": {label: row.get(col) or 0 for col, label in SP_COLUMNS},
                "비율": row.get("percentage_value"),
            })
            continue

        en = row.get("name") or ""
        ko = (_pokemon_ko(maps, en) if cat == "teammate"
              else maps.get(cat, {}).get(slugify(en)))
        entry = {"이름": ko or en, "비율": row.get("percentage_value")}
        if ko is None:
            # 못 바꾼 것은 영문임을 밝힌다. 조용히 두면 오타로 보인다.
            entry["영문"] = en
        if cat == "stat_alignment":
            up, down = row.get("stat_up"), row.get("stat_down")
            entry["보정"] = (f"↑{STAT_KO.get(up, up) or '-'} "
                             f"↓{STAT_KO.get(down, down) or '-'}")
        bucket.append(entry)

    result = {
        "포켓몬": who,
        "집계대상": data.get("pokemon"),
        "포맷": fmt,
        "시즌": data.get("season"),
        "출처": "championsbattledata.com (게임 내 배틀 데이터를 옮긴 팬 사이트)",
    }
    if was_mega:
        # 밝히지 않으면 "메가갸라도스 채용률" 로 읽힌다. 실제로는 원종 통계다.
        result["주의"] = ("메가는 배틀 중 상태라 채용률이 원종으로 집계됩니다. "
                          "아래는 원종 기준이고, 메가로 가는 비율은 "
                          "'도구' 항목의 메가스톤 비율로 보세요.")
    result.update(out)
    return result
