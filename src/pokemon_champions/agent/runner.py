"""도구 호출 루프 — 물어보고, 도구를 부르고, 다시 물어본다.

    python -m scripts.chat "메가갸라도스 지진이 한카리아스를 몇 방에 보내?"

── 여기에 없는 것 ──
  어느 회사에 어떻게 물어보는지는 여기 없다. backends/ 가 그것만 한다.
  이 파일은 "언제 그만 물어보나" 와 "무엇을 시키나" 만 안다. 둘을 한
  파일에 두면 회사를 바꿔 재 볼 때마다 루프까지 같이 손대게 된다.

── 왜 루프인가 ──
  한 번 물어보고 끝이 아니다. "내 팀이 메가갸라도스를 버티나" 는 my_team
  으로 6마리를 받고, 그중 몇에 대해 calc_damage 를 부르고, 그 결과를 모아
  답한다. 모델이 도구를 그만 부를 때까지 돌린다.

── 두 가지 제한 ──
  MAX_TURNS   같은 도구를 무한히 부르는 것을 막는다
  TIME_BUDGET 오래 걸리는 것을 막는다

  둘 다 걸리면 도구를 떼고 한 번 더 물어본다. 그동안 모은 것을 버리지
  않는다 — 안내 문장만 돌려주고 끝내면 그 시간이 통째로 버려진다.

  바퀴 수만으로는 모자랐다. 대화가 길어지면 한 요청이 통째로 느려져서,
  여덟 바퀴를 안 채우고도 90초가 넘는다. 사람이 기다릴 수 있는 것은
  시간이지 바퀴가 아니다.
"""

import time

from . import tools
from .backends import DEFAULT_MODEL, pick          # noqa: F401 - 밖에서 쓴다
from ..usecases import naming

MAX_TURNS = 8

# 한 질문에 쓰는 전체 시간. 넘기면 도구를 그만 부르고 지금까지 받은
# 것으로 답한다.
#
# ── 새 바퀴만 막아서는 안 됐다 ──
#   처음에는 바퀴를 시작할지만 봤는데 41초가 나왔다. 대화가 길어지면
#   프롬프트가 수만 토큰이 되어 한 요청이 십수 초씩 걸리는데, 이미
#   시작한 요청도 마지막 한 번도 그 검사에 안 걸린다.
#
#   그래서 요청마다 남은 시간을 시한으로 준다. 저쪽이 늦으면 그 자리에서
#   끊고 다음으로 넘어간다.
TIME_BUDGET = 25.0

# 마지막 한 번에 남겨 두는 몫. 도구를 아무리 많이 불렀어도 답은 내야
# 한다 — 여기까지 다 써 버리면 그때까지 모은 도구 결과가 통째로 버려진다.
FINAL_RESERVE = 10.0

# history 에 온전히 남길 도구 결과의 개수.
#
# ── 왜 줄이나 ──
#   도구 결과 하나가 200~1,200 토큰인데 그대로 쌓인다. 네 턴을 주고받으면
#   프롬프트가 9천에서 2만 7천이 되고, 그러면 한 요청이 십수 초가 되어
#   시한 안에 도구를 한 번도 못 부르는 일이 생긴다. 실제로 겪었다.
#
#   글로 된 답과 질문은 그대로 둔다. 부피는 도구 결과가 만들고, 그건
#   그 턴이 지나면 대개 답 안에 이미 녹아 있다.
#
#   지운 자리에 짧은 쪽지를 남긴다. 통째로 빼면 tool_call_id 의 짝이
#   어긋나서, 오류가 아니라 "엉뚱한 도구 결과를 보고 쓴 답" 이 된다.
KEEP_TOOL_RESULTS = 6

STALE_TOOL = ("(앞 턴의 도구 결과입니다. 길어서 접었습니다. "
              "이 값이 다시 필요하면 그 도구를 다시 부르세요.)")


def compact(messages):
    """오래된 도구 결과를 쪽지로 바꾼 새 목록. 원본은 안 건드린다.

    최근 KEEP_TOOL_RESULTS 개만 온전히 남긴다. 순서를 지키려고 뒤에서부터
    세되, 돌려줄 때는 원래 차례 그대로다.
    """
    kept = 0
    out = []
    for m in reversed(messages):
        if m.get("role") == "tool" and m.get("content"):
            kept += 1
            if kept > KEEP_TOOL_RESULTS:
                m = {**m, "content": STALE_TOOL}
        out.append(m)
    out.reverse()
    return out

