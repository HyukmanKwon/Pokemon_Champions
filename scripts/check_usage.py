"""317마리가 채용률 자료의 어느 이름에 붙는지 한 번에 확인한다.

    python -m scripts.check_usage              전체 대조
    python -m scripts.check_usage --miss       못 붙은 것만
    python -m scripts.check_usage --clear      캐시 비우고 다시 받기
    python -m scripts.check_usage 한카리아스     한 마리만 실제로 받아보기

── 왜 필요한가 ──
  이름 맞추기를 표로 적지 않고 색인에서 자동으로 한다. 자동이라 조용히
  틀릴 수 있다 — 엉뚱한 포켓몬에 붙어도 에러가 안 난다. 그래서 317줄을
  눈으로 훑을 수 있게 뽑아준다.

  특히 볼 것: 메가폼이 원종으로 접히는지, 지역폼이 제 이름으로 붙는지,
  펌킨인·킬가르도·모르페코처럼 저쪽이 안 나누는 폼이 한 곳으로 모이는지.
"""

import argparse
import sys

from pokemon_champions.usecases import usage_source
from pokemon_champions.db import connect
from pokemon_champions.db.repositories import pokemon_repo
from pokemon_champions.usecases import usage


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", nargs="?", help="한 마리만 실제로 받아본다")
    ap.add_argument("--miss", action="store_true", help="못 붙은 것만 출력")
    ap.add_argument("--format", default="Singles", choices=["Singles", "Doubles"])
    ap.add_argument("--clear", action="store_true", help="캐시를 비우고 시작")
    args = ap.parse_args()

    if args.clear:
        print(f"캐시 {usage_source.clear()}개 삭제")

    conn = connect()
    try:
        if args.name:
            cur = conn.cursor()
            cur.execute("SELECT name FROM pokemons WHERE ko_name = %s", (args.name,))
            row = cur.fetchone()
            if row is None:
                print(f"'{args.name}' 은(는) DB에 없습니다.")
                return 1
            import json
            print(json.dumps(
                usage.usage_of(conn, row[0], args.name, args.format),
                ensure_ascii=False, indent=2))
            return 0

        rows = pokemon_repo.fetch_list(conn)
        if usage_source.fetch_index() is None:
            print("색인을 못 받았습니다. 네트워크를 확인하세요.")
            return 1

        hit = miss = mega = 0
        for r in sorted(rows, key=lambda r: r["name"]):
            name, was_mega = usage_source.battle_name(r["name"])
            if name is None:
                miss += 1
                print(f"  ✗ {r['ko_name'] or r['name']:<18} {r['name']}")
                continue
            hit += 1
            mega += bool(was_mega)
            if not args.miss:
                tag = " (메가→원종)" if was_mega else ""
                print(f"  · {r['ko_name'] or r['name']:<18} -> {name}{tag}")

        print(f"\n붙음 {hit} · 못 붙음 {miss} · 그중 메가 접힘 {mega}")
        print("못 붙은 것은 랭크배틀 표본이 적어 자료에 안 실린 경우가 많습니다.")
        return 0 if miss == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
