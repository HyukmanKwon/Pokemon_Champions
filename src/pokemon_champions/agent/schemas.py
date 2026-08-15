"""도구 스키마 — 모델에게 주는 설명.

── 왜 tools.py 와 나눴나 ──
  이 파일에는 실행되는 코드가 없다. 전부 모델이 읽을 글이다. 계산을
  고치는 일과 "언제 이 도구를 부르는가" 를 고치는 일은 성격이 다른 작업인데,
  한 파일에 있으면 프롬프트 한 줄을 만지려고 데미지 계산을 스크롤해야 한다.

── 스키마를 손으로 적는 이유 ──
  파이썬 시그니처에서 자동 생성할 수도 있지만, 도구 설명은 모델에게 주는
  프롬프트다. "언제 이걸 부르는가" 를 사람이 써야 한다. 자동 생성하면
  타입만 맞고 판단 근거가 빠져서, 모델이 엉뚱한 도구를 고른다.

── 인자를 적게 ──
  포켓몬 하나를 세우는 데 필요한 것은 이름·SP·성격·특성·도구 다섯이지만,
  대부분의 질문은 "메가갸라도스가 한카리아스를 몇 방에" 처럼 이름 둘과
  기술 하나뿐이다. 나머지는 기본값(SP 0 · 성실 · 첫 특성 · 도구 없음)으로
  두고, 모델이 말한 것만 채우게 한다.

── 영어로 적는다 ──
  모델은 Garchomp · Earthquake · Focus Sash 를 한카리아스 · 지진 ·
  기합의띠 보다 훨씬 잘 안다. 다만 한국어 예시는 남긴다 — 그건 설명이
  아니라 "한국어를 그대로 넘겨도 걸린다" 는 증거다.

  이름과 값을 어떻게 주고받는지, 실패를 왜 값으로 돌려주는지는
  tools.py 첫머리에 적혀 있다.
"""

# 이름 인자는 전부 양방향이다. 모델이 한국어 질문을 그대로 옮겨 적기도
# 하고 영문으로 바꿔 주기도 하는데, 둘 중 하나만 받으면 나머지 절반이
# "그런 포켓몬은 없습니다" 가 된다.
_NAME_DESC = ("Korean name or English slug. "
              "Both 한카리아스 and garchomp work")
_MOVE_DESC = ("Korean name or English slug. "
              "Both 지진 and earthquake work")

_SIDE = {
    "type": "object",
    "description": "A single Pokemon. Only name is required; the rest fall "
                   "back to defaults (SP 0 · Serious nature · first ability "
                   "· no item).",
    "properties": {
        "name": {"type": "string",
                 "description": f"{_NAME_DESC}. Mega forms work too"},
        "ability": {"type": "string", "description":
                    "Ability name. Both 까칠한피부 and rough-skin work"},
        "item": {"type": "string", "description":
                 "Item name. Both 기합의띠 and focus-sash work"},
        "nature": {"type": "string", "description":
                   "Nature name. Both 고집 and adamant work. "
                   "Defaults to Serious"},
        "sp": {"type": "array", "items": {"type": "integer"},
               "description": "6 values in hp, atk, def, spa, spd, spe order. "
                              "66 total"},
        "rank": {"type": "object",
                 "description": 'Stat stage changes. e.g. {"a": 2} is +2 Atk'},
        "condition": {"type": "string", "description":
                      "Status condition: burn, poison, toxic, paralysis, "
                      "sleep, freeze. Burn halves physical attack; burn, "
                      "poison and toxic also chip HP at the end of "
                      "every turn"},
    },
    "required": ["name"],
}

_STR = {"type": "string"}

# 덱은 이름으로만 부를 수 있다. id 를 열어두면 모델이 짐작해서 고르고,
# 사용자가 보고 있는 것과 다른 덱을 답하게 된다.
_DECK_DESC = ("Deck name, exactly as the user wrote it. Omit this to use the "
              "deck the user currently has open — that is almost always what "
              "'my team' means. Call list_decks first if you need the names.")

