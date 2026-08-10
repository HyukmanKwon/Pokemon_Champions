"""한국어 이름과 설명을 브라우저에서 직접 고친다.

    python -m scripts.etl.annotator.ko_names abilities
    python -m scripts.etl.annotator.ko_names items
    python -m scripts.etl.annotator.ko_names moves

고치는 칸은 둘이다.

    ko_name      한 줄. Enter 로 다음 줄 같은 칸으로 넘어간다
    description  여러 줄. 오른쪽의 영문 effect 를 보면서 쓰면 된다

── 왜 필요한가 ──
  PokeAPI 에 아직 한국어가 없는 항목이 있다. 포챔스 신규 특성(eelevate,
  fire-mane)과 신규 메가스톤 58개 정도가 그렇다. 지금까지는 ko_name 이
  NULL 이어도 아무 문자열이나 입력할 수 있어서 문제가 안 됐다.

  그런데 "이상해꽃이 가질 수 있는 특성만 허용"으로 검증을 조이면, 한국어
  이름이 없는 특성을 가진 포켓몬은 입력할 이름 자체가 없어서 등록이
  불가능해진다. 검증을 붙이기 전에 이 구멍을 먼저 메워야 한다.

  설명(description)은 검증에 쓰이지 않지만 화면에 그대로 노출되고, 나중에
  LLM 이 특성 효과를 읽을 때 근거가 된다. PokeAPI 의 flavor text 는 세대별로
  잘리거나 옛 표현인 경우가 많아 손볼 값이 꽤 있다.

── 왜 파일 하나로 세 테이블을 다루나 ──
  abilities · items · moves 는 (id, name, ko_name, description, effect) 모양이
  똑같다. annotator/abilities.py, items.py 로 나누면 거의 같은 파일이
  세 개가 되고, 고칠 일이 생기면 세 군데를 고쳐야 한다.

── 저장은 두 군데에 동시에 ──
    DB                         즉시 반영. 계산기·검증·화면이 바로 쓴다
    data/overrides/*.json      재구축해도 살아남는다. git 에 커밋된다

  moves 는 이미 이 방식을 쓰고 있었다(깨뜨리다 -> 깨트리기). 같은 구조를
  abilities · items 로 넓히고, 설명까지 담게 한 것이다.

  JSON 파일 이름이 아직 *_ko_names 인 것은 설명 지원 이전에 붙은 이름이라
  그렇다. 이미 손으로 채운 값이 들어 있는 파일이라 굳이 바꾸지 않았다.

── 사람이 넣은 값이 항상 이긴다 ──
  기술 플래그는 "추측과 다른 것만" JSON 에 남기지만, 한국어 표기는 입력한
  값을 무조건 남긴다. PokeAPI 가 나중에 한국어를 주더라도 그건 옛 세대
  번역일 수 있어서, 포챔스 표기를 우선해야 하기 때문이다.

── 영문 effect 는 못 고친다 ──
  일부러 읽기 전용으로 뒀다. PokeAPI 원문이라 우리가 손댈 값이 아니고,
  한국어를 쓸 때 대조할 기준으로 두는 편이 낫다.
"""

import argparse
import sys

from pokemon_champions.db import connect

from .. import overrides
from ._common import Spec, serve

# 고칠 수 있는 열. 세 테이블이 공통이라 밖으로 뺐다.
TEXT_COLUMNS = [
    ("ko_name", "한국어 이름", 150),
    ("description", "한국어 설명", 380, "area"),
]
EDITABLE = [c[0] for c in TEXT_COLUMNS]

# 테이블마다 다른 것만 여기 적는다.
TABLES = {
    "abilities": {
        "title": "특성 한국어 표기",
        "override_key": "ability_ko_names",
        "port": 8766,
        "info_columns": [("id", "번호", "num"), ("name", "영문 이름")],
        "search_fields": ("name", "ko_name", "description", "effect"),
    },
    "items": {
        "title": "도구 한국어 표기",
        "override_key": "item_ko_names",
        "port": 8767,
        "info_columns": [("id", "번호", "num"), ("name", "영문 이름"),
                         ("category", "분류"), ("related", "이 도구의 주인")],
        "search_fields": ("name", "ko_name", "category", "related",
                          "description", "effect"),
        # 메가스톤은 영문 이름만 봐서는 누구 것인지 모른다. clefablite 가
        # 픽시 것이라는 걸 알아야 한글 이름을 쓸 수 있다. mega_evolutions 에
        # 그 관계가 이미 있으므로 붙여서 보여준다.
        #
        # 성별 폼(meowstic-male/female)이 스톤을 공유해서 한 도구에 여러
        # 행이 걸린다. 그대로 조인하면 도구가 중복되므로 미리 묶는다.
        "extra_select": [("related", "stone_owner.ko_names")],
        "join_sql": """
            LEFT JOIN (
                SELECT m.item_name,
                       string_agg(DISTINCT p.ko_name, ', ') AS ko_names
                FROM mega_evolutions m
                JOIN pokemons p ON p.name = m.base_name
                WHERE m.item_name IS NOT NULL
                GROUP BY m.item_name
            ) stone_owner ON stone_owner.item_name = t.name
        """,
    },
    "moves": {
        "title": "기술 한국어 표기",
        "override_key": "move_ko_names",
        "port": 8768,
        "info_columns": [("id", "번호", "num"), ("name", "영문 이름"),
                         ("type", "타입")],
        "search_fields": ("name", "ko_name", "type", "description", "effect"),
    },
}

