from pokemon_champions.db import connect

from . import paths
from . import schema
from .parse_utils import render

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
    """01_types.sql 전문을 만들어 돌려준다. (API 호출 없음)"""
    rows = []
    for atk in TYPES:
        for dfn in TYPES:
            rows.append(f"    ('{atk}', '{dfn}', {multiplier(atk, dfn)})")
        print(f"{atk} 완료")
    return render(schema.TYPES, TABLE, COLUMNS, rows)


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"\n{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
