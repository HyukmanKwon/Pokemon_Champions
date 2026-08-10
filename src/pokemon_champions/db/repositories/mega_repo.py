"""mega_evolutions 테이블 조회.

엔트리에는 원종만 등록한다. 메가진화는 배틀 중 상태이고, 조건은 "그 포켓몬
전용 메가스톤을 지녔는가" 하나다. 그 판정에 필요한 조회가 여기 있다.

    거북왕 + 거북왕나이트  ->  메가거북왕
    거북왕 + 기합의띠      ->  None (틀린 게 아니라 그냥 메가가 아닐 뿐)
"""

from ...domain import Stats
from ...text import normalize


def fetch_form(conn, base_ko_name, item_ko_name):
    """원종과 도구가 맞물리면 메가폼 정보를, 아니면 None 을 돌려준다.

    도구가 비었거나 메가스톤이 아니면 그냥 None 이다. 예외를 올리지 않는다 —
    기합의띠를 지니는 건 잘못이 아니기 때문이다.

    X/Y 는 스톤이 서로 다르므로 결과는 항상 0행 아니면 1행이다.
    """
    if not item_ko_name:
        return None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT mp.id, mp.name, mp.ko_name, mp.type1, mp.type2,
               mp.h, mp.a, mp.b, mp.c, mp.d, mp.s,
               mp.ability1, ab.ko_name, ab.description
        FROM mega_evolutions me
        JOIN pokemons bp  ON bp.name = me.base_name
        JOIN pokemons mp  ON mp.name = me.mega_name
        JOIN items i      ON i.name  = me.item_name
        LEFT JOIN abilities ab ON ab.name = mp.ability1
        WHERE bp.ko_name = %s AND i.ko_name = %s
        """,
        (normalize(base_ko_name), normalize(item_ko_name)),
    )
    row = cur.fetchone()
    if row is None:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "ko_name": row[2],
        "type1": row[3],
        "type2": row[4],
        "base": Stats(*row[5:11]),
        "ability": {
            "name": row[12] or row[11],      # 한국어가 없으면 영문으로
            "effect": row[13],
        },
    }


def fetch_stones(conn, base_ko_name):
    """이 포켓몬이 메가진화하려면 무슨 스톤이 필요한지.

    화면에 "거북왕나이트를 지니면 메가진화할 수 있습니다" 라고 안내하는 데
    쓴다. 메가가 없는 포켓몬이면 빈 리스트다.

    item_ko_name 이 None 일 수 있다. mega_evolutions.item_name 매칭이 실패한
    경우인데(README §8), 그때도 메가폼 이름은 알려주는 편이 낫다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT mp.ko_name, i.ko_name, me.variant
        FROM mega_evolutions me
        JOIN pokemons bp ON bp.name = me.base_name
        JOIN pokemons mp ON mp.name = me.mega_name
        LEFT JOIN items i ON i.name = me.item_name
        WHERE bp.ko_name = %s
        ORDER BY me.variant NULLS FIRST, mp.ko_name
        """,
        (normalize(base_ko_name),),
    )
    return [{"mega_ko_name": r[0], "item_ko_name": r[1], "variant": r[2]}
            for r in cur.fetchall()]
