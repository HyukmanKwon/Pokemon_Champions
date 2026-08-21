"""PokeAPI 에서 받아 표 여섯 개를 만든다. 재구축의 유일한 수집 지점.

    pokemons          포켓몬 317마리
    pokemon_abilities 포켓몬-특성 연결   (포켓몬 응답에서 같이 나온다)
    moves             기술 498개
    move_stat_changes 능력 변화          (기술 응답에서 같이 나온다)
    abilities         특성               (포켓몬 응답이 대상을 정한다)
    items             도구
    pokemon_moves     포켓몬-기술 연결

전체 재구축은 약 1,900회 호출이다. 직접 돌리지 않고 build.py 가 부른다.

── 왜 한 파일인가 ──
  전에는 get/ 아래 다섯 파일 + parse_utils + translation + move_flags 로
  여덟 벌이었다. 여덟 다 "PokeAPI 를 부르고 INSERT 를 만든다" 하나를 하고
  있었고, 한 파일만 열어서는 어디까지가 수집인지 알 수 없었다. 표를 하나
  늘릴 때 파일을 몇 개 건드려야 하는지도 매번 세어 봐야 했다.

  갈라 두는 값은 "무엇이 어디서 오는가" 인데, 그건 이제 파일 이름이
  말한다 — pokeapi.py 는 남의 서버, build.py 는 코드에 적힌 값,
  sync_usage.py 는 날마다 쌓이는 것.

── 이 파일이 넘지 않는 선 ──
  build(conn) 은 INSERT 문자열만 돌려준다. 표를 만드는 SQL 은 schema.py
  한 곳에서만 나오고, DB 에 실행하는 것은 build.py 가 한다.

── 한국어 표기는 여기가 끝이 아니다 ──
  PokeAPI 의 한국어는 없거나 옛 세대 번역인 것이 있다. 그 교정은 DB 에
  직접 넣고 dump_sql 로 data/sql/ 에 굳힌다. 재구축은 출발점을 만들 뿐이다.
"""

import csv
import re

import requests

from pokemon_champions.config import CACHE_DIR

from .schema import sql_of, to_values

POKEMON_URL = "https://pokeapi.co/api/v2/pokemon"
MOVE_URL = "https://pokeapi.co/api/v2/move"
ABILITY_URL = "https://pokeapi.co/api/v2/ability"
ITEM_URL = "https://pokeapi.co/api/v2/item"
ITEM_CATEGORY_URL = "https://pokeapi.co/api/v2/item-category"


# ─────────────────────────────────────────────────────────────
# 받기 — 네 자원이 똑같이 하던 일
# ─────────────────────────────────────────────────────────────

def get_json(url):
    """GET 후 JSON 을 돌려준다. 200 이 아니면 None."""
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return None
    return resp.json()


def endpoint(base):
    """이름 하나를 받아 그 자원의 JSON 을 돌려주는 함수를 만든다.

        fetch_move = endpoint(MOVE_URL)
        fetch_move("fire-punch")        # -> dict 또는 None

    함수로 남기는 이유는 collect() 가 이걸 인자로 받기 때문이다.
    """
    def fetch(name):
        return get_json(f"{base}/{name}")
    return fetch


fetch_pokemon = endpoint(POKEMON_URL)
fetch_move = endpoint(MOVE_URL)
fetch_ability = endpoint(ABILITY_URL)
fetch_item = endpoint(ITEM_URL)


