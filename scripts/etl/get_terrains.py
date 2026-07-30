"""필드 상수표(terrains)를 만든다. API 호출 없음.

name 은 기술 이름의 접두사와 같다.

    electric-terrain -> electric    grassy-terrain -> grassy
    misty-terrain    -> misty       psychic-terrain -> psychic

── 필드는 '접지된' 포켓몬에게만 걸린다 ──
  비행 타입, 부유 특성, 풍선 소지, 텔레키네시스 대상은 영향을 받지 않는다.
  이 판정은 테이블이 아니라 계산 코드에서 해야 한다. 위력 보정을 적용하기
  전에 시전자·대상이 접지 상태인지 먼저 확인할 것.

  위력 보정 1.3배도 '기술을 쓰는 쪽이 접지되어 있을 때'만 붙는다.
  일렉트릭필드에서 공중에 뜬 포켓몬이 쓰는 전기 기술은 그대로 1.0배다.

단독 실행:
    python get_terrains.py
"""

from pokemon_champions.db import connect

from . import paths
from . import schema
from .parse_utils import render, mogrify_rows

FILENAME = "12_terrains.sql"
TABLE = "terrains"
COLUMNS = ["name", "ko_name", "boost_type", "boost_mult",
           "weaken_type", "weaken_mult", "heal_fraction", "note"]
DDL = schema.TERRAINS
USES_API = False   # 생성 시 PokeAPI를 호출하는가

TERRAINS = [
    ("electric", "일렉트릭필드",
     "electric", 1.3, None, None, None,
     "접지된 포켓몬은 잠듦 상태가 되지 않는다"),
    ("grassy", "그래스필드",
     "grass", 1.3, None, None, 1 / 16,
     "지진·땅고르기·매그니튜드의 위력 0.5배. 접지된 포켓몬이 매 턴 회복"),
    ("misty", "미스트필드",
     None, None, "dragon", 0.5, None,
     "접지된 포켓몬은 상태이상·혼란에 걸리지 않는다"),
    ("psychic", "사이코필드",
     "psychic", 1.3, None, None, None,
     "접지된 포켓몬에게 우선도 1 이상의 기술이 통하지 않는다"),
]


def build(conn):
    """12_terrains.sql 전문을 만들어 돌려준다. (4행)"""
    cur = conn.cursor()
    for t in TERRAINS:
        print(f"{t[0]:<10} {t[1]}")
    return render(schema.TERRAINS, TABLE, COLUMNS,
                  mogrify_rows(cur, TERRAINS, len(COLUMNS)))


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"\n{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
