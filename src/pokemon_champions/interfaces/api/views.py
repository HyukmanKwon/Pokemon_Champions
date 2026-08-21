"""조립 층이 준 값을 화면이 읽을 JSON 모양으로.

app.py 는 라우트만 갖는다. "무엇을 부를지" 는 라우트가 정하고, "어떤 칸에
담아 보낼지" 는 여기가 정한다.

── 왜 갈랐나 ──
  app.py 가 833줄이 됐다. 그중 밑줄 헬퍼 18개 가운데 13개가 행을 JSON 으로
  옮겨 적는 일이었고, /api/calc/damage 라우트는 76줄 중 60줄이 dict 리터럴
  이었다. 실제 로직은 battle.one_hit() 한 줄이다.

  그렇게 되면 파일을 열어도 이 앱이 무엇을 하는지 안 보인다. 라우트 목록이
  dict 사이에 파묻힌다.

── 여기 있는 것과 없는 것 ──
  있는 것: 칸 이름 · 아이콘 URL · 한국어 표기 고르기 · 기본값 문구("없음")
  없는 것: 계산 · SQL · HTTP 상태코드 · 조립

  이 파일의 함수는 전부 이미 조회·계산이 끝난 값을 받는다. conn 을 받는
  함수가 생기면 그 조회는 usecases/ 로 가야 한다는 신호다.

── agent/views.py 와 왜 합치지 않나 ──
  같은 자료를 담지만 필요한 칸이 다르다. 화면은 아이콘 URL 과 타입 배지가
  필요하고 모델은 그것들이 쓸모없다. 반대로 모델은 영문·한국어를 짝으로
  받아야 이름을 되짚을 수 있는데 화면은 한국어만 쓴다.

  둘을 한 함수로 만들면 인자로 "누가 부르는가" 를 넘기게 되고, 그때부터
  칸 하나를 고칠 때마다 양쪽을 다 확인해야 한다. 지금은 서로 모른다.
"""

from ... import assets
from ...domain import STAT_LABELS, STAT_ORDER
from ...text import normalize


# ─────────────────────────────────────────────────────────────
# 조각
# ─────────────────────────────────────────────────────────────

def stats_dict(stats):
    d = stats.as_dict()
    d["total"] = stats.total()
    return d


def type_badges(*names):
    """타입 이름들을 {이름, 아이콘} 목록으로. None 은 건너뛴다(단일타입)."""
    return [{"name": t, "icon": assets.url_type_icon(t)} for t in names if t]


def move_brief(name, move_type):
    return {"name": name, "type": move_type,
            "icon": assets.url_type_icon(move_type)}


# ─────────────────────────────────────────────────────────────
# 도감 — 행 하나에 그림 주소를 붙인다
#
# repositories 가 아니라 여기서 붙인다. 어떤 크기의 그림을 쓰는지는 화면
# 사정이지 DB 의 성질이 아니다. 목록과 상세가 같은 함수를 쓴다.
# ─────────────────────────────────────────────────────────────

def decorate_pokemon(row):
    row["types"] = type_badges(row.get("type1"), row.get("type2"))
    row["icon"] = assets.url_pokemon_icon(row.get("id"))
    row["sprite"] = assets.url_pokemon_sprite(row.get("id"))
    return row


def decorate_move(row):
    row["icon"] = assets.url_type_icon(row["type"])
    return row


def decorate_item(row):
    row["icon"] = assets.url_item_sprite(row["name"])
    return row


# 상세 응답에는 목록에 없는 칸이 붙는다(배우는 포켓몬, 메가 관계 …).
# 여기서만 다르므로 종류마다 따로 적는다.

def detail_pokemon(row):
    decorate_pokemon(row)
    for m in row["moves"]:
        m["icon"] = assets.url_type_icon(m["type"])
    for f in row["mega_forms"]:
        f["item_icon"] = assets.url_item_sprite(f["item_name"])
    if row["mega_of"]:
        row["mega_of"]["item_icon"] = assets.url_item_sprite(
            row["mega_of"]["item_name"])
    return row


