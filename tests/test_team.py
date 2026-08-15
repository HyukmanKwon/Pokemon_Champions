"""엔트리 검증 테스트.

── DB 없이 돈다 ──
  validate_spec 안에 SQL 이 없고 조회를 repositories 에 맡기기 때문에,
  그 조회만 가짜로 바꿔치면 PostgreSQL 없이 규칙만 검증할 수 있다.
  실패했을 때 "규칙이 틀렸는지 데이터가 틀렸는지" 헷갈리지 않는 것이
  이 구조의 값이다.

  conn 은 아무 데도 안 쓰이므로 표식 하나를 넘긴다.

  실행:  pytest
"""

import pytest

from pokemon_champions.usecases import team

CONN = object()          # 가짜 조회는 conn 을 보지 않는다

# 이상해꽃 기준. 검증에 필요한 만큼만 있으면 된다.
ABILITIES = ["심록", "엽록소"]
LEARNABLE = ["기가드레인", "맹독", "수면가루", "씨뿌리기", "지진"]
USABLE = ["기합의띠", "생명의구슬", "신비의물방울"]
MEGA_STONES = ["리자몽나이트X", "이상해꽃나이트"]

SPEC = dict(ko_name="이상해꽃", sp_values=(2, 0, 0, 32, 32, 0),
            ko_nature="차분", ability="심록", item="신비의물방울",
            moves=["기가드레인", "씨뿌리기", "수면가루", "맹독"])


@pytest.fixture(autouse=True)
def fake_repos(monkeypatch):
    """조회 세 개를 고정값으로 바꾼다. 메가폼 여부는 이름으로 판단한다."""
    monkeypatch.setattr(team.pokemon_repo, "fetch_meta",
                        lambda conn, ko: {"is_mega": ko.startswith("메가")})
    monkeypatch.setattr(team.pokemon_repo, "fetch_abilities",
                        lambda conn, ko: list(ABILITIES))
    monkeypatch.setattr(team.move_repo, "fetch_learnable",
                        lambda conn, ko: list(LEARNABLE))
    monkeypatch.setattr(
        team.item_repo, "fetch_usable",
        lambda conn, include_mega_stones=False:
            USABLE + (MEGA_STONES if include_mega_stones else []))


def spec(**changes):
    return {**SPEC, **changes}


# ─────────────────────────────────────────────────────────────
# 통과하는 것
# ─────────────────────────────────────────────────────────────

def test_규칙에_맞는_엔트리는_통과한다():
    team.validate_spec(CONN, spec())


def test_도구가_없어도_된다():
    team.validate_spec(CONN, spec(item=None))


def test_기술이_4개보다_적어도_된다():
    team.validate_spec(CONN, spec(moves=["맹독"]))
    team.validate_spec(CONN, spec(moves=[]))


def test_주인이_아닌_메가스톤은_잘못이_아니다():
    """메가진화가 안 될 뿐이다. 기합의띠를 지니는 것과 다르지 않다."""
    team.validate_spec(CONN, spec(item="리자몽나이트X"))


# ─────────────────────────────────────────────────────────────
# 막는 것
# ─────────────────────────────────────────────────────────────

def test_그_포켓몬의_특성이_아니면_거부한다():
    with pytest.raises(ValueError, match="특성이 아닙니다"):
        team.validate_spec(CONN, spec(ability="맹화"))


def test_특성이_비어도_거부한다():
    with pytest.raises(ValueError, match="특성이 아닙니다"):
        team.validate_spec(CONN, spec(ability=None))


def test_배울_수_없는_기술을_거부한다():
    with pytest.raises(ValueError, match="리프블레이드"):
        team.validate_spec(CONN, spec(moves=["맹독", "리프블레이드"]))


def test_못_배우는_기술을_한꺼번에_알려준다():
    """하나씩 고쳐가며 다섯 번 저장하게 만들지 않는다."""
    with pytest.raises(ValueError) as e:
        team.validate_spec(CONN, spec(moves=["리프블레이드", "10만볼트"]))
    assert "리프블레이드" in str(e.value) and "10만볼트" in str(e.value)


def test_기술이_5개면_거부한다():
    moves = LEARNABLE[:5]
    with pytest.raises(ValueError, match="4개까지"):
        team.validate_spec(CONN, spec(moves=moves))


def test_같은_기술을_두_번_넣으면_거부한다():
    with pytest.raises(ValueError, match="두 번"):
        team.validate_spec(CONN, spec(moves=["맹독", "맹독"]))


def test_포챔스에서_못_쓰는_도구를_거부한다():
    with pytest.raises(ValueError, match="지닐 수 없는 도구"):
        team.validate_spec(CONN, spec(item="마스터볼"))


def test_메가폼은_엔트리에_등록할_수_없다():
    with pytest.raises(ValueError, match="메가폼"):
        team.validate_spec(CONN, spec(ko_name="메가이상해꽃"))


# ─────────────────────────────────────────────────────────────
# 조회 횟수 — 규칙 2 (성능)
# ─────────────────────────────────────────────────────────────

def test_기술_검사는_조회를_한_번만_한다(monkeypatch):
    """4개를 하나씩 물으면 쿼리가 4번 나간다. 6마리면 24번이다."""
    calls = []
    monkeypatch.setattr(team.move_repo, "fetch_learnable",
                        lambda conn, ko: calls.append(ko) or list(LEARNABLE))
    team.validate_spec(CONN, spec())
    assert calls == ["이상해꽃"]


# ─────────────────────────────────────────────────────────────
# 두 경로가 같은 검증을 탄다
# ─────────────────────────────────────────────────────────────

def test_build_pokemon_도_같은_검증을_탄다(monkeypatch):
    """CLI 는 build_pokemon 을 거친다. 여기가 뚫리면 터미널이 무방비다."""
    monkeypatch.setattr(team.pokemon_repo, "fetch_base",
                        lambda conn, ko: pytest.fail("검증 전에 조회했다"))
    with pytest.raises(ValueError, match="특성이 아닙니다"):
        team.build_pokemon(CONN, ko_name="이상해꽃", sp_values=(0,) * 6,
                           ko_nature="차분", ability="맹화")