def collect(names, fetch, parse):
    """이름 목록을 하나씩 받아 파싱한 dict 목록으로 만든다.

    포켓몬·기술·특성·도구 넷이 같은 모양이다 — 받고, 못 받으면 건너뛰고,
    파싱하고, 한국어 이름이 비었으면 세어 두고, 진행 상황을 한 줄씩 찍는다.

    실패와 '한국어 이름 없음' 은 돌려주지 않고 여기서 세어 찍기만 한다.
    부르는 쪽이 그 값으로 하는 일이 없기 때문이다 — 실패가 0이 아닐 때
    이 SQL 을 쓸지 말지는 사람이 화면을 보고 정한다.

    parse 는 dict 를 돌려줘야 하고 그 안에 name·ko_name 이 있어야 한다.
    값 튜플이 아니라 dict 인 이유는, 기술처럼 한 응답에서 두 표가 나오는
    쪽이 COLUMNS 밖의 값도 같이 들고 가야 하기 때문이다. 튜플로 만드는
    것은 to_values 가 한다.

    ── 여기 안 들어오는 것 ──
      build_pokemon_moves 는 이름 하나가 행 수십 개가 되고 ko_name 이 없다.
      끼워 넣으려면 분기가 둘 생기고, 그러면 네 생성기가 공유하는 뜻이
      흐려진다. 그쪽은 자기 루프를 그대로 둔다.
    """
    rows, no_ko, failed = [], [], []
    for name in names:
        data = fetch(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue
        row = parse(data)
        if row["ko_name"] is None:
            no_ko.append(row["name"])
        rows.append(row)
        print(f"{row['name']} -> {row['ko_name']}")

    print(f"\n수집 {len(rows)}개")
    print(f"한국어 이름 없음: {len(no_ko)}개 - {no_ko}")
    print(f"실패: {len(failed)}개 - {failed}")
    return rows


def pick_korean(entries, key_text="name"):
    """names 리스트에서 한국어(ko) 항목을 고른다. 없으면 None."""
    for e in entries:
        if e["language"]["name"] == "ko":
            return e[key_text]
    return None


def pick_korean_flavor(entries, key="flavor_text"):
    """flavor_text_entries 에서 한국어 설명을 고른다(마지막=최신 우선).

    본문 키가 자료마다 다르다.
      - move, ability : "flavor_text"
      - item          : "text"
    """
    ko = [e[key] for e in entries if e["language"]["name"] == "ko"]
    if not ko:
        return None
    # 줄바꿈·제어문자 정리
    return ko[-1].replace("\n", " ").replace("\f", " ").strip()


def pick_english_effect(entries):
    """effect_entries 에서 영어 효과 설명(short_effect)을 고른다."""
    for e in entries:
        if e["language"]["name"] == "en":
            return e.get("short_effect", "").replace("\n", " ").strip()
    return None


def korean(data, flavor_key="flavor_text"):
    """한국어 이름·설명을 뽑는다. -> dict

    기술·특성·도구 셋이 같은 다섯 줄을 적고 있었다. 여기 값이 최종은
    아니다 — 파일 첫머리 "한국어 표기는 여기가 끝이 아니다" 참고.
    """
    return {
        "ko_name": pick_korean(data["names"]),
        "description": pick_korean_flavor(data["flavor_text_entries"],
                                          key=flavor_key),
    }

# ─────────────────────────────────────────────────────────────
# 기술 플래그 — PokeAPI CSV + 이름 규칙
# /move 응답에 flags 가 없다. 같은 저장소의 CSV 덤프에는 있어서
# 그쪽을 받아 쓰고, CSV 가 못 채우는 셋만 이름으로 추측한다.
# ─────────────────────────────────────────────────────────────

FLAGS = [
    "is_contact", "is_punch", "is_bite", "is_sound", "is_powder",
    "is_bullet", "is_wind", "is_slicing", "is_dance", "is_pulse",
    "is_gravity", "is_press",
]

FLAG_LABELS = {
    "is_contact": "접촉",
    "is_punch": "펀치",
    "is_bite": "물기",
    "is_sound": "소리",
    "is_powder": "가루",
    "is_bullet": "총알",
    "is_wind": "바람",
    "is_slicing": "베기",
    "is_dance": "춤",
    "is_pulse": "파동",
    "is_gravity": "상승",
    "is_press": "압박",
}

# ─────────────────────────────────────────────────────────────
# PokeAPI CSV
# ─────────────────────────────────────────────────────────────

FLAG_MAP_URL = ("https://raw.githubusercontent.com/PokeAPI/pokeapi/master/"
           "data/v2/csv/move_flag_map.csv")

FLAG_MAP_PATH = CACHE_DIR / "move_flag_map.csv"

# move_flags.csv 의 내용. 21줄이고 안 바뀌므로 받지 않는다.
# 우리가 쓰지 않는 flag(charge, protect, mirror ...)는 적지 않았다.
CSV_FLAG_IDS = {
    1: "is_contact",
    8: "is_punch",
    9: "is_sound",
    10: "is_gravity",
    15: "is_powder",
    16: "is_bite",
    17: "is_pulse",
    18: "is_bullet",
    21: "is_dance",
}

# CSV 가 채워 주지 않는 플래그. 항상 추측이다.
GUESS_ONLY = ["is_wind", "is_slicing", "is_press"]

_flag_map = None            # {move_id: {플래그: True}}


def _download_flag_map(force=False):
    """move_flag_map.csv 를 cache/ 에 받아 둔다. 있으면 그냥 쓴다."""
    if FLAG_MAP_PATH.exists() and not force:
        return FLAG_MAP_PATH
    CACHE_DIR.mkdir(exist_ok=True)
    print(f"    PokeAPI CSV 받는 중 - {FLAG_MAP_PATH.name}")
    resp = requests.get(FLAG_MAP_URL, timeout=30)
    resp.raise_for_status()
    FLAG_MAP_PATH.write_bytes(resp.content)
    return FLAG_MAP_PATH


def _load_flag_map():
    """{move_id: {플래그: True}} 를 만든다. 한 번만 읽는다."""
    global _flag_map
    if _flag_map is not None:
        return _flag_map

    _flag_map = {}
    try:
        path = _download_flag_map()
    except Exception as e:
        print(f"    CSV 를 받지 못했습니다 ({type(e).__name__}). 추측만 사용합니다.")
        return _flag_map

    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = int(row["move_id"])
            col = CSV_FLAG_IDS.get(int(row["move_flag_id"]))
            if col is None:                 # 우리가 안 쓰는 flag
                _flag_map.setdefault(mid, {})
                continue
            _flag_map.setdefault(mid, {})[col] = True
    print(f"    CSV 플래그 {len(_flag_map)}개 기술 로드")
    return _flag_map


def resolve_flags(move_id, name, category):
    """플래그 최종값과 출처를 돌려준다. -> (dict, "csv" 또는 "guess_flags")

    CSV 에 그 기술이 있으면 9개 플래그를 CSV 값으로 채우고, 나머지 3개는
    추측한다. CSV 에 없으면 12개 전부 추측한다.
    """
    guessed = guess_flags(name, category)
    entry = _load_flag_map().get(move_id)
    if entry is None:
        return guessed, "guess_flags"

    # CSV 에 등장하면, 그 기술에 안 적힌 flag 는 '없음'이 확정이다
    flags = {col: entry.get(col, False) for col in CSV_FLAG_IDS.values()}
    for col in GUESS_ONLY:
        flags[col] = guessed[col]
    return flags, "csv"


# ─────────────────────────────────────────────────────────────
# 이름 규칙 추측
#
# 맞히려고 만든 게 아니라, 사람이 확인할 출발점을 만드는 게 목적이다.
# CSV 가 채워 주는 9개는 사실 여기 규칙이 쓰이지 않는다 (id > 826 만 예외).
# ─────────────────────────────────────────────────────────────

# ── 펀치 ──────────────────────────────────────────────
PUNCH_EXTRA = {"meteor-mash", "rage-fist"}
PUNCH_EXCLUDE = {"sucker-punch"}        # 기습. 이름만 펀치다

# ── 소리 ──────────────────────────────────────────────
SOUND = {
    "sing", "roar", "screech", "snore", "uproar", "perish-song",
    "heal-bell", "hyper-voice", "bug-buzz", "round", "echoed-voice",
    "boomburst", "snarl", "noble-roar", "parting-shot", "metal-sound",
    "clanging-scales", "clangorous-soul", "sparkling-aria", "chatter",
    "torch-song", "alluring-voice", "psychic-noise", "eerie-spell",
    "overdrive", "disarming-voice", "relic-song", "grass-whistle",
    "supersonic", "confide", "howl",
}

# ── 총알·구슬·폭탄 ────────────────────────────────────
# 찍찍베기(population-bomb)는 이름에 bomb 이 있지만 베기 기술이다.
BULLET = {
    "bullet-seed", "rock-blast", "rock-wrecker", "seed-bomb",
    "aura-sphere", "focus-blast", "energy-ball", "shadow-ball",
    "electro-ball", "gyro-ball", "weather-ball", "zap-cannon",
    "pollen-puff", "syrup-bomb", "sludge-bomb", "acid-spray",
    "mist-ball", "magnet-bomb", "egg-bomb", "barrage", "octazooka",
    "searing-shot", "pyro-ball", "ice-ball", "steel-beam",
    "beak-blast", "mud-bomb",
}

# ── 바람 (9세대 신규. CSV 에 없음) ────────────────────
WIND = {
    "air-cutter", "blizzard", "heat-wave", "hurricane", "icy-wind",
    "petal-blizzard", "sandstorm", "tailwind", "whirlwind", "twister",
    "gust", "fairy-wind", "bleakwind-storm", "wildbolt-storm",
    "sandsear-storm", "springtide-storm",
}

# ── 베기 (9세대 신규. CSV 에 없음) ────────────────────
# 할퀴기·공간절단·사이코블레이드·타키온커터는 여기 안 들어간다.
SLICING = {
    "aerial-ace", "air-cutter", "air-slash", "aqua-cutter",
    "bitter-blade", "ceaseless-edge", "cross-poison", "crush-claw",
    "cut", "dragon-claw", "fury-cutter", "kowtow-cleave", "leaf-blade",
    "night-slash", "population-bomb", "psycho-cut", "razor-leaf",
    "razor-shell", "sacred-sword", "shadow-claw", "slash",
    "solar-blade", "stone-axe", "x-scissor", "behemoth-blade",
}

# ── 압박 (CSV 에 없음) ────────────────────────────────
# 작아지기 상태 상대에게 반드시 명중하고 피해가 2배가 된다.
# 바디프레스(body-press)는 이름이 비슷하지만 이 분류가 아니다.
PRESS = {
    "body-slam", "stomp", "dragon-rush", "steamroller",
    "flying-press", "heavy-slam", "heat-crash", "malicious-moonsault",
}

# ── 파동 ──────────────────────────────────────────────
PULSE = {
    "water-pulse", "dark-pulse", "dragon-pulse", "heal-pulse",
    "aura-sphere", "terrain-pulse", "origin-pulse",
}

# ── 춤 ────────────────────────────────────────────────
# 이름에 dance 가 들어가면 대체로 맞다. 비바라기는 날씨 기술이라 아니다.
DANCE_EXTRA = {"aqua-step"}
DANCE_EXCLUDE = {"rain-dance"}

# ── 상승 (중력 상태에서 사용 불가) ────────────────────
GRAVITY = {
    "fly", "bounce", "high-jump-kick", "jump-kick", "magnet-rise",
    "flying-press", "sky-drop", "telekinesis", "splash",
}

# ── 접촉 ──────────────────────────────────────────────
# 물리 기술은 대체로 접촉이다. 여기 적힌 것만 빼고 TRUE 로 둔다.
NON_CONTACT = {
    "earthquake", "fissure", "bulldoze", "magnitude",
    "rock-slide", "stone-edge", "rock-tomb", "rock-blast",
    "rock-wrecker", "smack-down", "ancient-power",
    "bullet-seed", "icicle-spear", "pin-missile", "bone-rush",
    "scale-shot", "dragon-darts", "gunk-shot", "poison-sting",
    "self-destruct", "explosion", "sand-tomb", "meteor-beam",
    "fling", "present", "spike-cannon", "twineedle",
    "bonemerang", "bone-club", "egg-bomb", "barrage",
    "air-cutter", "psycho-cut", "secret-sword", "icicle-crash",
    # 아래는 CSV 가 커버하지 않는 9세대 신기술 중 비접촉인 것들
    "triple-arrows", "aqua-cutter", "mountain-gale",
    "barb-barrage", "last-respects", "salt-cure",
}
# 반대로, 특수 기술인데 접촉인 것들
SPECIAL_CONTACT = {
    "draining-kiss", "grass-knot", "infestation", "petal-dance",
    "trump-card", "wring-out", "surf",
}


def guess_flags(name, category):
    """기술 하나의 플래그 추측값. category 는 physical/special/status."""
    contact = category == "physical" and name not in NON_CONTACT
    if name in SPECIAL_CONTACT:
        contact = True

    punch = (name.endswith("-punch") or name in PUNCH_EXTRA) \
        and name not in PUNCH_EXCLUDE

    return {
        "is_contact": contact,
        "is_punch": punch,
        "is_bite": "fang" in name or name in ("bite", "crunch", "bug-bite"),
        "is_sound": name in SOUND,
        "is_powder": "powder" in name or "spore" in name,
        "is_bullet": name in BULLET,
        "is_wind": name in WIND,
        "is_slicing": name in SLICING,
        "is_dance": ("dance" in name or name in DANCE_EXTRA)
                    and name not in DANCE_EXCLUDE,
        "is_pulse": name in PULSE,
        "is_gravity": name in GRAVITY,
        "is_press": name in PRESS,
    }

# ─────────────────────────────────────────────────────────────
# 포켓몬 폼 이름 한국어 조립
# 폼 이름은 API 가 한국어로 주지 않는다. 원종 이름을 받아 붙인다.
# ─────────────────────────────────────────────────────────────

def fetch_korean_name(data):
    """PokeAPI 포켓몬 응답에서 species를 타고 들어가 기본 한국어 이름을 얻는다."""
    species = requests.get(data["species"]["url"], timeout=10).json()
    for n in species["names"]:
        if n["language"]["name"] == "ko":
            return n["name"]        # "냐오닉스"
    return None


# "이름(꼬리표)" 꼴로 붙는 폼들.
#
# 메가·알로라처럼 앞에 붙이지 않는 이유는, 이것들이 다른 포켓몬이 아니라
# 같은 한 마리의 다른 상태이기 때문이다. 캐스퐁·킬가르도·모르페코는 배틀
# 도중에 서로 오가고, 펌킨인은 크기만 다르다. 앞에 붙이면 목록에서 원래
# 이름과 떨어져 앉아 한눈에 묶이지 않는다.
#
# 기본 폼(castform, gourgeist-average)도 꼬리표를 단다. 하나만 맨몸이면
# 그것이 폼 구분이 없는 포켓몬인지 기본값인지 화면에서 알 수 없다.
FORM_LABEL = {
    "castform": "노말",
    "castform-sunny": "태양의 모습",
    "castform-rainy": "빗방울의 모습",
    "castform-snowy": "설운의 모습",
    "aegislash-shield": "실드폼",
    "aegislash-blade": "블레이드폼",
    "gourgeist-small": "소과종",
    "gourgeist-average": "중과종",
    "gourgeist-large": "대과종",
    "gourgeist-super": "특대과종",
    "morpeko-full-belly": "배부른 모양",
    "morpeko-hangry": "배고픈 모양",
}


def build_korean_name(data, base_ko):
    """폼 접미사(-mega, -alola ...)를 한국어 표기로 붙인다."""
    en = data["name"]              # "meowstic-mega"
    if en in FORM_LABEL:
        return f"{base_ko}({FORM_LABEL[en]})"
    if en == "floette-eternal":
        return "영원의 꽃 플라엣테"
    if en == "palafin-zero":
        return f"{base_ko} 나이브폼"
    if en == "palafin-hero":
        return f"{base_ko} 마이티폼"
    # 성별 폼은 메가 검사보다 먼저 본다. "-mega" 가 먼저 걸리면
    # meowstic-male-mega 가 그냥 "메가냐오닉스" 가 되어 암수가 같은 이름이 된다.
    # 냐오닉스는 성별로 특성 3번(짓궂은마음/승기)과 기술 7개가 다르다.
    if en == "meowstic-male-mega":
        return f"메가{base_ko}(수컷)"
    if en == "meowstic-female-mega":
        return f"메가{base_ko}(암컷)"
    if en == "meowstic-male":
        return f"{base_ko}(수컷)"
    if en == "meowstic-female":
        return f"{base_ko}(암컷)"
    if "-mega-x" in en:
        return f"메가{base_ko}X"
    if "-mega-y" in en:
        return f"메가{base_ko}Y"
    if "-mega" in en:
        return f"메가{base_ko}"
    if "-alola" in en:
        return f"알로라 {base_ko}"
    if "-galar" in en:
        return f"가라르 {base_ko}"
    if "-hisui" in en:
        return f"히스이 {base_ko}"
    if "tauros-paldea-combat" in en:
        return f"팔데아 {base_ko}(격투)"
    if "tauros-paldea-blaze" in en:
        return f"팔데아 {base_ko}(불꽃)"
    if "tauros-paldea-aqua" in en:
        return f"팔데아 {base_ko}(물)"
    if "rotom-heat" in en:
        return f"히트{base_ko}"
    if "rotom-wash" in en:
        return f"워시{base_ko}"
    if "rotom-frost" in en:
        return f"프로스트{base_ko}"
    if "rotom-fan" in en:
        return f"스핀{base_ko}"
    if "rotom-mow" in en:
        return f"커트{base_ko}"
    if "lycanroc-midday" in en:
        return f"{base_ko}(한낮)"
    if "lycanroc-dusk" in en:
        return f"{base_ko}(황혼)"
    if "lycanroc-midnight" in en:
        return f"{base_ko}(한밤)"
    if "basculegion-female" in en:
        return f"{base_ko}(암컷)"
    if "basculegion-male" in en:
        return f"{base_ko}(수컷)"
    return base_ko

# ─────────────────────────────────────────────────────────────
# pokemons — 포켓몬 + 특성 연결의 재료
# ─────────────────────────────────────────────────────────────

pokemon_M_B = [
    # ===== 1세대 (기본 29, 폼 26) =====
    "venusaur", "charizard", "blastoise", "beedrill", "pidgeot", "arbok",
    "pikachu", "raichu", "clefable", "ninetales", "vileplume", "arcanine",
    "alakazam", "machamp", "victreebel", "slowbro", "gengar", "kangaskhan",
    "starmie", "pinsir", "tauros", "gyarados", "ditto", "vaporeon",
    "jolteon", "flareon", "aerodactyl", "snorlax", "dragonite",
    # -- 1세대 폼 --
    "aerodactyl-mega", "alakazam-mega", "arcanine-hisui", "beedrill-mega", "blastoise-mega", "charizard-mega-x",
    "charizard-mega-y", "clefable-mega", "dragonite-mega", "gengar-mega", "gyarados-mega", "kangaskhan-mega",
    "ninetales-alola", "pidgeot-mega", "pinsir-mega", "raichu-alola", "raichu-mega-x", "raichu-mega-y",
    "slowbro-galar", "slowbro-mega", "starmie-mega", "tauros-paldea-aqua-breed", "tauros-paldea-blaze-breed", "tauros-paldea-combat-breed",
    "venusaur-mega", "victreebel-mega",
    # ===== 2세대 (기본 18, 폼 11) =====
    "meganium", "typhlosion", "feraligatr", "ariados", "ampharos", "azumarill",
    "politoed", "espeon", "umbreon", "slowking", "forretress", "steelix",
    "qwilfish", "scizor", "heracross", "skarmory", "houndoom", "tyranitar",
    # -- 2세대 폼 --
    "ampharos-mega", "feraligatr-mega", "heracross-mega", "houndoom-mega", "meganium-mega", "scizor-mega",
    "skarmory-mega", "slowking-galar", "steelix-mega", "typhlosion-hisui", "tyranitar-mega",
    # ===== 3세대 (기본 21, 폼 20) =====
    "sceptile", "blaziken", "swampert", "pelipper", "gardevoir", "sableye",
    "mawile", "aggron", "medicham", "manectric", "sharpedo", "camerupt",
    "torkoal", "altaria", "milotic", "castform", "banette", "chimecho",
    "absol", "glalie", "metagross",
    # -- 3세대 폼 --
    "absol-mega", "aggron-mega", "altaria-mega", "banette-mega", "blaziken-mega", "camerupt-mega",
    "castform-rainy", "castform-snowy", "castform-sunny",
    "chimecho-mega", "gardevoir-mega", "glalie-mega", "manectric-mega", "mawile-mega", "medicham-mega",
    "metagross-mega", "sableye-mega", "sceptile-mega", "sharpedo-mega", "swampert-mega",
    # ===== 4세대 (기본 24, 폼 12) =====
    "torterra", "infernape", "empoleon", "staraptor", "luxray", "roserade",
    "rampardos", "bastiodon", "lopunny", "spiritomb", "garchomp", "lucario",
    "hippowdon", "toxicroak", "abomasnow", "weavile", "rhyperior", "leafeon",
    "glaceon", "gliscor", "mamoswine", "gallade", "froslass", "rotom",
    # -- 4세대 폼 --
    "abomasnow-mega", "froslass-mega", "gallade-mega", "garchomp-mega", "lopunny-mega", "lucario-mega",
    "rotom-fan", "rotom-frost", "rotom-heat", "rotom-mow", "rotom-wash", "staraptor-mega",
    # ===== 5세대 (기본 29, 폼 11) =====
    "serperior", "emboar", "samurott", "watchog", "liepard", "simisage",
    "simisear", "simipour", "musharna", "excadrill", "audino", "conkeldurr",
    "scolipede", "whimsicott", "krookodile", "scrafty", "cofagrigus",
    "garbodor", "zoroark", "reuniclus", "vanilluxe", "emolga", "eelektross",
    "chandelure", "beartic", "stunfisk", "golurk", "hydreigon", "volcarona",
    # -- 5세대 폼 --
    "audino-mega", "chandelure-mega", "eelektross-mega", "emboar-mega", "excadrill-mega", "golurk-mega",
    "samurott-hisui", "scolipede-mega", "scrafty-mega", "stunfisk-galar", "zoroark-hisui",
    # ===== 6세대 (기본 34, 폼 15) =====
    "chesnaught", "delphox", "greninja", "diggersby", "talonflame", "vivillon",
    "pyroar-male", "florges", "pangoro", "furfrou",
    "meowstic-male","meowstic-female", "aegislash-shield", "aromatisse", "slurpuff", "malamar", "barbaracle",
    "dragalge", "clawitzer", "heliolisk", "tyrantrum", "aurorus", "sylveon",
    "hawlucha", "dedenne", "goodra", "klefki", "trevenant", "gourgeist-average",
    "avalugg", "noivern", "floette-eternal", "meowstic-male-mega","meowstic-female-mega",
    # -- 6세대 폼 --
    "aegislash-blade",
    "avalugg-hisui", "barbaracle-mega", "chesnaught-mega", "delphox-mega", "dragalge-mega", "floette-mega",
    "goodra-hisui", "gourgeist-large", "gourgeist-small", "gourgeist-super",
    "greninja-mega", "hawlucha-mega", "malamar-mega",
    "pyroar-mega",
    # ===== 7세대 (기본 16, 폼 6) =====
    "decidueye", "incineroar", "primarina", "toucannon", "vikavolt", "crabominable",
    "toxapex", "mudsdale", "araquanid", "salazzle", "tsareena",
    "oranguru", "passimian", "mimikyu-disguised", "drampa", "kommo-o",
    # -- 7세대 폼 --
    "crabominable-mega", "decidueye-hisui", "drampa-mega", "lycanroc-midday", "lycanroc-dusk", "lycanroc-midnight",
    # ===== 8세대 (기본 17, 폼 3) =====
    "corviknight", "flapple", "appletun", "sandaconda", "polteageist",
    "hatterene", "grimmsnarl", "mr-rime", "alcremie", "falinks", "morpeko-full-belly",
    "dragapult", "wyrdeer", "kleavor", "basculegion-male", "sneasler", "overqwil", "runerigus",
    # -- 8세대 폼 --
    "basculegion-female", "falinks-mega", "morpeko-hangry",
    # ===== 9세대 (기본 23, 폼 2) =====
    "meowscarada", "skeledirge", "quaquaval", "maushold-family-of-four", "garganacl", "armarouge",
    "ceruledge", "bellibolt", "scovillain", "espathra", "tinkaton",
    "palafin-zero", "palafin-hero", "orthworm", "glimmora", "houndstone", "annihilape", "farigiraf",
    "kingambit", "gholdengo", "sinistcha", "archaludon", "hydrapple",
    # -- 9세대 폼 --
    "glimmora-mega", "scovillain-mega",
]

POKEMONS_TABLE = "pokemons"
POKEMONS_COLUMNS = ["id", "dex_no", "name", "ko_name", "type1", "type2",
           "height", "weight",
           "h", "a", "b", "c", "d", "s"]

# 한 파일 안에 두 번째 표도 같이 만든다. 같은 응답에서 나오므로 API 를
# 다시 부르지 않는다. (get_moves 의 move_stat_changes 와 같은 결)
# 특성 연결은 여기서 만들지 않는다.
#
# pokemon_abilities.ability_id 가 abilities(id) 를 참조하는데, 어느 특성을
# 받아야 하는지는 포켓몬 응답을 봐야 알 수 있다. 즉 abilities 는 이 단계
# 뒤에 오고, 그러면 이 단계에서 특성 행을 넣을 수 없다.
#
# 그래서 (포켓몬 id, 특성 이름, 슬롯) 을 여기 담아 두고, get_abilities 가
# 자기 표를 넣은 뒤 같은 단계에서 이어서 넣는다.
ABILITY_ROWS = []

# charizard-mega-x -> ("charizard", "x") / gengar-mega -> ("gengar", None)
MEGA_RE = re.compile(r"^(.*)-mega(?:-([xy]))?$")

# 이름을 잘라서는 베이스를 못 찾는 예외. 여기 적힌 것이 우선한다.
#   pyroar-mega  -> 목록에 pyroar 가 아니라 pyroar-male 로 들어 있다
#   floette-mega -> 메가가 되는 건 일반 플라엣테가 아니라 영원의 꽃 쪽이다.
#                   일반 플라엣테를 목록에서 뺐으므로 여기서 이어줘야 한다.
# make_mega_evolutions.py 도 이 표를 그대로 쓴다 — 베이스 판정이 두 곳에서
# 갈리면 can_mega 는 켜졌는데 관계표에는 없는 상태가 된다.
MANUAL_BASE = {
    "pyroar-mega": "pyroar-male",
    "floette-mega": "floette-eternal",
}


def split_mega(name):
    """메가폼 이름을 (베이스, 변형) 으로 쪼갠다. 메가폼이 아니면 (None, None)."""
    m = MEGA_RE.match(name)
    if m is None:
        return None, None
    return m.group(1), m.group(2)


def base_of(name):
    """메가폼의 베이스 이름. 메가폼이 아니면 None."""
    if name in MANUAL_BASE:
        return MANUAL_BASE[name]
    return split_mega(name)[0]


def mega_bases(names):
    """목록 안에서 메가폼을 가진 베이스 이름의 집합."""
    return {b for b in map(base_of, names) if b is not None}


def species_id(data):
    """폼 응답에서 원종(species) 번호를 뽑는다.

    .../pokemon-species/6/ 의 6 이다. 폼이 무엇이든 원종이 같으면 같은 값이
    나오므로, 10000번대로 흩어지는 id 대신 화면에 보여줄 도감 번호가 된다.
    """
    return int(data["species"]["url"].rstrip("/").rsplit("/", 1)[1])


def parse_pokemon(data):
    """포켓몬 한 마리의 응답에서 pokemons 한 행을 뽑는다.

    """
    stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}
    types = {t["slot"]: t["type"]["name"] for t in data["types"]}
    abilities = {a["slot"]: a["ability"]["name"] for a in data["abilities"]}

    # 폼 이름은 API 가 한국어로 주지 않는다. 원종 이름을 받아서 조립한다.
    base_ko = fetch_korean_name(data)
    ko_name = build_korean_name(data, base_ko)

    return {
        "id": data["id"],
        # 원종 도감 번호. species URL 끝 숫자가 그것이라 API 를 더 부르지
        # 않는다 — .../pokemon-species/6/ 이면 메가리자몽X 도 6 이 된다.
        "dex_no": species_id(data),
        "name": data["name"],
        "ko_name": ko_name,
        "type1": types.get(1),
        "type2": types.get(2),
        "height": data["height"] / 10,   # 17 → 1.7 (m)
        "weight": data["weight"] / 10,   # 905 → 90.5 (kg)
        "h": stats["hp"],
        "a": stats["attack"],
        "b": stats["defense"],
        "c": stats["special-attack"],
        "d": stats["special-defense"],
        "s": stats["speed"],

        # 밑줄로 시작해서 POKEMONS_COLUMNS 에 없다. pokemons 행에는 안 들어가지만
        # 같은 응답에서만 나오는 값이라 여기서 같이 들고 나간다.
        #
        # 특성은 아직 이름이다 — abilities 가 05 단계라 이 시점에 id 를 모른다.
        # 이름 -> id 는 넣기 직전에 옮긴다. (build_abilities 가 한다)
        "_abilities": [(data["id"], en, slot)
                       for slot, en in sorted(abilities.items())],
    }