def detail_move(row):
    decorate_move(row)
    row["learners"] = [decorate_pokemon(p) for p in row["learners"]]
    return row


def detail_ability(row):
    row["pokemons"] = [decorate_pokemon(p) for p in row["pokemons"]]
    return row


def detail_item(row):
    decorate_item(row)
    if row["mega"]:
        row["mega"]["base_icon"] = assets.url_pokemon_icon(
            row["mega"]["base_id"])
        row["mega"]["mega_icon"] = assets.url_pokemon_icon(
            row["mega"]["mega_id"])
    return row


# ─────────────────────────────────────────────────────────────
# 전역 목록
# ─────────────────────────────────────────────────────────────

def types(ko_names):
    """{영문: 한국어} 18줄을 화면용 목록으로."""
    return [{"name": t, "ko_name": ko_names[t], "icon": assets.url_type_icon(t)}
            for t in sorted(ko_names)]


def natures(rows):
    """성격 21종. 이름만 주면 무엇이 오르내리는지 알 수 없어 능력치를 붙인다.

    성실은 up·down 이 둘 다 None 이다.
    """
    return [{"name": n["ko_name"],
             "up": STAT_LABELS.get(n["up"]),
             "down": STAT_LABELS.get(n["down"])}
            for n in rows]


def calc_rules(rules):
    """날씨·필드·상태이상 선택지와 능력치 표기. 드롭다운을 이걸로 채운다."""
    def pairs(rows):
        return [{"name": k, "ko_name": v["ko_name"]} for k, v in rows.items()]

    return {
        "weathers": pairs(rules.weathers),
        "terrains": pairs(rules.terrains),
        "conditions": pairs(rules.conditions),
        "stat_order": list(STAT_ORDER),
        "stat_labels": {k: STAT_LABELS[k] for k in STAT_ORDER},
    }


# ─────────────────────────────────────────────────────────────
# 채용률
# ─────────────────────────────────────────────────────────────

def usage_ranking(got):
    """메타 순위표. 235줄에 타입 배지와 순위 변화를 붙인다.

    delta 는 오른 만큼 양수다(3위 -> 1위 가 +2). 화면이 부호를 다시
    뒤집지 않게 조립 층에서 이미 맞춰 두었다.
    """
    if not got:
        return {"ranking": [], "total": 0,
                "note": "채용률 자료가 아직 없습니다. "
                        "python -m scripts.etl.sync_usage --backfill"}
    return {
        "format": got["format"],
        "date": got["date"],
        "compared_to": got["compared_to"],
        "total": got["total"],
        "ranking": [{"position": r["position"],
                     # 우리 로스터에 없는 폼은 name 이 없다. 그때는 저쪽
                     # 표기라도 보여준다 — 빼면 순위에 구멍이 생긴다.
                     "name": r["name"],
                     "ko_name": r["ko_name"] or r["battle_name"],
                     "icon": assets.url_pokemon_icon(r["pokemon_id"]),
                     "types": type_badges(*r["types"]),
                     "delta": r["delta"]}
                    for r in got["ranking"]],
    }


