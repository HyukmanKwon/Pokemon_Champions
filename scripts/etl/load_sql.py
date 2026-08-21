"""data/sql/ 에 있는 SQL 을 빈 DB 에 넣는다. API 를 부르지 않는다.

    createdb pokemon
    python -m scripts.etl.load_sql

    python -m scripts.etl.load_sql --dry-run    무엇을 넣을지만 본다

── build.py 와 무엇이 다른가 ──
  build.py 는 PokeAPI 에 1,900번 물어서 SQL 을 새로 만든다. 몇 분 걸리고,
  부르는 날짜에 따라 결과가 달라지고, 무엇보다 사람이 손으로 확정한 값을
  되살리지 못한다 — 애노테이터로 고친 한국어 표기와 기술 플래그는
  PokeAPI 어디에도 없다.

  이 스크립트는 그 결과물을 그대로 넣는다. 몇 초 걸리고, 누가 언제
  돌려도 같은 DB 가 선다. 설치하는 쪽이 쓰는 것은 이쪽이다.

  build.py 는 새 레귤레이션이 나왔을 때 관리자가 돌린다. 그 뒤
  dump_sql.py 로 다시 받아 적어 커밋하면, 다음 사람은 또 이 스크립트만
  돌리면 된다.

── 파일 순서는 이름순 ──
  01_ 부터 12_ 까지 앞의 번호가 곧 실행 순서다. 뒤 파일이 앞 파일의
  테이블을 참조하므로(pokemon_moves 는 pokemons 와 moves 가 있어야 한다)
  순서를 바꾸면 외래키에서 멈춘다.

  build.py 의 STEPS 를 읽지 않고 폴더를 보는 이유는, 받은 파일만 있으면
  돌아야 하기 때문이다. 생성기는 배포판에 없을 수도 있다.

── 채용률 두 표는 여기서 만든다 ──
  usage_names · usage_snapshots · usage_rows 는 SQL 파일에 없다.
  PokeAPI 가 아니라 championsbattledata.com 에서 하루 한 벌씩 쌓이는
  것이라, 배포할 내용이 아니라 빈 표만 있으면 된다. DDL 은 schema.py
  에서 가져온다.

  받은 사람은 python -m scripts.etl.sync.usage --backfill 로 채운다.

── 이미 있는 DB 에는 넣지 않는다 ──
  DDL 에 IF NOT EXISTS 가 없어서 두 번째 실행은 "already exists" 로
  멈춘다. 그게 맞다 — 덮어쓰면 무엇이 지워졌는지 아무도 모른다.
  다시 넣으려면 먼저 지운다.

      python -m scripts.etl.load_sql --drop-sql   지우는 SQL 을 찍는다
"""

import argparse
import sys

import psycopg2

from pokemon_champions.config import DB_CONFIG, SQL_DIR
from pokemon_champions.db import connect

from . import schema

def sql_files():
    """00_schema.sql 다음 01_content.sql. 하나도 없으면 멈춘다.

    이름순이 곧 실행 순서다 — 표를 전부 만든 뒤에 넣는다. 스키마와 데이터를
    가른 이유는 출처가 다르기 때문이다. 00 은 schema.py 에서 나오고,
    01 은 지금 DB 에서 나온다. (dump_sql)
    """
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(
            f"{SQL_DIR} 에 SQL 파일이 없다.\n"
            "  저장소에서 받았다면 data/sql/ 이 같이 왔어야 한다.\n"
            "  직접 만들려면: python -m scripts.etl.build"
        )
    return files


def drop_sql():
    """전부 지우는 SQL. 찍어만 주고 실행하지 않는다.

    뷰를 먼저 지운다. 표에 CASCADE 를 걸면 뷰도 같이 딸려 나가지만, 그러면
    "무엇이 지워졌는지" 가 NOTICE 로만 남는다. 이름을 적어 두면 지우는
    목록만 읽어도 무엇이 있었는지 보인다.
    """
    views = ", ".join(name for name, _ in schema.VIEWS)
    tables = ", ".join(schema.ALL_TABLES)
    enums = ", ".join(schema.ALL_ENUMS)
    return (f"DROP VIEW  IF EXISTS {views} CASCADE;\n"
            f"DROP TABLE IF EXISTS {tables} CASCADE;\n"
            f"DROP TYPE  IF EXISTS {enums} CASCADE;")


def row_count(cur, table):
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="넣지 않고 무엇을 넣을지만 본다")
    ap.add_argument("--drop-sql", action="store_true",
                    help="전부 지우는 SQL 을 찍는다 (실행하지 않는다)")
    args = ap.parse_args(argv)

    if args.drop_sql:
        print(drop_sql())
        return 0

    files = sql_files()
    print(f"대상 DB  : {DB_CONFIG['dbname']} @ {DB_CONFIG['host']}")
    print(f"SQL 폴더 : {SQL_DIR}")

    if args.dry_run:
        for path in files:
            print(f"  {path.name:<24} {path.stat().st_size:>9,} bytes")
        print(f"\n파일 {len(files)}개. 확인만 했다")
        return 0

    conn = connect()
    cur = conn.cursor()

    # 한 덩어리로 넣는다. 중간에 멈추면 전부 되돌린다 — 절반만 들어간
    # DB 는 "다시 돌리면 되는" 상태가 아니라 손으로 치워야 하는 상태다.
    try:
        for path in files:
            cur.execute(path.read_text(encoding="utf-8"))
            print(f"  {path.name}")
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        conn.close()
        print(f"\n멈췄습니다. 아무것도 들어가지 않았습니다.")
        print(f"  {type(e).__name__}: {str(e).strip()}")
        if "already exists" in str(e):
            print("\n이미 만들어진 DB 입니다. 다시 넣으려면 먼저 지우세요.")
            print("  python -m scripts.etl.load_sql --drop-sql | psql -d "
                  f"{DB_CONFIG['dbname']}")
        return 1

    print("\n넣기 완료")
    for table in sorted(schema.ALL_TABLES):
        print(f"  {table:<20} {row_count(cur, table):>8,}행")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
