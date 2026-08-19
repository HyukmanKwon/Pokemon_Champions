"""
데이터베이스 구축 스크립트.

    python -m scripts.etl.build

표를 전부 만든 뒤(schema.CREATE_ORDER), 생성기를 순서대로 돌려 넣는다.

  pokemon_types        타입 상성표        고정값     API 0회
  pokemon_type_names   타입 이름 3언어    고정값     API 0회
  pokemon_natures      성격 25종          고정값     API 0회
  pokemons             포켓몬             PokeAPI
  pokemon_abilities    포켓몬-특성        (위와 같은 응답)
  moves                기술               PokeAPI
  move_stat_changes    능력 변화          (위와 같은 응답)
  abilities            특성               PokeAPI    <- pokemon_abilities 필요
  items                도구               PokeAPI
  pokemon_moves        포켓몬-기술 연결   PokeAPI    <- pokemons, moves 필요
  mega_evolutions      메가진화 관계      고정값     <- pokemons, items 필요

날씨·필드·상태이상은 여기 없다 — src/pokemon_champions/calc/rules.py 의
상수다. 열다섯 줄짜리라 표로 둘 이유가 없었다.

── 표를 먼저 다 만든다 ──
  전에는 단계마다 자기 CREATE TABLE 을 들고 다녀서, 실행 순서가 곧 생성
  순서였다. 03 단계의 표가 05 단계의 표를 참조하면 외래키를 나중에 ALTER
  로 붙여야 했다. 이제 순서는 schema.CREATE_ORDER 한 곳이 정하고, 생성기는
  넣을 것만 만든다.

── 이 스크립트는 data/sql/ 을 쓰지 않는다 ──
  DB 에 넣기만 한다. 파일로 굳히는 것은 dump_sql 의 일이다.

      python -m scripts.etl.build      PokeAPI -> DB
      python -m scripts.etl.dump_sql   DB -> data/sql/

  둘을 갈라 둔 이유는 출처가 하나여야 하기 때문이다. 파일은 언제나 지금
  DB 를 받아 적은 것이고, 그래서 "파일과 DB 가 다르다" 를 dump_sql 이
  혼자 판정할 수 있다.

── 실행 전 DB가 비어 있어야 한다 ──
  CREATE TYPE / CREATE TABLE 에 IF NOT EXISTS 가 없어서, 이미 표가 있는
  DB 에 실행하면 "already exists" 로 멈춘다. 먼저 지운다.

      python -m scripts.etl.load_sql --drop-sql | psql -d pokemon

── 매 실행마다 PokeAPI 를 다시 호출한다 ──
  전체 약 1,900회. 한 표만 따로 뽑고 싶으면 --only 를 준다.

── 부분 실행 ──
      python -m scripts.etl.build --only items          만들기만 (DB 안 건드림)
      python -m scripts.etl.build --only items --exec   DB 에도 넣기
      python -m scripts.etl.build --only items --only moves

  --exec 없이는 API 만 부르고 아무 데도 안 쓴다. 잘못 넣으면 되돌릴 방법이
  psql 뿐이라 실행을 따로 시키게 한다.
"""

import argparse

from pokemon_champions.config import DB_CONFIG
from pokemon_champions.db import connect

from . import paths
from . import schema
from . import (get_abilities, get_items, make_mega_evolutions, get_moves,
               make_natures, get_pokemon_moves, get_pokemons, make_types)

# 실행 순서. 앞 단계가 DB에 올라간 뒤에 뒤 단계가 생성된다.
STEPS = [
    make_types,
    make_natures,
    get_pokemons,
    get_moves,
    get_abilities,
    get_items,
    get_pokemon_moves,
    make_mega_evolutions,
]


def step_name(step):
    """모듈 이름에서 출처 접두사를 뗀 꼬리.

        scripts.etl.get_items   -> items
        scripts.etl.make_types  -> types

    접두사는 값이 어디서 오는지를 말한다 — make_ 는 코드에 적힌 고정값,
    get_ 는 PokeAPI. 고르는 이름에는 그 구분이 필요 없다.
    """
    tail = step.__name__.rsplit(".", 1)[-1]
    for prefix in ("get_", "make_"):
        tail = tail.removeprefix(prefix)
    return tail


def select(names):
    """--only 로 받은 이름들을 STEPS 의 부분집합으로. 순서는 STEPS 를 따른다.

    모듈 꼬리(items)와 표 이름(items) 둘 다 걸린다. 하나라도 못 찾으면
    그 자리에서 멈춘다 — 오타를 조용히 건너뛰면 "돌렸는데 아무 일도
    안 일어난다" 가 된다.
    """
    wanted = {n.lower().removesuffix(".sql") for n in names}
    chosen, found = [], set()
    for step in STEPS:
        keys = {step_name(step), step.TABLE}
        if wanted & keys:
            chosen.append(step)
            found |= wanted & keys

    missing = wanted - found
    if missing:
        raise SystemExit(
            f"그런 단계가 없습니다: {', '.join(sorted(missing))}\n"
            f"고를 수 있는 것: {', '.join(step_name(s) for s in STEPS)}")
    return chosen


def row_count(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def create_schema(conn):
    """표를 전부 만든다. 단계를 돌기 전에 한 번.

    전에는 단계마다 자기 CREATE TABLE 을 들고 다녔다. 그래서 실행 순서가
    곧 생성 순서였고, 03 단계의 표가 05 단계의 표를 참조하면 외래키를
    나중에 ALTER 로 붙여야 했다. 이제 순서는 schema.CREATE_ORDER 한 곳이
    정하고, 생성기는 넣을 것만 만든다.
    """
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
    # (05_abilities 는 pokemon_abilities 를 훑어 대상 목록을 만든다).
    execute = args.execute or not args.only

    print(f"대상 DB  : {DB_CONFIG['dbname']} @ {DB_CONFIG['host']}")
    print(f"SQL 폴더 : {paths.SQL_DIR}")
    if not execute:
        print("DB 실행  : 안 함 (--exec 로 켠다)")

    paths.SQL_DIR.mkdir(exist_ok=True)
    conn = connect()

    if execute:
        create_schema(conn)
        print(f"\n표 {len(schema.CREATE_ORDER)}개 생성 완료")

    for step in steps:
        print(f"\n── {step.TABLE} ──")
        try:
            sql = step.build(conn)
            if execute:
                execute_inserts(conn, sql)
        except Exception as e:
            # 롤백하지 않으면 커넥션이 aborted 로 남아 이후 단계가
            # 전부 "current transaction is aborted" 로 무너진다.
            conn.rollback()
            conn.close()
            print(f"\n{step.TABLE} 에서 멈췄습니다.")
            print(f"  {type(e).__name__}: {e}")
            if execute:
                print("\n앞 단계까지는 DB에 반영돼 있습니다. 이어서 진행할 수 없으니")
                print("README §7 로 전부 지운 뒤 다시 실행하세요.")
            raise SystemExit(1)
        if execute:
            print(f"    실행 완료 - {step.TABLE} {row_count(conn, step.TABLE)}행")

    if execute:
        print("\n구축 완료")
        for step in steps:
            print(f"  {step.TABLE:<16} {row_count(conn, step.TABLE):>6}행")
    else:
        print(f"\n{len(steps)}개 단계 생성 완료 (DB 에는 안 넣었다)")
    conn.close()


if __name__ == "__main__":
    main()
