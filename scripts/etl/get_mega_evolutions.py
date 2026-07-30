"""메가진화 관계표(mega_evolutions)를 만든다. API 호출 없음.

pokemons 와 items 를 읽어서 만들기 때문에 03·06 단계 뒤에 와야 한다.

── 베이스 찾기 ──
  이름 규칙으로 자른다. `gengar-mega` -> `gengar`,
  `charizard-mega-x` -> `charizard` + variant 'x'.
  규칙에서 벗어나는 것만 MANUAL_BASE 에 적는다.

── 메가스톤 찾기 ──
  스톤 이름은 규칙이 없다. `gengarite`(gengar)는 순순히 잘리지만
  `blastoisinite`(blastoise), `heracronite`(heracross), `alakazite`(alakazam)
  처럼 철자가 깎이거나 늘어난다. 그래서 접두사가 가장 길게 겹치는
  스톤을 고르는 방식으로 맞춘다.

  겹치는 길이가 베이스 이름의 60% 에 못 미치면 매칭하지 않고 NULL 로
  두고 끝에 목록을 출력한다. 틀린 스톤을 넣느니 비워두는 편이 낫다.

단독 실행:
    python get_mega_evolutions.py
"""

from pokemon_champions.db import connect

from . import paths
from . import schema
from .get_pokemons import split_mega
from .parse_utils import render, mogrify_rows

FILENAME = "10_mega_evolutions.sql"
TABLE = "mega_evolutions"
COLUMNS = ["mega_name", "base_name", "variant", "item_name"]
DDL = schema.MEGA_EVOLUTIONS
USES_API = False   # 생성 시 PokeAPI를 호출하는가

# 이름 규칙으로 베이스를 못 찾는 예외.
#   pyroar-mega 의 베이스는 pyroar 인데, 목록에는 pyroar-male 로 들어 있다.
MANUAL_BASE = {
    "pyroar-mega": "pyroar-male",
}

# 접두사가 이만큼은 겹쳐야 같은 포켓몬으로 본다
MIN_PREFIX_RATIO = 0.6
MIN_PREFIX_LEN = 4

# 스톤 이름에는 성별 구분이 없다. meowstic-male 과 meowstic-female 이
# 똑같이 meowsticite 를 쓴다. 매칭할 때만 이 꼬리를 떼어낸다.
FORM_SUFFIXES = ("-male", "-female")


def match_key(base):
    """스톤과 비교할 때 쓸 이름. meowstic-female -> meowstic"""
    for suffix in FORM_SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def select_pokemons(cur):
    cur.execute("SELECT name, is_mega FROM pokemons ORDER BY name")
    rows = cur.fetchall()
    return {n for n, _ in rows}, [n for n, is_mega in rows if is_mega]


def select_stones(cur):
    cur.execute(
        "SELECT name FROM items WHERE category = 'mega-stones' ORDER BY name")
    return [row[0] for row in cur.fetchall()]


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


def build(conn):
    """10_mega_evolutions.sql 전문을 만들어 돌려준다. (API 호출 없음)"""
    cur = conn.cursor()
    names, megas = select_pokemons(cur)
    stones = select_stones(cur)
    print(f"DB 메가폼 수: {len(megas)} / 메가스톤 수: {len(stones)}")

    values = []
    no_base = []
    no_stone = []
    for mega in megas:
        base, variant = split_mega(mega)
        base = MANUAL_BASE.get(mega, base)
        if base not in names:
            no_base.append(mega)
            print(f"{mega} - 베이스 없음")
            continue
        stone = match_stone(base, variant, stones)
        if stone is None:
            no_stone.append(mega)
        values.append((mega, base, variant, stone))
        print(f"{mega} <- {base} / {stone}")

    print(f"\n연결 {len(values)}행")
    print(f"베이스 없음: {len(no_base)}개 - {no_base}")
    print(f"스톤 못 찾음: {len(no_stone)}개 - {no_stone}")
    return render(schema.MEGA_EVOLUTIONS, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"\n{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