def usage_detail(got):
    """한 마리의 채용 내역. 갈래마다 순위대로.

    아이콘을 붙이는 갈래와 안 붙이는 갈래가 갈린다 — 기술은 타입 배지,
    도구는 스프라이트, 팀원은 아이콘이고 성격·SP 는 그림이 없다.
    """
    if "error" in got:
        return got

    def named(rows, icon=None):
        """이름 · 비율에 그림을 붙인다.

        갈래마다 그림이 다른 표에서 온다 — 기술은 타입 배지, 도구는
        스프라이트, 팀원은 포켓몬 아이콘이다. 조립 층이 필요한 열쇠
        (type · pokemon_id)를 이미 실어 보내므로 여기서는 URL 만 만든다.
        """
        out = []
        for r in rows:
            e = {"name": r["ko_name"] or r["name"],
                 "key": r["name"],          # 눌러서 도감으로 건너뛸 때 쓴다
                 "percent": r["percent"]}
            if icon and r["name"]:
                e["icon"] = icon(r["name"])
            if r.get("type"):
                e["icon"] = assets.url_type_icon(r["type"])
                e["type"] = r["type"]
            if r.get("pokemon_id"):
                e["icon"] = assets.url_pokemon_icon(r["pokemon_id"])
            out.append(e)
        return out

    return {
        "pokemon": got["pokemon"],
        "ko_name": got["ko_name"],
        "format": got["format"],
        "season": got["season"],
        "date": got["date"],
        "meta_rank": got["meta_rank"],
        "sprite": assets.url_pokemon_sprite(got["pokemon_id"]),
        "types": type_badges(*got["types"]),
        # 한국어 이름이 없는 폼은 종족값을 못 읽는다. 칸은 남기고 null 로
        # 둔다 — 빼 버리면 읽는 쪽이 그 칸이 있다는 것을 잊는다.
        "base": stats_dict(got["base"]) if got.get("base") else None,
        "source": got["source"],
        "moves": named(got.get("moves", [])),
        "items": named(got.get("items", []), assets.url_item_sprite),
        "abilities": named(got.get("abilities", [])),
        "teammates": named(got.get("teammates", [])),
        "natures": [{"name": r["ko_name"] or r["name"],
                     "percent": r["percent"],
                     "up": r["up_ko_name"], "down": r["down_ko_name"]}
                    for r in got.get("natures", [])],
        "spreads": [{"spread": [r["spread"][k] for k in
                                ("hp", "atk", "def", "spa", "spd", "spe")],
                     "percent": r["percent"]}
                    for r in got.get("spreads", [])],
    }


# ─────────────────────────────────────────────────────────────
# 계산기
# ─────────────────────────────────────────────────────────────

def side(pokemon, asked, usage=None):
    """계산에 실제로 쓰인 한 쪽. 무엇으로 쟀는지를 같이 돌려준다.

    asked 는 화면이 보낸 CalcSide 다. 랭크와 상태이상은 BattlePokemon 이
    아니라 요청에 실려 오므로 그쪽에서 가져온다.

    usage 가 있으면 안 말한 칸을 채용률로 채웠다는 뜻이다. 화면이 "내가
    정한 값" 과 "남들이 많이 쓰는 값" 을 갈라 보여줄 수 있게 그대로 싣는다.
    """
    return {
        "usage": usage,
        "name": pokemon.name,
        "types": type_badges(*pokemon.types),
        "stats": {k: pokemon.stats[k] for k in STAT_ORDER},
        "ability": pokemon.ability,
        "item": pokemon.item,
        "nature": pokemon.nature,
        "rank": asked.rank,
        "condition": asked.condition,
    }


def power(got, asked):
    """결정력 — 기술별 지표."""
    return {
        "side": side(got.pokemon, asked, got.usage),
        "moves": [{"name": s.row["ko_name"] or s.row["name"],
                   "type": s.row["type"],
                   "icon": assets.url_type_icon(s.row["type"]),
                   "category": s.row["category"],
                   "power": s.row["power"],
                   "stab": s.stab,
                   "index": s.index}
                  for s in got.moves],
    }


def bulk(got, asked):
    """내구력. 나눈 상수까지 주는 것은 화면이 계산식을 그대로 보여주기 때문이다."""
    return {
        "side": side(got.pokemon, asked, got.usage),
        "bulk": {"physical": got.physical, "special": got.special,
                 "factor": got.factor},
    }


