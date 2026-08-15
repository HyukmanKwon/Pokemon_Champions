from . import schema
from .parse_utils import literal_build, sql_of

FILENAME = "01_types.sql"
TABLE = "pokemon_types"
COLUMNS = ["attack_type", "defense_type", "multiplier"]
DDL = schema.TYPES

TYPES = schema.TYPE_NAMES

# 타입 이름의 언어별 표기. 한 파일에 담기는 두 번째 표다.
#
# PokeAPI 로 받지 않고 적어 두는 이유는 배수표와 같다 — 열여덟 줄이고,
# 세대가 바뀌어도 변하지 않으며, API 를 부르면 01_types.sql 이 지금의
# "호출 0회" 를 잃는다.
NAME_LANGUAGES = ["ko", "ja", "en"]

TYPE_LABELS = {
    "normal":   ("노말",   "ノーマル",   "Normal"),
    "fire":     ("불꽃",   "ほのお",     "Fire"),
    "water":    ("물",     "みず",       "Water"),
    "electric": ("전기",   "でんき",     "Electric"),
    "grass":    ("풀",     "くさ",       "Grass"),
    "ice":      ("얼음",   "こおり",     "Ice"),
    "fighting": ("격투",   "かくとう",   "Fighting"),
    "poison":   ("독",     "どく",       "Poison"),
    "ground":   ("땅",     "じめん",     "Ground"),
    "flying":   ("비행",   "ひこう",     "Flying"),
    "psychic":  ("에스퍼", "エスパー",   "Psychic"),
    "bug":      ("벌레",   "むし",       "Bug"),
    "rock":     ("바위",   "いわ",       "Rock"),
    "ghost":    ("고스트", "ゴースト",   "Ghost"),
    "dragon":   ("드래곤", "ドラゴン",   "Dragon"),
    "dark":     ("악",     "あく",       "Dark"),
    "steel":    ("강철",   "はがね",     "Steel"),
    "fairy":    ("페어리", "フェアリー", "Fairy"),
}

NAME_TABLE = "pokemon_type_names"
NAME_COLUMNS = ["type_name", "language", "name"]

# dump_sql 이 읽는 목록 — 이 파일에 표가 하나 더 있다는 뜻이다.
EXTRA = [(schema.POKEMON_TYPE_NAMES, NAME_TABLE, NAME_COLUMNS)]

# 공격타입 -> {배수: [그 배수를 받는 방어타입들]}
TYPE_CHART = {
    "normal": {
        0.5: ["rock", "steel"],
        0.0: ["ghost"],
    },
    "fire": {
        2.0: ["grass", "ice", "bug", "steel"],
        0.5: ["fire", "water", "rock", "dragon"],
    },
    "water": {
        2.0: ["fire", "ground", "rock"],
        0.5: ["water", "grass", "dragon"],
    },
    "electric": {
        2.0: ["water", "flying"],
        0.5: ["electric", "grass", "dragon"],
        0.0: ["ground"],
    },
    "grass": {
        2.0: ["water", "ground", "rock"],
        0.5: ["fire", "grass", "poison", "flying", "bug", "dragon", "steel"],
    },
    "ice": {
        2.0: ["grass", "ground", "flying", "dragon"],
        0.5: ["fire", "water", "ice", "steel"],
    },
    "fighting": {
        2.0: ["normal", "ice", "rock", "dark", "steel"],
        0.5: ["poison", "flying", "psychic", "bug", "fairy"],
        0.0: ["ghost"],
    },
    "poison": {
        2.0: ["grass", "fairy"],
        0.5: ["poison", "ground", "rock", "ghost"],
        0.0: ["steel"],
    },
    "ground": {
        2.0: ["fire", "electric", "poison", "rock", "steel"],
        0.5: ["grass", "bug"],
        0.0: ["flying"],
    },
    "flying": {
        2.0: ["grass", "fighting", "bug"],
        0.5: ["electric", "rock", "steel"],
    },
    "psychic": {
        2.0: ["fighting", "poison"],
        0.5: ["psychic", "steel"],
        0.0: ["dark"],
    },
    "bug": {
        2.0: ["grass", "psychic", "dark"],
        0.5: ["fire", "fighting", "poison", "flying", "ghost", "steel", "fairy"],
    },
    "rock": {
        2.0: ["fire", "ice", "flying", "bug"],
        0.5: ["fighting", "ground", "steel"],
    },
    "ghost": {
        2.0: ["psychic", "ghost"],
        0.5: ["dark"],
        0.0: ["normal"],
    },
    "dragon": {
        2.0: ["dragon"],
        0.5: ["steel"],
        0.0: ["fairy"],
    },
    "dark": {
        2.0: ["psychic", "ghost"],
        0.5: ["fighting", "dark", "fairy"],
    },
    "steel": {
        2.0: ["ice", "rock", "fairy"],
        0.5: ["fire", "water", "electric", "steel"],
    },
    "fairy": {
        2.0: ["fighting", "dragon", "dark"],
        0.5: ["fire", "poison", "steel"],
    },
}


def multiplier(attack, defense):
    """공격타입이 방어타입에게 주는 배수. 표에 없으면 1.0."""
    for mult, targets in TYPE_CHART[attack].items():
        if defense in targets:
            return mult
    return 1.0


def build(conn):
    """01_types.sql 전문을 만들어 돌려준다. (API 호출 없음)

    표가 둘이다 — 배수표(pokemon_types)와 언어별 표기(pokemon_type_names).

    TYPE_CHART 는 '배수 -> 그 배수를 받는 타입들' 이라 빈칸이 많다. 여기서
    18×18 을 전부 펴서 324행으로 만든다 — 표에 없는 짝이 1.0 이라는 것을
    조회하는 쪽이 알아야 할 이유가 없다.
    """
    values = [(atk, dfn, multiplier(atk, dfn))
              for atk in TYPES for dfn in TYPES]
    print(f"{len(TYPES)}×{len(TYPES)} = {len(values)}행")
    sql = literal_build(conn, DDL, TABLE, COLUMNS, values)

    names = [(t, lang, TYPE_LABELS[t][i])
             for t in TYPES
             for i, lang in enumerate(NAME_LANGUAGES)]
    print(f"{len(TYPES)}타입 × {len(NAME_LANGUAGES)}언어 = {len(names)}행")
    return sql + "\n" + sql_of(conn.cursor(), schema.POKEMON_TYPE_NAMES,
                               NAME_TABLE, NAME_COLUMNS, names)

