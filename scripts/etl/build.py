"""데이터베이스를 처음부터 짓는다. 재구축의 유일한 진입점.

    python -m scripts.etl.build                    전체 (PokeAPI 약 1,900회)
    python -m scripts.etl.build --only items       06_items 만 만든다
    python -m scripts.etl.build --only items --exec  DB 에도 넣는다

**프로젝트 루트에서** 돌린다. 그냥 쓰려는 것이라면 이 파일이 아니라
load_sql 이다 — data/sql/ 이 저장소에 들어 있어 몇 초면 끝난다.

    python -m scripts.etl.load_sql

── 세 방향을 헷갈리지 말 것 ──
    load_sql   설치할 때마다   data/sql/ -> DB.   API 0회, 몇 초
    build      새 레귤레이션   PokeAPI  -> DB.    약 1,900회, 몇 분
    dump_sql   DB 를 고친 뒤   DB -> data/sql/,   그리고 커밋

  이 파일은 data/sql/ 을 쓰지 않는다. 파일로 굳히는 것은 dump_sql 의
  일이다. 둘을 갈라 둔 이유는 출처가 하나여야 하기 때문이다 — 파일은
  언제나 지금 DB 를 받아 적은 것이고, 그래서 "파일과 DB 가 다르다" 를
  dump_sql 이 혼자 판정할 수 있다.

── 실행 전 DB 가 비어 있어야 한다 ──
  CREATE TYPE / CREATE TABLE 에 IF NOT EXISTS 가 없어서, 이미 표가 있는
  DB 에 실행하면 "already exists" 로 멈춘다. 먼저 지운다.

      python -m scripts.etl.load_sql --drop-sql | psql -d pokemon

── 값이 어디서 오는가 ──
  이 파일에 적힌 고정값     타입 상성 324행 · 성격 25행 · 메가진화 관계
  pokeapi.py                포켓몬 · 기술 · 특성 · 도구 · 연결
  sync_usage.py             채용률. 날마다 쌓이므로 여기 안 들어온다

  고정값이 여기 있는 이유는 API 를 안 부르기 때문이다. 열여덟 줄짜리
  상성표를 받으러 남의 서버에 가면 "호출 0회" 를 잃는다.

  날씨·필드·상태이상은 표가 아니다 — src/pokemon_champions/calc/rules.py
  의 상수다. 열다섯 줄이라 표로 둘 이유가 없었다.

── 표를 먼저 다 만든다 ──
  전에는 단계마다 자기 CREATE TABLE 을 들고 다녀서 실행 순서가 곧 생성
  순서였다. 이제 순서는 schema.CREATE_ORDER 한 곳이 정하고, 생성기는
  넣을 것만 만든다.
"""

import argparse
from typing import Callable, NamedTuple

from pokemon_champions.config import DB_CONFIG, SQL_DIR
from pokemon_champions.db import connect

from . import pokeapi
from . import schema
from .schema import sql_of


def literal_build(conn, table, columns, values, echo=None):
    """코드에 적힌 행 목록을 그대로 SQL 로. API 를 안 부르는 생성기의 몸통.

    echo 는 한 행을 어떻게 찍을지 정하는 함수다. 생성기마다 보고 싶은
    칸이 달라서(성격은 이름만, 타입은 이름+한글) 형식까지 통일하지는
    않는다. None 이면 아무것도 안 찍는다.
    """
    if echo is not None:
        for v in values:
            print(echo(v))
    return sql_of(conn.cursor(), table, columns, values)


# ─────────────────────────────────────────────────────────────
# pokemon_types · pokemon_type_names — 타입 상성과 이름
# 18×18 배수표. 세대가 바뀌어도 변하지 않아서 적어 둔다.
# ─────────────────────────────────────────────────────────────

TYPES_TABLE = "pokemon_types"
TYPES_COLUMNS = ["attack_type", "defense_type", "multiplier"]

TYPE_LIST = schema.TYPE_NAMES

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

TYPE_NAMES_TABLE = "pokemon_type_names"
TYPE_NAMES_COLUMNS = ["type_name", "language", "name"]

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


def type_multiplier(attack, defense):
    """공격타입이 방어타입에게 주는 배수. 표에 없으면 1.0."""
    for mult, targets in TYPE_CHART[attack].items():
        if defense in targets:
            return mult
    return 1.0


