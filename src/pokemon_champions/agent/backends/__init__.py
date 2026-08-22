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

import os

from . import ollama
from .openai_compat import OpenAICompat
from ._base import Call

__all__ = ["Call", "DEFAULT_MODEL", "MODELS", "available", "pick"]

# 회사별로 다른 것은 키와 주소뿐이다.
PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "base_url": None,           # SDK 기본값
    },
    "gemini": {
        "label": "Gemini",
        # 구글이 자기 도구에서 둘 다 받는다. 앞의 것이 먼저다.
        "env_key": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
}

# ── 왜 모델을 하나하나 적나 ──
#   접두사로 가리면("gpt-" 로 시작하면 OpenAI) 새 모델이 나올 때마다 조용히
#   맞거나 조용히 틀린다. 여기 적힌 것만 유료로 나가고, 나머지는 로컬이다.
#
#   effort 는 필요한 모델에만 붙인다. 무엇이고 왜인지는
#   openai_compat.py 첫머리에 있다 — 취향이 아니라 조건이다.
# ── effort 는 시간을 사는 손잡이다 ──
#   생각(thinking) 토큰은 출력이라 시간에 그대로 얹힌다. 입력은 아무리
#   커도 시간이 거의 안 늘지만(6 토큰 3.2초 vs 17,642 토큰 2.9초) 출력은
#   늘어난다. 같은 도구 4개를 부르는데 13.9초에서 6.2초가 됐다.
#
#   Gemini 는 "none" 을 400 으로 거부한다. 그건 OpenAI 쪽 값이다.
MODELS = {
    "gpt-5.6-luna": {"provider": "openai", "effort": "none",
                     "no_temperature_with_effort": True},
    # 견줘 보려고 같이 둔다. 이 seam 을 만든 이유가 이것이다.
    # 이름은 짐작하지 않고 저쪽 목록에서 그대로 옮겼다 (models.list).
    "gemini-3.6-flash": {"provider": "gemini", "effort": "minimal"},
    "gemini-3.7-flash": {"provider": "gemini", "effort": "minimal"},
}

# 화면(agent.js)은 모델을 안 보낸다. 그래서 이 값이 곧 웹에서 쓰는
# 모델이고, 여기 적힌 회사의 키가 없으면 도우미 탭이 통째로 막힌다.
# 바꿀 때는 .env 에 그쪽 키가 있는지 같이 본다.
DEFAULT_MODEL = "gemini-3.6-flash"


def pick(model=None):
    """모델 이름 하나로 백엔드를 고른다."""
    model = model or DEFAULT_MODEL
    spec = MODELS.get(model)
    if spec is None:
        return ollama.Ollama(model)

    provider = PROVIDERS[spec["provider"]]
    return OpenAICompat(
        model=model,
        label=provider["label"],
        env_key=provider["env_key"],
        base_url=provider["base_url"],
        effort=spec.get("effort"),
        no_temperature_with_effort=spec.get("no_temperature_with_effort", False))


def env_keys(provider):
    """그 회사가 찾는 환경변수 이름들. 하나일 수도 여럿일 수도 있다."""
    key = PROVIDERS[provider]["env_key"]
    return (key,) if isinstance(key, str) else tuple(key)


def available():
    """고를 수 있는 모델. [{name, label, ready}]

    ready 는 그 회사 키가 지금 잡혀 있는가다. 키가 없는 것도 목록에서
    빼지 않고 그대로 두되 그렇다고 알린다 — 빼 버리면 왜 안 보이는지
    알 길이 없고, .env 를 고치면 되는 일이다.

    로컬 모델(Ollama)은 안 들어온다. MODELS 에 적는 것은 돈이 나가는
    쪽뿐이고 나머지 이름은 무엇이든 로컬로 간다(pick).

    ── 왜 화면이 아니라 여기서 만드나 ──
      키 이름이 회사마다 다르다는 것도, 어느 모델이 어느 회사인지도 이
      파일이 안다. 화면이 그것을 다시 알면 모델을 하나 더할 때 두 군데를
      고치게 된다.
    """
    return [
        {"name": name,
         "label": PROVIDERS[spec["provider"]]["label"],
         "ready": any(os.environ.get(k) for k in env_keys(spec["provider"]))}
        for name, spec in MODELS.items()
    ]