def build_pokemons(conn):
    """03_pokemons.sql 전문을 만들어 돌려준다. (pokemon_M_B 개수만큼 API 호출)"""
    cur = conn.cursor()
    bases = mega_bases(pokemon_M_B)        # 메가폼을 가진 베이스 이름들


    rows = collect(pokemon_M_B, fetch_pokemon, parse_pokemon)

    # 다음 단계(get_abilities)가 가져간다. 위 ABILITY_ROWS 주석 참고.
    ABILITY_ROWS.clear()
    ABILITY_ROWS.extend(a for r in rows for a in r["_abilities"])
    print(f"특성 {len(ABILITY_ROWS)}행 (abilities 단계에서 넣는다)")

    # 베이스가 목록에 없는 메가폼은 mega_evolutions(10단계)에서 빠진다
    orphans = sorted(bases - set(pokemon_M_B))
    if orphans:
        print(f"베이스가 목록에 없는 메가: {len(orphans)}개 - {orphans}")

    return sql_of(cur, POKEMONS_TABLE, POKEMONS_COLUMNS, to_values(rows, POKEMONS_COLUMNS))

# ─────────────────────────────────────────────────────────────
# moves — 기술 + 능력 변화
# ─────────────────────────────────────────────────────────────

MOVE_URL = "https://pokeapi.co/api/v2/move"

