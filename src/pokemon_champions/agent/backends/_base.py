"""백엔드가 주고받는 공용 모양 — Call 과 Usage.

이 자리에 추상 클래스를 두지 않는 이유는, 백엔드가 셋도 아니고 둘이라
상속으로 묶어 얻을 것이 없기 때문이다. runner 는 메서드 이름만 보고
부르고, 어긋나면 첫 질문에서 바로 AttributeError 로 터진다.
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


class Usage(NamedTuple):
    """한 질문이 쓴 토큰. 백엔드가 요청마다 더한다.

    ── 왜 total 을 따로 세나 ──
      prompt + completion 이 total 이 아니다. Gemini 는 생각(thinking)
      토큰을 total 에만 넣는데 그것도 과금 대상이라, 앞의 둘만 더하면
      실제보다 적게 나온다. 실제로 3 + 12 인데 total 이 265 인 응답을 봤다.

    ── 왜 돈으로 안 바꾸나 ──
      가격표를 코드에 박으면 저쪽이 바꿨을 때 조용히 틀린 금액을 보게
      된다. 틀린 숫자는 없는 숫자보다 나쁘다. 토큰만 정확히 세고 환산은
      저쪽 콘솔에 맡긴다.

    requests 는 저쪽에 몇 번 물어봤는가다. 도구를 한 번 부르면 두 번
    나가므로, 이 값이 곧 "도구를 몇 번 불렀나 + 1" 이다.
    """
    requests: int = 0
    prompt: int = 0
    completion: int = 0
    total: int = 0

    def plus(self, prompt, completion, total):
        """요청 하나치를 더한 새 Usage. 못 받은 칸은 0 으로 친다."""
        return Usage(self.requests + 1,
                     self.prompt + (prompt or 0),
                     self.completion + (completion or 0),
                     self.total + (total or 0))

    def line(self):
        """사람이 읽을 한 줄. 생각 토큰은 나머지에서 뽑는다."""
        thought = self.total - self.prompt - self.completion
        out = (f"요청 {self.requests}번 · {self.total:,} 토큰"
               f" (프롬프트 {self.prompt:,} · 출력 {self.completion:,}")
        return out + (f" · 생각 {thought:,})" if thought > 0 else ")")