def build_types(conn):
    """01_types.sql 전문을 만들어 돌려준다. (API 호출 없음)

    표가 둘이다 — 배수표(pokemon_types)와 언어별 표기(pokemon_type_names).

    TYPE_CHART 는 '배수 -> 그 배수를 받는 타입들' 이라 빈칸이 많다. 여기서
    18×18 을 전부 펴서 324행으로 만든다 — 표에 없는 짝이 1.0 이라는 것을
    조회하는 쪽이 알아야 할 이유가 없다.
    """
    values = [(atk, dfn, type_multiplier(atk, dfn))
              for atk in TYPE_LIST for dfn in TYPE_LIST]
    print(f"{len(TYPE_LIST)}×{len(TYPE_LIST)} = {len(values)}행")
    sql = literal_build(conn, TYPES_TABLE, TYPES_COLUMNS, values)

    names = [(t, lang, TYPE_LABELS[t][i])
             for t in TYPE_LIST
             for i, lang in enumerate(NAME_LANGUAGES)]
    print(f"{len(TYPE_LIST)}타입 × {len(NAME_LANGUAGES)}언어 = {len(names)}행")
    return sql + "\n" + sql_of(conn.cursor(), TYPE_NAMES_TABLE, TYPE_NAMES_COLUMNS, names)

# ─────────────────────────────────────────────────────────────
# pokemon_natures — 성격 25종
# ─────────────────────────────────────────────────────────────

NATURES_TABLE = "pokemon_natures"
NATURES_COLUMNS = ["en_name", "ko_name", "up", "down"]

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


def build_natures(conn):
    """02_natures.sql 전문을 만들어 돌려준다. (25행, API 호출 없음)"""
    return literal_build(conn, NATURES_TABLE, NATURES_COLUMNS, NATURES,
                         echo=lambda n: f"{n[0]:<10} {n[1]}")

# ─────────────────────────────────────────────────────────────
# mega_evolutions — 메가진화 관계
# pokemons 와 items 를 읽어 만든다. 그 둘 뒤에 와야 한다.
# ─────────────────────────────────────────────────────────────

MEGA_TABLE = "mega_evolutions"
MEGA_COLUMNS = ["mega_id", "base_id", "item_id"]

# 이름 규칙으로 베이스를 못 찾는 예외는 pokeapi.MANUAL_BASE 에 있다.
# can_mega 를 켜는 쪽과 같은 표를 봐야 둘이 어긋나지 않는다.

# 접두사가 이만큼은 겹쳐야 같은 포켓몬으로 본다
MIN_PREFIX_RATIO = 0.6
MIN_PREFIX_LEN = 4

# 스톤 이름에는 폼 구분이 없다. meowstic-male 과 meowstic-female 이
# 똑같이 meowsticite 를 쓰고, floette-eternal 의 스톤도 floette 기준이다.
# 꼬리를 안 떼면 이름이 길어진 만큼 겹침 비율이 떨어져 매칭이 깨진다.
FORM_SUFFIXES = ("-male", "-female", "-eternal")


def match_key(base):
    """스톤과 비교할 때 쓸 이름. meowstic-female -> meowstic"""
    for suffix in FORM_SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def select_pokemons(cur):
    """({이름: id}, 메가폼 이름들). 메가폼 여부는 이름 규칙으로 가른다 —
    pokemons 에 is_mega 칸이 없고, pokeapi.split_mega 가 그 판정의 단일 출처다.

    표에는 id 로 넣지만 고르는 일(베이스 찾기·스톤 맞추기)은 이름으로 한다.
    그래서 대응표째 들고 나간다."""
    cur.execute("SELECT name, id FROM pokemons ORDER BY name")
    by_name = dict(cur.fetchall())
    return by_name, [n for n in by_name if pokeapi.split_mega(n)[0] is not None]


def select_stones(cur):
    """{스톤 이름: id}. 접두사 비교는 이름으로 하고 넣을 때 id 로 옮긴다."""
    cur.execute("SELECT name, id FROM items "
                "WHERE category = 'mega-stones' ORDER BY name")
    return dict(cur.fetchall())


def stone_variant(stone):
    """charizardite-x -> 'x', gengarite -> None"""
    tail = stone.rsplit("-", 1)
    if len(tail) == 2 and tail[1] in ("x", "y", "z"):
        return tail[1]
    return None


