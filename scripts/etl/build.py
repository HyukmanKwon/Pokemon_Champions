"""
데이터베이스 구축 스크립트.

    python -m scripts.etl.build

data/sql/ 폴더를 만들고, 아래 순서대로
  (1) 생성기를 돌려 SQL 파일을 만들고  (2) 바로 DB에 실행한다.

  01_types.sql          타입 상성표        고정값     API 0회
  02_natures.sql        성격 21종          고정값     API 0회
  03_pokemons.sql       포켓몬             PokeAPI
  04_moves.sql          기술               PokeAPI
  05_abilities.sql      특성               PokeAPI    <- pokemons 필요
  06_items.sql          도구               PokeAPI
  07_pokemon_moves.sql  포켓몬-기술 연결   PokeAPI    <- pokemons, moves 필요
  09_status_conditions  상태이상 상수      고정값     API 0회
  10_mega_evolutions    메가진화 관계      고정값     <- pokemons, items 필요
  11_weathers.sql       날씨 상수          고정값     API 0회
  12_terrains.sql       필드 상수          고정값     API 0회

생성과 실행을 번갈아 하기 때문에, 뒤 단계가 앞 단계의 테이블을
읽어야 하는 의존 관계가 저절로 맞는다.

── 실행 전 DB가 비어 있어야 한다 ──
  SQL 파일의 CREATE TYPE / CREATE TABLE 에 IF NOT EXISTS 가 없어서,
  이미 테이블이 있는 DB에 실행하면 "already exists" 로 멈춘다.
  다시 구축하려면 psql 에서 먼저 지운다.

    DROP TABLE IF EXISTS pokemon_moves, items, abilities,
        moves, pokemons, pokemon_types, pokemon_natures CASCADE;
    DROP TYPE IF EXISTS pokemon_types_enum, pokemon_natures_enum CASCADE;

── 매 실행마다 PokeAPI 를 다시 호출한다 ──
  data/sql/ 에 파일이 남아 있어도 재사용하지 않는다.
  전체 약 1300회. 한 표만 따로 뽑고 싶으면 --only 를 준다.

── 부분 실행 ──
      python -m scripts.etl.build --only items          06_items.sql 만 생성
      python -m scripts.etl.build --only items --exec   생성하고 DB 에도 실행
      python -m scripts.etl.build --only 06 --only 07   여러 개

  --only 는 SQL 파일만 만들고 DB 를 건드리지 않는 것이 기본이다. 한 표만
  다시 넣는 일은 드물고, 잘못 넣으면 되돌릴 방법이 psql 뿐이라(README §7)
  실행은 --exec 로 따로 시키게 한다.

  예전에는 생성기마다 main() 이 있어서 `python -m scripts.etl.get_items` 로
  돌렸다. 그 아홉 줄이 열두 파일에 똑같이 들어 있었고, 파일을 쓰는 자리가
  여기 ensure_sql() 과 둘로 갈려 있었다. 진입점을 여기 하나로 모은다.
"""

import argparse

from pokemon_champions.config import DB_CONFIG
from pokemon_champions.db import connect

from . import paths
from . import (get_abilities, get_items, get_mega_evolutions, get_moves,
               get_natures, get_pokemon_moves, get_pokemons,
               get_status_conditions, get_terrains, get_types, get_weathers)

# 실행 순서. 앞 단계가 DB에 올라간 뒤에 뒤 단계가 생성된다.
STEPS = [
    get_types,
    get_natures,
    get_pokemons,
    get_moves,
    get_abilities,
    get_items,
    get_pokemon_moves,
    get_status_conditions,
    get_mega_evolutions,
    get_weathers,
    get_terrains,
]


def step_name(step):
    """모듈 이름 꼬리. scripts.etl.get_items -> items"""
    return step.__name__.rsplit(".", 1)[-1].removeprefix("get_")


def select(names):
    """--only 로 받은 이름들을 STEPS 의 부분집합으로. 순서는 STEPS 를 따른다.

    세 가지로 걸린다 — 모듈 꼬리(items) · 파일명 앞자리(06) · 확장자 뺀
    파일명(06_items). 손으로 치는 값이라, 무엇을 기억하고 있든 걸리는
    편이 낫다. 하나라도 못 찾으면 그 자리에서 멈춘다 — 오타를 조용히
    건너뛰면 "돌렸는데 파일이 안 바뀐다" 가 된다.
    """
    wanted = {n.lower().removesuffix(".sql") for n in names}
    chosen, found = [], set()
    for step in STEPS:
        keys = {step_name(step),
                step.FILENAME.split("_")[0],
                step.FILENAME.removesuffix(".sql")}
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


def ensure_sql(step, conn):
    """단계 하나의 SQL 파일을 만든다. 경로를 돌려준다."""
    path = paths.SQL_DIR / step.FILENAME
    path.write_text(step.build(conn), encoding="utf-8")
    return path


def execute_sql(conn, path):
    """SQL 파일 하나를 실행한다."""
    cur = conn.cursor()
    cur.execute(path.read_text(encoding="utf-8"))
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
        help="--only 로 만든 SQL 을 DB 에도 실행한다 (기본은 파일만)")
    args = ap.parse_args(argv)

    steps = select(args.only) if args.only else STEPS
    # 전체 구축은 생성과 실행을 번갈아 해야 뒤 단계가 앞 단계의 테이블을
    # 읽을 수 있다. 부분 실행만 파일에서 멈추는 것이 기본이다.
    execute = args.execute or not args.only

    print(f"대상 DB  : {DB_CONFIG['dbname']} @ {DB_CONFIG['host']}")
    print(f"SQL 폴더 : {paths.SQL_DIR}")
    if not execute:
        print("DB 실행  : 안 함 (--exec 로 켠다)")

    paths.SQL_DIR.mkdir(exist_ok=True)
    conn = connect()

    for step in steps:
        print(f"\n── {step.FILENAME} ──")
        try:
            path = ensure_sql(step, conn)
            if execute:
                execute_sql(conn, path)
        except Exception as e:
            # 롤백하지 않으면 커넥션이 aborted 로 남아 이후 단계가
            # 전부 "current transaction is aborted" 로 무너진다.
            conn.rollback()
            conn.close()
            print(f"\n{step.FILENAME} 에서 멈췄습니다.")
            print(f"  {type(e).__name__}: {e}")
            if execute:
                print("\n앞 단계까지는 DB에 반영돼 있습니다. 이어서 진행할 수 없으니")
                print("README §7 로 전부 지운 뒤 다시 실행하세요.")
            raise SystemExit(1)
        if execute:
            print(f"    실행 완료 - {step.TABLE} {row_count(conn, step.TABLE)}행")
        else:
            print(f"    {path}")

    if execute:
        print("\n구축 완료")
        for step in steps:
            print(f"  {step.TABLE:<16} {row_count(conn, step.TABLE):>6}행")
    else:
        print(f"\n{len(steps)}개 파일 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
