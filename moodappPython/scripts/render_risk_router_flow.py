from __future__ import annotations

from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1600, 1200
OUT = Path(__file__).resolve().parents[1] / "docs" / "competition" / "risk-constrained-routing-flow.png"


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
BOX = font(25, True)
SMALL = font(18)
DECISION = font(24, True)
BRANCH = font(21, True)
PATH = font(20, True)
AUDIT = font(26, True)
AUDIT_SUB = font(17)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, font=fnt, fill=fill)


def rounded_box(draw: ImageDraw.ImageDraw, rect, fill, outline, radius=18, width=3) -> None:
    x1, y1, x2, y2 = rect
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


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((54, 42, 68, 119), radius=7, fill="#3973A5")
    draw.text((91, 48), "风险约束动态路由流程", font=TITLE, fill="#17324D")
    draw.text((92, 99), "安全硬约束优先，普通请求再依据多源特征选择服务路径", font=SUBTITLE, fill="#66798C")

    rounded_box(draw, (390, 150, 1210, 252), "#EDF5FA", "#8CB6D3")
    centered(draw, (800, 190), "危机、情绪、趋势、知识需求及历史反馈", BOX, "#17324D")
    centered(draw, (800, 227), "多源状态信号输入", SMALL, "#496177")
    arrow(draw, [(800, 252), (800, 300)])

    rounded_box(draw, (535, 308, 1065, 398), "#E8F0F7", "#6C9AC1")
    centered(draw, (800, 354), "路由特征归一化", BOX, "#17324D")
    arrow(draw, [(800, 398), (800, 445)])

    diamond = [(800, 445), (1040, 530), (800, 615), (560, 530)]
    draw.polygon([(x + 5, y + 7) for x, y in diamond], fill="#DCE4EB")
    draw.polygon(diamond, fill="#FFF8E8", outline="#C99B3B", width=3)
    centered(draw, (800, 510), "是否触发", DECISION, "#17324D")
    centered(draw, (800, 550), "危机安全硬约束？", DECISION, "#17324D")

    arrow(draw, [(560, 530), (310, 530), (310, 677)], color="#C14B50")
    centered(draw, (437, 505), "是", BRANCH, "#B33F45")
    centered(draw, (310, 584), "安全升级 / 高危 / 危机响应动作", SMALL, "#B33F45")
    rounded_box(draw, (95, 690, 525, 805), "#FCEDEF", "#C14B50")
    centered(draw, (310, 732), "危机响应路径", BOX, "#9C3036")
    centered(draw, (310, 775), "跳过普通对话，标记人工复核", SMALL, "#9C3036")

    arrow(draw, [(1040, 530), (1290, 530), (1290, 638)])
    centered(draw, (1165, 505), "否", BRANCH, "#3973A5")
    rounded_box(draw, (1090, 650, 1490, 735), "#EDF5FA", "#6C9AC1")
    centered(draw, (1290, 693), "计算四类路径得分", BOX, "#17324D")
    arrow(draw, [(1290, 735), (1290, 780)])
    rounded_box(draw, (1090, 790, 1490, 875), "#E8F0F7", "#6C9AC1")
    centered(draw, (1290, 833), "按优先级检查路由条件", BOX, "#17324D")

    bus_y = 905
    draw.line([(1290, 875), (1290, bus_y), (640, bus_y)], fill="#3973A5", width=4)
    path_boxes = [
        ((535, 935, 755, 1015), "跟进支持", "#EAF7F3", "#57A78D"),
        ((770, 935, 990, 1015), "知识支持", "#EEF3FA", "#6C91BF"),
        ((1005, 935, 1225, 1015), "综合评估", "#F4F0FA", "#8B72B6"),
        ((1240, 935, 1460, 1015), "探索式陪伴", "#F3F6F8", "#8295A7"),
    ]
    centers = []
    for rect, label, fill, outline in path_boxes:
        cx = (rect[0] + rect[2]) / 2
        centers.append(cx)
        arrow(draw, [(cx, bus_y), (cx, rect[1])])
        rounded_box(draw, rect, fill, outline, radius=15, width=3)
        centered(draw, (cx, 976), label, PATH, "#17324D")

    merge_y = 1055
    draw.line([(centers[0], merge_y), (centers[-1], merge_y)], fill="#3973A5", width=4)
    for cx in centers:
        draw.line([(cx, 1015), (cx, merge_y)], fill="#3973A5", width=4)

    draw.line([(310, 805), (310, 1055), (480, 1055)], fill="#C14B50", width=4)
    arrow(draw, [(480, 1055), (800, 1055), (800, 1080)], color="#C14B50")
    arrow(draw, [(1000, 1055), (800, 1055), (800, 1080)], color="#3973A5")

    rounded_box(draw, (450, 1085, 1150, 1175), "#244F73", "#244F73", radius=18, width=2)
    centered(draw, (800, 1120), "输出路由解释并写入审计记录", AUDIT, "#FFFFFF")
    centered(draw, (800, 1155), "路径 · 得分 · 理由 · 证据状态 · 策略版本", AUDIT_SUB, "#DCEAF5")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, dpi=(220, 220), optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
