"""LLM 백엔드 — 어디에 물어볼지.

runner.ask 의 루프는 어느 백엔드를 쓰든 똑같다. 백엔드가 감추는 것은 다섯뿐이다.

    chat(messages, use_tools)   한 번 물어본다
    calls(msg)                  도구 호출을 Call 로 꺼낸다
    text(msg)                   답변 글자를 꺼낸다
    tool_message(call, result)  도구 결과를 그쪽 모양으로 싼다
    friendly_error(exc)         사람이 읽을 오류 한 줄 (모르면 None)

── 왜 한 모양으로 통일하지 않았나 ──
  도구 결과를 되돌리는 방법이 회사마다 다르다. 지금은 Ollama 하나뿐이라
  차이가 안 보이지만, 이름으로 짝짓는 쪽과 id 로 짝짓는 쪽이 있다. 한쪽
  모양으로 눌러 담으면 다른 쪽에서 짝이 어긋나는데, 그건 오류로 안 나오고
  "엉뚱한 도구 결과를 보고 쓴 답" 으로 나온다. 그래서 메시지 모양은
  백엔드가 끝까지 들고 있는다.

  대가가 하나 있다. history 는 그 대화를 시작한 백엔드의 모양이라, 대화
  도중에 모델을 바꾸면 짝이 맞지 않는다.
"""

from . import ollama
from ._base import Call

__all__ = ["Call", "DEFAULT_MODEL", "pick"]

DEFAULT_MODEL = ollama.DEFAULT_MODEL


def pick(model=None):
    """모델 이름 하나로 백엔드를 고른다."""
    return ollama.Ollama(model or DEFAULT_MODEL)
