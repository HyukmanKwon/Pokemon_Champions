"""기술 플래그를 정한다. PokeAPI CSV 를 먼저 보고, 없으면 이름으로 추측한다.

PokeAPI /move 응답에는 flags 가 없다. 접촉인지 펀치인지 소리인지를 알려주는
필드가 어디에도 없다. 그런데 **CSV 덤프에는 있다.** 같은 저장소인데 API 로
노출만 안 된 것이다.

    https://raw.githubusercontent.com/PokeAPI/pokeapi/master/
        data/v2/csv/move_flags.csv       flag_id -> 이름
        data/v2/csv/move_flag_map.csv    move_id -> flag_id

앞의 파일은 21줄이고 안 바뀌므로 CSV_FLAG_IDS 에 그대로 박아 뒀다.
뒤의 파일만 내려받아 data/cache/ 에 둔다. 한 번 받으면 재사용한다.

── 값을 정하는 순서 ──
  1. CSV 에 그 기술이 있으면        -> CSV 값 (9개 플래그)
  2. 없으면                        -> 이름 규칙 추측
  3. 추측이 틀린 것                 -> DB 에서 직접 고치고 dump_sql 로 굳힌다

── CSV 로 안 되는 것 ──
  * move_id 가 826 에서 끊긴다. 우리 498개 중 55개가 빠진다
    (레전드 아르세우스 이후 신기술)
  * 바람·베기는 9세대 신규 플래그라 CSV 에 아예 없다
  * 압박은 나무위키 분류로, 어느 공식 flag 에도 대응이 없다

  그래서 이 세 플래그는 항상 추측이고, 사람이 확인해야 한다.
  annotator/moves.py 에서 "미확인만" 필터로 걸러 보면 된다.

── 각 플래그가 왜 필요한가 ──
  is_contact  까칠한피부·정전기·불꽃몸·철가시가 반응. 방어측 특성 다수
  is_punch    철주먹 위력 +20%
  is_bite     옹골찬턱 위력 +50%
  is_sound    방음이 무효화. 대타출동을 뚫는다
  is_powder   풀 타입에게 무효. 방진고글·방진도 막는다
  is_bullet   방탄이 무효화
  is_wind     바람타기가 무효화하고 공격 1랭크 상승. 풍력발전은 충전 상태
  is_slicing  예리함 위력 1.5배
  is_dance    무희가 따라서 쓴다
  is_pulse    메가런처 위력 1.5배
  is_gravity  중력 상태에서 사용할 수 없다 (나무위키 '상승')
  is_press    작아지기 상태 상대에게 반드시 명중하고 피해 2배 (나무위키 '압박')
"""

import csv

import requests

from . import paths

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

MAP_URL = ("https://raw.githubusercontent.com/PokeAPI/pokeapi/master/"
           "data/v2/csv/move_flag_map.csv")

CACHE_DIR = paths.CACHE_DIR
MAP_PATH = CACHE_DIR / "move_flag_map.csv"

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


def download_map(force=False):
    """move_flag_map.csv 를 cache/ 에 받아 둔다. 있으면 그냥 쓴다."""
    if MAP_PATH.exists() and not force:
        return MAP_PATH
    CACHE_DIR.mkdir(exist_ok=True)
    print(f"    PokeAPI CSV 받는 중 - {MAP_PATH.name}")
    resp = requests.get(MAP_URL, timeout=30)
    resp.raise_for_status()
    MAP_PATH.write_bytes(resp.content)
    return MAP_PATH


def load_map():
    """{move_id: {플래그: True}} 를 만든다. 한 번만 읽는다."""
    global _flag_map
    if _flag_map is not None:
        return _flag_map

    _flag_map = {}
    try:
        path = download_map()
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


def resolve(move_id, name, category):
    """플래그 최종값과 출처를 돌려준다. -> (dict, "csv" 또는 "guess")

    CSV 에 그 기술이 있으면 9개 플래그를 CSV 값으로 채우고, 나머지 3개는
    추측한다. CSV 에 없으면 12개 전부 추측한다.
    """
    guessed = guess(name, category)
    entry = load_map().get(move_id)
    if entry is None:
        return guessed, "guess"

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


def guess(name, category):
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
