"""날씨 상수표(weathers)를 만든다. API 호출 없음.

name 은 기술 이름과 맞춰 뒀다. 날씨를 까는 기술과 바로 이어진다.

    sunny-day  -> sun          rain-dance -> rain
    sandstorm  -> sandstorm    snowscape  -> snow

── 보정이 두 종류다 ──
  1. 기술 위력      비에서 물 기술 1.5배, 불꽃 기술 0.5배
  2. 방어 능력치    모래바람에서 바위 타입의 '특수방어' 1.5배
                    눈에서 얼음 타입의 '방어' 1.5배

  둘이 붙는 능력치가 달라서 def_boost_stat 으로 구분한다.

── 값의 출처 ──
9세대 본가 기준이다. 8세대까지 '싸라기눈(hail)'은 얼음 타입을 뺀 전원이
매 턴 1/16을 잃었지만, 9세대 '눈(snow)'은 지속 데미지가 없고 대신 얼음
타입의 방어가 1.5배가 된다. 포챔스가 다르면 WEATHERS 만 고치면 된다.
"""

from pokemon_champions.db import connect

from . import paths
from . import schema
from .parse_utils import render, mogrify_rows

FILENAME = "11_weathers.sql"
TABLE = "weathers"
COLUMNS = ["name", "ko_name", "boost_type", "boost_mult",
           "weaken_type", "weaken_mult",
           "def_boost_type", "def_boost_stat", "def_boost_mult",
           "chip_damage", "chip_immune", "note"]
DDL = schema.WEATHERS

WEATHERS = [
    ("sun", "쾌청",
     "fire", 1.5, "water", 0.5, None, None, None, None, None,
     "솔라빔이 즉시 발동. 대타출동·아침햇살 회복량 2/3"),
    ("rain", "비",
     "water", 1.5, "fire", 0.5, None, None, None, None, None,
     "번개·폭풍이 필중. 아침햇살 회복량 1/4"),
    ("sandstorm", "모래바람",
     None, None, None, None, "rock", "d", 1.5,
     1 / 16, ["rock", "ground", "steel"],
     "바위 타입의 특수방어 1.5배"),
    ("snow", "눈",
     None, None, None, None, "ice", "b", 1.5, None, None,
     "얼음 타입의 방어 1.5배. 9세대부터 지속 데미지 없음"),
]


def build(conn):
    """11_weathers.sql 전문을 만들어 돌려준다. (4행)"""
    cur = conn.cursor()
    for w in WEATHERS:
        print(f"{w[0]:<10} {w[1]}")
    return render(schema.WEATHERS, TABLE, COLUMNS,
                  mogrify_rows(cur, WEATHERS, len(COLUMNS)))


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"\n{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
