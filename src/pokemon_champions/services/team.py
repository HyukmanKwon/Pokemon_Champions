"""내 포켓몬 6마리의 스펙을 들고 있다가 Pokemon 객체로 만들어주는 모듈.

스펙(이름/SP/성격/특성/도구/기술)과 실제로 빌드된 Pokemon 객체는 다르다.
배틀 중에는 build_team() 이 만들어준 Pokemon 객체의 rank/condition 이 바뀔 수
있지만, 그건 스펙에는 반영되지 않는다. 배틀이 끝나면 스펙으로 build_team() 을
다시 부르기만 하면 배틀 이전 상태로 돌아간다.

── 여기에는 print/input 이 없다 ──
  CLI 와 웹 API 가 이 모듈을 그대로 공유한다. 출력 형식을 여기서 정하는
  순간 둘 중 하나는 못 쓰게 된다.

── 저장은 여기가 아니다 ──
  덱을 읽고 쓰는 일은 usecases/roster.py 가 한다. 덱이 여러 벌이 되면서
  "어느 덱인가" 가 붙었는데, 그건 이 모듈이 알 필요가 없는 것이다.
  여기는 스펙 한 벌을 받아 검증하고 Pokemon 으로 만드는 데까지만 한다.

  DEFAULT_TEAM 은 남는다 — 새 덱이 무엇으로 시작하는지는 팀의 규칙이다.
"""

from ..config import MAX_MOVES
from ..db.repositories import (item_repo, mega_repo, move_repo, nature_repo,
                               pokemon_repo)
from ..domain import Pokemon
from ..text import normalize
from .stats import calc_stats, make_sp

# 여섯 마리 전부 validate_spec 을 통과하는 조합이다. 예시라고 대충 적으면
# 처음 실행하는 사람이 화면을 열자마자 검증 오류를 보게 된다.
DEFAULT_TEAM = [
    dict(ko_name="리자몽", sp_values=(0, 0, 0, 32, 2, 32), ko_nature="겁쟁이",
         ability="맹화", item="생명의구슬",
         moves=["화염방사", "폭풍", "기합구슬", "솔라빔"]),
    dict(ko_name="이상해꽃", sp_values=(2, 0, 0, 32, 32, 0), ko_nature="차분",
         ability="심록", item="신비의물방울",
         moves=["기가드레인", "씨뿌리기", "수면가루", "맹독"]),
    dict(ko_name="거북왕", sp_values=(2, 0, 32, 0, 32, 0), ko_nature="의젓",
         ability="급류", item="기합의띠",
         moves=["파도타기", "지진", "고속스핀", "냉동빔"]),
    dict(ko_name="피카츄", sp_values=(0, 0, 0, 32, 2, 32), ko_nature="명랑",
         ability="정전기", item="전기구슬",
         moves=["10만볼트", "볼트태클", "아이언테일", "전광석화"]),
    dict(ko_name="잠만보", sp_values=(32, 0, 0, 2, 32, 0), ko_nature="신중",
         ability="먹보", item="맹독구슬",
         moves=["지진", "파도타기", "번개", "깨물어부수기"]),
    dict(ko_name="루카리오", sp_values=(0, 32, 0, 0, 2, 32), ko_nature="고집",
         ability="정의의마음", item="구애스카프",
         moves=["인파이트", "코멧펀치", "스톤에지", "지진"]),
]


# ─────────────────────────────────────────────────────────────
# 스펙 수정
# ─────────────────────────────────────────────────────────────

def edit_spec(specs, index, **fields):
    """specs[index] 중 fields 로 넘어온 필드만 바꾼다. 나머지는 그대로 둔다."""
    if not 0 <= index < len(specs):
        raise ValueError(f"슬롯은 0~{len(specs) - 1} 사이여야 합니다: {index}")
    specs[index].update(fields)
    return specs[index]


# ─────────────────────────────────────────────────────────────
# 검증
# ─────────────────────────────────────────────────────────────