MOVES_TABLE = "moves"
MOVES_COLUMNS = ["id", "name", "ko_name", "type", "power", "accuracy",
           "pp", "category", "priority",
           "target", "meta_category", "ailment", "ailment_chance",
           "crit_rate", "drain", "healing", "flinch_chance",
           "stat_chance", "min_hits", "max_hits",
           *FLAGS,
           "description", "effect"]

# 한 파일 안에 두 번째 테이블도 같이 만든다. 같은 응답에서 나오므로
# API를 다시 부르지 않으려고 04 단계에 합쳤다.
MOVE_STAT_TABLE = "move_stat_changes"
MOVE_STAT_COLUMNS = ["move_id", "stat", "change"]

# PokeAPI 능력치 이름 -> 이 프로젝트 표기
STAT_MAP = {
    "attack": "a", "defense": "b",
    "special-attack": "c", "special-defense": "d",
    "speed": "s", "accuracy": "acc", "evasion": "eva",
}

# ─────────────────────────────────────────────────────────────
# 포챔스 사용 가능 기술 (PokeAPI 이름 형식: 소문자, 공백/점→하이픈)
#   예: "Fire Punch" -> "fire-punch"
#   (Bulbapedia ✔ 목록을 여기에 채워넣을 것)
# ─────────────────────────────────────────────────────────────
moves_M_B = [
    "fire-punch", "ice-punch", "thunder-punch", "guillotine", "swords-dance", "whirlwind",
    "fly", "bind", "mega-kick", "horn-drill", "body-slam", "wrap",
    "thrash", "double-edge", "pin-missile", "bite", "roar", "sing",
    "disable", "flamethrower", "hydro-pump", "surf", "ice-beam", "blizzard",
    "hyper-beam", "drill-peck", "low-kick", "counter", "seismic-toss", "leech-seed",
    "growth", "solar-beam", "poison-powder", "stun-spore", "sleep-powder", "petal-dance",
    "string-shot", "fire-spin", "thunderbolt", "thunder-wave", "thunder", "earthquake",
    "fissure", "dig", "toxic", "psychic", "hypnosis", "agility",
    "quick-attack", "night-shade", "screech", "double-team", "recover", "minimize",
    "confuse-ray", "light-screen", "haze", "reflect", "focus-energy", "self-destruct",
    "fire-blast", "waterfall", "amnesia", "high-jump-kick", "glare", "leech-life",
    "sky-attack", "transform", "acid-armor", "crabhammer", "explosion", "rest",
    "rock-slide", "tri-attack", "super-fang", "substitute", "struggle", "thief",
    "snore", "curse", "flail", "cotton-spore", "reversal", "spite",
    "protect", "mach-punch", "scary-face", "sweet-kiss", "belly-drum", "sludge-bomb",
    "mud-slap", "spikes", "zap-cannon", "destiny-bond", "perish-song", "icy-wind",
    "detect", "bone-rush", "lock-on", "outrage", "sandstorm", "giga-drain",
    "endure", "charm", "swagger", "steel-wing", "mean-look", "attract",
    "sleep-talk", "heal-bell", "safeguard", "pain-split", "dynamic-punch", "megahorn",
    "baton-pass", "encore", "rapid-spin", "sweet-scent", "iron-tail", "morning-sun",
    "synthesis", "moonlight", "cross-chop", "rain-dance", "sunny-day", "crunch",
    "mirror-coat", "psych-up", "extreme-speed", "ancient-power", "shadow-ball", "future-sight",
    "whirlpool", "beat-up", "fake-out", "uproar", "stockpile", "spit-up",
    "swallow", "heat-wave", "torment", "flatter", "will-o-wisp", "memento",
    "facade", "focus-punch", "follow-me", "charge", "taunt", "helping-hand",
    "trick", "role-play", "wish", "ingrain", "superpower", "recycle",
    "brick-break", "yawn", "knock-off", "endeavor", "eruption", "skill-swap",
    "imprison", "dive", "feather-dance", "teeter-dance", "blaze-kick", "slack-off",
    "hyper-voice", "poison-fang", "crush-claw", "blast-burn", "hydro-cannon", "meteor-mash",
    "weather-ball", "fake-tears", "air-cutter", "overheat", "rock-tomb", "metal-sound",
    "tickle", "cosmic-power", "water-spout", "shadow-punch", "extrasensory", "sand-tomb",
    "sheer-cold", "muddy-water", "bullet-seed", "aerial-ace", "icicle-spear", "iron-defense",
    "block", "howl", "dragon-claw", "frenzy-plant", "bulk-up", "bounce",
    "mud-shot", "covet", "volt-tackle", "calm-mind", "leaf-blade", "dragon-dance",
    "rock-blast", "water-pulse", "roost", "gravity", "hammer-arm", "gyro-ball",
    "healing-wish", "feint", "pluck", "tailwind", "acupressure", "metal-burst",
    "u-turn", "close-combat", "payback", "assurance", "fling", "power-trick",
    "gastro-acid", "copycat", "power-swap", "guard-swap", "last-resort", "worry-seed",
    "sucker-punch", "toxic-spikes", "aqua-ring", "magnet-rise", "flare-blitz", "aura-sphere",
    "rock-polish", "poison-jab", "dark-pulse", "night-slash", "aqua-tail", "seed-bomb",
    "air-slash", "x-scissor", "bug-buzz", "dragon-pulse", "dragon-rush", "power-gem",
    "drain-punch", "vacuum-wave", "focus-blast", "energy-ball", "brave-bird", "earth-power",
    "switcheroo", "giga-impact", "nasty-plot", "bullet-punch", "avalanche", "ice-shard",
    "shadow-claw", "thunder-fang", "ice-fang", "fire-fang", "shadow-sneak", "psycho-cut",
    "zen-headbutt", "flash-cannon", "defog", "trick-room", "draco-meteor", "discharge",
    "lava-plume", "leaf-storm", "power-whip", "rock-wrecker", "cross-poison", "gunk-shot",
    "iron-head", "stone-edge", "stealth-rock", "grass-knot", "bug-bite", "charge-beam",
    "wood-hammer", "aqua-jet", "head-smash", "double-hit", "wide-guard", "guard-split",
    "power-split", "wonder-room", "psyshock", "venoshock", "rage-powder", "magic-room",
    "smack-down", "storm-throw", "sludge-wave", "quiver-dance", "heavy-slam", "electro-ball",
    "soak", "flame-charge", "coil", "low-sweep", "acid-spray", "foul-play",
    "simple-beam", "entrainment", "after-you", "round", "clear-smog", "stored-power",
    "quick-guard", "ally-switch", "scald", "shell-smash", "heal-pulse", "hex",
    "circle-throw", "quash", "acrobatics", "reflect-type", "final-gambit", "inferno",
    "volt-switch", "struggle-bug", "bulldoze", "frost-breath", "dragon-tail", "electroweb",
    "wild-charge", "drill-run", "horn-leech", "sacred-sword", "razor-shell", "heat-crash",
    "cotton-guard", "night-daze", "tail-slap", "hurricane", "fiery-dance", "snarl",
    "icicle-crash", "flying-press", "belch", "sticky-web", "fell-stinger", "phantom-force",
    "trick-or-treat", "noble-roar", "parabolic-charge", "forests-curse", "petal-blizzard", "freeze-dry",
    "parting-shot", "topsy-turvy", "draining-kiss", "grassy-terrain", "misty-terrain", "electrify",
    "play-rough", "moonblast", "boomburst", "fairy-lock", "kings-shield", "water-shuriken",
    "mystical-fire", "spiky-shield", "aromatic-mist", "eerie-impulse", "magnetic-flux", "electric-terrain",
    "dazzling-gleam", "baby-doll-eyes", "nuzzle", "infestation", "light-of-ruin", "first-impression",
    "baneful-bunker", "spirit-shackle", "darkest-lariat", "sparkling-aria", "ice-hammer", "high-horsepower",
    "strength-sap", "solar-blade", "toxic-thread", "throat-chop", "pollen-puff", "psychic-terrain",
    "lunge", "fire-lash", "power-trip", "burn-up", "speed-swap", "smart-strike",
    "trop-kick", "instruct", "beak-blast", "clanging-scales", "brutal-swing", "aurora-veil",
    "psychic-fangs", "stomping-tantrum", "accelerock", "liquidation", "tearful-look", "stuff-cheeks",
    "no-retreat", "magic-powder", "dragon-darts", "teatime", "clangorous-soul", "body-press",
    "decorate", "snap-trap", "aura-wheel", "breaking-swipe", "apple-acid", "grav-apple",
    "spirit-break", "life-dew", "steel-beam", "expanding-force", "steel-roller", "scale-shot",
    "meteor-beam", "shell-side-arm", "misty-explosion", "grassy-glide", "rising-voltage", "terrain-pulse",
    "skitter-smack", "burning-jealousy", "lash-out", "poltergeist", "corrosive-gas", "coaching",
    "flip-turn", "triple-axel", "dual-wingbeat", "scorching-sands", "eerie-spell", "dire-claw",
    "psyshield-bash", "stone-axe", "raging-fury", "wave-crash", "mountain-gale", "headlong-rush",
    "barb-barrage", "bitter-malice", "shelter", "triple-arrows", "infernal-parade", "ceaseless-edge",
    "axe-kick", "last-respects", "lumina-crash", "jet-punch", "spicy-extract", "population-bomb",
    "ice-spinner", "revival-blessing", "salt-cure", "mortal-spin", "kowtow-cleave", "flower-trick",
    "torch-song", "aqua-step", "raging-bull", "make-it-rain", "shed-tail", "chilly-reception",
    "tidy-up", "snowscape", "pounce", "trailblaze", "chilling-water", "twin-beam",
    "rage-fist", "armor-cannon", "bitter-blade", "double-shock", "gigaton-hammer", "comeuppance",
    "aqua-cutter", "matcha-gotcha", "syrup-bomb", "electro-shot", "fickle-beam", "hard-press",
    "dragon-cheer", "alluring-voice", "temper-flare", "supercell-slam", "psychic-noise", "upper-hand",
]

