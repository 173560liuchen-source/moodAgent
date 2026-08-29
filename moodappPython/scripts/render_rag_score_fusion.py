from __future__ import annotations

from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1600, 1120
OUT = Path(__file__).resolve().parents[1] / "docs" / "competition" / "rag-score-fusion.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


TITLE = font(40, True)
SUBTITLE = font(20)
SECTION = font(23, True)
BOX = font(24, True)
BOX_SUB = font(17)
WEIGHT = font(25, True)
FORMULA = font(25, True)
NOTE = font(17)
MINI = font(16)
GATE = font(20, True)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill: str) -> None:
    bounds = draw.textbbox((0, 0), text, font=fnt)
    draw.text(
        (xy[0] - (bounds[2] - bounds[0]) / 2, xy[1] - (bounds[3] - bounds[1]) / 2),
        text,
        font=fnt,
        fill=fill,
    )


def rounded_box(draw: ImageDraw.ImageDraw, rect, fill, outline, radius=18, width=3, shadow=True) -> None:
    x1, y1, x2, y2 = rect
    if shadow:
        draw.rounded_rectangle((x1 + 5, y1 + 7, x2 + 5, y2 + 7), radius=radius, fill="#DCE4EB")
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw: ImageDraw.ImageDraw, points, color="#3973A5", width=4, head=14) -> None:
    draw.line(points, fill=color, width=width, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    angle = atan2(y2 - y1, x2 - x1)
    left = (x2 - head * cos(angle - 0.48), y2 - head * sin(angle - 0.48))
    right = (x2 - head * cos(angle + 0.48), y2 - head * sin(angle + 0.48))
    draw.polygon([(x2, y2), left, right], fill=color)


def score_box(draw, rect, title, subtitle, fill, outline, title_color="#17324D") -> None:
    rounded_box(draw, rect, fill, outline)
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    centered(draw, (cx, cy - 14), title, BOX, title_color)
    centered(draw, (cx, cy + 23), subtitle, BOX_SUB, title_color)


def weight_badge(draw, xy, text, fill, outline) -> None:
    x, y = xy
    draw.rounded_rectangle((x - 58, y - 25, x + 58, y + 25), radius=25, fill=fill, outline=outline, width=2)
    centered(draw, (x, y), text, WEIGHT, outline)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((54, 42, 68, 119), radius=7, fill="#3973A5")
    draw.text((91, 48), "混合召回与重排序得分融合", font=TITLE, fill="#17324D")
    draw.text((92, 99), "两阶段加权融合：先扩大召回覆盖，再强化证据相关性", font=SUBTITLE, fill="#66798C")

    rounded_box(draw, (80, 150, 1520, 500), "#F8FAFC", "#B7C8D6", radius=22, width=2, shadow=False)
    draw.rounded_rectangle((105, 174, 360, 218), radius=22, fill="#3973A5")
    centered(draw, (232, 196), "阶段一：初始混合召回", SECTION, "#FFFFFF")

    score_box(draw, (145, 270, 515, 370), "向量检索得分", "vector_score · 语义相似性", "#EEF3FA", "#6C91BF")
    score_box(draw, (1085, 270, 1455, 370), "关键词检索得分", "keyword_score · 精确匹配", "#F4F0FA", "#8B72B6")

    weight_badge(draw, (575, 320), "× 0.65", "#E4EEF8", "#3973A5")
    weight_badge(draw, (1025, 320), "× 0.35", "#EEE8F7", "#765AA4")
    arrow(draw, [(515, 320), (517, 320)], color="#3973A5", head=9)
    arrow(draw, [(1085, 320), (1083, 320)], color="#765AA4", head=9)

    rounded_box(draw, (650, 250, 950, 390), "#E8F0F7", "#3973A5")
    centered(draw, (800, 285), "初始混合得分", BOX, "#17324D")
    centered(draw, (800, 328), "hybrid_score", FORMULA, "#3973A5")
    centered(draw, (800, 357), "0.65 × vector_score", MINI, "#496177")
    centered(draw, (800, 379), "+ 0.35 × keyword_score", MINI, "#496177")

    draw.rounded_rectangle((365, 425, 1235, 474), radius=12, fill="#EFF4F7", outline="#B7C8D6", width=2)
    centered(draw, (800, 449), "单路命中时直接保留该路得分；候选扩展至 top_k × 4，最多50条", NOTE, "#496177")

    arrow(draw, [(800, 500), (800, 548)])
    rounded_box(draw, (525, 558, 1075, 645), "#FFF8E8", "#C99B3B")
    centered(draw, (800, 585), "语义重排序", BOX, "#725511")
    centered(draw, (800, 618), "原始得分归一化为 rerank_score", BOX_SUB, "#725511")

    arrow(draw, [(800, 645), (800, 688)])
    rounded_box(draw, (80, 698, 1520, 1010), "#F8FAFC", "#B7C8D6", radius=22, width=2, shadow=False)
    draw.rounded_rectangle((105, 722, 405, 766), radius=22, fill="#244F73")
    centered(draw, (255, 744), "阶段二：最终得分融合", SECTION, "#FFFFFF")

    final_inputs = [
        ((125, 825, 465, 920), "向量得分", "vector_score", "× 0.35", "#EEF3FA", "#6C91BF"),
        ((630, 825, 970, 920), "关键词得分", "keyword_score", "× 0.20", "#F4F0FA", "#8B72B6"),
        ((1135, 825, 1475, 920), "重排序得分", "rerank_score", "× 0.45", "#FFF5DD", "#C99B3B"),
    ]
    centers = []
    for rect, title, subtitle, weight, fill, outline in final_inputs:
        score_box(draw, rect, title, subtitle, fill, outline)
        cx = (rect[0] + rect[2]) / 2
        centers.append(cx)
        draw.rounded_rectangle((cx - 62, 775, cx + 62, 815), radius=20, fill="#FFFFFF", outline=outline, width=2)
        centered(draw, (cx, 795), weight, GATE, outline)

    bus_y = 955
    for cx in centers:
        draw.line([(cx, 920), (cx, bus_y)], fill="#3973A5", width=4)
    draw.line([(centers[0], bus_y), (centers[-1], bus_y)], fill="#3973A5", width=4)
    arrow(draw, [(800, bus_y), (800, 985)], color="#3973A5")

    rounded_box(draw, (280, 975, 1320, 1070), "#EAF7F3", "#57A78D")
    centered(draw, (800, 1006), "最终融合得分 final_score", BOX, "#226C56")
    centered(draw, (800, 1042), "0.35 × vector_score + 0.20 × keyword_score + 0.45 × rerank_score", FORMULA, "#226C56")

    draw.rounded_rectangle((385, 1080, 1215, 1110), radius=15, fill="#244F73")
    centered(draw, (800, 1095), "证据门槛：final_score ≥ 0.35 且 rerank_raw_score ≥ 0.01", GATE, "#FFFFFF")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, dpi=(220, 220), optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