def validate_spec(conn, spec, allow_mega=False):
    """엔트리 하나가 규칙에 맞는지 본다. 어기면 ValueError.

    ── allow_mega ──
      메가폼 금지는 "엔트리에 올릴 수 있는가" 의 규칙이지 "그런 포켓몬이
      존재하는가" 의 규칙이 아니다. 데미지 계산기는 메가리자몽이 상대로
      나오는 판을 그대로 물어보는 곳이라 그 금지가 걸리면 안 된다.
      특성·기술·도구 검사는 그대로 걸린다 — 틀린 특성으로 계산하면
      숫자만 조용히 어긋난다.

    ── 여기 하나로 모으는 이유 ──
      CLI 는 edit_slot -> build_pokemon 으로, 웹은 patch_team 으로 들어오는데
      웹은 _slot_view 가 repositories 를 직접 부르느라 build_pokemon 을
      거치지 않는다. 검증을 build_pokemon 안에만 두면 CLI 만 막히고 웹은
      그대로 통과한다. 두 경로가 이 함수를 부른다.

    ── 무엇이 잘못이고 무엇이 아닌가 ──
      메가스톤을 엉뚱한 포켓몬에게 주는 것은 잘못이 아니다. 그냥 메가진화가
      안 될 뿐이라서, 주인이 아닌 스톤도 통과시킨다. (resolve_mega 참고)
    """
    ko_name = normalize(spec["ko_name"])

    # 없는 포켓몬이면 여기서 걸린다.
    if pokemon_repo.fetch_meta(conn, ko_name)["is_mega"] and not allow_mega:
        raise ValueError(
            f"메가폼은 엔트리에 등록할 수 없습니다: {ko_name}. "
            "메가진화는 배틀 중 상태라 원종에 메가스톤을 지니는 것으로 표현합니다."
        )

    ability = normalize(spec["ability"]) if spec.get("ability") else None
    selectable = pokemon_repo.fetch_abilities(conn, ko_name)
    if ability not in selectable:
        raise ValueError(
            f"{ko_name}의 특성이 아닙니다: {ability or '없음'} "
            f"(가능: {', '.join(selectable) or '없음'})"
        )

    moves = [normalize(m) for m in (spec.get("moves") or [])]
    if len(moves) > MAX_MOVES:
        raise ValueError(f"기술은 {MAX_MOVES}개까지입니다: {len(moves)}개")
    duplicated = [m for i, m in enumerate(moves) if m in moves[:i]]
    if duplicated:
        raise ValueError(f"같은 기술을 두 번 넣었습니다: {', '.join(duplicated)}")

    # 하나씩 물으면 쿼리가 기술 수만큼 나간다. 목록을 한 번에 받아 대조한다.
    learnable = set(move_repo.fetch_learnable(conn, ko_name))
    unlearnable = [m for m in moves if m not in learnable]
    if unlearnable:
        raise ValueError(
            f"{ko_name}이(가) 배울 수 없는 기술입니다: {', '.join(unlearnable)}"
        )

    item = normalize(spec["item"]) if spec.get("item") else None
    if item and item not in set(
            item_repo.fetch_usable(conn, include_mega_stones=True)):
        raise ValueError(f"포챔스에서 지닐 수 없는 도구입니다: {item}")


# ─────────────────────────────────────────────────────────────
# 조립
# ─────────────────────────────────────────────────────────────

def build_pokemon(conn, ko_name, sp_values, ko_nature,
                  ability, item=None, moves=None, condition=None,
                  rank=None, allow_mega=False):
    """DB를 읽어 Pokemon 하나를 만든다.

    조회는 repositories 에, 계산은 services.stats 에 맡기고 여기서는
    순서만 정한다.
    """
    ko_name = normalize(ko_name)
    validate_spec(conn, dict(ko_name=ko_name, ability=ability,
                             item=item, moves=moves), allow_mega=allow_mega)
    base = pokemon_repo.fetch_base(conn, ko_name)
    sp = make_sp(sp_values)
    nature = nature_repo.fetch_modifiers(conn, ko_nature)
    # 타입은 데미지 계산(자속·상성)에 필요하다. 여기서 같이 실어 보내지
    # 않으면 계산 쪽이 이름만 들고 DB 로 되돌아가야 한다.
    meta = pokemon_repo.fetch_meta(conn, ko_name)

    return Pokemon(
        name=ko_name,
        stats=calc_stats(base, sp, nature),
        ability=ability,
        item=normalize(item) if item else None,
        moves=[normalize(m) for m in (moves or [])],
        condition=condition,
        rank=rank or None,
        nature=normalize(ko_nature),
        types=tuple(t for t in (meta["type1"], meta["type2"]) if t),
    )


def build_team(conn, specs):
    """스펙 리스트를 읽어 Pokemon 들을 만든다."""
    return [build_pokemon(conn, **spec) for spec in specs]


# ─────────────────────────────────────────────────────────────
# 메가진화
# ─────────────────────────────────────────────────────────────

def resolve_mega(conn, spec):
    """지닌 도구가 이 포켓몬의 메가스톤이면 메가진화 후 상태를 돌려준다.

    아니면 None. 도구가 메가스톤이 아닌 건 잘못이 아니므로 예외가 아니다.

    ── 무엇이 바뀌고 무엇이 그대로인가 ──
      바뀜   종족값 · 타입 · 특성
      그대로 SP 투자 · 성격 · 레벨 · 개체값

    그래서 실능치는 "메가폼 종족값 + 원래 SP + 원래 성격"으로 다시 계산한다.
    SP 나 성격이 바뀐다고 착각하기 쉬운 지점이다.
    """
    form = mega_repo.fetch_form(conn, spec["ko_name"], spec.get("item"))
    if form is None:
        return None

    sp = make_sp(spec["sp_values"])
    nature = nature_repo.fetch_modifiers(conn, spec["ko_nature"])

    return {
        **form,
        "sp": sp,
        "stats": calc_stats(form["base"], sp, nature),
    }


def mega_hint(conn, ko_name):
    """이 포켓몬이 메가진화하려면 무슨 스톤이 필요한지. 없으면 빈 리스트."""
    return mega_repo.fetch_stones(conn, ko_name)