# {도구 이름: 스키마}. 실행할 함수는 tools.HANDLERS 에 같은 열쇠로 있고,
# 두 열쇠 집합이 어긋나면 tools.py 가 import 할 때 잡는다.
TOOLS = {
    "find_pokemon": {
        "description": "Base stats, types, abilities and mega relations of a "
                       "single Pokemon. Call this first whenever the user "
                       "asks about a specific Pokemon.",
        "properties": {"name": {**_STR, "description": _NAME_DESC}},
        "required": ["name"]},

    "search_pokemon": {
        "description": "Narrow down Pokemon by criteria. Use this when "
                       "looking for candidates rather than one Pokemon, "
                       "e.g. 'fast Fire types'.",
        "properties": {
            "type": {**_STR, "description":
                     "English type. fire, water, dragon …"},
            "min_total": {"type": "integer",
                          "description": "Minimum base stat total"},
            "order_by": {**_STR, "description":
                         "Sort key. hp/atk/def/spa/spd/spe/bst"},
            "limit": {"type": "integer",
                      "description": "Max results. Defaults to 8"}},
        "required": []},

    "type_matchup": {
        "description": "How much damage that Pokemon takes from each of the "
                       "18 types, all at once. 'What is it weak to?', 'What "
                       "should I hit it with?', 'What does it wall?' are all "
                       "answered by this one tool. Do not call "
                       "type_effectiveness once per type — types you never "
                       "checked stay blank, and filling those blanks from "
                       "memory produces wrong answers.",
        "properties": {"pokemon": {**_STR, "description": _NAME_DESC}},
        "required": ["pokemon"]},

    "type_effectiveness": {
        "description": "How much damage one attacking type deals to that "
                       "Pokemon. Use only when the attacking type is already "
                       "decided. If you are still looking for what works, "
                       "call type_matchup.",
        "properties": {
            "attack_type": {**_STR, "description":
                            "English type. fire, ground …"},
            "defender": {**_STR, "description":
                         f"The defending Pokemon. {_NAME_DESC}"}},
        "required": ["attack_type", "defender"]},

    "find_move": {
        "description": "Power, type, category and effect of a single move.",
        "properties": {"name": {**_STR, "description": _MOVE_DESC}},
        "required": ["name"]},

    "moves_of": {
        "description": "Moves that Pokemon can learn, ordered by power. "
                       "Never guess whether it learns a move — check here. "
                       "One Pokemon can learn over sixty moves, so prefer "
                       "narrowing with type, category or min_power.",
        "properties": {
            "pokemon": {**_STR, "description": _NAME_DESC},
            "type": {**_STR, "description":
                     "Filter by English type. fire, ground …"},
            "category": {**_STR, "description":
                         "Filter by one of physical / special / status"},
            "min_power": {"type": "integer",
                          "description": "Only moves at or above this power"},
            "limit": {"type": "integer",
                      "description": "Max results. Defaults to 40"}},
        "required": ["pokemon"]},

    "find_ability": {
        "description": "The effect of a single ability and the Pokemon "
                       "that have it.",
        "properties": {"name": {**_STR, "description":
                                "Ability name. Both 까칠한피부 and "
                                "rough-skin work"}},
        "required": ["name"]},

    "find_item": {
        "description": "The effect and category of a single item.",
        "properties": {"name": {**_STR, "description":
                                "Item name. Both 기합의띠 and "
                                "focus-sash work"}},
        "required": ["name"]},

    "calc_damage": {
        "description": "Damage rolls and guaranteed-KO analysis. Every "
                       "'how many hits to KO', 'does it survive', 'is it a "
                       "OHKO' question goes through this. Do not multiply it "
                       "out yourself — the official formula rounds in "
                       "unusual places, and hand calculation flips "
                       "guaranteed vs. rolled KO verdicts. It also settles "
                       "end-of-turn HP: status chip, sandstorm and Leftovers. "
                       "Never add those up yourself either — toxic grows by "
                       "n/16 each turn and Leftovers is capped at full HP, so "
                       "the verdict is not damage times N.",
        "properties": {
            "attacker": _SIDE, "defender": _SIDE,
            "move": {**_STR, "description": _MOVE_DESC},
            "weather": {**_STR, "description":
                        "One of sun, rain, sandstorm, snow"},
            "terrain": {**_STR, "description":
                        "One of electric, grassy, misty, psychic"},
            "is_critical": {"type": "boolean",
                            "description": "Whether the hit is a critical"},
            "is_doubles": {"type": "boolean",
                           "description": "Whether this is a double battle"},
            "toxic_turn": {"type": "integer", "description":
                           "How many turns the defender has already been "
                           "badly poisoned. Defaults to 1 (just applied). "
                           "Only matters when the defender's condition "
                           "is toxic"}},
        "required": ["attacker", "defender", "move"]},

    "power_index": {
        "description": "Offensive power index. Ranks one Pokemon's moves by "
                       "output. Use it for 'which move hits hardest?' when "
                       "no specific target is given.",
        "properties": {
            "pokemon": _SIDE,
            "moves": {"type": "array", "items": _STR,
                      "description": f"Move names. {_MOVE_DESC}"}},
        "required": ["pokemon", "moves"]},

    "bulk_index": {
        "description": "Bulk index. HP × Def and HP × SpD. Use it to "
                       "compare how sturdy Pokemon are against each other.",
        "properties": {"pokemon": _SIDE},
        "required": ["pokemon"]},

    "my_team": {
        "description": "The specs and computed stats of the six Pokemon in "
                       "the user's deck. Call this first whenever 'my team', "
                       "'my entry' or 'my deck' comes up. Defaults to the "
                       "deck the user is currently looking at.",
        "properties": {"deck": {**_STR, "description": _DECK_DESC}},
        "required": []},

    "list_decks": {
        "description": "The user's saved decks and which one is currently "
                       "open. Use it when the user asks what decks they have, "
                       "or before answering about a deck you cannot name.",
        "properties": {}, "required": []},

    "team_weaknesses": {
        "description": "Type matchup table for all six Pokemon in the deck. "
                       "Computes how many members are weak to each type. "
                       "When asked about the deck's weaknesses, call this "
                       "instead of recalling the type chart from memory.",
        "properties": {"deck": {**_STR, "description": _DECK_DESC}},
        "required": []},

    "usage_stats": {
        "description": "Ranked battle usage stats. What moves, items, "
                       "abilities, natures and SP spreads that Pokemon "
                       "actually shows up with, and who it is paired with. "
                       "Use it for 'what is it running lately?', 'the "
                       "popular spread', 'what item does it hold?'. Do not "
                       "answer from memory — the metagame shifts daily and "
                       "these numbers come from in-game battle data.",
        "properties": {
            "pokemon": {**_STR, "description": _NAME_DESC},
            "format": {**_STR, "description":
                       "Singles or Doubles. Defaults to Singles"}},
        "required": ["pokemon"]},
}


def as_array():
    """Ollama·OpenAI 형식의 tools 배열."""
    return [{"type": "function",
             "function": {"name": name,
                          "description": spec["description"],
                          "parameters": {"type": "object",
                                         "properties": spec["properties"],
                                         "required": spec["required"]}}}
            for name, spec in TOOLS.items()]
