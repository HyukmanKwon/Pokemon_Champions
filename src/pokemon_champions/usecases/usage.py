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
from ..db.repositories import (lookup_repo, nature_repo, pokemon_repo,
                               usage_repo)

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


# STAT_KO 는 저쪽 표기(Sp. Atk)가 열쇠다. DB 에서 읽은 값은 이미 우리
# 키(spa)라 그쪽으로도 찾을 수 있어야 한다.
STAT_KO_BY_KEY = {STAT_KEY[k]: v for k, v in STAT_KO.items()}


def _num(v):
    """NUMERIC(4,1) 은 Decimal 로 온다. JSON 이 못 담으므로 float 으로.

    round 를 한 번 더 거는 이유는 float(Decimal("40.5")) 이 40.5 로 잘
    떨어지지만, 소수 한 자리라는 것을 여기서 못 박아 두면 나중에 자릿수가
    늘었을 때 화면이 40.500000000000004 를 그린다.
    """
    return None if v is None else round(float(v), 1)


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


# 성격 보정 칸 이름을 DB 의 한 글자로. pokemon_natures.up/down 이
# a·b·c·d·s 라서 STAT_KEY 의 결과(atk·spe …)를 한 번 더 옮겨야 한다.
# HP 는 성격이 안 건드리므로 여기 없다.
NATURE_STAT = {"atk": "a", "def": "b", "spa": "c", "spd": "d", "spe": "s"}

# 보정이 없는 성격. 저쪽은 넷으로 나눠 주지만 우리 표에는 하나다.
NEUTRAL_NATURE_KO = "성실"


def popular_spec(conn, en_name, fmt="Singles"):
    """DB 에 쌓인 가장 최근 채용률에서 "가장 많이 쓰인 한 벌" 을 만든다.

    돌려주는 것은 battle.build_side 가 받는 스펙과 같은 모양이다.

        {"ability": "까칠한피부", "item": "기합의띠", "nature": "발랄",
         "sp": [2, 32, 0, 0, 0, 32], "moves": [...],
         "usage": {"date": ..., "percent": {...}}}

    자료가 없으면 빈 dict. 그때는 부르는 쪽이 예전대로 무보정을 쓴다 —
    채용률이 없다고 계산을 못 하게 만들면 새로 나온 폼을 아예 못 잰다.

    ── 왜 사이트가 아니라 DB 인가 ──
      usage_of() 는 저쪽에 물어 오늘 값을 받는다. 이쪽은 우리가 쌓아둔
      것에서 읽는다. 계산기 기본값은 매번 네트워크를 타면 안 된다 —
      한 번 계산에 여섯 마리를 세우면 여섯 번 나간다.

    ── 못 찾은 이름은 버린다 ──
      우리 표에 없는 도구·기술이 1위일 수 있다. 그대로 스펙에 넣으면
      validate_spec 이 막아서 계산 자체가 실패한다. 채우지 못한 칸은
      비워 두고, 무엇을 못 채웠는지는 usage.unmatched 에 남긴다.
    """
    got = usage_repo.fetch_top_build(conn, en_name, fmt)
    if not got:
        return {}

    maps = _ko_maps(conn)
    spec, percent, unmatched = {}, {}, []

    def ko_of(cat, en):
        return maps.get(cat, {}).get(slugify(en or ""))

    # 카테고리 -> 스펙의 어느 칸에 담나
    SINGLE = {"held_item": "item", "ability": "ability"}

    for r in got:
        cat, en, pct = r["category"], r["name"], r["percent"]

        if cat == "stat_points":
            spec["sp"] = [r[col] or 0 for col, _ in SP_COLUMNS]
            percent["sp"] = pct

        elif cat == "stat_alignment":
            # DB 의 stat_up/stat_down 은 이미 우리 키다(spe · spa).
            # sync_usage.to_row 가 넣을 때 STAT_KEY 로 옮겨 두었으므로
            # 여기서 또 옮기면 None 이 되어 전부 성실로 떨어진다.
            up = NATURE_STAT.get(r["stat_up"])
            down = NATURE_STAT.get(r["stat_down"])
            ko = nature_repo.fetch_by_mods(conn, up, down)
            if ko is None:
                unmatched.append(("nature", en))
            else:
                spec["nature"] = ko
                percent["nature"] = pct

        elif cat in SINGLE:
            key = SINGLE[cat]
            ko = ko_of(cat, en)
            if ko is None:
                unmatched.append((key, en))
            else:
                spec[key] = ko
                percent[key] = pct

        elif cat == "move":
            ko = ko_of(cat, en)
            if ko is None:
                unmatched.append(("move", en))
            else:
                spec.setdefault("moves", []).append(ko)
                percent.setdefault("moves", []).append(pct)

    if spec:
        spec["usage"] = {
            "date": got[0]["snapshot_date"].isoformat(),
            "season": got[0]["season"],
            "format": fmt,
            "percent": percent,
            "unmatched": unmatched,
        }
    return spec