# 목록에 넣었다가 도로 뺀 것들. 다시 넣지 않기 위해 남긴다.
#
# 외부 목록과 대조하다 "DB 에 없다" 로 걸려서 넷 다 한 번 들어왔었다.
# 그런데 포챔스에서 못 쓰는 기술이다. 대조용 목록에 이것들이 섞여 있으면
# 다음 대조에서 또 '진짜 누락' 으로 뜨는데, 그때 이 주석이 없으면 같은
# 판단을 처음부터 다시 하게 된다.
#
#   spore        버섯포자   (147)
#   soft-boiled  알낳기     (135)
#   milk-drink   우유마시기 (208)
#   power-shift  파워시프트 (LA 신기술)
#
# 되살릴 때는 이름만 위 목록에 옮기지 말고 pokemon_moves 까지 같이 채워야
# 한다. moves 에만 있으면 아무도 못 배우는 기술이 된다.
EXCLUDED_MOVES = ["spore", "soft-boiled", "milk-drink", "power-shift"]

# 주석은 읽히지 않을 수 있으므로 import 시점에 걸리게 해 둔다.
_readded = sorted(set(EXCLUDED_MOVES) & set(moves_M_B))
if _readded:
    raise ValueError(
        f"포챔스에서 못 쓰는 기술이 moves_M_B 에 다시 들어왔다: {_readded}. "
        "되살리는 것이 맞다면 EXCLUDED_MOVES 에서도 빼라."
    )


