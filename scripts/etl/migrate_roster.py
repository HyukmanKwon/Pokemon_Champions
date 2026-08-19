"""pokemon_M_B 목록이 바뀐 것을 지금 DB에 그대로 반영한다.

    python -m scripts.etl.migrate_roster --dry-run   무엇이 바뀔지만 보기
    python -m scripts.etl.migrate_roster             실제 반영

── 왜 build.py 를 안 쓰나 ──
  build.py 는 빈 DB 전용이다. CREATE TABLE 에 IF NOT EXISTS 가 없어서 이미
  테이블이 있으면 첫 단계에서 멈추고, 전부 지우고 다시 돌리면 API 를 1,900번
  다시 부른다. 목록에서 몇 마리 늘고 주는 정도로 그 값을 치를 이유가 없다.

  그래서 이 스크립트는 "DB 에 있는 것"과 "목록에 있는 것"의 차이만 본다.
  들어갈 것은 PokeAPI 에서 받아 INSERT 하고, 빠질 것은 DELETE 한다.
  목록을 안 건드리고 그냥 돌리면 아무 일도 일어나지 않는다.

── 포켓몬만 넣어서는 안 되는 것들 ──
  pokemons 행 하나가 pokemon_abilities · pokemon_moves · mega_evolutions
  세 곳을 가리킨다. 그래서 포켓몬을 넣고 뺀 뒤에 세 표를 차례로 맞춘다.

  특성은 넣는 순서가 정해져 있다. pokemon_abilities.ability_id 가
  abilities(id) 를 참조하므로, 처음 보는 특성은 abilities 에 먼저 받아
  두어야 한다. 그래서 포켓몬 행만 먼저 넣고 특성 행은 모아 두었다가
  sync_abilities 뒤에 넣는다.

  기술도 같은 이유로 moves 에 있는 것만 넣는다 (insert_moves 가 교집합을
  취한다). 없는 기술을 넣으려 하면 move_id 가 NULL 이 되어 막힌다.

── 지우는 순서 ──
  mega_evolutions 가 pokemons(name) 을 참조하는데 CASCADE 가 아니라,
  먼저 끊지 않으면 외래키에 걸린다. pokemon_moves 와 pokemon_abilities 는
  ON DELETE CASCADE 라 따로 지우지 않아도 딸려 나간다.

── 한 트랜잭션 ──
  중간에 실패하면 전부 되돌린다. 포켓몬은 지워졌는데 기술 연결만 남는
  어중간한 상태가 제일 고치기 어렵다.
"""

import argparse

from pokemon_champions.db import connect

from .get_abilities import COLUMNS as ABILITY_COLUMNS
from .get_abilities import fetch_ability, parse_ability, select_ability_names
from .get_items import COLUMNS as ITEM_COLUMNS
from .get_items import collect_item_names, fetch_item, parse_item
from .get_mega_evolutions import match_stone, select_stones
from .get_pokemons import (COLUMNS, base_of, fetch_pokemon,
                           parse_pokemon, pokemon_M_B, split_mega)
from .get_pokemon_moves import fetch_pokemon as fetch_moves_source


def db_names(cur):
    cur.execute("SELECT name FROM pokemons")
    return {r[0] for r in cur.fetchall()}


def ensure_pokemon_id_column(cur):
    """pokemon_id 컬럼이 없으면 만든다.

    schema.py 에는 들어 있지만, 이 DB 는 그 DDL 이 생기기 전에 구축됐을 수
    있다. 있으면 아무 일도 안 한다.
    """
    cur.execute("""
        ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS pokemon_id INT
    """)


def insert_pokemon(cur, row):
    cols = ", ".join(COLUMNS)
    marks = ", ".join(["%s"] * len(COLUMNS))
    cur.execute(
        f"INSERT INTO pokemons ({cols}) VALUES ({marks})",
        tuple(row[c] for c in COLUMNS),
    )


