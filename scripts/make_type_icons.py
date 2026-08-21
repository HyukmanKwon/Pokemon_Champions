"""타입 배지를 한국어로 다시 그린다.

    python -m scripts.make_type_icons
    python -m scripts.make_type_icons --force      이미 있어도 다시 그린다

── 왜 받지 않고 그리는가 ──
  PokeAPI sprites 저장소의 타입 배지는 영문뿐이다(FIRE · WATER). 한국어
  배지는 어디서도 받을 수 없다. 그렇다고 글자만 바꾼 그림을 새로 만들면
  본가와 모양이 달라져서 화면에서 혼자 튄다.

  그래서 받아둔 영문 배지에서 **왼쪽 심볼만 떼어내** 쓴다. 알약 모양과
  색과 심볼은 본가 그대로이고, 오른쪽 글자만 한국어로 다시 얹는다.

      data/images/types_en/fire.png   내려받은 원본 (FIRE)
      data/images/types/fire.png      여기서 만든 것 (불꽃)

  화면과 API 는 아래쪽만 본다. 원본은 재료라서 따로 둔다 — 한 폴더에
  두면 다시 그릴 때 자기가 만든 것을 원본으로 삼아 글자가 겹친다.

── 한국어 표기는 DB 에서 읽는다 ──
  pokemon_type_names 가 유일한 출처다. 여기 열여덟 줄을 적어두면 표기를
  다듬을 때 한쪽만 고치게 되고, 화면의 글자와 그림 속 글자가 갈린다.

── 다시 그려도 되는 파일이다 ──
  data/images/ 는 .gitignore 에 있다. 이 스크립트가 결정적이므로 지워도
  같은 그림이 다시 나온다 — data/sql/ 을 build.py 가 다시 만드는 것과
  같은 성격이다.
"""

import argparse
import sys

from PIL import Image, ImageDraw, ImageFont

from pokemon_champions import assets
from pokemon_champions.db import connection
from pokemon_champions.db.repositories import rules_repo

# ── 배치 ──
# 원본이 200×40 이고, 왼쪽 심볼이 x 16~44 에 있다. 그 오른쪽을 글자 자리로
# 쓴다. 원본 크기가 바뀌면 여기도 같이 봐야 한다.
ICON_RIGHT = 50          # 이 왼쪽까지가 심볼. 여기부터 글자 자리
TEXT_PAD_RIGHT = 16      # 오른쪽 여백. 알약 끝에 글자가 붙지 않게

# 내보낼 알약 너비. 원본 200 에서 30% 줄인 값이다.
#
# ── 왜 CSS 로 안 줄이나 ──
#   화면에서 폭만 줄이면 그림이 눌려 찌그러지고, 비율을 지켜 줄이면
#   글자까지 같이 작아져 못 읽는다. 원본은 알약이 200×40 을 꽉 채워
#   잘라낼 여백도 없다.
#
#   대신 알약의 곧은 가운데를 잘라낸다. 심볼도 글자도 원래 크기 그대로고
#   줄어드는 것은 빈 알약뿐이다. 본가 배지는 영문 세 낱말(FIGHTING)까지
#   담으려고 긴 것이라, 두세 자짜리 한국어에는 그 폭이 남는다.
PLATE_WIDTH = 140

# 글자는 두 자(불꽃)에서 세 자(에스퍼)까지다. 세 자가 넘치지 않는 크기로
# 잡고, 그래도 넘치면 아래 fit_font 가 한 단계씩 줄인다.
FONT_SIZE = 21
MIN_FONT_SIZE = 13

# 굵은 고딕. 앞에 있는 것부터 찾아 쓴다. 리눅스·맥 순.
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/AppleSDGothicNeo.ttc",
]

# 원본에서 심볼을 떼어낼 때의 기준. 알약은 진한 색이고 심볼만 흰색이라
# "충분히 밝고 충분히 불투명한" 픽셀을 심볼로 본다.
WHITE_MIN = 210
ALPHA_MIN = 80


def find_font(size):
    """굵은 한글 폰트. 하나도 없으면 어디에 무엇을 깔아야 하는지 말한다."""
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit(
        "한글 굵은 고딕을 찾지 못했습니다. 아래 중 하나를 깔거나\n"
        "FONT_CANDIDATES 에 경로를 더하세요.\n  "
        + "\n  ".join(FONT_CANDIDATES))


def fit_font(text, box_width):
    """상자 안에 들어가는 가장 큰 글꼴. 세 자짜리 타입이 넘치지 않게 한다."""
    for size in range(FONT_SIZE, MIN_FONT_SIZE - 1, -1):
        font = find_font(size)
        if font.getbbox(text)[2] - font.getbbox(text)[0] <= box_width:
            return font
    return find_font(MIN_FONT_SIZE)