def damage(shot, attacker_asked, defender_asked):
    """한 방의 전부 — 난수 16개 · 확정 N타 · 턴별 정산."""
    move, ctx, dmg, ko = shot.move, shot.ctx, shot.damage, shot.ko
    lo, hi = shot.percent()

    return {
        "attacker": side(shot.attacker, attacker_asked, shot.attacker_usage),
        "defender": side(shot.defender, defender_asked, shot.defender_usage),
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
        #
        # 랭크와 HP 는 이제 Pokemon 에 있고 나머지는 ctx 에 있다. 화면은
        # "무엇으로 쟀나" 를 한 덩어리로 읽으므로 칸 이름은 그대로 둔다.
        "context": {
            "weather": ctx.weather,
            "terrain": ctx.terrain,
            "attacker_rank": shot.attacker.rank or {},
            "defender_rank": shot.defender.rank or {},
            "is_critical": ctx.is_critical,
            "reflect": ctx.reflect,
            "light_screen": ctx.light_screen,
            "is_doubles": ctx.is_doubles,
            "attacker_hp": shot.attacker.hp,
            "defender_hp": shot.defender.hp,
        },
        "damage": {
            "min": dmg.min,
            "max": dmg.max,
            "rolls": dmg.rolls,
            "percent_min": lo,
            "percent_max": hi,
            "defender_hp": shot.defender.stats.h,
        },
        "ko": {
            "text": ko["text"],
            "guaranteed": ko["guaranteed"],
            "possible": ko["possible"],
            "residual": ko["residual"],
            "turns": [
                {"damage_min": t["damage"].min,
                 "damage_max": t["damage"].max,
                 "hp_before": t["hp_before"],
                 # 턴 끝 정산. 아무 일도 없었으면 null 이다. 합계만 주면
                 # "왜 한 턴 빨리 죽었나" 를 화면에서 되짚을 수 없다.
                 "tick": (None if t["tick"] is None else
                          {"net": t["tick"].net, "text": t["tick"].text})}
                for t in ko["turns"]
            ],
        },
    }


# ─────────────────────────────────────────────────────────────
# 엔트리 슬롯
#
# 조회는 usecases 가 끝내고 여기는 담기만 한다.
# ─────────────────────────────────────────────────────────────

def mega(form):
    """메가진화 후 모습. 스톤을 안 지녔으면 조립 층이 None 을 준다."""
    if form is None:
        return None
    return {
        "name": form["ko_name"],
        "sprite": assets.url_pokemon_sprite(form["id"]),
        "types": type_badges(form["type1"], form["type2"]),
        "base": stats_dict(form["base"]),
        "stats": {k: form["stats"][k] for k in STAT_ORDER},
        "ability": form["ability"],
    }


def slot(index, spec, data):
    """엔트리 한 칸. data 는 usecases.team.slot_data() 가 모아 준 것."""
    return {
        "index": index,
        "spec": spec,
        "name": normalize(spec["ko_name"]),
        "sprite": assets.url_pokemon_sprite(data["meta"]["id"]),
        "types": type_badges(data["meta"]["type1"], data["meta"]["type2"]),
        "base": stats_dict(data["base"]),
        "sp": stats_dict(data["sp"]),
        "stats": {k: data["stats"][k] for k in STAT_ORDER},
        "nature": {
            "name": normalize(spec["ko_nature"]),
            "up": STAT_LABELS.get(data["nature_up"]),
            "down": STAT_LABELS.get(data["nature_down"]),
        },
        "ability": {"name": spec["ability"], "effect": data["ability_effect"]},
        "item": (normalize(spec["item"]) if spec.get("item") else None) or "없음",
        "condition": spec.get("condition") or "정상",
        "moves": [move_brief(m["name"], m["type"]) for m in data["moves"]],
        # 고를 수 있는 것들. 포켓몬마다 다르므로 슬롯별로 실어 보낸다.
        # (도구는 포켓몬을 안 가리므로 /api/items 로 따로 한 번만 받는다)
        "selectable_abilities": data["selectable_abilities"],
        "learnable_moves": data["learnable_moves"],
        # 메가스톤을 지녔을 때만 값이 있다. 그때만 화면에 On/Off 버튼이 뜬다.
        "mega": mega(data["mega_form"]),
        # 메가는 가능한데 스톤을 안 지닌 경우의 안내
        "mega_stones": data["mega_stones"],
    }