SYSTEM = """You are a battle assistant for Pokémon Champions (Regulation M-B).

Rules you must follow:

1. Never compute numbers yourself. Damage, type-effectiveness multipliers,
   actual stats, offensive output, and bulk all come from the tools. If you do
   the multiplication in your head, you will get it wrong. The mainline formula
   uses 4096-based fixed-point arithmetic with its own peculiar rounding, so
   hand calculation flips a "guaranteed 2HKO" into a "roll-dependent 2HKO."
   This includes end-of-turn HP. Status chip, sandstorm and Leftovers are
   already folded into calc_damage's verdict — never add or subtract them
   yourself. When calc_damage returns a "residual" field, the verdict counts
   turns (턴), not hits (타): the target goes down without the last attack.
   Say so, and quote the residual lines as the reason.

2. Do not rely on memory. Verify base stats, learnable moves, Abilities, and
   types with the tools. Champions uses different data from the mainline games
   in some places.

3. If a tool returns an error, report it to the user as-is. Do not fabricate to
   fill the gap. In particular, there is no data yet for usage-rate or metagame
   questions.

4. Regulation M-B rules: Level fixed at 50, IVs fixed at 31, SP instead of EVs
   (66 total, max 32 per stat), 21 Natures. If the user does not specify SP or
   Nature, calculate using the statistically most common sample.

5. Answer in Korean, briefly and decisively. Lead with the answer itself in
   one sentence. Then, only if the question was a calculation, add ONE short
   line naming the conditions used (Ability, held item, Nature, stat stages).
   Quote the tool's numbers verbatim.

   Keep it to three lines or fewer. Do not restate the question, do not lay
   the tool result out as a bullet list, do not explain what you are about to
   do, and do not add caveats nobody asked for. If the user wants the full
   spread they will ask. A wall of bullets buries the one number they came
   for.

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
             "conversation. Keep it to three lines. If something is still "
             "unverified, say which part you could not check in one short "
             "clause rather than filling it in from memory.")


def ask(question, session, model=None, history=None, on_tool=None):
    """질문 하나에 답한다. 돌려주는 값은 (답변, 갱신된 history, 쓴 토큰).

    session 은 도구가 쓸 커넥션·참조표·덱이다(tools.Session). 부르는 쪽이
    만들어 넘긴다 — CLI 는 자기 커넥션으로, 웹은 요청마다 하나씩.

    on_tool(name, args, result) 를 주면 도구를 부를 때마다 불러준다.
    화면에 무엇을 물었는지 보여주려는 것 — 답만 나오면 그 숫자가 어디서
    왔는지 알 수 없다.

    history 는 그 대화를 시작한 백엔드의 메시지 모양이다. 도중에 모델을
    바꾸면 짝이 안 맞는다 (backends/__init__.py 참고).

    ── 토큰은 왜 백엔드가 세나 ──
      요청마다 저쪽이 돌려주는 값이고 그 이름이 회사마다 다르다. 여기서
      세려면 runner 가 응답 원본을 알아야 하는데, 그러면 백엔드가 감추는
      것이 하나 늘어난다. pick 이 질문마다 새 백엔드를 만들므로 그 위에
      쌓인 값이 곧 이번 질문이 쓴 양이다.
    """
    llm = pick(model)
    messages = list(history
                    or [{"role": "system", "content": system_prompt(session)}])
    messages.append({"role": "user", "content": question})

    deadline = time.monotonic() + TIME_BUDGET
    for _ in range(MAX_TURNS):
        # 새 바퀴를 시작할 시간이 남았나. 마지막 한 번 몫은 빼고 본다.
        # 첫 바퀴는 언제나 통과한다 — 아무것도 안 물어보고 끝낼 수는 없다.
        left = deadline - time.monotonic() - FINAL_RESERVE
        if left <= 0:
            break

        try:
            msg = llm.chat(compact(messages), timeout=left)
        except Exception:       # noqa: BLE001 - 늦은 것도 못 받은 것도 같다
            # 한 요청이 시한을 넘겼다. 지금까지 모은 것으로 답하러 간다 —
            # 여기서 올리면 도구를 다섯 번 부른 값이 통째로 사라진다.
            break
        messages.append(msg)

        calls = llm.calls(msg)
        if not calls:
            return llm.text(msg), messages, llm.usage

        for c in calls:
            result = tools.call(session, c.name, c.args)
            if on_tool:
                on_tool(c.name, c.args, result)
            messages.append(llm.tool_message(c, result))

    # 여기까지 왔으면 바퀴나 시간을 다 쓴 것이다. 도구를 떼고 한 번 더
    # 물어본다 — 그동안 모은 결과가 messages 에 그대로 있으므로, 그것만으로
    # 답이 나온다. 안내 문장을 돌려주고 끝내면 그 시간이 통째로 버려진다.
    messages.append({"role": "user", "content": LAST_CALL})
    try:
        msg = llm.chat(compact(messages), use_tools=False,
                       timeout=FINAL_RESERVE)
    except Exception:       # noqa: BLE001 - 늦은 것도 못 받은 것도 같다
        # 마지막 한 번까지 늦었다. 여기서 예외를 올리면 화면에는 빨간
        # 오류만 남고, 그때까지 부른 도구 값이 통째로 사라진다. 무엇이
        # 일어났는지 말해 주는 편이 낫다.
        return ("시간 안에 답을 못 만들었습니다. 질문을 좀 더 좁혀서 "
                "다시 물어봐 주세요.", messages, llm.usage)
    messages.append(msg)

    answer = llm.text(msg).strip()
    return (answer or "도구를 너무 여러 번 불러서 멈췄습니다. "
                      "질문을 좀 더 좁혀서 다시 물어봐 주세요.",
            messages, llm.usage)


def explain_error(exc, model=None):
    """예외 하나를 사람이 읽을 한 줄로. 모르면 타입 이름을 그대로 준다.

    부르는 쪽(CLI · 웹)이 백엔드마다 다른 예외를 따로 잡지 않게 하려는
    것이다. 예전에는 app.py 와 chat.py 가 각자 requests 예외를 잡아
    "Ollama 가 떠 있나요" 를 적었는데, 회사가 늘면 그 자리가 둘 다 늘어난다.
    """
    said = pick(model).friendly_error(exc)
    return said or f"{type(exc).__name__}: {exc}"