# 마지막 열에 읽기 전용으로 붙는 원문. 한국어를 쓸 때 대조용이다.
DETAIL_FIELD = "effect"


def make_spec(table):
    cfg = TABLES[table]
    key = cfg["override_key"]
    extra = cfg.get("extra_select", [])          # [(별칭, SQL 식)]
    extra_names = [alias for alias, _ in extra]

    # 테이블에 실제로 있는 열 = 보여주기만 하는 열 + 고칠 열 + 원문
    # (다른 테이블에서 끌어온 extra 는 여기서 뺀다)
    info_fields = [c[0] for c in cfg["info_columns"]
                   if c[0] not in extra_names]
    base_fields = list(dict.fromkeys(info_fields + EDITABLE + [DETAIL_FIELD]))

    select_sql = ", ".join([f"t.{f}" for f in base_fields]
                           + [f"{expr} AS {alias}" for alias, expr in extra])
    result_fields = base_fields + extra_names

    def fetch():
        """이름이 비어 있는 것을 맨 위로 올린다. 할 일이 바로 보이게."""
        conn = connect()
        cur = conn.cursor()
        cur.execute(
            f"SELECT {select_sql} FROM {table} t"
            f"{cfg.get('join_sql', '')} "
            f"ORDER BY (t.ko_name IS NOT NULL), (t.description IS NOT NULL), "
            f"         t.name"
        )
        rows = [dict(zip(result_fields, r)) for r in cur.fetchall()]
        conn.close()

        reviewed = set(overrides.load(key, refresh=True)["reviewed"])
        for r in rows:
            r["reviewed"] = r["name"] in reviewed
        return rows

    def save(name, values, reviewed):
        # 화면에 있는 칸만 받는다. 엉뚱한 컬럼이 UPDATE 되지 않게 한다.
        fields = {f: values.get(f) for f in EDITABLE}

        conn = connect()
        cur = conn.cursor()
        sets = ", ".join(f"{f} = %s" for f in EDITABLE)
        cur.execute(
            f"UPDATE {table} SET {sets} WHERE name = %s RETURNING name",
            [fields[f] for f in EDITABLE] + [name],
        )
        found = cur.fetchone()
        conn.commit()
        conn.close()
        if found is None:
            raise KeyError(f"{name} 이(가) {table} 테이블에 없습니다")

        # 값이 있는 필드만 JSON 에 남긴다. 다 비우면 항목 자체를 지운다.
        data = overrides.load(key, refresh=True)
        kept = {f: v for f, v in fields.items() if v}
        if kept:
            data["values"][name] = kept
        else:
            data["values"].pop(name, None)
        if reviewed:
            data["reviewed"] = sorted(set(data["reviewed"]) | {name})
        else:
            data["reviewed"] = [n for n in data["reviewed"] if n != name]
        overrides.save(key, data)
        return fields

    def summary():
        data = overrides.load(key, refresh=True)
        conn = connect()
        cur = conn.cursor()
        cur.execute(
            f"SELECT count(*) FILTER (WHERE ko_name IS NULL), "
            f"       count(*) FILTER (WHERE description IS NULL) FROM {table}"
        )
        no_name, no_desc = cur.fetchone()
        conn.close()
        print(f"확인 {len(data['reviewed'])}개 / "
              f"직접 넣은 항목 {len(data['values'])}개")
        print(f"아직 비어 있음 — 이름 {no_name}개, 설명 {no_desc}개")
        print(f"저장 위치: {overrides.path(key)}")

    return Spec(
        title=cfg["title"],
        subtitle="빈 칸(주황 테두리)을 채우세요. 오른쪽 영문이 원문입니다",
        info_columns=cfg["info_columns"],
        check_columns=[],
        text_columns=TEXT_COLUMNS,
        fetch=fetch,
        save=save,
        key_field="name",
        search_fields=cfg["search_fields"],
        detail_field=DETAIL_FIELD,
        port=cfg["port"],
        summary=summary,
        labels={"ko_name": "이름", "description": "설명"},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("table", choices=sorted(TABLES),
                        help="한국어 이름을 채울 테이블")
    args = parser.parse_args()
    serve(make_spec(args.table))


if __name__ == "__main__":
    sys.exit(main())
