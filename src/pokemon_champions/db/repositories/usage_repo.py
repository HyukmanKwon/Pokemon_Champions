"""채용률 기록 — 하루 한 벌씩 쌓이는 스냅샷.

다른 repo 와 달리 쓰기가 있다. 이 표만 ETL 이 만들고 끝나는 것이 아니라
계속 자라기 때문이다. (scripts/etl/sync_usage.py)

── 같은 날을 두 번 받아도 한 벌이어야 한다 ──
  받다가 끊기면 이어서 다시 돌리게 된다. 그때 이미 넣은 것이 두 벌이 되면
  추세가 조용히 틀어진다. 그래서 (시즌·날짜·포맷·이름) 이 같으면 새 스냅샷을
  만들지 않고 그 자리의 행을 갈아끼운다.
"""

from ._rows import one, rows

ROW_COLUMNS = ["category", "rank", "source_name", "percent",
               "hp_points", "attack_points", "defense_points",
               "sp_atk_points", "sp_def_points", "speed_points"]


def known_keys(conn, season, fmt):
    """이미 받아둔 (날짜, 저쪽 이름) 집합. 이어받을 때 무엇을 건너뛸지 정한다.

    본문(usage_rows)이 있는 것만 "받았다" 로 센다. 순위만 받는 길이
    있어서(--rankings-only) 스냅샷 줄만 있고 본문이 빈 경우가 생긴다 —
    그것까지 받았다고 세면 백필이 안 받은 날짜를 건너뛴다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT s.snapshot_date, s.battle_name FROM usage_snapshots s"
        " WHERE s.season = %s AND s.format = %s"
        "   AND EXISTS (SELECT 1 FROM usage_rows r WHERE r.snapshot_id = s.id)",
        (season, fmt))
    return {(d, n) for d, n in cur.fetchall()}


def link_battle_name(conn, battle_name, pokemon_name):
    """저쪽 표기를 대응표에 올린다. 이미 있으면 우리 이름만 갱신한다.

    이름을 못 붙였으면(NULL) 기존 값을 덮지 않는다. 로스터가 늘어 한 번
    붙은 이름을, 매칭이 잠깐 실패한 날의 NULL 이 도로 지우면 안 된다.
    """
    conn.cursor().execute(
        """
        INSERT INTO usage_names (source_name, category, pokemon_id)
        VALUES (%s, 'pokemon', (SELECT id FROM pokemons WHERE name = %s))
        ON CONFLICT (source_name) DO UPDATE
            SET pokemon_id = COALESCE(EXCLUDED.pokemon_id,
                                      usage_names.pokemon_id)
        """,
        (battle_name, pokemon_name),
    )


def save(conn, meta, rows_):
    """스냅샷 한 장을 넣거나 갈아끼운다. snapshot_id 를 돌려준다.

    meta 는 season · snapshot_date · format · battle_name · pokemon_name ·
    source 여섯이다. pokemon_name 은 usage_snapshots 가 아니라 usage_names
    로 간다.

    position 은 순위다. 본문 없이 순위만 아는 줄이 생길 수 있어서
    NULL 이 허용된다. (save_rankings 참고)

    ── meta 에 position 이 없어도 된다 ──
      부르는 쪽 둘 다 본문을 넣는 길이고, 순위는 그 직후 save_rankings 가
      따로 채운다. 그래서 여기 자리를 비워 둔다. %(position)s 는 키가
      없으면 NULL 이 되는 것이 아니라 KeyError 로 터진다 — 기본값을
      먼저 깔고 meta 로 덮는다.

      비워 두어도 값을 잃지 않는다. 위 ON CONFLICT 가 COALESCE 라서
      이미 들어 있던 순위를 NULL 이 지우지 못한다.
    """
    cur = conn.cursor()
    link_battle_name(conn, meta["battle_name"], meta.get("pokemon_name"))
    cur.execute(
        """
        INSERT INTO usage_snapshots
            (season, snapshot_date, format, battle_name, position, source)
        VALUES (%(season)s, %(snapshot_date)s, %(format)s,
                %(battle_name)s, %(position)s, %(source)s)
        ON CONFLICT (season, snapshot_date, format, battle_name) DO UPDATE
            SET position = COALESCE(EXCLUDED.position, usage_snapshots.position),
                source = EXCLUDED.source, fetched_at = now()
        RETURNING id
        """,
        {"position": None, **meta},
    )
    snapshot_id = cur.fetchone()[0]

    # 갈아끼우기다. 저쪽 순위가 바뀌면 없어진 줄이 생기는데, 지우지 않으면
    # 옛 줄이 남아 한 스냅샷에 두 시점이 섞인다.
    cur.execute("DELETE FROM usage_rows WHERE snapshot_id = %s", (snapshot_id,))
    if rows_:
        marks = ", ".join(f"%({c})s" for c in ROW_COLUMNS)
        cur.executemany(
            f"INSERT INTO usage_rows (snapshot_id, {', '.join(ROW_COLUMNS)})"
            f" VALUES (%(snapshot_id)s, {marks})",
            [{"snapshot_id": snapshot_id,
              **{c: r.get(c) for c in ROW_COLUMNS}} for r in rows_],
        )
    return snapshot_id


def link_names(conn, category, mapping):
    """저쪽 표기 -> 우리 것 대응을 usage_names 에 올린다.

    mapping 은 {저쪽 이름: 우리 id 또는 None}. 못 붙인 이름도 넣는다 —
    원문이 남아야 저쪽 오타를 찾을 수 있고, 나중에 규칙이 좋아지면 이 표
    한 행만 고치면 15만 줄이 한꺼번에 이어붙는다.

    이미 있으면 우리 쪽만 갱신하되, NULL 로 덮지 않는다. 매칭이 하루
    실패했다고 이미 붙은 것이 풀리면 안 된다.
    """
    column = {"move": "move_id", "held_item": "item_id",
              "ability": "ability_id", "stat_alignment": "nature"}[category]
    cur = conn.cursor()
    cur.executemany(
        f"""
        INSERT INTO usage_names (category, source_name, {column})
        VALUES (%s, %s, %s)
        ON CONFLICT (source_name) DO UPDATE
            SET {column} = COALESCE(EXCLUDED.{column}, usage_names.{column})
        """,
        [(category, name, ref) for name, ref in mapping.items()],
    )


def distinct_names(conn, category, season=None, snapshot_date=None, fmt=None):
    """그 갈래에 등장한 영문 이름 전부. 우리 표에 없는 것을 찾을 때 쓴다."""
    sql = ["SELECT DISTINCT r.source_name FROM usage_rows r",
           "JOIN usage_snapshots s ON s.id = r.snapshot_id",
           "WHERE r.category = %s"]
    args = [category]
    for column, value in (("s.season", season), ("s.snapshot_date", snapshot_date),
                          ("s.format", fmt)):
        if value is not None:
            sql.append(f"AND {column} = %s")
            args.append(value)

    cur = conn.cursor()
    cur.execute(" ".join(sql), args)
    return sorted(r[0] for r in cur.fetchall())


def counts(conn):
    """(스냅샷 수, 행 수, 가장 이른 날, 가장 늦은 날). 쌓인 것을 한눈에."""
    cur = conn.cursor()
    cur.execute(
        "SELECT (SELECT count(*) FROM usage_snapshots),"
        "       (SELECT count(*) FROM usage_rows),"
        "       (SELECT min(snapshot_date) FROM usage_snapshots),"
        "       (SELECT max(snapshot_date) FROM usage_snapshots)")
    return cur.fetchone()


def fetch_top_build(conn, pokemon_name, fmt="Singles", moves=4):
    """그 포켓몬의 가장 최근 스냅샷에서 카테고리별 1위. 없으면 빈 리스트.

    기술만 여러 줄이다(기본 4개). 나머지는 1위 한 줄뿐이라 rank = 1 로
    거른다 — 2위 이하를 여기서 주면 부르는 쪽이 다시 골라야 한다.

    ── 왜 최신 하루만 보나 ──
      여러 날을 평균 내면 "아무도 안 쓰는 조합" 이 나온다. 도구 1위가
      기합의띠인 날과 구애머리띠인 날을 섞으면 그 중간이 되는데, 실제로
      그렇게 쓰는 사람은 없다. 하루치 1위는 적어도 그날 실제로 가장
      많이 쓰인 값이다.

      추세를 보고 싶으면 그건 다른 질문이고 다른 함수다.

    돌려주는 것은 저쪽 표기 그대로(Focus Sash)다. 한국어로 옮기는 것은
    usecases/usage.py 가 한다 — repositories 는 이름을 안 만진다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest AS (
            SELECT s.id FROM usage_snapshots s
            JOIN usage_names b ON b.source_name = s.battle_name
            JOIN pokemons pk ON pk.id = b.pokemon_id
            WHERE pk.name = %s AND s.format = %s
            ORDER BY snapshot_date DESC, id DESC
            LIMIT 1
        )
        SELECT r.snapshot_id, r.category, r.rank, r.source_name AS name,
               r.percent,
               COALESCE(m.name, i.name, ab.name, n.nature::text,
                        tp.name) AS linked_name,
               m.type AS move_type, tp.id AS teammate_id,
               -- 성격의 보정. 표에 안 담는다 — 성격이 정해지면 따라오는
               -- 값이라 pokemon_natures 에서 읽는다. 무보정이면 NULL.
               CASE pn.up WHEN 'a' THEN 'atk' WHEN 'b' THEN 'def'
                          WHEN 'c' THEN 'spa' WHEN 'd' THEN 'spd'
                          WHEN 's' THEN 'spe' END AS stat_up,
               CASE pn.down WHEN 'a' THEN 'atk' WHEN 'b' THEN 'def'
                            WHEN 'c' THEN 'spa' WHEN 'd' THEN 'spd'
                            WHEN 's' THEN 'spe' END AS stat_down,
               r.hp_points, r.attack_points, r.defense_points,
               r.sp_atk_points, r.sp_def_points, r.speed_points,
               s.snapshot_date, s.season
        FROM usage_rows r
        JOIN latest l ON l.id = r.snapshot_id
        JOIN usage_snapshots s ON s.id = r.snapshot_id
        LEFT JOIN usage_names  n  ON n.source_name = r.source_name
        LEFT JOIN moves        m  ON m.id = n.move_id
        LEFT JOIN items        i  ON i.id = n.item_id
        LEFT JOIN abilities    ab ON ab.id = n.ability_id
        LEFT JOIN pokemons        tp ON tp.id = n.pokemon_id
                                     AND r.category = 'teammate'
        LEFT JOIN pokemon_natures pn ON pn.en_name = n.nature
        WHERE (r.category = 'move' AND r.rank <= %s) OR r.rank = 1
        ORDER BY r.category, r.rank
        """,
        (pokemon_name, fmt, moves),
    )
    return rows(cur)


def save_rankings(conn, taken_on, fmt, season, source, rows):
    """순위 한 벌을 스냅샷에 넣거나 갈아끼운다. 넣은 줄 수를 돌려준다.

    rows 는 [{position, battle_name, pokemon_name}] 다. 본문 없이 순위만
    아는 줄이 생길 수 있다 — 색인은 235마리를 한 번에 주지만 CSV 는 하루
    235번이라, 순위만 먼저 받아두는 길이 있다.

    시즌과 출처는 한 벌이 통째로 같은 값이라 줄이 아니라 인자다. 저쪽
    응답에도 season 이 있는데 "Current" 라고만 하지 우리 시즌을 말해 주지
    않는다 — 줄에서 받았더니 그 값이 섞여 들어왔다.
    """
    cur = conn.cursor()
    for r in rows:
        link_battle_name(conn, r["battle_name"], r.get("pokemon_name"))
    cur.executemany(
        """
        INSERT INTO usage_snapshots
            (season, snapshot_date, format, battle_name, position, source)
        VALUES (%(season)s, %(taken_on)s, %(format)s,
                %(battle_name)s, %(position)s, %(source)s)
        ON CONFLICT (season, snapshot_date, format, battle_name) DO UPDATE
            SET position = EXCLUDED.position, source = EXCLUDED.source,
                fetched_at = now()
        """,
        [{"taken_on": taken_on, "format": fmt, "season": season,
          "source": source, "position": r["position"],
          "battle_name": r["battle_name"]} for r in rows],
    )
    return len(rows)


def fetch_ranking(conn, fmt="Singles", limit=20):
    """가장 최근에 받은 전체 순위. 1위부터.

    "가장 많이 쓰이는 포켓몬" 에 답하는 유일한 자료다. usage_rows 의
    percent 는 전부 그 포켓몬 안에서의 비율이라 이 질문에 못 쓴다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.position, r.battle_name, p.name AS pokemon_name, p.ko_name,
               p.id AS pokemon_id, p.type1, p.type2,
               r.snapshot_date AS taken_on, r.season
        FROM usage_snapshots r
        JOIN usage_names b ON b.source_name = r.battle_name
        LEFT JOIN pokemons p ON p.id = b.pokemon_id
        WHERE r.format = %s AND r.position IS NOT NULL
          AND r.snapshot_date = (SELECT max(snapshot_date) FROM usage_snapshots
                                 WHERE format = %s AND position IS NOT NULL)
        ORDER BY r.position
        LIMIT %s
        """,
        # None 이면 전부. psycopg2 가 NULL 로 넘기고 Postgres 의 LIMIT NULL
        # 은 "제한 없음" 이다 — 파이썬에서 문자열을 갈아 끼우지 않아도 된다.
        (fmt, fmt, limit),
    )
    return rows(cur)


def fetch_rank_of(conn, pokemon_name, fmt="Singles"):
    """그 포켓몬의 최신 순위 한 줄. 없으면 None.

    usage_stats 응답에 실어, 모델이 기술 채용률을 순위로 오해하지 않게 한다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.position, r.snapshot_date AS taken_on,
               (SELECT count(*) FROM usage_snapshots k
                WHERE k.format = r.format AND k.snapshot_date = r.snapshot_date
                  AND k.position IS NOT NULL) AS total
        FROM usage_snapshots r
        JOIN usage_names b ON b.source_name = r.battle_name
        JOIN pokemons pk ON pk.id = b.pokemon_id
        WHERE pk.name = %s AND r.format = %s
        ORDER BY r.snapshot_date DESC
        LIMIT 1
        """,
        (pokemon_name, fmt),
    )
    return one(cur)


def fetch_detail(conn, pokemon_name, fmt="Singles", top=10):
    """한 마리의 가장 최근 스냅샷 전부. 갈래별로 top 개까지.

    fetch_top_build 와 다르다. 저쪽은 계산기 기본값을 채우려고 1위만 뽑고,
    이쪽은 화면에 늘어놓으려고 순위대로 다 가져온다.

    저쪽 원본이 갈래마다 주는 개수가 다르다 — 기술·도구·팀원·성격은 10개,
    SP 배분은 8개, 특성은 2개다. top 으로 자르되 없는 것을 만들지 않는다.

    linked_name 을 같이 준다. 화면이 그 이름을 눌러 도감으로 건너뛰려면
    우리 DB 의 키가 필요한데, 저쪽 표기(Focus Sash)로는 못 찾는다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id, s.snapshot_date, s.season,
               s.position AS usage_rank
        FROM usage_snapshots s
        JOIN usage_names b ON b.source_name = s.battle_name
        JOIN pokemons pk ON pk.id = b.pokemon_id
        WHERE pk.name = %s AND s.format = %s
        ORDER BY s.snapshot_date DESC, s.id DESC
        LIMIT 1
        """,
        (pokemon_name, fmt),
    )
    head = one(cur)
    if head is None:
        return []

    cur.execute(
        """
        SELECT r.category, r.rank, r.source_name AS name, r.percent,
               COALESCE(m.name, i.name, ab.name, n.nature::text,
                        tp.name) AS linked_name,
               m.type AS move_type, tp.id AS teammate_id,
               -- 성격의 보정. 표에 안 담는다 — 성격이 정해지면 따라오는
               -- 값이라 pokemon_natures 에서 읽는다. 무보정이면 NULL.
               CASE pn.up WHEN 'a' THEN 'atk' WHEN 'b' THEN 'def'
                          WHEN 'c' THEN 'spa' WHEN 'd' THEN 'spd'
                          WHEN 's' THEN 'spe' END AS stat_up,
               CASE pn.down WHEN 'a' THEN 'atk' WHEN 'b' THEN 'def'
                            WHEN 'c' THEN 'spa' WHEN 'd' THEN 'spd'
                            WHEN 's' THEN 'spe' END AS stat_down,
               r.hp_points, r.attack_points, r.defense_points,
               r.sp_atk_points, r.sp_def_points, r.speed_points
        FROM usage_rows r
        LEFT JOIN usage_names  n  ON n.source_name = r.source_name
        LEFT JOIN moves        m  ON m.id = n.move_id
        LEFT JOIN items        i  ON i.id = n.item_id
        LEFT JOIN abilities    ab ON ab.id = n.ability_id
        LEFT JOIN pokemons        tp ON tp.id = n.pokemon_id
                                     AND r.category = 'teammate'
        LEFT JOIN pokemon_natures pn ON pn.en_name = n.nature
        WHERE r.snapshot_id = %s AND r.rank <= %s
        ORDER BY r.category, r.rank
        """,
        (head["id"], top),
    )
    out = rows(cur)

    meta = {k: head[k] for k in ("snapshot_date", "season", "usage_rank")}
    for r in out:
        r.update(meta)
    return out


def fetch_rank_delta(conn, fmt="Singles", days=7):
    """{저쪽 이름: {순위, 변화}}. 변화는 오른 만큼 양수.

    3위였다가 1위가 되면 +2 다. 순위 숫자는 줄었지만 사람이 읽을 때는
    "두 계단 올랐다" 이므로 부호를 뒤집어 둔다 — 화면에서 다시 뒤집게
    하면 한쪽은 반드시 틀린다.

    ── 왜 직전 날과 안 견주나 ──
      저쪽이 매일 갱신하지 않는다. 실제로 07-30 과 08-04 는 235마리 순위가
      한 마리도 안 달랐다. 직전과만 견주면 화면이 늘 "변화 없음" 이 되어
      쓸모가 없다. 대신 days 일 전과 견준다.

    비교할 앞날이 없으면 delta 가 None 이다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest AS (
            SELECT max(snapshot_date) AS d FROM usage_snapshots WHERE format = %(fmt)s
        ),
        base AS (
            -- days 일 전에 가장 가까운 날. 그날이 없으면 그 앞의 것.
            SELECT max(snapshot_date) AS d FROM usage_snapshots
            WHERE format = %(fmt)s
              AND snapshot_date <= (SELECT d FROM latest) - %(days)s::int
        )
        SELECT now.battle_name, p.name AS pokemon_name,
               now.position AS usage_rank,
               was.position - now.position AS delta,
               now.snapshot_date, was.snapshot_date AS compared_to
        FROM usage_snapshots now
        JOIN usage_names b ON b.source_name = now.battle_name
        LEFT JOIN pokemons p ON p.id = b.pokemon_id
        LEFT JOIN usage_snapshots was
               ON was.battle_name = now.battle_name
              AND was.format = now.format
              AND was.snapshot_date = (SELECT d FROM base)
        WHERE now.format = %(fmt)s
          AND now.snapshot_date = (SELECT d FROM latest)
        """,
        {"fmt": fmt, "days": days},
    )
    return {r["battle_name"]: r for r in rows(cur)}
