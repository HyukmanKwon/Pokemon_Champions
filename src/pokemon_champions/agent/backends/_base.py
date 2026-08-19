"""백엔드가 주고받는 유일한 공용 모양.

Call 하나뿐이다. 이 자리에 추상 클래스를 두지 않는 이유는, 백엔드가 셋도
아니고 둘이라 상속으로 묶어 얻을 것이 없기 때문이다. runner 는 메서드
이름만 보고 부르고, 어긋나면 첫 질문에서 바로 AttributeError 로 터진다.
"""

from typing import NamedTuple


class Call(NamedTuple):
    """모델이 부르겠다고 한 도구 하나.

    id 는 회사마다 있고 없다. OpenAI 는 tool_call_id 로 결과를 짝짓고,
    Ollama 는 이름으로 짝짓는다. 없는 쪽에서는 None 이고, 그 값을 쓰는 것은
    그 백엔드의 tool_message 뿐이다 — runner 는 id 를 들여다보지 않는다.
    """
    id: str | None
    name: str
    args: dict
