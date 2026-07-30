"""외부 목록과 DB의 기술을 대조한다.

    python check_moves.py 목록.txt

목록 파일은 한국어 기술 이름 한 줄에 하나. op.gg / Game8 / 포켓몬 Zone 같은
포챔스 전용 사이트에서 기술 목록을 복사해 붙이면 된다.

── 왜 필요한가 ──
  moves_M_B 는 손으로 채운 목록이라 빠진 것이 생긴다. 개수만 비교하면
  몇 개 다른지는 알아도 어느 것이 다른지는 알 수 없다.

── 두 종류를 구분해서 보고한다 ──
  1. 번역 차이   같은 기술인데 한국어 표기만 다르다
                 PokeAPI 의 한국어 이름이 옛 세대 번역일 때 생긴다
                 예: 깨뜨리다(PokeAPI) vs 깨트리기(포챔스)
     -> moves_M_B 는 고칠 필요 없다. ko_name 만 손보면 된다

  2. 진짜 누락   DB 어디에도 비슷한 이름이 없다
     -> moves_M_B 에 영문 이름을 추가하고 다시 구축해야 한다

  구분은 difflib 유사도로 한다. 애매한 것은 '판단 필요'로 따로 모은다.
"""

import difflib
import sys
import unicodedata

from pokemon_champions.db import connect


# 이 이상 닮았으면 같은 기술의 다른 번역으로 본다
SAME_MOVE = 0.75
# 이 아래로 닮았으면 아예 없는 기술로 본다
NOT_FOUND = 0.45
#
# 사이 구간(0.45~0.75)은 기계가 판단하지 않고 사람에게 넘긴다. 유사도만으로는
# 갈라지지 않는 경우가 실제로 있다.
#   깨트리기 vs 깨뜨리다  0.625  같은 기술 (번역 차이)
#   알낳기   vs 아픔나누기 0.632  다른 기술 (우연히 닮았을 뿐)
# 점수가 거의 같으므로 임계치를 어디에 두든 하나는 틀린다. 그래서 이 구간은
# 후보 3개를 같이 띄우고 눈으로 고르게 한다.


def jamo(s):
    """한글을 자모로 풀어 놓는다.

    음절 단위로 비교하면 '깨트리기'와 '깨뜨리다'가 2/4 밖에 안 닮은 것으로
    나온다. 자모로 풀면 초성·중성이 겹치는 만큼 점수가 올라가서, 표기만
    다른 같은 기술을 훨씬 잘 잡아낸다.
    """
    return unicodedata.normalize("NFD", s)


def load_db():
    """{ko_name: (영문 이름, id)}"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT ko_name, name, id FROM moves ORDER BY id")
    rows = {ko: (en, mid) for ko, en, mid in cur.fetchall() if ko}
    cur.execute("SELECT count(*) FROM moves")
    total = cur.fetchone()[0]
    conn.close()
    return rows, total


def ranked(name, pool, top=3):
    """닮은 순으로 [(이름, 유사도)] 를 돌려준다."""
    a = jamo(name)
    scored = [(c, difflib.SequenceMatcher(None, a, jamo(c)).ratio())
              for c in pool]
    scored.sort(key=lambda x: -x[1])
    return scored[:top]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    external = []
    seen = set()
    for line in open(sys.argv[1], encoding="utf-8"):
        n = line.strip()
        if n and n not in seen:
            seen.add(n)
            external.append(n)

    ours, total = load_db()
    print(f"외부 목록 {len(external)}개 / DB {total}개 "
          f"(한국어 이름 있는 것 {len(ours)}개)\n")

    matched, renamed, unsure, missing = [], [], [], []
    for n in external:
        if n in ours:
            matched.append(n)
            continue
        top = ranked(n, ours)
        score = top[0][1] if top else 0.0
        if score >= SAME_MOVE:
            renamed.append((n, top[0][0]))
        elif score >= NOT_FOUND:
            unsure.append((n, top))
        else:
            missing.append(n)

    print(f"그대로 일치      {len(matched)}개")

    if renamed:
        print(f"\n번역만 다름      {len(renamed)}개 "
              f"- moves_M_B 는 그대로 두고 ko_name 만 고치면 된다")
        for n, cand in renamed:
            en, mid = ours[cand]
            print(f"    {n:<14} <- DB: {cand:<14} ({en}, id={mid})")

    if unsure:
        print(f"\n판단 필요        {len(unsure)}개 - 눈으로 확인할 것")
        for n, top in unsure:
            cands = ", ".join(
                f"{c}({ours[c][0]}) {s:.2f}" for c, s in top)
            print(f"    {n:<14} {cands}")

    if missing:
        print(f"\nDB 에 없음       {len(missing)}개 "
              f"- moves_M_B 에 영문 이름을 추가해야 한다")
        for n in missing:
            print(f"    {n}")

    extra = [ko for ko in ours if ko not in seen]
    if extra:
        print(f"\n우리에만 있음    {len(extra)}개 "
              f"- 외부 목록이 잘렸거나 포챔스에서 빠진 기술")
        for ko in extra[:30]:
            print(f"    {ko:<14} ({ours[ko][0]})")
        if len(extra) > 30:
            print(f"    ... 외 {len(extra) - 30}개")


if __name__ == "__main__":
    main()