def insert_abilities(cur, triples):
    """pokemon_abilities 행들. abilities 를 채운 뒤에 불러야 한다.

    triples 는 (포켓몬 id, 특성 이름, 슬롯) 이다. 특성만 이름인 것은
    get_pokemons 가 만들 때 abilities 가 아직 없어 id 를 몰라서다.
    여기서 이름을 id 로 옮긴다 — 그 표가 이제 막 채워졌다.

    ability_id 가 abilities(id) 를 참조하므로, 처음 보는 특성을 아직
    안 받아둔 상태에서 넣으면 외래키가 막고 트랜잭션 전체가 무너진다.
    그래서 포켓몬 행과 따로 떼어 sync_abilities 뒤로 미룬다.
    """
    for pokemon_id, ability, slot in triples:
        cur.execute(
            "INSERT INTO pokemon_abilities (pokemon_id, ability_id, slot)"
            " VALUES (%s, (SELECT id FROM abilities WHERE name = %s), %s)",
            (pokemon_id, ability, slot),
        )


def insert_moves(cur, name, valid):
    """새로 들어온 포켓몬의 습득 기술을 연결한다.

    moves 테이블에 이미 있는 기술만 넣는다. 폼이 새로 배우는 기술이 DB 에
    없으면 조용히 빠지는데, 그건 04_moves 단계가 따로 다룰 일이다.
    """
    data = fetch_moves_source(name)
    if data is None:
        return 0
    learned = sorted({m["move"]["name"] for m in data["moves"]} & valid)
    for move in learned:
        cur.execute(
            "INSERT INTO pokemon_moves (pokemon_id, move_id)"
            " VALUES ((SELECT id FROM pokemons WHERE name = %s),"
            "         (SELECT id FROM moves WHERE name = %s))"
            " ON CONFLICT DO NOTHING",
            (name, move),
        )
    return len(learned)


def delete_pokemon(cur, name):
    # pokemon_moves 와 pokemon_abilities 는 ON DELETE CASCADE 라 딸려 나간다.
    # mega_evolutions 만 CASCADE 가 아니라 여기서 먼저 끊는다 — 메가 관계를
    # 조용히 지우면 어느 폼이 사라졌는지 로그에 안 남는다.
    cur.execute(
        "DELETE FROM mega_evolutions WHERE mega_name = %s OR base_name = %s",
        (name, name),
    )
    cur.execute("DELETE FROM pokemons WHERE name = %s", (name,))


def sync_mega_bases(cur):
    """mega_evolutions.base_name 을 MANUAL_BASE 기준으로 고친다."""
    fixed = []
    cur.execute("SELECT mega_name, base_name FROM mega_evolutions")
    for mega, base in cur.fetchall():
        want = base_of(mega)
        if want and want != base:
            cur.execute(
                "UPDATE mega_evolutions SET base_name = %s WHERE mega_name = %s",
                (want, mega))
            fixed.append((mega, base, want))
    return fixed


def sync_items(cur):
    """items 를 get_items 의 목록에 맞춘다. 없는 건 받아 넣고, 남는 건 지운다.

    mega_evolutions.item_name 이 items(name) 을 참조하므로, 지울 도구를
    가리키는 행이 있으면 먼저 NULL 로 끊는다. 그냥 지우면 외래키에 걸려
    트랜잭션 전체가 무너진다 — 메가스톤은 남기는 쪽이라 보통 안 걸리지만,
    목록을 더 줄일 때를 대비해 둔다.
    """
    want = set(collect_item_names())
    cur.execute("SELECT name FROM items")
    have = {r[0] for r in cur.fetchall()}

    to_add = sorted(want - have)
    to_drop = sorted(have - want)

    added, failed = [], []
    cols = ", ".join(ITEM_COLUMNS)
    marks = ", ".join(["%s"] * len(ITEM_COLUMNS))
    for name in to_add:
        data = fetch_item(name)
        if data is None:
            failed.append(name)
            continue
        it = parse_item(data)
        cur.execute(f"INSERT INTO items ({cols}) VALUES ({marks})",
                    tuple(it[c] for c in ITEM_COLUMNS))
        added.append((it["name"], it["ko_name"]))

    unlinked = []
    if to_drop:
        cur.execute(
            "SELECT mega_name FROM mega_evolutions WHERE item_name = ANY(%s)",
            (to_drop,))
        unlinked = [r[0] for r in cur.fetchall()]
        cur.execute(
            "UPDATE mega_evolutions SET item_name = NULL WHERE item_name = ANY(%s)",
            (to_drop,))
        cur.execute("DELETE FROM items WHERE name = ANY(%s)", (to_drop,))

    return added, to_drop, failed, unlinked


