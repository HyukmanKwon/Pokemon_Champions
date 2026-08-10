"""DB 에 있는 한국어 표기를 override 파일에 그대로 고정한다.

    python -m scripts.etl.pin_ko_names moves          아직 안 담긴 것만
    python -m scripts.etl.pin_ko_names moves --dry-run  무엇이 담길지만 보기
    python -m scripts.etl.pin_ko_names all            세 테이블 전부

── 왜 필요한가 ──
  애노테이터는 "내가 손댄 것"만 override 에 담는다. PokeAPI 가 이미 멀쩡한
  한국어를 준 항목은 손댈 이유가 없으니 안 담기고, 그러면 그 항목만 재구축
  때마다 PokeAPI 값을 따라가게 된다.

  지금 화면에 나오는 글자는 어느 쪽이든 같아서 차이가 안 보인다. 문제는
  PokeAPI 가 번역을 갱신하거나 응답이 바뀔 때다. 고정해 둔 것은 꿈쩍 않는데
  안 담긴 것만 조용히 달라진다.

  이 스크립트는 "지금 DB 값이 맞다"고 선언해서 그 구멍을 메운다. 값을
  지어내지 않는다 — DB 에 이미 있는 것을 옮겨 적을 뿐이다.

── 안전장치 ──
  이미 override 에 있는 항목은 건드리지 않는다. 손으로 고쳐 둔 값을
  DB 값으로 되돌리는 사고를 막기 위해서다. 정말 다시 담고 싶으면
  --force 를 준다.
"""

import argparse
import sys

from pokemon_champions.db import connect

from . import overrides
from .annotator.ko_names import EDITABLE, TABLES


def pin(table, dry_run=False, force=False):
    """돌려주는 값: (새로 담은 수, 이미 있던 수, 값이 없어 건너뛴 수)"""
    key = TABLES[table]["override_key"]
    data = overrides.load(key, refresh=True)

    conn = connect()
    cur = conn.cursor()
    cur.execute(f"SELECT name, {', '.join(EDITABLE)} FROM {table} ORDER BY name")
    rows = [dict(zip(["name"] + EDITABLE, r)) for r in cur.fetchall()]
    conn.close()

    added = skipped_existing = skipped_empty = 0
    for row in rows:
        name = row["name"]
        # 값이 있는 필드만 담는다. NULL 을 고정하는 건 의미가 없다.
        values = {f: row[f] for f in EDITABLE if row[f]}
        if not values:
            skipped_empty += 1
            continue

        current = data["values"].get(name)
        if current and not force:
            # 이미 담긴 항목이라도 빠진 필드가 있으면 그것만 채운다.
            missing = {f: v for f, v in values.items() if f not in current}
            if not missing:
                skipped_existing += 1
                continue
            values = {**current, **missing}

        if not dry_run:
            data["values"][name] = values
            data["reviewed"] = sorted(set(data["reviewed"]) | {name})
        added += 1
        mark = "담을 예정" if dry_run else "담음"
        print(f"  {mark}  {name:<24} {values.get('ko_name') or '-'}")

    if not dry_run and added:
        overrides.save(key, data)

    return added, skipped_existing, skipped_empty


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("table", choices=sorted(TABLES) + ["all"])
    parser.add_argument("--dry-run", action="store_true",
                        help="파일을 건드리지 않고 무엇이 담길지만 출력")
    parser.add_argument("--force", action="store_true",
                        help="이미 담긴 항목도 DB 값으로 덮어쓴다 (주의)")
    args = parser.parse_args()

    tables = sorted(TABLES) if args.table == "all" else [args.table]
    for table in tables:
        print(f"── {table} ──")
        added, existing, empty = pin(table, args.dry_run, args.force)
        print(f"  새로 담음 {added} / 이미 있음 {existing} / 값이 없어 건너뜀 {empty}")
        if not args.dry_run and added:
            print(f"  저장: {overrides.path(TABLES[table]['override_key'])}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
