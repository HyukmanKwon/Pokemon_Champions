"""DB에 있는 포켓몬·타입·도구 이미지를 전부 내려받아 data/images/ 에 캐시한다.

    python -m scripts.fetch_assets              전체
    python -m scripts.fetch_assets --limit 5    먼저 5마리만 시험
    python -m scripts.fetch_assets --sleep 0.1  요청 간격을 둔다

── 왜 etl/ 이 아니라 scripts/ 바로 밑인가 ──
  scripts/etl 은 "PokeAPI -> SQL -> DB" 파이프라인이고, 각 모듈이
  FILENAME/TABLE/build(conn) 이라는 약속을 지킨다. 이미지 받기는 DB에 쓰는
  게 아니라 파일 캐시를 채우는 일이라 그 약속에 안 맞는다. 억지로 끼워
  넣으면 build.py 의 STEPS 규칙이 흐려진다.

── 왜 별도 스크립트인가 ──
  앱은 이미 필요할 때 알아서 받는다(assets.py). 이 스크립트는 그걸 미리
  한꺼번에 해두는 것뿐이다. 그래서 로직을 새로 쓰지 않고 assets 의 같은
  함수를 부른다 — 두 벌이 되면 저장 위치나 URL 규칙이 갈라진다.

── 여러 번 돌려도 안전하다 ──
  이미 받은 파일은 건너뛴다. 중간에 끊기면 그냥 다시 실행하면 된다.
"""

import argparse
import sys
import time

import requests

from pokemon_champions import assets
from pokemon_champions.config import IMAGES_DIR
from pokemon_champions.db import connect
from pokemon_champions.db.repositories import item_repo, pokemon_repo


def human(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def total_size(path):
    return sum(p.stat().st_size for p in path.rglob("*.png"))


def probe_network():
    """저장소에 닿는지 한 번 확인한다. 반드시 있는 파일을 골라 받아본다.

    파일로 저장하지 않는다. 캐시를 건드리면 다음 실행의 '이미 있음' 수가
    이 확인 때문에 달라진다.
    """
    try:
        res = requests.get(assets.TYPE_ICON_URL.format(type_id=1), timeout=10)
        return res.status_code == 200
    except requests.RequestException:
        return False


def fetch_all(label, jobs, sleep):
    """jobs = [(표시이름, 저장경로, 받는 함수)] 를 순서대로 처리한다.

    돌려주는 값: (받음, 건너뜀, 실패한 이름들)
    """
    got = skipped = 0
    failed = []
    width = len(str(len(jobs)))

    for i, (name, path, download) in enumerate(jobs, 1):
        if path.exists():
            skipped += 1
            continue

        print(f"\r  [{i:>{width}}/{len(jobs)}] {label} {name:<28}", end="", flush=True)
        if download() is None:
            failed.append(name)
        else:
            got += 1
        if sleep:
            time.sleep(sleep)

    print(f"\r  {' ' * 60}\r", end="")
    return got, skipped, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int,
                        help="포켓몬·도구를 이 개수까지만 처리 (시험용)")
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="요청 사이 대기 초 (기본 0)")
    args = parser.parse_args()

    conn = connect()
    try:
        pokemons = pokemon_repo.fetch_all_meta(conn)
        items = [r["name"] for r in item_repo.fetch_list(conn)]
    finally:
        conn.close()

    if args.limit:
        pokemons = pokemons[:args.limit]
        items = items[:args.limit]

    # DB 안에 실제로 쓰이는 타입만 모은다. 18개가 다 나오겠지만,
    # 수집 범위를 줄이면 여기도 따라 줄어드는 게 맞다.
    types = sorted({t for p in pokemons for t in (p["type1"], p["type2"]) if t})

    before = total_size(IMAGES_DIR) if IMAGES_DIR.exists() else 0
    print(f"대상     : 포켓몬 {len(pokemons)}마리 · 타입 {len(types)}종 "
          f"· 도구 {len(items)}개")
    print(f"저장 위치 : {IMAGES_DIR}")
    print()

    # 받는 것은 영문 원본까지다. 화면이 쓰는 한국어 배지는 이 원본의
    # 심볼을 살려 따로 그린다 — python -m scripts.make_type_icons
    print("타입 아이콘 (영문 원본. 한국어 배지는 make_type_icons 가 그린다)")
    t_got, t_skip, t_fail = fetch_all(
        "", [(t, assets.TYPES_EN_DIR / f"{t}.png",
              lambda t=t: assets.ensure_type_source(t)) for t in types],
        args.sleep)
    print(f"  받음 {t_got} · 이미 있음 {t_skip} · 실패 {len(t_fail)}")

    print("포켓몬 사진")
    p_got, p_skip, p_fail = fetch_all(
        "", [(p["name"], assets.POKEMON_DIR / f"{p['id']}.png",
              lambda p=p: assets.ensure_pokemon_sprite(p["id"])) for p in pokemons],
        args.sleep)
    print(f"  받음 {p_got} · 이미 있음 {p_skip} · 실패 {len(p_fail)}")

    # 목록 표에 깔리는 96px 도트. 상세용 큰 그림과 다른 파일이라 따로 받는다.
    print("포켓몬 아이콘")
    i_got, i_skip, i_fail = fetch_all(
        "", [(p["name"], assets.POKEMON_ICON_DIR / f"{p['id']}.png",
              lambda p=p: assets.ensure_pokemon_icon(p["id"])) for p in pokemons],
        args.sleep)
    print(f"  받음 {i_got} · 이미 있음 {i_skip} · 실패 {len(i_fail)}")

    # 도구는 id 가 아니라 영문 이름으로 찾는다 (leftovers.png).
    print("도구 아이콘")
    m_got, m_skip, m_fail = fetch_all(
        "", [(n, assets.ITEM_DIR / f"{n}.png",
              lambda n=n: assets.ensure_item_sprite(n)) for n in items],
        args.sleep)
    print(f"  받음 {m_got} · 이미 있음 {m_skip} · 실패 {len(m_fail)}")

    after = total_size(IMAGES_DIR)
    print()
    print(f"용량 : {human(before)} -> {human(after)}  (+{human(after - before)})")

    failed = t_fail + p_fail + i_fail + m_fail
    if not failed:
        return 0

    print()
    # assets 는 다운로드 실패를 조용히 None 으로 넘긴다. 능력치 조회가 사진
    # 때문에 막히면 안 되기 때문인데, 일괄 받기에서는 그 침묵이 "저장소에
    # 이미지가 없음"과 "네트워크가 안 됨"을 똑같아 보이게 만든다.
    #
    # 받은 게 하나도 없다고 네트워크 탓을 하면 안 된다. 두 번째 실행부터는
    # 성공한 것이 전부 '이미 있음'으로 빠져서, 남은 실패만 세면 언제나
    # "전부 실패"로 보인다. 그래서 세는 대신 직접 한 번 받아본다.
    if not probe_network():
        print("스프라이트 저장소에 닿지 못했습니다. 개별 이미지 문제가 아니라")
        print("네트워크나 raw.githubusercontent.com 접근 문제입니다.")
        return 1

    print(f"실패 {len(failed)}개 — 저장소에 그 이름의 이미지가 없습니다.")
    print("(저장소 연결 자체는 정상입니다)")
    for name in failed:
        print("   ", name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
