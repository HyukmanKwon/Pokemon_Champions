"""포켓몬 한 마리 — 엔트리용과 배틀용이 따로 있다.

    Pokemon        엔트리에 올린 한 마리. 스펙에서 실능치를 계산한 결과다.
    BattlePokemon  판에 나가 있는 한 마리. 위에 배틀 중 변하는 것이 붙는다.

── 왜 나눠 두나 ──
  엔트리에는 남은 HP 도 랭크도 상태이상도 있을 수 없다. 저장되는 스펙에
  그런 칸이 없고(ko_name · sp_values · ko_nature · ability · item · moves),
  대전이 끝나면 사라지는 값이기 때문이다.

  한 클래스에 다 넣으면 엔트리를 그리는 코드가 늘 None 인 칸을 달고 다닌다.
  실제로 CLI 의 엔트리 표가 "상태이상: 정상" 을 무조건 찍고 있었다 — 엔트리
  포켓몬은 상태이상에 걸릴 수가 없는데 그 자리를 그리고 있었던 것이다.

  더 중요한 것은 시그니처가 요구사항을 말한다는 점이다.

      def calc_damage(attacker: BattlePokemon, defender: BattlePokemon, ...)

  엔트리 Pokemon 을 넘기면 그 자리에서 걸린다. 한 클래스면 조용히 만피 ·
  랭크 0 으로 계산되고, 부르는 쪽은 자기가 무엇을 빠뜨렸는지 모른다.

── 배틀 중 상태는 전부 BattlePokemon 에 있다 ──
  예전에는 랭크 · 상태이상 · 남은 HP · 접지가 BattleContext 에도 같이
  있었다. 같은 사실이 두 군데 적히니 읽는 쪽이 갈렸다 — 화상의 공격
  반감은 ctx 를 보고 근성은 Pokemon 을 봐서, "화상 걸린 근성" 을 재려면
  burn 을 두 번 적어야 했다. 한 번만 적으면 예외가 아니라 조용히 다른
  값이 나왔다.

  지금은 가르는 기준이 하나다.

      BattlePokemon   이 한 마리에게 걸린 것
      BattleContext   판 전체에 걸린 것 (날씨 · 필드 · 급소 · 스크린 · 더블)

── 화면 출력은 여기 없다 ──
  예전 __str__ 은 터미널 폭을 맞춰 표를 그렸다. 그건 CLI 사정이지 포켓몬의
  성질이 아니라서 interfaces/cli.py 의 format_pokemon() 으로 옮겼다.
  웹은 같은 객체를 JSON으로 내보낸다 — 표현을 밖에 두면 이게 가능하다.
"""

from dataclasses import dataclass, fields

from .stats import Stats


@dataclass
class Pokemon:
    """엔트리에 올린 한 마리. 대전과 무관하게 늘 같은 값이다."""

    name: str               # 한국어 이름
    stats: Stats            # 실능치
    ability: str
    item: str = None
    moves: list = None      # 기술 4개까지
    nature: str = None
    # 영문 타입 1~2개. ("fire", "flying") 또는 ("water",)
    #
    # 이름이 아니라 타입을 들고 있는 이유: 데미지 계산이 자속과 상성을
    # 판정하려면 타입이 필요한데, calc/damage.py 는 DB를 안 본다.
    # 이름만 들고 있으면 계산 함수가 "이 이름의 타입이 뭐지"를 물으러
    # DB로 돌아가야 하고, 그 순간 순수 함수가 아니게 된다.
    #
    # 메가진화하면 여기가 바뀐다 — 메가폼의 타입으로 다시 만들면 된다.
    types: tuple = ()


@dataclass
class BattlePokemon(Pokemon):
    """판에 나가 있는 한 마리. 계산기가 받는 것은 전부 이쪽이다."""

    # 남은 HP. None 은 "안 물어봤다" 이고 만피로 본다. 0 과 구분해야
    # 하므로 기본값을 stats.h 로 채우지 않는다 — 그러면 만들 때 실능치가
    # 이미 있어야 한다.
    #
    # 멀티스케일(만피일 때만)과 궁지 특성(1/3 이하일 때만)이 이걸 본다.
    hp: int = None

    rank: dict = None       # {"a": int, ..., "s": int} -6 ~ +6, 기본 0
    condition: str = None   # None 이면 정상, "poison" 등

    # 접지 여부. 필드 효과는 접지된 쪽에만 걸린다. 부유나 비행 타입이
    # 아니면 참이라 기본값이 True 다.
    grounded: bool = True

    @classmethod
    def of(cls, pokemon, hp=None, rank=None, condition=None, grounded=True):
        """엔트리 한 마리를 판에 올린다.

        조회를 다시 하지 않으려고 이 자리가 있다. 스펙에서 Pokemon 을
        만드는 일(실능치 계산 · 타입 조회)은 usecases/team.py 가 하고,
        여기서는 배틀 중 상태만 얹는다.
        """
        base = {f.name: getattr(pokemon, f.name) for f in fields(Pokemon)}
        return cls(**base, hp=hp, rank=rank, condition=condition,
                   grounded=grounded)

    def rank_of(self, stat):
        """랭크 변화 단계. 안 걸려 있으면 0."""
        return (self.rank or {}).get(stat, 0)

    def hp_now(self):
        """남은 HP. 안 물어봤으면 만피.

        부르는 쪽이 매번 `hp if hp is not None else stats.h` 를 적지 않게
        한다. 그 세 갈래를 여섯 군데 적으면 한 곳은 반드시 틀린다.
        """
        return self.stats.h if self.hp is None else self.hp
