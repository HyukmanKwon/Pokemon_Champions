"""로컬 백엔드 — Ollama 의 /api/chat.

    ollama serve
    ollama pull qwen3.5:9b

── 왜 남겨 두나 ──
  인터넷이 끊기거나 API 키가 없어도 도우미가 돌아야 한다. 대회장에서
  회선이 나가는 것은 실제로 있는 일이고, 그때 도우미가 통째로 죽으면
  계산기까지 못 믿게 된다.

  3060 데스크톱과 M4 맥북 둘 다에서 같은 코드로 돈다 — Ollama 가 두 쪽
  모두 같은 HTTP 주소를 주므로 기기별 분기가 생기지 않는다.

── 모델 고르기 ──
  도구 호출을 지원하는 모델이어야 한다.

  ── 메모리부터 본다 ──
    MoE 의 "활성 3B" 는 속도 얘기지 메모리 얘기가 아니다. 가중치는 35B
    전부를 올려둬야 해서 4비트로도 20GB 가 넘고, 24GB 통합 메모리에서는
    스왑이 돌기 시작한다. 여기에 KV 캐시와 브라우저·DB 가 더 얹힌다.

    4비트 기준 대략:
      qwen3.5:9b       ~6GB   24GB 맥에서 편안
      qwen3.6:27b     ~16GB   다른 걸 다 끄면
      qwen3.6:35b-a3b ~20GB   24GB 에서는 무리

  ── 그래서 9b 가 기본 ──
    도구를 여러 번 이어 부르면 이 체급이 인자를 흘릴 때가 있다. 그때
    27b 로 올리되, 메모리가 남는지 먼저 본다. 한국어 답변만 보면 exaone
    계열이 자연스럽지만 도구 호출이 불안하다. 어차피 숫자와 이름은 도구가
    한국어로 만들어 주므로, 모델은 도구 선택 정확도로 고른다.

── 500 은 seed 를 바꿔 다시 물어본다 ──
  Ollama(0.32.6) 가 모델이 뱉은 도구 호출을 파싱하다 실패하는 일이 있다:

    {"error": "expected element type <function> but have <parameter>"}

  생각(thinking)은 멀쩡히 끝내놓고 마지막 XML 만 어긋난 것이라, 프롬프트로
  고칠 수 있는 게 아니다. 같은 질문으로 열 번에 네 번쯤 통한다.

  ── 그냥 다시 부르면 안 된다 ──
    seed 를 고정해 다섯 번 부르면 다섯 번 다 똑같이 나온다. 생성이 seed 에
    대해 결정적이고, seed 를 안 주면 Ollama 가 가까운 요청에 같은 값을 다시
    쓴다. 그래서 실패가 하나씩이 아니라 대여섯 개씩 뭉쳐서 온다 —
    재시도 세 번이 그 덩어리 안에 통째로 들어가 셋 다 같은 실패를 재현한다.

    부를 때마다 seed 를 새로 뽑으면 시도끼리 독립이 된다. 한 번에 6할이니
    네 번이면 97% 다.
"""

import json
import random

import requests

from .. import schemas
from ._base import Call, Usage

URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3.5:9b"

# 도구 호출 파싱 실패(500)를 몇 번까지 다시 물어볼지. 시도마다 seed 를 새로
# 뽑아 한 번에 6할이므로 네 번이면 97%. 그래도 안 되면 모델을 바꿀 문제다.
RETRIES = 4

# ── 생각(thinking)을 끈다 ──
#   qwen3.5 는 답하기 전에 생각을 길게 쓴다. 도구를 두 번 부르는 질문이면
#   그 생각이 세 번 나오고, 그게 시간의 대부분이다. 같은 질문을 재보면:
#
#     한 턴    생각 켬  97토큰 6.3초    생각 끔  14토큰 0.9초
#     전체     생각 켬     59초         생각 끔     22초
#
#   끄고도 도구 선택은 그대로였다 — 상성표를 물으면 type_matchup, 데미지를
#   물으면 calc_damage, 기술을 물으면 moves_of 를 부른다. 어느 도구를
#   부를지는 스키마의 설명이 정하는 것이지 모델의 독백이 정하는 게 아니다.
#   숫자와 이름도 도구가 만들어 주므로 생각할 거리가 애초에 적다.
#
#   더 어려운 질문에서 도구를 잘못 고르기 시작하면 이걸 True 로 되돌린다.
THINK = False

# ── 모델을 메모리에 얹어 둔다 ──
#   Ollama 기본은 5분이다. 그 뒤 처음 묻는 한 번이 유난히 느린데, 재보면
#   모델 로드 4.8초 + 프롬프트 3,689토큰 재계산 19.9초다. 두 번째부터는
#   프롬프트가 캐시에 맞아 0.2초로 떨어진다.
#
#   9b 4비트가 6GB 쯤 잡는다. 24GB 맥에서 30분 얹어 두는 건 감당되지만,
#   메모리가 아쉬우면 "5m" 로 되돌리면 된다.
KEEP_ALIVE = "30m"

