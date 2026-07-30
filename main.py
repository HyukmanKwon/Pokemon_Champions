#실제로 모든 python 파일을 실행하고 유지하는 python 파일
from core.database import db
from core import my_pokemons
from core.stat_calculator import ask, build

FIELDS = ["ko_name", "sp_values", "ko_nature", "ability", "item", "moves"]
LABELS = {
    "ko_name": "이름",
    "sp_values": "SP (H A B C D S, 공백으로 구분)",
    "ko_nature": "성격",
    "ability": "특성",
    "item": "도구",
    "moves": "기술 (쉼표로 구분, 최대 4개)",
}


def _parse(field, text):
    if field == "sp_values":
        return tuple(map(int, text.split()))
    if field == "moves":
        return [m.strip() for m in text.split(",") if m.strip()]
    return text


def show_slots(specs):
    for i, spec in enumerate(specs, 1):
        print(f"{i}. {spec['ko_name']} ({spec['ability']}, {spec['item']})")


def edit_slot(conn, specs, index):
    """빈 입력은 기존 값 유지. build()로 검증하고 실패하면 이 슬롯만 되돌린다."""
    spec = specs[index]
    before = dict(spec)

    fields = {}
    for field in FIELDS:
        text = ask(f"{LABELS[field]} [{spec[field]}]: ")
        if text:
            fields[field] = _parse(field, text)
    if not fields:
        return

    my_pokemons.edit_spec(specs, index, **fields)
    try:
        build(conn, **specs[index])
    except ValueError as e:
        specs[index] = before
        print(f"입력 오류, 수정을 취소합니다: {e}")


def main():
    conn = db.connect()
    specs = my_pokemons.load_specs()
    try:
        while True:
            print()
            show_slots(specs)
            choice = ask("번호를 선택해 수정, v로 상세 보기, q로 종료: ")
            if choice == "q":
                break
            if choice == "v":
                print()
                my_pokemons.show_team(my_pokemons.build_team(conn, specs))
                continue
            if not choice.isdigit() or not (1 <= int(choice) <= len(specs)):
                print("1~6, v, q 중에서 입력하세요.")
                continue
            edit_slot(conn, specs, int(choice) - 1)
    finally:
        my_pokemons.save_specs(specs)
        conn.close()


if __name__ == "__main__":
    main()
