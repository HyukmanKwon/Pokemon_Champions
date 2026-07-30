"""
데이터베이스 구축 스크립트.

    python main.py

database/sql/ 폴더를 만들고, 아래 순서대로
  (1) 생성기를 돌려 SQL 파일을 만들고  (2) 바로 DB에 실행한다.

  01_types.sql          타입 상성표        고정값     API 0회
  02_natures.sql        성격 21종          고정값     API 0회
  03_pokemons.sql       포켓몬             PokeAPI
  04_moves.sql          기술               PokeAPI
  05_abilities.sql      특성               PokeAPI    <- pokemons 필요
  06_items.sql          도구               PokeAPI
  07_pokemon_moves.sql  포켓몬-기술 연결   PokeAPI    <- pokemons, moves 필요
  08_stat_stages.sql    랭크 변화 배수     고정값     API 0회
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
  database/sql/ 에 파일이 남아 있어도 재사용하지 않는다.
  전체 약 1300회. SQL 파일만 따로 뽑고 싶으면 개별 생성기를 쓴다.

    python get_items.py        sql/06_items.sql 만 생성 (DB 실행 안 함)
"""

import db

import get_types
import get_natures
import get_pokemons
import get_moves
import get_abilities
import get_items
import get_pokemon_moves
import get_stat_stages
import get_status_conditions
import get_mega_evolutions
import get_weathers
import get_terrains

# 실행 순서. 앞 단계가 DB에 올라간 뒤에 뒤 단계가 생성된다.
STEPS = [
    get_types,
    get_natures,
    get_pokemons,
    get_moves,
    get_abilities,
    get_items,
    get_pokemon_moves,
    get_stat_stages,
    get_status_conditions,
    get_mega_evolutions,
    get_weathers,
    get_terrains,
]


def row_count(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def ensure_sql(step, conn):
    """단계 하나의 SQL 파일을 만든다. 경로를 돌려준다."""
    path = db.SQL_DIR / step.FILENAME
    path.write_text(step.build(conn), encoding="utf-8")
    return path


def execute_sql(conn, path):
    """SQL 파일 하나를 실행한다."""
    cur = conn.cursor()
    cur.execute(path.read_text(encoding="utf-8"))
    conn.commit()


def main():
    print(f"대상 DB  : {db.DB_CONFIG['dbname']} @ {db.DB_CONFIG['host']}")
    print(f"SQL 폴더 : {db.SQL_DIR}")

    db.SQL_DIR.mkdir(exist_ok=True)
    conn = db.connect()

    for step in STEPS:
        print(f"\n── {step.FILENAME} ──")
        try:
            path = ensure_sql(step, conn)
            execute_sql(conn, path)
        except Exception as e:
            # 롤백하지 않으면 커넥션이 aborted 로 남아 이후 단계가
            # 전부 "current transaction is aborted" 로 무너진다.
            conn.rollback()
            conn.close()
            print(f"\n{step.FILENAME} 에서 멈췄습니다.")
            print(f"  {type(e).__name__}: {e}")
            print("\n앞 단계까지는 DB에 반영돼 있습니다. 이어서 진행할 수 없으니")
            print("README §5 로 전부 지운 뒤 다시 실행하세요.")
            raise SystemExit(1)
        print(f"    실행 완료 - {step.TABLE} {row_count(conn, step.TABLE)}행")

    print("\n구축 완료")
    for step in STEPS:
        print(f"  {step.TABLE:<16} {row_count(conn, step.TABLE):>6}행")
    conn.close()


if __name__ == "__main__":
    main()
