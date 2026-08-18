from . import schema
from .parse_utils import literal_build

FILENAME = "02_natures.sql"
TABLE = "pokemon_natures"
COLUMNS = ["en_name", "ko_name", "up", "down"]
DDL = schema.NATURES

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
    ("calm",    "침착",       "d",  "a"),
    ("gentle",  "얌전",       "d",  "b"),
    ("sassy",   "건방",       "d",  "s"),
    ("careful", "신중",       "d",  "c"),
    # 무보정 성격 다섯. 능력치가 안 움직여서 서로 구별할 근거가 이름뿐이다.
    ("serious", "성실",       None, None),
    ("hardy",   "노력",       None, None),
    ("docile",  "온순",       None, None),
    ("bashful", "수줍음",     None, None),
    ("quirky",  "변덕",       None, None),
]


def build(conn):
    """02_natures.sql 전문을 만들어 돌려준다. (25행, API 호출 없음)"""
    return literal_build(conn, DDL, TABLE, COLUMNS, NATURES,
                         echo=lambda n: f"{n[0]:<10} {n[1]}")