def common_prefix_len(a, b):
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def match_stone(base, variant, stones):
    """베이스와 접두사가 가장 길게 겹치는 스톤. 못 찾으면 None."""
    key = match_key(base)
    best, best_len = None, 0
    for s in stones:
        if stone_variant(s) != variant:
            continue
        n = common_prefix_len(key, s)
        if n > best_len:
            best, best_len = s, n
    if best_len < max(MIN_PREFIX_LEN, MIN_PREFIX_RATIO * len(key)):
        return None
    return best


def build_mega_evolutions(conn):
    """10_mega_evolutions.sql 전문을 만들어 돌려준다. (API 호출 없음)"""
    cur = conn.cursor()
    names, megas = select_pokemons(cur)
    stones = select_stones(cur)
    print(f"DB 메가폼 수: {len(megas)} / 메가스톤 수: {len(stones)}")

    values = []
    no_base = []
    no_stone = []
    for mega in megas:
        base, variant = pokeapi.split_mega(mega)
        base = pokeapi.MANUAL_BASE.get(mega, base)
        if base not in names:
            no_base.append(mega)
            print(f"{mega} - 베이스 없음")
            continue
        stone = match_stone(base, variant, stones)
        if stone is None:
            no_stone.append(mega)
        # 고르는 일은 이름으로 끝났다. 표에는 id 로 넣는다.
        values.append((names[mega], names[base],
                       stones[stone] if stone else None))
        print(f"{mega} <- {base} / {stone}")

    print(f"\n연결 {len(values)}행")
    print(f"베이스 없음: {len(no_base)}개 - {no_base}")
    print(f"스톤 못 찾음: {len(no_stone)}개 - {no_stone}")
    return sql_of(cur, MEGA_TABLE, MEGA_COLUMNS, values)

# ─────────────────────────────────────────────────────────────
# 구축 순서와 실행
# ─────────────────────────────────────────────────────────────

class Step(NamedTuple):
    """구축 한 단계. --only 가 고르는 단위이자 dump_sql 이 읽는 목록이다.

    name    --only 로 부르는 이름
    table   행 수를 세어 찍을 대표 표
    build   conn 을 받아 INSERT 문자열을 돌려주는 함수
    extra   같은 응답에서 나오는 곁다리 표들. (표, COLUMNS) 짝
    """
    name: str
    table: str
    columns: list
    build: Callable
    extra: tuple = ()


# 실행 순서. 앞 단계가 DB 에 올라간 뒤에 뒤 단계가 생성된다.
#
#   abilities 는 pokemons 뒤여야 한다 — 어느 특성을 받을지는 포켓몬
#   응답을 봐야 안다. pokemon_moves 는 pokemons·moves 뒤,
#   mega_evolutions 는 pokemons·items 뒤다.
STEPS = [
    Step("types", TYPES_TABLE, TYPES_COLUMNS, build_types,
         ((TYPE_NAMES_TABLE, TYPE_NAMES_COLUMNS),)),
    Step("natures", NATURES_TABLE, NATURES_COLUMNS, build_natures),
    Step("pokemons", pokeapi.POKEMONS_TABLE, pokeapi.POKEMONS_COLUMNS,
         pokeapi.build_pokemons),
    Step("moves", pokeapi.MOVES_TABLE, pokeapi.MOVES_COLUMNS,
         pokeapi.build_moves,
         ((pokeapi.MOVE_STAT_TABLE, pokeapi.MOVE_STAT_COLUMNS),)),
    Step("abilities", pokeapi.ABILITIES_TABLE, pokeapi.ABILITIES_COLUMNS,
         pokeapi.build_abilities,
         ((pokeapi.LINK_TABLE, pokeapi.LINK_COLUMNS),)),
    Step("items", pokeapi.ITEMS_TABLE, pokeapi.ITEMS_COLUMNS,
         pokeapi.build_items),
    Step("pokemon_moves", pokeapi.POKEMON_MOVES_TABLE,
         pokeapi.POKEMON_MOVES_COLUMNS, pokeapi.build_pokemon_moves),
    Step("mega_evolutions", MEGA_TABLE, MEGA_COLUMNS, build_mega_evolutions),
]


