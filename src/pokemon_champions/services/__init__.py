"""비즈니스 로직.

두 종류가 섞여 있고, 구분해서 읽어야 한다.

  순수 계산 (stats.py, damage.py)
      conn 을 받지 않는다. 같은 입력이면 항상 같은 출력. DB 없이 테스트되고,
      나중에 LLM 툴로 감쌀 때 시그니처가 그대로 툴 스키마가 된다.

  조립 (team.py)
      repositories 로 값을 모아 순수 계산에 넘긴다. conn 을 인자로 받되
      SQL 은 쓰지 않는다.

어느 쪽이든 print()/input() 은 하지 않는다. 그건 interfaces 의 일이다.
"""

__all__ = []
