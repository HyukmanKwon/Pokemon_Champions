"""로컬 LLM 도우미와 대화한다.

    ollama serve                       (한 번만, 따로 띄워둔다)
    ollama pull qwen3.5:9b

    python -m scripts.chat                          대화 모드
    python -m scripts.chat "메가갸라도스 지진이 한카리아스를 몇 방에 보내?"
    python -m scripts.chat --model qwen3.6:27b --tools  도구 호출을 같이 보기

── 왜 웹이 아니라 CLI 부터인가 ──
  도구를 제대로 고르는지, 숫자를 지어내지 않는지를 먼저 봐야 한다. 화면을
  먼저 만들면 모델이 틀린 답을 예쁘게 감싸서 내놓는 것만 확인하게 된다.
  --tools 로 무엇을 어떤 인자로 불렀는지 눈으로 보면서 프롬프트를 조인다.
"""

import argparse
import contextlib
import itertools
import sys
import threading
import time

from pokemon_champions.db import connection
from pokemon_champions.agent import runner, tools


@contextlib.contextmanager
def waiting():
    """기다리는 동안 초를 세어 보여준다.

    ── 왜 필요한가 ──
      Ollama 응답을 통째로 받은 뒤에 찍으므로 그 사이 화면이 비어 있다.
      1분이 걸리면 멈춘 건지 도는 건지 알 수가 없다. 스트리밍을 붙이기
      전까지의 임시방편이다 — 실제 시간은 그대로지만 몇 초짜리인지는
      알 수 있다.
    """
    stop = threading.Event()

    def tick():
        start = time.monotonic()
        for ch in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if stop.wait(0.1):
                break
            print(f"\r  \033[90m{ch} {time.monotonic() - start:.0f}초\033[0m",
                  end="", flush=True)
        print("\r" + " " * 20 + "\r", end="", flush=True)

    t = threading.Thread(target=tick, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=1)


def show_tool(name, args, result):
    brief = str(result)
    if len(brief) > 160:
        brief = brief[:160] + " …"
    print(f"  \033[90m→ {name}({args})\033[0m")
    print(f"  \033[90m  {brief}\033[0m")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("question", nargs="*", help="한 번만 묻고 끝낼 질문")
    ap.add_argument("--model", default=runner.DEFAULT_MODEL)
    ap.add_argument("--tools", action="store_true",
                    help="어떤 도구를 어떤 인자로 불렀는지 같이 보여준다")
    args = ap.parse_args()

    on_tool = show_tool if args.tools else None
    history = None
    # 커넥션은 진입점에서 연다. CLI 는 한 사람이 한 줄씩 묻는 곳이라
    # 하나면 충분하고, with 를 벗어나면 반드시 닫힌다.
    conn_box = connection()
    conn = conn_box.__enter__()
    sess = tools.session(conn)

    def once(q):
        nonlocal history
        started = time.monotonic()
        try:
            with waiting():
                answer, history = runner.ask(
                    q, sess, args.model, history, on_tool)
        # 무엇이 잘못됐는지는 백엔드가 안다. 여기서 회사별 예외를 잡으면
        # 백엔드를 하나 더할 때마다 이 자리가 같이 늘어난다.
        except Exception as e:      # noqa: BLE001
            print(runner.explain_error(e, args.model))
            return 1
        print(answer)
        # 몇 초 걸렸는지 남긴다. 도구를 고칠 때마다 나아졌는지 눈으로 본다.
        print(f"\033[90m({time.monotonic() - started:.1f}초)\033[0m")
        return 0

    try:
        if args.question:
            return once(" ".join(args.question))

        print(f"모델: {args.model} · 도구 {len(tools.HANDLERS)}개 · 빈 줄이면 종료")
        while True:
            try:
                q = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not q:
                return 0
            print()
            once(q)
    finally:
        conn_box.__exit__(None, None, None)


if __name__ == "__main__":
    sys.exit(main())
