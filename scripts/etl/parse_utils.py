import requests


def get_json(url):
    """GET 후 JSON을 돌려준다. 200이 아니면 None."""
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return None
    return resp.json()


def pick_korean(entries, key_text="name"):
    """names 리스트에서 한국어(ko) 항목을 고른다. 없으면 None."""
    for e in entries:
        if e["language"]["name"] == "ko":
            return e[key_text]
    return None


def pick_korean_flavor(entries, key="flavor_text"):
    """flavor_text_entries에서 한국어 설명을 고른다(가장 마지막=최신 우선).

    본문 키가 자료마다 다르다.
      - move, ability : "flavor_text"
      - item          : "text"
    """
    ko = [e[key] for e in entries if e["language"]["name"] == "ko"]
    if not ko:
        return None
    # 줄바꿈·제어문자 정리
    return ko[-1].replace("\n", " ").replace("\f", " ").strip()


def pick_english_effect(entries):
    """effect_entries에서 영어 효과 설명(short_effect)을 고른다."""
    for e in entries:
        if e["language"]["name"] == "en":
            return e.get("short_effect", "").replace("\n", " ").strip()
    return None


def render(ddl, table, columns, rows):
    """DDL + INSERT 를 합쳐 SQL 파일 전문을 만든다.

    rows 는 cur.mogrify 로 만든 "    (...)" 문자열들의 리스트.
    """
    body = f"INSERT INTO {table}\n    ({', '.join(columns)})\nVALUES\n"
    body += ",\n".join(rows) + ";\n"
    return ddl + "\n" + body


def mogrify_rows(cur, values_list, width):
    """값 튜플 리스트를 SQL 리터럴 행 문자열 리스트로 바꾼다."""
    placeholder = "    (" + ", ".join(["%s"] * width) + ")"
    return [cur.mogrify(placeholder, v).decode("utf-8") for v in values_list]