def ranking_from_db(conn, fmt="Singles", days=7):
    """전체 메타 순위 + 며칠 전 대비 변화. 1위부터.

    usage_repo 가 준 것에 한국어 이름과 타입을 붙인다. 화면이 순위표를
    그리려면 타입 배지가 필요한데 usage_rankings 에는 이름밖에 없다.
    """
    got = usage_repo.fetch_ranking(conn, fmt=fmt, limit=None)
    if not got:
        return {}

    delta = usage_repo.fetch_rank_delta(conn, fmt=fmt, days=days)
    meta = {r["name"]: r for r in pokemon_repo.fetch_list(conn)}

    out = []
    for r in got:
        d = delta.get(r["battle_name"]) or {}
        row = meta.get(r["pokemon_name"]) or {}
        out.append({
            "position": r["position"],
            "name": r["pokemon_name"],
            "ko_name": r["ko_name"],
            # 우리 로스터에 없는 폼이면 저쪽 표기라도 보여준다. 빼 버리면
            # 순위에 구멍이 생겨 "13위가 왜 없지" 가 된다.
            "battle_name": r["battle_name"],
            "types": [t for t in (row.get("type1"), row.get("type2")) if t],
            "delta": d.get("delta"),
        })

    first = got[0]
    sample = next(iter(delta.values()), {})
    return {
        "format": fmt,
        "date": first["taken_on"].isoformat(),
        "compared_to": (sample.get("compared_to").isoformat()
                        if sample.get("compared_to") else None),
        "total": len(out),
        "ranking": out,
    }


def detail_from_db(conn, en_name, ko_name=None, fmt="Singles", top=10):
    """한 마리의 채용 내역. DB 에 쌓인 가장 최근 스냅샷에서 읽는다.

    ── usage_of() 와 무엇이 다른가 ──
      저쪽은 사이트에 물어 오늘 값을 받는다. 이쪽은 우리가 쌓아둔 것을
      읽는다. 화면이 목록에서 한 마리씩 누를 때마다 남의 서버를 두드릴
      수는 없고, 순위(usage_rank)는 DB 에만 있다.

      돌려주는 모양은 usage_of() 와 최대한 맞춘다. 같은 자료를 읽는 코드가
      받아온 경로에 따라 두 벌로 갈리지 않게 하려는 것이다.
    """
    got = usage_repo.fetch_detail(conn, en_name, fmt=fmt, top=top)
    if not got:
        return {"error": f"'{ko_name or en_name}' 의 {fmt} 채용률이 "
                         "DB 에 아직 없습니다. "
                         "python -m scripts.etl.sync_usage --backfill"}

    maps = _ko_maps(conn)
    out = {}
    for r in got:
        cat = r["category"]
        if cat not in CATEGORY_KEY:
            continue
        bucket = out.setdefault(CATEGORY_KEY[cat], [])

        if cat == "stat_points":
            bucket.append({
                "spread": {key: r[col] or 0 for col, key in SP_COLUMNS},
                "percent": _num(r["percent"]),
            })
            continue

        en = r["name"] or ""
        # linked_name 이 있으면 그것을 쓴다. 적재할 때 맞춰 둔 값이라
        # 여기서 슬러그를 다시 만들 필요가 없다.
        linked = r["linked_name"]
        ko = (maps.get(cat, {}).get(linked) if linked
              else maps.get(cat, {}).get(slugify(en)))
        entry = {"name": linked or en, "ko_name": ko,
                 "percent": _num(r["percent"])}
        if cat == "stat_alignment" and ko is None and not r["stat_up"]:
            # 저쪽은 무보정 성격을 넷으로 준다(Hardy · Docile · Serious ·
            # Quirky). 레귤레이션 M-B 는 보정이 같은 것을 하나로 접어
            # "성실" 만 두므로, 이름을 못 찾는 게 아니라 우리 쪽에 없는
            # 것이다. 영문 그대로 두면 화면에 Hardy 가 뜬다.
            entry["ko_name"] = ko = NEUTRAL_NATURE_KO
        if cat == "stat_alignment":
            entry["up"] = r["stat_up"]
            entry["up_ko_name"] = STAT_KO_BY_KEY.get(r["stat_up"])
            entry["down"] = r["stat_down"]
            entry["down_ko_name"] = STAT_KO_BY_KEY.get(r["stat_down"])
        bucket.append(entry)

    first = got[0]
    return {
        "pokemon": en_name,
        "ko_name": ko_name,
        "format": fmt,
        "season": first["season"],
        "date": first["snapshot_date"].isoformat(),
        "meta_rank": first["usage_rank"],
        "source": "championsbattledata.com (게임 내 배틀 데이터를 옮긴 팬 사이트)",
        **out,
    }
