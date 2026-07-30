"""도메인 모델 — "포켓몬이란 무엇인가"만 안다.

이 폴더의 모듈은 프로젝트 내 어떤 것도 import 하지 않는다. DB에서 왔는지
PokeAPI에서 왔는지 JSON에서 왔는지 몰라야, 바깥이 바뀔 때 여기가 안 깨진다.
"""

from .pokemon import Pokemon
from .stats import STAT_LABELS, STAT_ORDER, Stats

__all__ = ["Pokemon", "Stats", "STAT_ORDER", "STAT_LABELS"]
