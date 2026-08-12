from . import schema
from .parse_utils import literal_build

FILENAME = "01_types.sql"
TABLE = "pokemon_types"
COLUMNS = ["attack_type", "defense_type", "multiplier"]
DDL = schema.TYPES

TYPES = schema.TYPE_NAMES

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

    TYPE_CHART 는 '배수 -> 그 배수를 받는 타입들' 이라 빈칸이 많다. 여기서
    18×18 을 전부 펴서 324행으로 만든다 — 표에 없는 짝이 1.0 이라는 것을
    조회하는 쪽이 알아야 할 이유가 없다.
    """
    values = [(atk, dfn, multiplier(atk, dfn))
              for atk in TYPES for dfn in TYPES]
    print(f"{len(TYPES)}×{len(TYPES)} = {len(values)}행")
    return literal_build(conn, DDL, TABLE, COLUMNS, values)

