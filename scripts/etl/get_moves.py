from . import move_flags
from . import overrides
from . import schema
from .parse_utils import (get_json, pick_korean, pick_korean_flavor,
                         pick_english_effect, render, mogrify_rows)

POKEAPI_BASE = "https://pokeapi.co/api/v2/move"

FILENAME = "04_moves.sql"
TABLE = "moves"
COLUMNS = ["id", "name", "ko_name", "type", "power", "accuracy",
           "pp", "category", "priority",
           "target", "meta_category", "ailment", "ailment_chance",
           "crit_rate", "drain", "healing", "flinch_chance",
           "stat_chance", "min_hits", "max_hits",
           *move_flags.FLAGS, "reviewed",
           "description", "effect"]

# annotator.py 가 쓰는 override 파일 이름
OVERRIDE_KEY = "move_flags"

# PokeAPI 의 한국어 이름은 옛 세대 번역이라 포챔스 표기와 다른 것이 있다.
# /move 의 names 배열은 언어당 하나뿐이고 갱신되지 않아서, API 로는 최신
# 표기를 얻을 방법이 없다. 그래서 손으로 고친 값을 여기에 쌓는다.
#   깨뜨리다 -> 깨트리기 (brick-break)
#   독실     -> 독독실   (toxic-thread)
# 목록 대조는 check_moves.py 가 한다. (README §6)
KO_OVERRIDE_KEY = "move_ko_names"
DDL = schema.MOVES

# 한 파일 안에 두 번째 테이블도 같이 만든다. 같은 응답에서 나오므로
# API를 다시 부르지 않으려고 04 단계에 합쳤다.
STAT_TABLE = "move_stat_changes"
STAT_COLUMNS = ["move_name", "stat", "change"]
STAT_DDL = schema.MOVE_STAT_CHANGES

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
# check_moves.py 로 외부 목록과 대조하다 "DB 에 없다" 로 걸려서 넷 다 한 번
# 들어왔었다. 그런데 포챔스에서 못 쓰는 기술이다. 대조용 목록에 이것들이
# 섞여 있으면 다음 대조에서 또 '진짜 누락' 으로 뜨는데, 그때 이 주석이
# 없으면 같은 판단을 처음부터 다시 하게 된다.
#
#   spore        버섯포자   (147)
#   soft-boiled  알낳기     (135)
#   milk-drink   우유마시기 (208)
#   power-shift  파워시프트 (LA 신기술)
#
# 되살릴 때는 이름만 위 목록에 옮기지 말고 sync_moves 로 pokemon_moves 까지
# 같이 채워야 한다. moves 에만 있으면 아무도 못 배우는 기술이 된다.
EXCLUDED_MOVES = ["spore", "soft-boiled", "milk-drink", "power-shift"]

# 주석은 읽히지 않을 수 있으므로 import 시점에 걸리게 해 둔다.
_readded = sorted(set(EXCLUDED_MOVES) & set(moves_M_B))
if _readded:
    raise ValueError(
        f"포챔스에서 못 쓰는 기술이 moves_M_B 에 다시 들어왔다: {_readded}. "
        "되살리는 것이 맞다면 EXCLUDED_MOVES 에서도 빼라."
    )


def fetch_move(name):
    """PokeAPI에서 기술 하나의 원본 JSON을 받아온다. 실패 시 None."""
    return get_json(f"{POKEAPI_BASE}/{name}")


def parse_move(data):
    # meta 가 통째로 없는 기술이 있어서 빈 dict 로 받아둔다.
    meta = data.get("meta") or {}
    ailment = (meta.get("ailment") or {}).get("name")
    if ailment == "none":               # 상태이상 없음을 NULL 로 통일
        ailment = None

    # 플래그는 API에 없다. PokeAPI CSV -> 이름 추측 -> 사람이 확정한 값 순으로
    # 덮어쓴다. flag_source 는 CSV 를 썼는지 추측했는지 (통계용).
    category = data["damage_class"]["name"]
    flags, source = move_flags.resolve(data["id"], data["name"], category)
    reviewed = overrides.apply(OVERRIDE_KEY, data["name"], flags)

    # 한국어 이름·설명도 override 를 태운다. PokeAPI 값이 옛 번역인 경우가 있다.
    #   python -m scripts.etl.annotator.ko_names moves
    ko = {
        "ko_name": pick_korean(data["names"]),
        "description": pick_korean_flavor(data["flavor_text_entries"]),
    }
    overrides.apply(KO_OVERRIDE_KEY, data["name"], ko)

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
        "reviewed": reviewed,
        "_source": source,                       # COLUMNS 에 없다. 통계용

        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
    }


def parse_stat_changes(data):
    """능력 변화 목록을 (기술명, 능력, 변화량) 튜플들로 바꾼다.

    변화가 없는 기술은 빈 리스트다. 누구에게 걸리는지는 여기서 알 수 없고
    moves.meta_category 를 봐야 한다. (schema.MOVE_STAT_CHANGES 주석 참고)
    """
    rows = []
    for sc in data.get("stat_changes") or []:
        stat = STAT_MAP.get(sc["stat"]["name"])
        if stat is None:                # hp 등 배틀에서 안 쓰는 항목
            continue
        rows.append((data["name"], stat, sc["change"]))
    return rows


def build(conn):
    """04_moves.sql 전문을 만들어 돌려준다. (moves_M_B 개수만큼 API 호출)

    한 파일에 moves 와 move_stat_changes 두 테이블이 들어간다.
    둘 다 같은 응답에서 나오므로 API를 두 번 부르지 않는다.
    """
    cur = conn.cursor()
    failed = []
    values = []
    stat_values = []
    guessed = []            # CSV 에 없어서 추측으로 채운 기술
    for name in moves_M_B:
        data = fetch_move(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue
        m = parse_move(data)
        values.append(tuple(m[c] for c in COLUMNS))
        stat_values.extend(parse_stat_changes(data))
        if m["_source"] == "guess":
            guessed.append(name)
        print(f"{m['name']} -> {m['ko_name']}")

    print(f"\n수집 {len(values)}개 / 실패: {len(failed)}개 - {failed}")
    print(f"능력 변화 {len(stat_values)}행")
    print(f"플래그: CSV {len(values) - len(guessed)}개 / 추측 {len(guessed)}개")
    if guessed:
        print(f"  추측으로 채운 기술: {', '.join(guessed)}")
    print("  바람·베기·압박은 CSV 에 없어 전부 추측입니다."
          " annotator/moves.py 로 확인하세요.")

    sql = render(DDL, TABLE, COLUMNS,
                 mogrify_rows(cur, values, len(COLUMNS)))

    # 변화가 하나도 없으면 INSERT 없이 테이블만 만든다 (VALUES; 는 문법 오류)
    if stat_values:
        sql += "\n" + render(STAT_DDL, STAT_TABLE, STAT_COLUMNS,
                             mogrify_rows(cur, stat_values, len(STAT_COLUMNS)))
    else:
        sql += "\n" + STAT_DDL
    return sql

