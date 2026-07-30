"""종족값·SP·성격으로 실능치를 계산하고 Pokemon 객체를 만든다.

    conn = db.connect()
    p = build(conn, "메가리자몽X", (0, 252, 0, 0, 4, 252), "고집",
              ability="단단한발톱", item="생명의구슬",
              moves=["플레어드라이브", "역린", "지진", "용의춤"])

단독 실행하면 입력을 받아 실능치를 출력한다.

    python stat_calculator.py

── 공식 ──
    HP     = 종족값 + 75 + SP
    나머지  = int((종족값 + 20 + SP) * 성격보정)

  성격 보정은 1.1 / 1.0 / 0.9 이고, 성실은 보정이 없다(up·down 이 둘 다 NULL).
  랭크 변화는 여기서 곱하지 않는다. 교체하면 초기화되므로 데미지 계산
  시점에 적용한다. (pokemons.py 참고)

── DB 커넥션을 인자로 받는다 ──
  모듈 최상단에서 connect() 하지 않는다. import 만 해도 접속이 일어나면
  테스트할 수 없고, 파일이 늘어날수록 커넥션이 같이 늘어난다.
"""

import sys
import unicodedata

from .database import db
from .pokemons import Pokemon, Stats

MAX_SP = 66             # SP 총 투자 가능치
MAX_SP_PER_STAT = 32    # 능력치 하나당 SP 투자 가능치


def normalize(text):
    """한글 입력을 NFC로 맞춘다.

    macOS에서 복사해 온 문자열은 자모가 분리된 NFD일 수 있다. 눈으로는
    같아 보이는데 '성실' != '성실' 이 되어 DB 조회가 조용히 실패한다.
    """
    return unicodedata.normalize("NFC", text.strip())


# ─────────────────────────────────────────────────────────────
# DB 조회
# ─────────────────────────────────────────────────────────────

def fetch_base(conn, ko_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT h, a, b, c, d, s FROM pokemons WHERE ko_name = %s",
        (normalize(ko_name),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 포켓몬: {ko_name}")
    return Stats(*row)


def fetch_pokemon_meta(conn, ko_name):
    """도감 번호(id)와 타입을 읽어온다. 사진/타입 아이콘을 고르는 데 쓴다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, type1, type2 FROM pokemons WHERE ko_name = %s",
        (normalize(ko_name),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 포켓몬: {ko_name}")
    pokemon_id, type1, type2 = row
    return {"id": pokemon_id, "type1": type1, "type2": type2}


def fetch_nature(conn, ko_nature):
    cur = conn.cursor()
    cur.execute(
        "SELECT up, down FROM pokemon_natures WHERE ko_name = %s",
        (normalize(ko_nature),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 성격: {ko_nature}")

    up, down = row
    mods = {}
    if up is not None:
        mods[up] = 1.1
    if down is not None:
        mods[down] = 0.9
    return mods


def fetch_ability_effect(conn, ko_ability):
    cur = conn.cursor()
    cur.execute(
        "SELECT description FROM abilities WHERE ko_name = %s",
        (normalize(ko_ability),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 특성: {ko_ability}")
    return row[0]


def fetch_move_type(conn, ko_move):
    cur = conn.cursor()
    cur.execute(
        "SELECT type FROM moves WHERE ko_name = %s",
        (normalize(ko_move),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 기술: {ko_move}")
    return row[0]

# ─────────────────────────────────────────────────────────────
# 계산
# ─────────────────────────────────────────────────────────────

def make_sp(values):
    """SP 투자값 (h, a, b, c, d, s) 를 Stats 로 만들고 합계를 확인한다."""
    if len(values) != 6:
        raise ValueError(f"SP는 6개여야 합니다. 받은 개수: {len(values)}")
    if any(v < 0 for v in values):
        raise ValueError(f"SP에 음수가 있습니다: {values}")
    if any(v > MAX_SP_PER_STAT for v in values):
        raise ValueError(f"능력치 하나당 SP는 최대 {MAX_SP_PER_STAT}입니다: {values}")

    sp = Stats(*values)
    total = sp.h + sp.a + sp.b + sp.c + sp.d + sp.s
    if total > MAX_SP:
        raise ValueError(f"SP 합계 {total}, 최대 {MAX_SP}")
    return sp


def calc_stats(base, sp, nature):
    """실능치를 계산한다. nature 는 fetch_nature 가 준 {능력치: 배수}."""
    return Stats(
        h=base.h + 75 + sp.h,
        **{k: int((base[k] + 20 + sp[k]) * nature.get(k, 1.0))
           for k in ("a", "b", "c", "d", "s")},
    )


# ─────────────────────────────────────────────────────────────
# 조립
# ─────────────────────────────────────────────────────────────

def build(conn, ko_name, sp_values, ko_nature,
          ability, item=None, moves=None, condition=None):
    """DB를 읽어 Pokemon 하나를 만든다."""
    ko_name = normalize(ko_name)
    base = fetch_base(conn, ko_name)
    sp = make_sp(sp_values)
    nature = fetch_nature(conn, ko_nature)

    return Pokemon(
        name=ko_name,
        stats=calc_stats(base, sp, nature),
        ability=ability,
        item=normalize(item) if item else None,
        moves=[normalize(m) for m in (moves or [])],
        condition=condition,
        nature=normalize(ko_nature),
    )


# ─────────────────────────────────────────────────────────────

def ask(prompt):
    return normalize(input(prompt))


def main():
    conn = db.connect()
    try:
        ko_name = ask("포켓몬 이름: ")
        sp_values = tuple(map(int, ask("SP 투자값 H A B C D S: ").split()))
        ko_nature = ask("성격: ")
        ability = "blaze"
        print()
        print(build(conn, ko_name, sp_values, ko_nature, ability,None,None, None))
    except ValueError as e:
        sys.exit(f"입력 오류: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
