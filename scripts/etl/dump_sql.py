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
  플래그와 한국어 표기를 사람이 눈으로 고치고, 빠진 기술을 채우고,
  로스터를 갈아끼운다 — 전부 psql 로 직접 한다. 그래서 재구축 결과와
  지금 DB 가 같다는 보장이 없다. 실제로 07/30 에 만든 파일과 지금 DB 는
  이만큼 달랐다.

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
from . import schema
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


SCHEMA_FILE = "00_schema.sql"
CONTENT_FILE = "01_content.sql"


def rows_sql(cur, table, columns):
    """지금 DB 의 행으로 INSERT 문을 만든다. 행이 없으면 빈 문자열."""
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
        return "", 0
    return sql_of(cur, table, columns, values), len(values)


def db_columns(cur, table):
    cur.execute(
        "SELECT attname FROM pg_attribute "
        "WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def table_columns():
    """{테이블: COLUMNS}. 생성기들이 선언한 것을 한 곳에 모은다.

    DB 에서 칼럼을 읽어오지 않는 이유는, 그러면 schema.py 와 DB 가 어긋나도
    조용히 지나가기 때문이다. 생성기가 적어 둔 목록과 대조해야 그 어긋남이
    table_sql 에서 그 자리에 멈춘다.
    """
    out = {}
    for step in STEPS:
        out[step.TABLE] = step.COLUMNS
        for table, columns in getattr(step, "EXTRA", []):
            out[table] = columns
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="파일을 쓰지 않고 달라지는 것만 보고한다")
    args = parser.parse_args()

    paths.SQL_DIR.mkdir(exist_ok=True)
    conn = connect()
    cur = conn.cursor()

    columns_of = table_columns()
    body, counts = [], []
    for table in schema.CONTENT_ORDER:
        columns = columns_of.get(table)
        if columns is None:
            raise SystemExit(f"{table}: 어느 생성기도 COLUMNS 를 선언하지 않았다.")
        sql, n = rows_sql(cur, table, columns)
        if sql:
            body.append(sql)
        counts.append((table, n))

    files = {
        SCHEMA_FILE: schema.SCHEMA_SQL,
        CONTENT_FILE: "\n".join(body),
    }

    changed = 0
    for name, text in files.items():
        path = paths.SQL_DIR / name
        old = path.read_text(encoding="utf-8") if path.exists() else None
        mark = "그대로" if old == text else ("새 파일" if old is None else "바뀜")
        if mark != "그대로":
            changed += 1
        if not args.dry_run:
            path.write_text(text, encoding="utf-8")
        print(f"  {mark:6} {name}")

    print()
    for table, n in counts:
        print(f"    {table:<22}{n:>8,}행")

    conn.close()
    where = "확인만 했다" if args.dry_run else f"기록: {paths.SQL_DIR}"
    print(f"\n2개 중 {changed}개가 파일과 다르다. {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