fetch_move = endpoint(MOVE_URL)


def parse_move(data):
    # meta 가 통째로 없는 기술이 있어서 빈 dict 로 받아둔다.
    meta = data.get("meta") or {}
    ailment = (meta.get("ailment") or {}).get("name")
    if ailment == "none":               # 상태이상 없음을 NULL 로 통일
        ailment = None

    # 플래그는 API 에 없다. PokeAPI CSV 로 채우고, 없는 것은 이름으로
    # 추측한다. flag_source 는 둘 중 어느 쪽이었는지 (통계용).
    # 추측이 틀린 것은 DB 에서 직접 고치고 dump_sql 로 굳힌다.
    category = data["damage_class"]["name"]
    flags, source = resolve_flags(data["id"], data["name"], category)

    # PokeAPI 의 한국어 이름은 옛 세대 번역이라 포챔스 표기와 다른 것이
    # 있다(깨뜨리다 -> 깨트리기). 그 교정도 DB 쪽에 있다.
    ko = korean(data)

    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": ko["ko_name"],
        "type": data["type"]["name"],
        "power": data["power"],                 # 변화기는 None
        "accuracy": data["accuracy"],           # 필중기는 None
        "pp": data["pp"],
        "category": category,                   # physical/special/status
        "priority": data["priority"],

        "target": (data.get("target") or {}).get("name"),
        "meta_category": (meta.get("category") or {}).get("name"),
        "ailment": ailment,
        "ailment_chance": meta.get("ailment_chance"),
        "crit_rate": meta.get("crit_rate"),
        "drain": meta.get("drain"),              # 음수면 반동
        "healing": meta.get("healing"),
        "flinch_chance": meta.get("flinch_chance"),
        "stat_chance": meta.get("stat_chance"),
        "min_hits": meta.get("min_hits"),        # 단타는 None
        "max_hits": meta.get("max_hits"),

        **flags,

        # 밑줄로 시작하는 둘은 MOVES_COLUMNS 에 없다. moves 행에는 안 들어가지만
        # 같은 응답에서만 나오는 값이라 여기서 같이 들고 나간다.
        "_source": source,                       # 플래그 출처. 통계용
        "_stat_changes": parse_stat_changes(data),   # move_stat_changes 행들

        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
    }


