"""로컬 LLM 도구 호출 루프 — Ollama 의 /api/chat 을 쓴다.

    ollama serve
    ollama pull qwen3.5:9b
    python -m scripts.chat

── 왜 Ollama 인가 ──
  3060 데스크톱과 M4 맥북 둘 다에서 같은 코드로 돌아야 한다. Ollama 는 두
  쪽 모두 같은 HTTP 주소를 주므로 기기별 분기가 생기지 않는다. 나중에
  llama.cpp 나 vLLM 으로 옮겨도 chat() 하나만 갈아끼우면 된다.

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

── 왜 루프인가 ──
  한 번 물어보고 끝이 아니다. "내 팀이 메가갸라도스를 버티나" 는 my_team
  으로 6마리를 받고, 그중 몇에 대해 calc_damage 를 부르고, 그 결과를 모아
  답한다. 모델이 도구를 그만 부를 때까지 돌린다.

── 한 바퀴 제한 ──
  MAX_TURNS 가 없으면 모델이 같은 도구를 무한히 부르는 일이 실제로 생긴다.
  막히면 멈추고, 지금까지 받은 것으로 답하게 한다.
"""

import json

import requests

from . import tools

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3.5:9b"
MAX_TURNS = 8

# ── 컨텍스트를 왜 우리가 정하나 ──
#   Ollama 는 VRAM 을 보고 기본값을 정한다. M4 에서 4096 이 잡혔는데 그건
#   이 용도에 좁다. 시스템 프롬프트와 도구 스키마 13개만으로 2천 토큰쯤
#   먹고, 거기에 my_team 6마리나 채용률 응답이 들어오면 넘친다.
#
#   넘치면 앞부분부터 잘리는데 그게 하필 시스템 프롬프트다. "계산하지
#   마라" 가 사라진 채로 답이 나오고, 그 답은 그럴듯하게 틀린다.
#   서버 설정에 맡기지 않고 요청마다 필요한 만큼 적어 보낸다.
NUM_CTX = 16384

SYSTEM = """너는 포켓몬 챔피언스(레귤레이션 M-B) 대전 도우미다.

지켜야 할 것:

1. 숫자는 절대 직접 계산하지 마라. 데미지·상성 배수·실능치·결정력·내구력은
   전부 도구가 낸다. 곱셈을 머릿속으로 하면 반드시 틀린다. 본가 공식은
   4096 고정소수점에 특유의 반올림을 쓰기 때문에, 손으로 계산하면 "확정 2타"
   가 "난수 2타" 로 뒤집힌다.

2. 기억에 의존하지 마라. 종족값·배우는 기술·특성·타입은 도구로 확인한다.
   포챔스는 본가와 다른 데이터를 쓰는 곳이 있다.

3. 도구가 error 를 돌려주면 그대로 사용자에게 알려라. 지어내서 메우지 마라.
   특히 채용률·메타 질문은 아직 데이터가 없다.

4. 레귤레이션 M-B 규칙: 레벨 50 고정, 개체값 31 고정, 노력치 대신 SP
   (총 66, 능력치당 최대 32), 성격 21종. 사용자가 SP·성격을 말하지 않으면
   무보정(SP 0 · 성실)으로 계산했다고 밝혀라.

5. 한국어로, 짧고 단정하게 답하라. 도구가 준 수치를 그대로 인용하고
   어떤 조건으로 계산했는지(특성·도구·성격·랭크) 한 줄로 밝혀라.

6. 도구 결과의 이름은 ko_name 필드를 글자 그대로 옮겨 적어라. 영문 name 을
   네가 번역하지 마라. ko_name 이 null 이면 영문을 그대로 쓰고 한국어 이름이
   아직 없다고 밝혀라."""


def chat(messages, model=DEFAULT_MODEL, url=OLLAMA_URL):
    """Ollama 에 한 번 물어본다. 돌려주는 값은 message 하나."""
    res = requests.post(url, timeout=300, json={
        "model": model,
        "messages": messages,
        "tools": tools.schemas(),
        "stream": False,
        # 도구 인자를 지어내지 않게 낮게 둔다. 답변 문장의 다양성보다
        # "포켓몬 이름을 정확히 적는가" 가 훨씬 중요하다.
        "options": {"temperature": 0.2, "num_ctx": NUM_CTX},
    })
    res.raise_for_status()
    return res.json()["message"]


def ask(question, model=DEFAULT_MODEL, history=None, on_tool=None):
    """질문 하나에 답한다. 돌려주는 값은 (답변, 갱신된 history).

    on_tool(name, args, result) 를 주면 도구를 부를 때마다 불러준다.
    화면에 무엇을 물었는지 보여주려는 것 — 답만 나오면 그 숫자가 어디서
    왔는지 알 수 없다.
    """
    messages = list(history or [{"role": "system", "content": SYSTEM}])
    messages.append({"role": "user", "content": question})

    for _ in range(MAX_TURNS):
        msg = chat(messages, model)
        messages.append(msg)

        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content", ""), messages

        for c in calls:
            fn = c["function"]
            args = fn.get("arguments") or {}
            # 모델이 인자를 문자열로 줄 때가 있다. Ollama 는 보통 dict 로
            # 주지만 모델에 따라 갈린다.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = tools.call(fn["name"], args)
            if on_tool:
                on_tool(fn["name"], args, result)
            messages.append({
                "role": "tool",
                # 어느 도구의 결과인지 붙여준다. 한 턴에 여러 도구를 부르면
                # 결과만으로는 짝을 못 맞춰서, 모델이 엉뚱한 것에 대고 답한다.
                "tool_name": fn["name"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return ("도구를 너무 여러 번 불러서 멈췄습니다. "
            "질문을 좀 더 좁혀서 다시 물어봐 주세요."), messages
