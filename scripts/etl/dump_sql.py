"""지금 DB 를 그대로 data/sql/ 에 받아 적는다.

    python -m scripts.etl.dump_sql              전체
    python -m scripts.etl.dump_sql 04_moves     한 파일만
    python -m scripts.etl.dump_sql --dry-run    무엇이 달라지는지만

── build.py 와 무엇이 다른가 ──
  build.py 는 "PokeAPI 가 지금 뭐라고 하는가" 를 묻는다. 1,900회를 호출하고,
  빈 DB 여야 하고, 결과를 DB 에 밀어 넣는다.

  이 스크립트는 반대다. "내 DB 에 지금 무엇이 들어 있는가" 를 파일로 받아
  적는다. API 를 부르지 않고 DB 를 건드리지도 않는다. 읽기만 한다.

  둘이 갈라지는 이유는 DB 가 빌드 이후로 계속 움직이기 때문이다.
  annotator 로 플래그와 한국어를 고치고, sync_moves 로 기술을 채우고,
  migrate_roster 로 로스터를 갈아끼운다. 그래서 재구축 결과와 지금 DB 가
  같다는 보장이 없다. 실제로 07/30 에 만든 파일과 지금 DB 는 이만큼 달랐다.

      moves          502 -> 498      items   285 -> 166
      pokemons       314 -> 317      pokemon_moves  21,296 -> 21,609


── DDL 은 여전히 schema.py 에서 온다 ──
  DB 에서 CREATE TABLE 을 역으로 만들어 내지 않는다. 그렇게 하면 주석이
  전부 날아가고 schema.py 가 단일 출처라는 규칙도 깨진다. 여기서 DB 에서
  가져오는 것은 행뿐이고, 테이블 정의는 schema.py 를 그대로 쓴다.

  뒤집어 말하면 이 스크립트는 DB 와 schema.py 가 어긋나면 조용히 넘어가지
  않는다. COLUMNS 에 있는 칼럼이 DB 에 없으면 그 자리에서 멈춘다.

── 행 순서는 기본키순 ──
  생성기들은 입력 목록 순서(moves_M_B 등)로 찍지만, 여기서는 기본키로
  정렬한다. 두 번 돌렸을 때 같은 파일이 나와야 diff 로 변화를 볼 수 있다.
  enum 칼럼은 선언 순서로 정렬되므로 타입 상성표는 원래 순서와 같다.
"""

import argparse
import sys

from pokemon_champions.db import connect

from . import paths
from .build import STEPS
from .parse_utils import sql_of


def primary_key(cur, table):
    """기본키 칼럼 이름을 순서대로. 없으면 빈 리스트."""
    cur.execute(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def table_sql(cur, ddl, table, columns):
    """DDL + 지금 DB 의 행으로 INSERT 문을 만든다."""
    missing = set(columns) - set(db_columns(cur, table))
    if missing:
        raise SystemExit(
            f"{table}: COLUMNS 에 있는데 DB 에 없는 칼럼 {sorted(missing)}.\n"
            "  schema.py 와 DB 가 어긋나 있다. 어느 쪽이 맞는지 먼저 정하라."
        )

    order = primary_key(cur, table) or columns
    cur.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY {', '.join(order)}"
    )
    values = cur.fetchall()

    # 행이 없으면 INSERT 를 붙이지 않는다. VALUES; 는 문법 오류다.
    if not values:
        return ddl, 0
    return sql_of(cur, ddl, table, columns, values), len(values)


def db_columns(cur, table):
    cur.execute(
        "SELECT attname FROM pg_attribute "
        "WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def build_file(cur, step):
    """단계 하나의 SQL 전문과 (테이블, 행 수) 목록을 돌려준다.

    한 파일에 표가 여럿일 수 있다. 생성기가 EXTRA 로 알려 주고, 순서는
    적힌 그대로 뒤에 붙는다 — 앞의 표를 참조하는 표가 있으면 그 순서가
    곧 실행 순서다.

        01_types.sql   pokemon_types + pokemon_type_names
        04_moves.sql   moves + move_stat_changes
    """
    sql, n = table_sql(cur, step.DDL, step.TABLE, step.COLUMNS)
    counts = [(step.TABLE, n)]

    for ddl, table, columns in getattr(step, "EXTRA", []):
        extra, m = table_sql(cur, ddl, table, columns)
        sql += "\n" + extra
        counts.append((table, m))

    # 행이 아니라 마지막에 한 번 실행되는 SQL. 파일 경계를 넘는 외래키가
    # 여기로 온다 — pokemon_abilities(03) -> abilities(05) 가 그것이다.
    post = getattr(step, "POST_SQL", "")
    if post:
        sql += "\n" + post

    return sql, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("only", nargs="?",
                        help="파일 이름 일부. 예: 04_moves")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일을 쓰지 않고 달라지는 것만 보고한다")
    args = parser.parse_args()

    steps = [s for s in STEPS if not args.only or args.only in s.FILENAME]
    if not steps:
        raise SystemExit(f"{args.only} 에 맞는 단계가 없다.")

    paths.SQL_DIR.mkdir(exist_ok=True)
    conn = connect()
    cur = conn.cursor()

    changed = 0
    for step in steps:
        sql, counts = build_file(cur, step)
        path = paths.SQL_DIR / step.FILENAME

        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old == sql:
            mark = "그대로"
        elif old is None:
            mark = "새 파일"
            changed += 1
        else:
            mark = "바뀜"
            changed += 1

        if not args.dry_run:
            path.write_text(sql, encoding="utf-8")

        body = " + ".join(f"{t} {n:,}행" for t, n in counts)
        print(f"  {mark:6} {step.FILENAME:<24} {body}")

    conn.close()
    where = "확인만 했다" if args.dry_run else f"기록: {paths.SQL_DIR}"
    print(f"\n{len(steps)}개 중 {changed}개가 파일과 다르다. {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