def table_columns():
    """{표: COLUMNS}. 단계들이 선언한 것을 한 곳에 모은다. dump_sql 이 쓴다.

    DB 에서 칼럼을 읽어오지 않는 이유는, 그러면 schema.py 와 DB 가 어긋나도
    조용히 지나가기 때문이다. 단계가 적어 둔 목록과 대조해야 그 어긋남이
    dump_sql 에서 그 자리에 멈춘다.
    """
    out = {}
    for step in STEPS:
        out[step.table] = step.columns
        for table, columns in step.extra:
            out[table] = columns
    return out


def select(names):
    """--only 로 받은 이름들을 STEPS 의 부분집합으로. 순서는 STEPS 를 따른다.

    단계 이름(items)과 표 이름(items) 둘 다 걸린다. 하나라도 못 찾으면
    그 자리에서 멈춘다 — 오타를 조용히 건너뛰면 "돌렸는데 아무 일도
    안 일어난다" 가 된다.
    """
    wanted = {n.lower().removesuffix(".sql") for n in names}
    chosen, found = [], set()
    for step in STEPS:
        keys = {step.name, step.table}
        if wanted & keys:
            chosen.append(step)
            found |= wanted & keys

    missing = wanted - found
    if missing:
        raise SystemExit(
            f"그런 단계가 없습니다: {', '.join(sorted(missing))}\n"
            f"고를 수 있는 것: {', '.join(s.name for s in STEPS)}")
    return chosen


def row_count(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def create_schema(conn):
    """표를 전부 만든다. 단계를 돌기 전에 한 번."""
    cur = conn.cursor()
    cur.execute(schema.SCHEMA_SQL)
    conn.commit()


def execute_inserts(conn, sql):
    """단계 하나가 만든 INSERT 문들을 실행한다."""
    if not sql.strip():
        return
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="PokeAPI 에서 받아 SQL 을 만들고 DB 에 올린다.")
    ap.add_argument(
        "--only", action="append", metavar="단계",
        help="이 단계만 만든다. 여러 번 줄 수 있다. "
             "items · 06 · 06_items 가 모두 같은 것을 가리킨다")
    ap.add_argument(
        "--exec", dest="execute", action="store_true",
        help="--only 로 만든 INSERT 를 DB 에도 실행한다 (기본은 안 함)")
    args = ap.parse_args(argv)

    steps = select(args.only) if args.only else STEPS
    # 전체 구축은 언제나 실행한다. 뒤 단계가 앞 단계의 표를 읽기 때문이다
    # (abilities 는 포켓몬 응답이 담아 둔 목록을 본다).
    execute = args.execute or not args.only

    print(f"대상 DB  : {DB_CONFIG['dbname']} @ {DB_CONFIG['host']}")
    print(f"SQL 폴더 : {SQL_DIR}")
    if not execute:
        print("DB 실행  : 안 함 (--exec 로 켠다)")

    SQL_DIR.mkdir(exist_ok=True)
    conn = connect()

    if execute:
        create_schema(conn)
        print(f"\n표 {len(schema.CREATE_ORDER)}개 생성 완료")

    for step in steps:
        print(f"\n── {step.table} ──")
        try:
            sql = step.build(conn)
            if execute:
                execute_inserts(conn, sql)
        except Exception as e:
            # 롤백하지 않으면 커넥션이 aborted 로 남아 이후 단계가
            # 전부 "current transaction is aborted" 로 무너진다.
            conn.rollback()
            conn.close()
            print(f"\n{step.table} 에서 멈췄습니다.")
            print(f"  {type(e).__name__}: {e}")
            if execute:
                print("\n앞 단계까지는 DB 에 반영돼 있습니다. 이어서 진행할 수 없으니")
                print("전부 지운 뒤 다시 실행하세요:")
                print("    python -m scripts.etl.load_sql --drop-sql | psql -d pokemon")
            raise SystemExit(1)
        if execute:
            print(f"    실행 완료 - {step.table} {row_count(conn, step.table)}행")

    if execute:
        print("\n구축 완료")
        for step in steps:
            print(f"  {step.table:<16} {row_count(conn, step.table):>6}행")
    else:
        print(f"\n{len(steps)}개 단계 생성 완료 (DB 에는 안 넣었다)")
    conn.close()


if __name__ == "__main__":
    main()
