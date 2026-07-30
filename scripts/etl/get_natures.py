from pokemon_champions.db import connect

from . import paths
from . import schema
from .parse_utils import render, mogrify_rows

FILENAME = "02_natures.sql"
TABLE = "pokemon_natures"
COLUMNS = ["en_name", "ko_name", "up", "down"]
DDL = schema.NATURES
USES_API = False   # 생성 시 PokeAPI를 호출하는가

# (영문명, 한글명, 오르는 능력치, 내리는 능력치)
NATURES = [
    ("lonely",  "외로움",     "a",  "b"),
    ("brave",   "용감",       "a",  "s"),
    ("adamant", "고집",       "a",  "c"),
    ("naughty", "개구쟁이",   "a",  "d"),
    ("bold",    "대담",       "b",  "a"),
    ("relaxed", "무사태평",   "b",  "s"),
    ("impish",  "장난꾸러기", "b",  "c"),
    ("lax",     "촐랑",       "b",  "d"),
    ("timid",   "겁쟁이",     "s",  "a"),
    ("hasty",   "성급",       "s",  "b"),
    ("jolly",   "명랑",       "s",  "c"),
    ("naive",   "천진난만",   "s",  "d"),
    ("modest",  "조심",       "c",  "a"),
    ("mild",    "의젓",       "c",  "b"),
    ("quiet",   "차분",       "c",  "s"),
    ("rash",    "덜렁",       "c",  "d"),
    ("calm",    "온순",       "d",  "a"),
    ("gentle",  "얌전",       "d",  "b"),
    ("sassy",   "건방",       "d",  "s"),
    ("careful", "신중",       "d",  "c"),
    ("serious", "성실",       None, None),
]


def build(conn):
    """02_natures.sql 전문을 만들어 돌려준다. (API 호출 없음)"""
    cur = conn.cursor()
    rows = mogrify_rows(cur, NATURES, len(COLUMNS))
    return render(schema.NATURES, TABLE, COLUMNS, rows)


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"\n{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