def sync_abilities(cur, extra=()):
    """pokemon_abilities 가 가리키는데 abilities 에 없는 특성을 받아 채운다.

    extra 는 아직 표에 안 들어간 특성 이름들이다. 새로 추가되는 포켓몬의
    특성이 여기로 온다 — 그 행을 넣으려면 abilities 가 먼저 있어야 하는데,
    표를 보고 목록을 만들면 아직 없어서 안 보인다. (모르페코의 하라펠코)

    삭제된 특성은 지우지 않는다. 어느 포켓몬도 안 가진 특성이 남아 있어도
    화면에 해로울 게 없고, 목록을 되돌릴 때 다시 받지 않아도 된다.
    """
    wanted = set(select_ability_names(cur)) | set(extra)
    cur.execute("SELECT name FROM abilities")
    have = {r[0] for r in cur.fetchall()}

    added, failed = [], []
    cols = ", ".join(ABILITY_COLUMNS)
    marks = ", ".join(["%s"] * len(ABILITY_COLUMNS))
    for name in sorted(wanted - have):
        data = fetch_ability(name)
        if data is None:
            failed.append(name)
            continue
        a = parse_ability(data)
        cur.execute(f"INSERT INTO abilities ({cols}) VALUES ({marks})",
                    tuple(a[c] for c in ABILITY_COLUMNS))
        added.append((a["name"], a["ko_name"]))
    return added, failed