def parse_stat_changes(data):
    """능력 변화 목록을 (기술 id, 능력, 변화량) 튜플들로 바꾼다.

    변화가 없는 기술은 빈 리스트다. 누구에게 걸리는지는 여기서 알 수 없고
    moves.meta_category 를 봐야 한다. (schema.MOVE_STAT_CHANGES 주석 참고)
    """
    rows = []
    for sc in data.get("stat_changes") or []:
        stat = STAT_MAP.get(sc["stat"]["name"])
        if stat is None:                # hp 등 배틀에서 안 쓰는 항목
            continue
        rows.append((data["id"], stat, sc["change"]))
    return rows


def build_moves(conn):
    """04_moves.sql 전문을 만들어 돌려준다. (moves_M_B 개수만큼 API 호출)

    한 파일에 moves 와 move_stat_changes 두 테이블이 들어간다.
    둘 다 같은 응답에서 나오므로 API를 두 번 부르지 않는다.
    """
    cur = conn.cursor()
    rows = collect(moves_M_B, fetch_move, parse_move)

    stat_values = [sc for r in rows for sc in r["_stat_changes"]]
    guessed = [r["name"] for r in rows if r["_source"] == "guess"]

    print(f"능력 변화 {len(stat_values)}행")
    print(f"플래그: CSV {len(rows) - len(guessed)}개 / 추측 {len(guessed)}개")
    if guessed:
        print(f"  추측으로 채운 기술: {', '.join(guessed)}")
    print("  바람·베기·압박은 CSV 에 없어 전부 추측입니다."
          " DB 에서 확인하고 고치세요.")

    sql = sql_of(cur, MOVES_TABLE, MOVES_COLUMNS, to_values(rows, MOVES_COLUMNS))

    # 변화가 하나도 없으면 아무것도 안 붙인다 (VALUES; 는 문법 오류다).
    # 표를 만드는 SQL 은 schema.py 에서만 나온다 — build 는 INSERT 만 돌려준다.
    if stat_values:
        sql += "\n" + sql_of(cur, MOVE_STAT_TABLE,
                              MOVE_STAT_COLUMNS, stat_values)
    return sql

# ─────────────────────────────────────────────────────────────
# abilities — 특성 + 포켓몬-특성 연결
# ─────────────────────────────────────────────────────────────

ABILITY_URL = "https://pokeapi.co/api/v2/ability"

ABILITIES_TABLE = "abilities"
ABILITIES_COLUMNS = ["id", "name", "ko_name", "description", "effect"]

LINK_TABLE = "pokemon_abilities"
LINK_COLUMNS = ["pokemon_id", "ability_id", "slot"]


fetch_ability = endpoint(ABILITY_URL)


def parse_ability(data):
    # PokeAPI 에 한국어가 없는 신규 특성이 있고, flavor text 도 옛 표현이거나
    # 잘려 있는 경우가 있다. 손본 값은 DB 쪽에 있다.
    ko = korean(data)

    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": ko["ko_name"],
        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
    }


def wanted_names():
    """받아야 할 특성 이름. get_pokemons 가 담아 둔 것에서 중복을 없앤다."""
    return sorted({name for _, name, _ in ABILITY_ROWS})


def build_abilities(conn):
    """abilities + pokemon_abilities INSERT. (특성 수만큼 API 호출)"""
    cur = conn.cursor()
    names = wanted_names()
    if not names:
        raise SystemExit(
            "받을 특성이 없습니다. 포켓몬 단계를 먼저 돌려야 합니다.\n"
            "  python -m scripts.etl.build_abilities --only pokemons --only abilities")
    print(f"대상 특성 수: {len(names)}")

    rows = collect(names, fetch_ability, parse_ability)
    sql = sql_of(cur, ABILITIES_TABLE, ABILITIES_COLUMNS, to_values(rows, ABILITIES_COLUMNS))

    # 이름 -> id. 방금 받은 응답에 id 가 들어 있어 조회가 필요 없다.
    ability_id = {r["name"]: r["id"] for r in rows}
    links = [(pokemon_id, ability_id[name], slot)
             for pokemon_id, name, slot in ABILITY_ROWS
             if name in ability_id]
    print(f"특성 연결 {len(links)}행")
    return sql + "\n" + sql_of(cur, LINK_TABLE, LINK_COLUMNS, links)

# ─────────────────────────────────────────────────────────────
# items — 도구
# ─────────────────────────────────────────────────────────────

ITEM_URL = "https://pokeapi.co/api/v2/item"
ITEM_CATEGORY_URL = "https://pokeapi.co/api/v2/item-category"

ITEMS_TABLE = "items"
ITEMS_COLUMNS = ["id", "name", "ko_name", "category",
           "fling_power", "description", "effect"]

