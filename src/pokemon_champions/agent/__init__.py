"""LLM 도우미 — 자연어를 결정적 도구로 잇는 층.

── LLM 은 계산하지 않는다 ──
  이 폴더의 존재 이유가 그것이다. 언어 모델은 "무엇을 물어봤는가" 를 읽고
  어느 도구를 어떤 인자로 부를지 정하는 데까지만 쓴다. 데미지·상성·실능치는
  전부 services 와 repositories 가 낸다.

  숫자를 모델에게 맡기면 그럴듯하게 틀린 값이 나오고, 틀렸다는 것을 알아챌
  방법이 없다. 반대로 도구가 낸 값은 scripts/check_damage.py 로 실제 게임과
  대조할 수 있고 tests/ 에 박아둘 수 있다.

── 왜 HTTP 를 안 거치나 ──
  web.py 가 떠 있어야만 도우미가 돌면, 터미널에서 한 줄 물어보려고 서버를
  먼저 띄워야 한다. 도구는 repositories 를 직접 부른다. 웹 라우트도 같은
  services 를 부르므로 두 경로의 답이 갈라지지 않는다.
"""

from .tools import TOOLS, call, schemas

__all__ = ["TOOLS", "call", "schemas"]
