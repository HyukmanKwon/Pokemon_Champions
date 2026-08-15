"""modifiers.py · residual.py 의 표에 적힌 이름이 DB에 실제로 있는지 검사한다.

    python -m scripts.check_modifiers

── 왜 필요한가 ──
  보정 표의 키는 한국어 이름이다. "옹골찬턱" 을 "옹골찬 턱" 으로 적으면
  예외가 나지 않는다. 그냥 그 특성이 영영 안 걸린 값이 나올 뿐이다.
  계산기에서 가장 찾기 어려운 종류의 버그라, 표를 고칠 때마다 여기서
  한 번 걸러낸다.

  반대 방향은 검사하지 않는다. DB에 있는데 표에 없는 특성은 300개쯤
  되고, 그건 오타가 아니라 "아직 안 넣었다" 이기 때문이다.
"""

import sys

from pokemon_champions.db import connection
from pokemon_champions.calc import modifiers, residual


def _known(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT ko_name FROM {table} WHERE ko_name IS NOT NULL")
    return {r[0] for r in cur.fetchall()}


def main():
    with connection() as conn:
        abilities = _known(conn, "abilities")
        items = _known(conn, "items")

    # residual.py 도 한국어 이름으로 특성·도구를 찾는다. 오타가 나면
    # 예외 없이 "먹다남은음식이 영영 안 차는" 값이 나오는 것도 똑같다.
    checks = [
        ("특성", modifiers.all_ability_keys() | residual.all_ability_keys(),
         abilities),
        ("도구", modifiers.all_item_keys() | residual.all_item_keys(), items),
    ]

    missing_total = 0
    for label, used, known in checks:
        missing = sorted(used - known)
        print(f"{label}: 표에 {len(used)}개, 그중 DB에 없는 것 {len(missing)}개")
        for name in missing:
            # 비슷한 이름을 같이 보여준다. 대개 띄어쓰기나 한 글자 차이다.
            near = sorted(k for k in known
                          if k.replace(" ", "") == name.replace(" ", "")
                          or (len(k) == len(name)
                              and sum(a != b for a, b in zip(k, name)) <= 1))
            hint = f"  -> 혹시 {', '.join(near)}?" if near else ""
            print(f"    {name}{hint}")
        missing_total += len(missing)

    print()
    if missing_total:
        print(f"{missing_total}개가 DB에 없습니다. 이 이름들은 보정이 영영")
        print("안 걸립니다. modifiers.py 의 표를 고치세요.")
        return 1

    print("표의 이름이 전부 DB에 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