def glyph_mask(source):
    """원본에서 왼쪽 심볼만 알파 마스크로 떼어낸다.

    글자를 지우는 대신 심볼을 떼어 오는 이유는 알약의 둥근 끝 때문이다.
    글자 자리를 알약 색으로 칠하면 오른쪽 끝의 투명한 모서리까지 메워져
    네모가 된다.
    """
    w, h = source.size
    mask = Image.new("L", (w, h), 0)
    src, dst = source.load(), mask.load()
    for y in range(h):
        for x in range(ICON_RIGHT):
            r, g, b, a = src[x, y]
            if a >= ALPHA_MIN and min(r, g, b) >= WHITE_MIN:
                dst[x, y] = a
    return mask


def body_color(source):
    """알약 색. 가운데 가로줄에서 흰색이 아닌 것 중 가장 흔한 색."""
    w, h = source.size
    px = source.load()
    seen = {}
    for y in range(h // 2 - 3, h // 2 + 4):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 200 and min(r, g, b) < WHITE_MIN:
                seen[(r, g, b)] = seen.get((r, g, b), 0) + 1
    if not seen:
        raise ValueError("알약 색을 못 찾았습니다. 원본이 배지가 맞습니까?")
    return max(seen, key=seen.get)


def plate(source):
    """글자가 지워진 알약. 모양·색·심볼은 원본 그대로다.

    알파는 원본을 그대로 쓴다 — 둥근 끝의 반투명 픽셀까지 옮겨 와야
    가장자리가 톱니로 보이지 않는다.
    """
    w, h = source.size
    r, g, b = body_color(source)
    out = Image.new("RGBA", (w, h), (r, g, b, 0))
    out.putalpha(source.getchannel("A"))
    out.paste((255, 255, 255, 255), (0, 0), glyph_mask(source))
    return out


def narrow(image, target_w):
    """알약의 곧은 가운데를 잘라내 좁힌다. 둥근 끝과 심볼은 그대로 둔다.

    자르는 자리를 가운데로 잡는 이유는 양 끝이 둥글기 때문이다. 반지름이
    높이의 절반이라 그 안쪽은 색도 알파도 한결같고, 거기서 잘라 붙이면
    이음매가 보이지 않는다. 끝을 건드리면 둥근 모서리가 잘려 네모가 된다.
    """
    w, h = image.size
    if target_w >= w:
        return image

    cut = w - target_w
    keep_right = h // 2 + 2          # 오른쪽 둥근 끝 + 여유
    start = w - keep_right - cut
    if start <= ICON_RIGHT:
        raise ValueError(
            f"{target_w}px 로는 심볼과 둥근 끝이 겹칩니다. "
            f"PLATE_WIDTH 를 {ICON_RIGHT + keep_right + 1}px 이상으로 잡으세요.")

    out = Image.new("RGBA", (target_w, h), (0, 0, 0, 0))
    out.paste(image.crop((0, 0, start, h)), (0, 0))
    out.paste(image.crop((start + cut, 0, w, h)), (start, 0))
    return out


def draw_label(image, text):
    """알약 오른쪽에 한국어 이름을 흰 글씨로 얹는다."""
    w, h = image.size
    left, right = ICON_RIGHT, w - TEXT_PAD_RIGHT
    font = fit_font(text, right - left)

    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    draw.text(((left + right) / 2 - (x0 + x1) / 2,
               h / 2 - (y0 + y1) / 2),
              text, font=font, fill=(255, 255, 255, 255))
    return image


def render(source_path, ko_name):
    """원본 배지 한 장 -> 한국어 배지 한 장."""
    with Image.open(source_path) as im:
        source = im.convert("RGBA")
    return draw_label(narrow(plate(source), PLATE_WIDTH), ko_name)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="영문 타입 배지의 심볼을 살려 한국어 배지를 그린다.")
    ap.add_argument("--force", action="store_true",
                    help="이미 있어도 다시 그린다")
    args = ap.parse_args(argv)

    with connection() as conn:
        ko = rules_repo.fetch_type_names(conn, "ko")

    made, skipped, missing = 0, 0, []
    for type_name in sorted(assets.TYPE_IDS):
        label = ko.get(type_name)
        if not label:
            missing.append(f"{type_name} (pokemon_type_names 에 ko 가 없다)")
            continue

        source = assets.ensure_type_source(type_name)
        if source is None:
            missing.append(f"{type_name} (원본을 못 받았다)")
            continue

        out = assets.TYPES_DIR / f"{type_name}.png"
        if out.exists() and not args.force:
            skipped += 1
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        render(source, label).save(out)
        print(f"  {type_name:<9} {label}")
        made += 1

    print(f"\n그림 {made}장 / 건너뜀 {skipped}장")
    if missing:
        print(f"못 만든 것 {len(missing)}개")
        for m in missing:
            print(f"  {m}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
