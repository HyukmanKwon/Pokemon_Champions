"""LLM 백엔드 — 어디에 물어볼지.

runner.ask 의 루프는 어느 백엔드를 쓰든 똑같다. 백엔드가 감추는 것은 넷뿐이다.

    chat(messages, use_tools)   한 번 물어본다
    calls(msg)                  도구 호출을 Call 로 꺼낸다
    text(msg)                   답변 글자를 꺼낸다
    tool_message(call, result)  도구 결과를 그쪽 모양으로 싼다
    friendly_error(exc)         사람이 읽을 오류 한 줄 (모르면 None)

── 왜 한 모양으로 통일하지 않았나 ──
  도구 결과를 되돌리는 방법이 회사마다 다르다. OpenAI 는 tool_call_id 로
  짝짓고 Ollama 는 이름으로 짝짓는다. 한쪽 모양으로 눌러 담으면 다른 쪽에서
  짝이 어긋나는데, 그건 오류로 안 나오고 "엉뚱한 도구 결과를 보고 쓴 답" 으로
  나온다. 그래서 메시지 모양은 백엔드가 끝까지 들고 있는다.

  대가가 하나 있다. history 는 그 대화를 시작한 백엔드의 모양이라, 대화
  도중에 모델을 바꾸면 짝이 맞지 않는다. 화면에서 모델을 바꾸면 대화를
  새로 시작하게 해야 한다.

── 모르는 이름은 로컬로 보낸다 ──
  아래 표는 "돈이 나가는 곳" 만 적는다. 여기 없는 이름은 Ollama 로 간다 —
  ollama pull 로 받아둔 무엇이든 --model 로 그냥 써볼 수 있어야 하고,
  오타로 이름이 틀렸을 때 조용히 유료 API 를 부르는 것보다 로컬에서
  "그런 모델이 없다" 를 보는 편이 낫다.
"""

from . import ollama
from .openai_compat import OpenAICompat
from ._base import Call

__all__ = ["Call", "DEFAULT_MODEL", "MODELS", "pick"]

# 회사별로 다른 것은 키와 주소뿐이다.
PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "base_url": None,           # SDK 기본값
    },
    "gemini": {
        "label": "Gemini",
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
}

# ── 왜 모델을 하나하나 적나 ──
#   접두사로 가리면("gpt-" 로 시작하면 OpenAI) 새 모델이 나올 때마다 조용히
#   맞거나 조용히 틀린다. 여기 적힌 것만 유료로 나가고, 나머지는 로컬이다.
#
#   effort 는 필요한 모델에만 붙인다. 무엇이고 왜인지는
#   openai_compat.py 첫머리에 있다 — 취향이 아니라 조건이다.
MODELS = {
    "gpt-5.6-luna": {"provider": "openai", "effort": "none"},
    # 견줘 보려고 같이 둔다. 이 seam 을 만든 이유가 이것이다.
    "gemini-3.7-flash": {"provider": "gemini"},
}

DEFAULT_MODEL = "gpt-5.6-luna"


def pick(model=None):
    """모델 이름 하나로 백엔드를 고른다."""
    model = model or DEFAULT_MODEL
    spec = MODELS.get(model)
    if spec is None:
        return ollama.Ollama(model)

    provider = PROVIDERS[spec["provider"]]
    return OpenAICompat(model=model,
                        label=provider["label"],
                        env_key=provider["env_key"],
                        base_url=provider["base_url"],
                        effort=spec.get("effort"))