# ─────────────────────────────────────────────────────────────
# 수집 대상 카테고리 (옆의 숫자는 현재 PokeAPI 기준 개수)
#   포챔스 룰에 따라 z-crystals, memories, jewels 등을 넣고 빼면 된다
# ─────────────────────────────────────────────────────────────
ITEM_CATEGORIES = [
    "type-enhancement",  # 22  목탄, 신비의물방울 ... (기술 위력 상승류)
    "mega-stones",       # 92  메가스톤 전체
    "type-protection",   # 19  오카열매, 꼬시개열매 ... (타입 데미지 반감 열매)
]

# 카테고리 통째로 담기에는 아까운 것들. 카테고리 안에 대전에서 못 쓰는
# 것이 더 많아서, 쓸 것만 이름으로 집는다.
#
# held-items 만 해도 72개인데 그중 남길 건 아래 정도다. 여기서 좁히는 것이
# 유일한 거름망이다 — 카테고리를 통째로 넣고 뒤에서 플래그로 거르면
# 도감이 안 쓰는 도구로 뒤덮이고, 거르는 자리가 둘로 갈린다.
EXTRA_ITEMS = [
    # 열매 — 상태이상 회복. status-cures 카테고리를 통째로 넣으면 해독제·
    # 만병통치제 같은 가방 아이템이 딸려 온다. 지니는 열매만 집는다.
    "aspear-berry",    # 얼음
    "cheri-berry",     # 마비
    "chesto-berry",    # 잠듦
    "lum-berry",       # 상태이상 전부 + 혼란
    "pecha-berry",     # 독
    "persim-berry",    # 혼란
    "rawst-berry",     # 화상
    # 열매 — 회복
    "sitrus-berry",    # 자뭉열매
    "oran-berry",      # 오랭열매
    # 목탄·자석과 하는 일이 같은데 PokeAPI 가 type-enhancement 가 아니라
    # held-items 로 분류해서 카테고리 수집에 안 걸린다.
    "fairy-feather",   # 요정의깃털
    # 허브류
    "mental-herb", "mirror-herb", "power-herb", "white-herb",
    # 렌즈류 (노력치용 파워렌즈는 대전에서 안 쓴다)
    "scope-lens", "wide-lens", "zoom-lens",
    # 바위류 — 날씨를 늘리는 것들. 딱딱한돌·가벼운돌은 여기가 아니다
    "damp-rock", "heat-rock", "icy-rock", "smooth-rock",
    # 구애 시리즈
    "choice-band", "choice-scarf", "choice-specs",
    # 기합 시리즈
    "focus-band", "focus-sash",
    # 낱개
    "big-root",        # 큰뿌리
    "bright-powder",   # 반짝가루
    "expert-belt",     # 달인의띠
    "iron-ball",       # 검은철구
    "kings-rock",      # 왕의징표석
    "leftovers",       # 먹다남은음식
    "life-orb",        # 생명의구슬
    "light-ball",      # 전기구슬
    "light-clay",      # 빛의점토
    "metronome",       # 메트로놈
    "muscle-band",     # 힘의머리띠
    "quick-claw",      # 선제공격손톱
    "shed-shell",      # 아름다운허물
    "shell-bell",      # 조개껍질방울
    "wise-glasses",    # 박식안경
]

# type-enhancement 안에 섞여 있는 향로류. 하는 일은 목탄·자석과 같은데
# 위력 배수가 더 낮아, 목록에 두면 고를 일 없는 줄만 늘어난다.
EXCLUDE_ITEMS = [
    "odd-incense", "rock-incense", "rose-incense",
    "sea-incense", "wave-incense",
]


def fetch_category(category):
    """카테고리 하나에 속한 도구 이름 목록을 받아온다. 실패 시 빈 리스트."""
    data = get_json(f"{ITEM_CATEGORY_URL}/{category}")
    if data is None:
        return []
    return [i["name"] for i in data["items"]]


def collect_item_names():
    """카테고리 + EXTRA_ITEMS 에서 EXCLUDE_ITEMS 를 뺀 이름 목록."""
    names = set()
    for category in ITEM_CATEGORIES:
        got = fetch_category(category)
        if not got:
            print(f"{category} - 카테고리 조회 실패")
            continue
        names.update(got)
        print(f"{category} - {len(got)}개")
    names.update(EXTRA_ITEMS)
    print(f"낱개 지정 - {len(EXTRA_ITEMS)}개")
    names -= set(EXCLUDE_ITEMS)
    print(f"제외 - {len(EXCLUDE_ITEMS)}개")
    return sorted(names)


fetch_item = endpoint(ITEM_URL)


def parse_item(data):
    # 신규 메가스톤 등 PokeAPI 에 한국어가 없는 도구가 많다. 손본 이름·
    # 설명은 DB 쪽에 있다. 도구만 본문 키가 "text" 다.
    ko = korean(data, flavor_key="text")

    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": ko["ko_name"],
        "category": data["category"]["name"],
        "fling_power": data["fling_power"],   # 던질 수 없는 도구는 None
        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
    }


def build_items(conn):
    """06_items.sql 전문을 만들어 돌려준다. (카테고리 12회 + 도구 수만큼 API 호출)"""
    cur = conn.cursor()
    items = collect_item_names()
    print(f"\n수집 대상 도구 수: {len(items)}\n")

    rows = collect(items, fetch_item, parse_item)

    return sql_of(cur, ITEMS_TABLE, ITEMS_COLUMNS, to_values(rows, ITEMS_COLUMNS))

# ─────────────────────────────────────────────────────────────
# pokemon_moves — 포켓몬-기술 연결
# pokemons 와 moves 가 DB 에 올라간 뒤에 돌아야 한다.
# ─────────────────────────────────────────────────────────────

POKEMON_URL = "https://pokeapi.co/api/v2/pokemon"

POKEMON_MOVES_TABLE = "pokemon_moves"
POKEMON_MOVES_COLUMNS = ["pokemon_id", "move_id"]


# collect() 를 쓰지 않는다. 이름 하나가 행 수십 개가 되고 ko_name 도 없어서,
# 끼워 넣으면 collect 에 이 생성기 전용 분기가 둘 생긴다. (parse_utils 참고)
def build_pokemon_moves(conn):
    """07_pokemon_moves.sql 전문을 만들어 돌려준다. (포켓몬 수만큼 API 호출)"""
    cur = conn.cursor()

    # 1) DB에 존재하는 유효 기술 목록 (교집합 기준)
    cur.execute("SELECT name, id FROM moves")
    move_id = dict(cur.fetchall())
    valid_moves = set(move_id)
    print(f"DB 기술 수: {len(valid_moves)}")

    # 2) DB에 존재하는 포켓몬 목록 (대상). 표에는 id 로 넣으므로 같이 읽는다.
    cur.execute("SELECT name, id FROM pokemons")
    pokemon_id = dict(cur.fetchall())
    pokemons = list(pokemon_id)
    print(f"DB 포켓몬 수: {len(pokemons)}")

    failed = []
    values = []
    for name in pokemons:
        data = fetch_pokemon(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue

        # PokeAPI가 준 습득 기술 전체
        learned = {m["move"]["name"] for m in data["moves"]}
        # DB에 있는 유효 기술과의 교집합만 저장
        valid = learned & valid_moves

        for move in sorted(valid):
            values.append((pokemon_id[name], move_id[move]))

        print(f"{name} - {len(valid)}개")

    print(f"\n연결 {len(values)}행 / 실패: {len(failed)}개 - {failed}")
    return sql_of(cur, POKEMON_MOVES_TABLE, POKEMON_MOVES_COLUMNS, values)
