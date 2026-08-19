"""moves_M_B 에 있는데 DB 에 없는 기술을 채운다. 전체 재구축 없이.

    python -m scripts.etl.fill_moves --dry-run   무엇이 들어갈지만 확인
    python -m scripts.etl.fill_moves             실제 반영

── 왜 필요한가 ──
  get_moves.py 의 moves_M_B 를 고쳐도 DB 는 그대로다. 재구축을 해야 반영되는데
  그건 PokeAPI 1,900회 호출이라 기술 몇 개 때문에 돌리기엔 과하다.

  실제로 check_moves.py 로 외부 목록과 대조해 찾은 4개를 moves_M_B 에 넣고도
  DB 에는 안 들어간 상태가 한동안 이어졌다. 애노테이터에 502개 중 498개만
  확인 표시가 뜬 이유가 그것이다.

  (그 4개는 그 뒤 포챔스에서 못 쓰는 기술로 판명나서 도로 뺐다.
   get_moves.py 의 EXCLUDED_MOVES 를 보라. 여기서는 "목록과 DB 가 어긋날
   수 있다" 는 사례로만 남긴다.)

── pokemon_moves 도 같이 채운다 ──
  moves 에만 넣으면 "아무 포켓몬도 못 배우는 기술"이 된다. 곧 붙일 검증이
  pokemon_moves 를 보기 때문에, 정상적인 엔트리가 거부되는데 원인이 검증 코드가
  아니라 데이터라 찾기가 아주 고약해진다.

  다행히 /move 응답의 learned_by_pokemon 에 배우는 포켓몬이 들어 있어서,
  기술 수만큼의 호출만으로 두 테이블을 다 채울 수 있다.

── 폼 변이는 추론이다 ──
  learned_by_pokemon 은 보통 원종만 준다(charizard). 우리 pokemons 테이블에는
  charizard-mega-x 같은 폼도 있고, 그 폼들은 원종의 기술을 그대로 배운다.
  그래서 "원종 이름 + 하이픈" 으로 시작하는 폼도 같이 넣는다.

  이건 추론이므로 결과를 따로 세어서 보고한다. 원종 매칭만 원하면
  --exact-only 를 준다. 정확히 하려면 get_pokemon_moves 를 다시 돌려야 하고,
  그건 포켓몬 수만큼(313회) 호출한다.
"""

import argparse
import sys

from pokemon_champions.db import connect

from .get_moves import (COLUMNS, STAT_COLUMNS, STAT_TABLE, TABLE, fetch_move,
                        moves_M_B, parse_move, parse_stat_changes)


def current_move_names(cur):
    cur.execute(f"SELECT name FROM {TABLE}")
    return {r[0] for r in cur.fetchall()}


def pokemon_names(cur):
    cur.execute("SELECT name FROM pokemons")
    return sorted(r[0] for r in cur.fetchall())


def expand_forms(base_names, all_pokemon, exact_only):
    """원종 이름 집합을 우리 DB 에 있는 실제 포켓몬 이름들로 넓힌다.

    돌려주는 값: (이름 집합, 폼 추론으로 늘어난 수)
    """
    exact = {n for n in all_pokemon if n in base_names}
    if exact_only:
        return exact, 0

    # 하이픈을 요구해서 kabuto 가 kabutops 를 잡는 사고를 막는다.
    forms = {p for p in all_pokemon
             if any(p.startswith(b + "-") for b in base_names)}
    return exact | forms, len(forms - exact)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 를 건드리지 않고 무엇이 들어갈지만 출력")
    parser.add_argument("--exact-only", action="store_true",
                        help="폼 변이 추론 없이 원종만 pokemon_moves 에 넣는다")
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()

    have = current_move_names(cur)
    missing = [n for n in moves_M_B if n not in have]
    extra = sorted(have - set(moves_M_B))

    print(f"moves_M_B {len(moves_M_B)}개 / DB {len(have)}개")
    if extra:
        print(f"\nDB 에만 있는 기술 {len(extra)}개 — 목록에서 뺐는데 남은 것입니다.")
        print("  이 스크립트는 지우지 않습니다. 직접 확인하세요.")
        for n in extra:
            print("   ", n)
    if not missing:
        print("\n채울 것이 없습니다.")
        conn.close()
        return 0

    print(f"\n채울 기술 {len(missing)}개: {', '.join(missing)}")
    all_pokemon = pokemon_names(cur)

    move_rows, stat_rows, link_rows = [], [], []
    failed, form_added = [], 0

    for name in missing:
        data = fetch_move(name)
        if data is None:
            failed.append(name)
            print(f"  {name} - PokeAPI 실패")
            continue

        m = parse_move(data)
        move_rows.append(tuple(m[c] for c in COLUMNS))
        stat_rows.extend(parse_stat_changes(data))

        learners = {p["name"] for p in data.get("learned_by_pokemon", [])}
        names, grown = expand_forms(learners, all_pokemon, args.exact_only)
        form_added += grown
        link_rows.extend((p, name) for p in sorted(names))

        print(f"  {name:<14} {m['ko_name']:<10} "
              f"배우는 포켓몬 {len(names)}마리 (폼 추론 {grown})")

    if failed:
        print(f"\nPokeAPI 실패 {len(failed)}개: {failed}")
        print("네트워크 문제일 수 있습니다. 다시 실행하면 재시도합니다.")

    print(f"\n넣을 행 — moves {len(move_rows)} / "
          f"move_stat_changes {len(stat_rows)} / pokemon_moves {len(link_rows)}")
    if form_added:
        print(f"  이 중 {form_added}건은 폼 추론입니다. 정확히 하려면 "
              f"get_pokemon_moves 를 다시 돌리세요.")

    if args.dry_run:
        print("\n--dry-run 이라 DB 를 건드리지 않았습니다.")
        conn.close()
        return 0

    if not move_rows:
        conn.close()
        return 1

    # ON CONFLICT DO NOTHING — 중간에 끊겨서 다시 돌려도 안전하다.
    # 대상 컬럼을 지정하지 않는다. moves 는 id 가 PK 이고 name 이 UNIQUE 라
    # 어느 쪽이 걸릴지 모르는데, 대상을 적으면 다른 제약에서는 에러가 난다.
    try:
        cur.executemany(
            f"INSERT INTO {TABLE} ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
            f"ON CONFLICT DO NOTHING",
            move_rows,
        )
        if stat_rows:
            cur.executemany(
                f"INSERT INTO {STAT_TABLE} ({', '.join(STAT_COLUMNS)}) "
                f"VALUES ({', '.join(['%s'] * len(STAT_COLUMNS))}) "
                f"ON CONFLICT DO NOTHING",
                stat_rows,
            )
        cur.executemany(
            "INSERT INTO pokemon_moves (pokemon_name, move_name) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            link_rows,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    cur.execute(f"SELECT count(*) FROM {TABLE}")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM pokemon_moves")
    links = cur.fetchone()[0]
    conn.close()

    print(f"\n반영 완료 — moves {total}행 / pokemon_moves {links}행")
    print("한국어 표기를 override 에 고정하려면:")
    print("    python -m scripts.etl.pin_ko_names moves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