# ── 컨텍스트를 왜 우리가 정하나 ──
#   Ollama 는 VRAM 을 보고 기본값을 정한다. M4 에서 4096 이 잡혔는데 그건
#   이 용도에 좁다. 시스템 프롬프트와 도구 스키마 16개만으로 2천 토큰쯤
#   먹고, 거기에 my_team 6마리나 채용률 응답이 들어오면 넘친다.
#
#   넘치면 앞부분부터 잘리는데 그게 하필 시스템 프롬프트다. "계산하지
#   마라" 가 사라진 채로 답이 나오고, 그 답은 그럴듯하게 틀린다.
#   서버 설정에 맡기지 않고 요청마다 필요한 만큼 적어 보낸다.
NUM_CTX = 16384


class Ollama:
    """로컬에 떠 있는 Ollama 하나."""

    label = "Ollama"

    def __init__(self, model=DEFAULT_MODEL, url=URL):
        self.model = model
        self.url = url
        # 이번 질문이 쓴 토큰. 로컬이라 돈은 안 나가지만 같은 자리에
        # 같은 모양으로 담는다 — 부르는 쪽이 백엔드를 가리지 않게.
        self.usage = Usage()

    def chat(self, messages, use_tools=True, timeout=None):
        """한 번 물어본다. 돌려주는 값은 message 하나.

        use_tools=False 면 도구 스키마를 빼고 보낸다. 도구를 못 부르니
        모델은 지금까지 받은 것으로 답을 쓸 수밖에 없다.

        500 이 오면 seed 를 바꿔 다시 물어본다. 서버가 죽은 게 아니라
        모델이 뱉은 도구 호출 XML 을 파싱하다 실패한 것이고, 다르게 뽑으면
        대개 통한다. 없는 모델을 부르면 404 라 여기 걸리지 않는다 —
        그건 그대로 올라간다.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": THINK,
            "keep_alive": KEEP_ALIVE,
            # 도구 인자를 지어내지 않게 낮게 둔다. 답변 문장의 다양성보다
            # "포켓몬 이름을 정확히 적는가" 가 훨씬 중요하다.
            "options": {"temperature": 0.2, "num_ctx": NUM_CTX},
        }
        if use_tools:
            payload["tools"] = schemas.as_array()

        for attempt in range(RETRIES):
            # seed 를 우리가 준다. 맡겨두면 재시도가 같은 값을 물려받아 같은
            # 실패를 그대로 재현한다. temperature 0.2 는 그대로 두고 뽑는
            # 자리만 옮기는 것이라, 인자 정확도에는 영향이 없다.
            payload["options"]["seed"] = random.randrange(2 ** 31)
            res = requests.post(self.url, json=payload,
                                timeout=max(timeout, 1.0) if timeout else 300)
            if res.status_code == 500 and attempt < RETRIES - 1:
                continue
            res.raise_for_status()
            body = res.json()
            # 저쪽 이름이 다르다. total 은 안 주므로 둘을 더해 쓴다 —
            # 로컬은 생각 토큰을 따로 세지 않는다.
            p_n = body.get("prompt_eval_count") or 0
            c_n = body.get("eval_count") or 0
            self.usage = self.usage.plus(p_n, c_n, p_n + c_n)
            return body["message"]

    def calls(self, msg):
        """assistant 메시지에서 도구 호출을 꺼낸다.

        Ollama 의 tool_call 에는 id 가 없다. 결과를 되돌릴 때 이름으로
        짝지으므로(tool_message 참고) 여기서도 id 를 만들지 않는다 —
        지어낸 id 는 어디에도 안 쓰이면서 있는 것처럼 보인다.
        """
        out = []
        for c in msg.get("tool_calls") or []:
            fn = c["function"]
            args = fn.get("arguments") or {}
            # 모델이 인자를 문자열로 줄 때가 있다. Ollama 는 보통 dict 로
            # 주지만 모델에 따라 갈린다.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            out.append(Call(id=None, name=fn["name"], args=args))
        return out

    def text(self, msg):
        return msg.get("content") or ""

    def tool_message(self, call, result):
        return {
            "role": "tool",
            # 어느 도구의 결과인지 붙여준다. 한 턴에 여러 도구를 부르면
            # 결과만으로는 짝을 못 맞춰서, 모델이 엉뚱한 것에 대고 답한다.
            "tool_name": call.name,
            "content": json.dumps(result, ensure_ascii=False, default=str),
        }

    def friendly_error(self, exc):
        if isinstance(exc, requests.ConnectionError):
            return "Ollama 에 연결하지 못했습니다. `ollama serve` 가 떠 있나요?"
        if isinstance(exc, requests.HTTPError):
            return (f"Ollama 오류: {exc}\n"
                    f"모델이 없다면 `ollama pull {self.model}` 을 먼저 하세요.")
        return None
