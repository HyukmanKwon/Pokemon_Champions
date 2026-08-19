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

── 한 바퀴 제한 ──
  MAX_TURNS 가 없으면 모델이 같은 도구를 무한히 부르는 일이 실제로 생긴다.
  막히면 멈추고, 지금까지 받은 것으로 답하게 한다 — 여덟 번을 다 쓰면
  도구를 떼고 한 번 더 물어본다. 그동안 모은 것을 버리지 않는다.
"""

from . import tools
from .backends import DEFAULT_MODEL, pick          # noqa: F401 - 밖에서 쓴다
from ..usecases import naming

MAX_TURNS = 8

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


def ask(question, session, model=None, history=None, on_tool=None):
    """질문 하나에 답한다. 돌려주는 값은 (답변, 갱신된 history).

    session 은 도구가 쓸 커넥션·참조표·덱이다(tools.Session). 부르는 쪽이
    만들어 넘긴다 — CLI 는 자기 커넥션으로, 웹은 요청마다 하나씩.

    on_tool(name, args, result) 를 주면 도구를 부를 때마다 불러준다.
    화면에 무엇을 물었는지 보여주려는 것 — 답만 나오면 그 숫자가 어디서
    왔는지 알 수 없다.

    history 는 그 대화를 시작한 백엔드의 메시지 모양이다. 도중에 모델을
    바꾸면 짝이 안 맞는다 (backends/__init__.py 참고).
    """
    llm = pick(model)
    messages = list(history
                    or [{"role": "system", "content": system_prompt(session)}])
    messages.append({"role": "user", "content": question})

    for _ in range(MAX_TURNS):
        msg = llm.chat(messages)
        messages.append(msg)

        calls = llm.calls(msg)
        if not calls:
            return llm.text(msg), messages

        for c in calls:
            result = tools.call(session, c.name, c.args)
            if on_tool:
                on_tool(c.name, c.args, result)
            messages.append(llm.tool_message(c, result))

    # 여기까지 왔으면 여덟 바퀴를 다 쓴 것이다. 도구를 떼고 한 번 더
    # 물어본다 — 그동안 모은 결과가 messages 에 그대로 있으므로, 그것만으로
    # 답이 나온다. 안내 문장을 돌려주고 끝내면 그 시간이 통째로 버려진다.
    messages.append({"role": "user", "content": LAST_CALL})
    msg = llm.chat(messages, use_tools=False)
    messages.append(msg)

    answer = llm.text(msg).strip()
    return answer or ("도구를 너무 여러 번 불러서 멈췄습니다. "
                      "질문을 좀 더 좁혀서 다시 물어봐 주세요."), messages


def explain_error(exc, model=None):
    """예외 하나를 사람이 읽을 한 줄로. 모르면 타입 이름을 그대로 준다.

    부르는 쪽(CLI · 웹)이 백엔드마다 다른 예외를 따로 잡지 않게 하려는
    것이다. 예전에는 app.py 와 chat.py 가 각자 requests 예외를 잡아
    "Ollama 가 떠 있나요" 를 적었는데, 회사가 늘면 그 자리가 둘 다 늘어난다.
    """
    said = pick(model).friendly_error(exc)
    return said or f"{type(exc).__name__}: {exc}"