def sync_mega_rows(cur):
    """pokemons 에는 있는데 mega_evolutions 에 없는 메가폼의 행을 채운다.

    포켓몬만 넣고 여기를 안 채우면, 도감에는 뜨는데 엔트리에서 메가 버튼이
    안 생긴다 — resolve_mega 가 이 표를 보기 때문이다.
    """
    # 고르는 일(베이스 찾기·스톤 맞추기)은 이름으로 하고, 넣을 때 id 로 옮긴다.
    cur.execute("SELECT name, id FROM pokemons")
    names = dict(cur.fetchall())
    megas = sorted(n for n in names if split_mega(n)[0] is not None)

    cur.execute("SELECT p.name FROM mega_evolutions me"
                " JOIN pokemons p ON p.id = me.mega_id")
    have = {r[0] for r in cur.fetchall()}

    stones = select_stones(cur)
    added, orphans = [], []
    for mega in megas:
        if mega in have:
            continue
        base = base_of(mega)
        if base not in names:
            orphans.append(mega)
            continue
        stone = match_stone(base, split_mega(mega)[1], stones)
        cur.execute(
            "INSERT INTO mega_evolutions"
            " (mega_id, base_id, item_id) VALUES (%s, %s, %s)",
            (names[mega], names[base], stones[stone] if stone else None),
        )
        added.append((mega, stone))
    return added, orphans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="바뀔 내용만 출력하고 DB 는 건드리지 않는다")
    args = ap.parse_args()

    conn = connect()
    cur = conn.cursor()

    have = db_names(cur)
    want = set(pokemon_M_B)
    to_add = sorted(want - have)
    to_drop = sorted(have - want)

    print(f"DB {len(have)}마리 / 목록 {len(want)}마리")
    print(f"추가 {len(to_add)}: {to_add}")
    print(f"삭제 {len(to_drop)}: {to_drop}")

    if args.dry_run:
        want_items = set(collect_item_names())
        cur.execute("SELECT name FROM items")
        have_items = {r[0] for r in cur.fetchall()}
        print(f"\n도구 DB {len(have_items)} / 목록 {len(want_items)}")
        print(f"추가 {sorted(want_items - have_items)}")
        print(f"삭제 {sorted(have_items - want_items)}")
        conn.close()
        return

    try:
        ensure_pokemon_id_column(cur)

        cur.execute("SELECT name FROM moves")
        valid_moves = {r[0] for r in cur.fetchall()}

        pending_abilities = []
        for name in to_add:
            data = fetch_pokemon(name)
            if data is None:
                # PokeAPI 에 없는 이름이면 여기서 멈춘다. 조용히 건너뛰면
                # 오타를 적어놓고 "추가됐겠지" 하고 넘어가게 된다.
                raise SystemExit(f"PokeAPI 에 없는 이름: {name}")
            row = parse_pokemon(data)
            insert_pokemon(cur, row)
            # 특성 행은 abilities 를 채운 뒤에 넣는다. 아래 sync_abilities 참고.
            pending_abilities.extend(row["_abilities"])
            n = insert_moves(cur, name, valid_moves)
            print(f"  + {name} (기술 {n}개)")

        # 삭제보다 먼저 한다. floette-mega 의 베이스를 floette-eternal 로
        # 옮겨두지 않으면, floette 를 지울 때 그 관계 행이 딸려 나간다.
        for mega, before, after in sync_mega_bases(cur):
            print(f"  ~ {mega} 베이스 {before} -> {after}")

        for name in to_drop:
            delete_pokemon(cur, name)
            print(f"  - {name}")

        # 이미 있던 행들의 pokemon_id 채우기. 폼 응답을 다시 받지 않으려고
        # id 로 역산하지 않는다 — 10000번대는 규칙이 없어서 계산이 안 된다.
        cur.execute("SELECT count(*) FROM pokemons WHERE pokemon_id IS NULL")
        missing = cur.fetchone()[0]
        if missing:
            cur.execute("SELECT name FROM pokemons WHERE pokemon_id IS NULL")
            for (name,) in cur.fetchall():
                data = fetch_pokemon(name)
                if data is None:
                    print(f"  ? {name} - pokemon_id 못 채움")
                    continue
                cur.execute(
                    "UPDATE pokemons SET pokemon_id = %s WHERE name = %s",
                    (parse_pokemon(data)["pokemon_id"], name))
            print(f"  pokemon_id 채움: {missing}행")

        # 메가 관계표보다 먼저 맞춘다. 스톤을 items 에서 찾기 때문이다.
        new_items, gone_items, item_failed, unlinked = sync_items(cur)
        for name, ko in new_items:
            print(f"  + 도구 {name} -> {ko}")
        if gone_items:
            print(f"  - 도구 {len(gone_items)}개 삭제")
        for mega in unlinked:
            print(f"  ! {mega} - 스톤이 삭제돼 연결이 끊겼다")
        if item_failed:
            print(f"  ! 도구 못 받음: {item_failed}")

        # 포켓몬을 다 넣고 뺀 뒤에 본다. 새로 들어온 폼이 처음 들고 오는
        # 특성(모르페코의 하라펠코 같은)이 여기서 채워진다.
        new_abilities, ability_failed = sync_abilities(
            cur, extra={a for _, a, _ in pending_abilities})
        for name, ko in new_abilities:
            print(f"  + 특성 {name} -> {ko}")
        if ability_failed:
            print(f"  ! 특성 못 받음: {ability_failed}")

        # 이제서야 넣을 수 있다 — 위에서 abilities 가 채워졌다.
        insert_abilities(cur, pending_abilities)

        added, orphans = sync_mega_rows(cur)
        for mega, stone in added:
            # 스톤을 못 찾으면 도감에는 뜨는데 엔트리에서 메가를 못 켠다.
            # items 테이블이 그 스톤이 생기기 전에 만들어진 경우다.
            note = stone or "스톤 없음 - items 를 다시 받아야 한다"
            print(f"  ~ mega_evolutions 에 {mega} 추가 ({note})")
        for mega in orphans:
            print(f"  ! {mega} - 베이스({base_of(mega)})가 DB 에 없어 건너뜀")


        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    cur.execute("SELECT count(*) FROM pokemons")
    print(f"\n완료 - pokemons {cur.fetchone()[0]}행")
    conn.close()


if __name__ == "__main__":
    main()
