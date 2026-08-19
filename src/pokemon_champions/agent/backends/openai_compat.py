"""OpenAI 호환 백엔드 — GPT · Gemini, 그리고 같은 모양을 내주는 무엇이든.

── 왜 이 한 벌로 여러 회사를 덮나 ──
  OpenAI 의 /v1/chat/completions 모양을 Google 도 그대로 내준다(호환
  엔드포인트). 우리 도구 스키마(schemas.as_array)가 애초에 그 모양이라,
  갈아끼울 것은 base_url 과 키뿐이다.

  회사를 바꿔 재 보려고 붙인 seam 이다. 한 회사에 맞춰 짜두면 "저쪽이 더
  나은가" 를 물어볼 방법이 없어지고, 그러면 처음 고른 것을 계속 쓰게 된다.

── reasoning_effort="none" 은 취향이 아니라 조건이다 ──
  gpt-5.6 계열은 /v1/chat/completions 에 도구를 실으면 400 을 낸다:

    Function tools with reasoning_effort are not supported for gpt-5.6-…
    in /v1/chat/completions. To use function tools, use /v1/responses or
    set reasoning_effort to 'none'.

  안 보내도 터진다 — 기본값이 medium 이라서다. 그러니 셋 중 하나다.
  도구를 빼거나, /v1/responses 로 가거나, 추론을 끄거나.

  도구를 빼는 것은 이 프로젝트의 전부를 버리는 것이고, /v1/responses 는
  모양이 달라 Ollama·Gemini 와 이 파일을 나눠 쓸 수 없게 된다. 그래서
  끈다. 마침 이건 이미 재 보고 내린 결론이기도 하다 — ollama.py 의
  THINK 주석에 그 측정이 있다. 생각을 꺼도 도구 선택은 그대로였고 시간은
  59초에서 22초로 줄었다. 어느 도구를 부를지는 스키마의 설명이 정하는
  것이지 모델의 독백이 정하는 게 아니다.

  ── 지우기 전에 읽을 것 ──
    이 줄을 "추론을 켜면 더 똑똑하겠지" 하고 지우면 도구가 붙은 모든
    요청이 400 으로 죽는다. 켜고 싶으면 /v1/responses 백엔드를 따로
    만들어야 한다.

── temperature 를 다시 쓸 수 있는 이유 ──
  effort 가 none 일 때만 temperature·top_p 가 허용된다. 다른 값과 같이
  보내면 오류다. 0.2 로 두는 까닭은 Ollama 쪽과 같다 — 답변 문장의
  다양성보다 "포켓몬 이름을 정확히 적는가" 가 훨씬 중요하다.
"""

import json
import os

from .. import schemas
from ._base import Call


class OpenAICompat:
    """OpenAI 호환 엔드포인트 하나.

    base_url 이 None 이면 SDK 기본값(OpenAI 본진)을 쓴다.
    effort 가 None 이면 reasoning_effort 를 아예 안 보낸다 — 이 파라미터를
    모르는 호환 엔드포인트가 있고, 모르는 열쇠를 받으면 400 을 내는 쪽도
    있다. 필요한 모델에만 붙인다.
    """

    def __init__(self, model, label, env_key, base_url=None, effort=None):
        self.model = model
        self.label = label
        self.env_key = env_key
        self.base_url = base_url
        self.effort = effort
        self._client = None

    # ── 클라이언트를 왜 늦게 만드나 ──
    #   app.py 는 뜰 때 agent 를 import 한다. 여기서 바로 클라이언트를
    #   만들면 API 키가 없는 사람은 웹 서버 자체가 안 뜬다 — 도감만 보러
    #   온 사람까지 키를 요구받는 셈이다. 처음 물어볼 때 만든다.
    #
    #   openai 패키지도 같은 이유로 여기서 import 한다. 로컬 모델만 쓰는
    #   설치에는 그 패키지가 없어도 된다.
    def _ready(self):
        if self._client is not None:
            return self._client

        key = os.environ.get(self.env_key)
        if not key:
            raise RuntimeError(
                f"{self.label} 키가 없습니다. .env 에 {self.env_key} 를 넣거나 "
                f"로컬 모델(예: qwen3.5:9b)로 바꿔 주세요.")
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                'openai 패키지가 없습니다. `pip install -e ".[llm]"` 을 '
                "먼저 하세요.")

        self._client = OpenAI(api_key=key, base_url=self.base_url)
        return self._client

    def chat(self, messages, use_tools=True):
        """한 번 물어본다. 돌려주는 값은 message 하나(dict).

        객체가 아니라 dict 로 돌려주는 이유는 이 값이 그대로 history 에
        쌓여 브라우저까지 갔다 오기 때문이다 — JSON 으로 오갈 수 있어야 한다.
        exclude_none 은 SDK 가 채워 넣는 빈 칸(refusal, audio …)을 걷어낸다.
        그대로 되돌려 보내면 저쪽이 모르는 열쇠라며 물리는 수가 있다.
        """
        kwargs = {"model": self.model, "messages": messages}
        if self.effort is not None:
            kwargs["reasoning_effort"] = self.effort
        if self.effort in (None, "none"):
            # effort 가 none 일 때만 허용된다. 파일 첫머리 참고.
            kwargs["temperature"] = 0.2
        if use_tools:
            kwargs["tools"] = schemas.as_array()

        res = self._ready().chat.completions.create(**kwargs)
        return res.choices[0].message.model_dump(exclude_none=True)

    def calls(self, msg):
        """assistant 메시지에서 도구 호출을 꺼낸다.

        arguments 는 규격상 늘 문자열(JSON)이다. 모델이 깨진 JSON 을 뱉는
        일이 있는데, 그때 예외를 올리면 루프가 죽는다. 빈 인자로 두면
        tools.call 이 "인자가 맞지 않습니다" 를 값으로 돌려주고, 모델이
        그걸 읽고 다시 부른다.
        """
        out = []
        for c in msg.get("tool_calls") or []:
            fn = c["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out.append(Call(id=c["id"], name=fn["name"], args=args))
        return out

    def text(self, msg):
        return msg.get("content") or ""

    def tool_message(self, call, result):
        # id 로 짝짓는다. 한 턴에 여러 도구를 부르면 이 값이 유일한 단서다 —
        # 이름으로 짝지으면 같은 도구를 두 번 부른 턴에서 뒤섞인다.
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(result, ensure_ascii=False, default=str),
        }

    def friendly_error(self, exc):
        """사람이 읽을 한 줄. 모르는 예외면 None 을 주고 위에서 처리한다."""
        if isinstance(exc, RuntimeError):       # _ready 가 낸 안내
            return str(exc)

        # openai 가 없으면 위 import 에서 이미 걸렸다. 여기 왔다는 것은
        # 패키지가 있다는 뜻이라 그냥 import 한다.
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return f"{self.label} 키가 거부됐습니다. {self.env_key} 를 확인해 주세요."
        if isinstance(exc, openai.RateLimitError):
            return (f"{self.label} 사용량 한도에 걸렸습니다. "
                    "잠시 뒤에 다시 물어봐 주세요.")
        if isinstance(exc, openai.APIConnectionError):
            return f"{self.label} 에 연결하지 못했습니다. 인터넷을 확인해 주세요."
        if isinstance(exc, openai.NotFoundError):
            return f"{self.label} 에 그런 모델이 없습니다: {self.model}"
        if isinstance(exc, openai.BadRequestError):
            return f"{self.label} 이 요청을 물렸습니다: {exc}"
        return None
