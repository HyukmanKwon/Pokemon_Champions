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
  막히면 멈추고, 지금까지 받은 것으로 답하게 한다 — 여덟 번을 다 쓰면
  도구를 떼고 한 번 더 물어본다. 2분 걸려 모은 것을 버리지 않는다.

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

from ..usecases import naming
from . import schemas, tools

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3.5:9b"
MAX_TURNS = 8

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
#   이 용도에 좁다. 시스템 프롬프트와 도구 스키마 13개만으로 2천 토큰쯤
#   먹고, 거기에 my_team 6마리나 채용률 응답이 들어오면 넘친다.
#
#   넘치면 앞부분부터 잘리는데 그게 하필 시스템 프롬프트다. "계산하지
#   마라" 가 사라진 채로 답이 나오고, 그 답은 그럴듯하게 틀린다.
#   서버 설정에 맡기지 않고 요청마다 필요한 만큼 적어 보낸다.
NUM_CTX = 16384

SYSTEM = """You are a battle assistant for Pokémon Champions (Regulation M-B).

Rules you must follow:

1. Never compute numbers yourself. Damage, type-effectiveness multipliers,
   actual stats, offensive output, and bulk all come from the tools. If you do
   the multiplication in your head, you will get it wrong. The mainline formula
   uses 4096-based fixed-point arithmetic with its own peculiar rounding, so
   hand calculation flips a "guaranteed 2HKO" into a "roll-dependent 2HKO."

2. Do not rely on memory. Verify base stats, learnable moves, Abilities, and
   types with the tools. Champions uses different data from the mainline games
   in some places.

3. If a tool returns an error, report it to the user as-is. Do not fabricate to
   fill the gap. In particular, there is no data yet for usage-rate or metagame
   questions.

4. Regulation M-B rules: Level fixed at 50, IVs fixed at 31, SP instead of EVs
   (66 total, max 32 per stat), 21 Natures. If the user does not specify SP or
   Nature, calculate using the statistically most common sample.

5. Answer in Korean, briefly and decisively. Quote the tool's numbers verbatim
   and state in one line the conditions used for the calculation (Ability, held
   item, Nature, stat stages).

6. Copy names from tool results exactly as they appear in the ko_name field. Do
   not translate the English name field yourself. If ko_name is null, use the
   English name as-is and note that there is no Korean name yet.

7. Type names are the one exception: tool results carry no ko_name for them,
   only the English slug (fire, ground, psychic). Keep passing those slugs to
   the tools, but when writing to the user, spell every type name using the
   table below, which is read from the pokemon_type_names table in the
   database. Never translate a type any other way — psychic is "에스퍼", not
   "초능력", and dark is "악", not "어둠"."""


def system_prompt(session):
    """SYSTEM 에 타입 이름 열여덟 줄을 붙여 돌려준다.

    표를 프롬프트에 박아두지 않고 매번 DB 에서 읽는 이유는, 박아두면 그
    순간 pokemon_type_names 와 두 벌이 되기 때문이다. 표기가 바뀌면 한쪽만
    고치게 되고, 모델은 낡은 쪽을 읽는다.
    """
    listing = ", ".join(f"{en}={ko}"
                        for en, ko in sorted(
                            naming.type_names(session.conn).items()))
    return f"{SYSTEM}\n\nType names (pokemon_type_names, ko):\n{listing}"


# 한 바퀴를 다 썼을 때 마지막으로 넣는 말. 도구를 떼고 보내므로 모델은
# 지금까지 받은 것으로 답할 수밖에 없다. 무엇을 확인 못 했는지 밝히라고
# 시키는 이유는, 안 그러면 빈칸을 기억으로 메우기 때문이다.
LAST_CALL = ("The tool budget is used up and no more tool calls are available. "
             "Answer now in Korean using only the tool results already in this "
             "conversation. If something is still unverified, say which part "
             "you could not check rather than filling it in from memory.")


def chat(messages, model=DEFAULT_MODEL, url=OLLAMA_URL, use_tools=True,
         think=THINK):
    """Ollama 에 한 번 물어본다. 돌려주는 값은 message 하나.

    use_tools=False 면 도구 스키마를 빼고 보낸다. 도구를 못 부르니 모델은
    지금까지 받은 것으로 답을 쓸 수밖에 없다.

    500 이 오면 seed 를 바꿔 다시 물어본다. 서버가 죽은 게 아니라 모델이
    뱉은 도구 호출 XML 을 파싱하다 실패한 것이고, 다르게 뽑으면 대개 통한다.
    없는 모델을 부르면 404 라 여기 걸리지 않는다 — 그건 그대로 올라간다.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
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
        res = requests.post(url, timeout=300, json=payload)
        if res.status_code == 500 and attempt < RETRIES - 1:
            continue
        res.raise_for_status()
        return res.json()["message"]


def ask(question, session, model=DEFAULT_MODEL, history=None, on_tool=None):
    """질문 하나에 답한다. 돌려주는 값은 (답변, 갱신된 history).

    session 은 도구가 쓸 커넥션·참조표·덱이다(tools.Session). 부르는 쪽이
    만들어 넘긴다 — CLI 는 자기 커넥션으로, 웹은 요청마다 하나씩.

    on_tool(name, args, result) 를 주면 도구를 부를 때마다 불러준다.
    화면에 무엇을 물었는지 보여주려는 것 — 답만 나오면 그 숫자가 어디서
    왔는지 알 수 없다.
    """
    messages = list(history
                    or [{"role": "system", "content": system_prompt(session)}])
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
            result = tools.call(session, fn["name"], args)
            if on_tool:
                on_tool(fn["name"], args, result)
            messages.append({
                "role": "tool",
                # 어느 도구의 결과인지 붙여준다. 한 턴에 여러 도구를 부르면
                # 결과만으로는 짝을 못 맞춰서, 모델이 엉뚱한 것에 대고 답한다.
                "tool_name": fn["name"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    # 여기까지 왔으면 여덟 바퀴를 다 쓴 것이다. 도구를 떼고 한 번 더
    # 물어본다 — 그동안 모은 결과가 messages 에 그대로 있으므로, 그것만으로
    # 답이 나온다. 안내 문장을 돌려주고 끝내면 2분이 통째로 버려진다.
    messages.append({"role": "user", "content": LAST_CALL})
    msg = chat(messages, model, use_tools=False)
    messages.append(msg)

    answer = (msg.get("content") or "").strip()
    return answer or ("도구를 너무 여러 번 불러서 멈췄습니다. "
                      "질문을 좀 더 좁혀서 다시 물어봐 주세요."), messages
