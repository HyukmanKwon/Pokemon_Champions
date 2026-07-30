"""CLI 진입점. `python main.py`

로직은 없다. 진입점은 "어떤 인터페이스를 띄울지"만 정하고, 실제 화면은
src/pokemon_champions/interfaces/cli.py 에 있다. 이렇게 두면 나중에
`pokemon-cli` 명령으로 설치하든 여기서 실행하든 같은 코드가 돈다.
"""

from pokemon_champions.interfaces.cli import main

if __name__ == "__main__":
    main()
