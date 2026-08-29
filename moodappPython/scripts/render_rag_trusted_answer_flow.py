from __future__ import annotations

from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1600, 1400
OUT = Path(__file__).resolve().parents[1] / "docs" / "competition" / "rag-trusted-answer-flow.png"


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
BOX = font(24, True)
BOX_SUB = font(17)
DECISION = font(23, True)
BRANCH = font(20, True)
STAGE = font(19, True)
SMALL = font(17)
AUDIT = font(25, True)
AUDIT_SUB = font(16)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill: str) -> None:
    bounds = draw.textbbox((0, 0), text, font=fnt)
    draw.text(
        (xy[0] - (bounds[2] - bounds[0]) / 2, xy[1] - (bounds[3] - bounds[1]) / 2),
        text,
        font=fnt,
        fill=fill,
    )


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


def labeled_box(draw, rect, title, subtitle, fill, outline, title_color="#17324D") -> None:
    rounded_box(draw, rect, fill, outline)
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    centered(draw, (cx, cy - 15), title, BOX, title_color)
    centered(draw, (cx, cy + 23), subtitle, BOX_SUB, title_color)


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((54, 42, 68, 119), radius=7, fill="#3973A5")
    draw.text((91, 48), "RAG检索与可信回答总体流程", font=TITLE, fill="#17324D")
    draw.text((92, 99), "规则优先识别知识需求，证据不足时停止无依据生成", font=SUBTITLE, fill="#66798C")

    labeled_box(draw, (550, 145, 1050, 225), "用户问题与近期对话", "当前问题 + 最近上下文", "#EDF5FA", "#8CB6D3")
    arrow(draw, [(800, 225), (800, 270)])

    diamond1 = [(800, 270), (1040, 345), (800, 420), (560, 345)]
    draw.polygon([(x + 5, y + 7) for x, y in diamond1], fill="#DCE4EB")
    draw.polygon(diamond1, fill="#FFF8E8", outline="#C99B3B", width=3)
    centered(draw, (800, 327), "是否需要", DECISION, "#17324D")
    centered(draw, (800, 363), "知识检索？", DECISION, "#17324D")

    arrow(draw, [(560, 345), (295, 345), (295, 450)], color="#71889D")
    centered(draw, (430, 320), "否", BRANCH, "#5D7184")
    labeled_box(
        draw,
        (90, 460, 500, 555),
        "普通支持性对话",
        "不附加RAG引用",
        "#F3F6F8",
        "#8295A7",
    )

    arrow(draw, [(1040, 345), (1305, 345), (1305, 450)])
    centered(draw, (1170, 320), "是", BRANCH, "#3973A5")
    labeled_box(
        draw,
        (1085, 460, 1525, 555),
        "确定性查询改写",
        "提取领域词并定位知识层级",
        "#E8F0F7",
        "#6C9AC1",
    )

    arrow(draw, [(1305, 555), (1305, 595), (800, 595), (800, 625)])
    rounded_box(draw, (315, 635, 1285, 745), "#EDF5FA", "#6C9AC1")
    centered(draw, (800, 667), "分层检索与逐级回退", BOX, "#17324D")
    stage_boxes = [
        ((365, 690, 610, 730), "子类精确检索"),
        ((680, 690, 925, 730), "父类范围回退"),
        ((995, 690, 1240, 730), "全知识库回退"),
    ]
    for rect, label in stage_boxes:
        draw.rounded_rectangle(rect, radius=12, fill="#FFFFFF", outline="#9EBBD1", width=2)
        centered(draw, ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2), label, STAGE, "#244F73")
    arrow(draw, [(610, 710), (680, 710)], head=11)
    arrow(draw, [(925, 710), (995, 710)], head=11)

    arrow(draw, [(800, 745), (800, 785)])
    draw.line([(800, 785), (465, 785), (465, 815)], fill="#3973A5", width=4)
    draw.line([(800, 785), (1135, 785), (1135, 815)], fill="#3973A5", width=4)
    labeled_box(draw, (255, 825, 675, 915), "向量检索", "语义相似度召回", "#EEF3FA", "#6C91BF")
    labeled_box(draw, (925, 825, 1345, 915), "关键词检索", "词项覆盖率与标题匹配", "#F4F0FA", "#8B72B6")

    draw.line([(465, 915), (465, 950), (800, 950)], fill="#3973A5", width=4)
    arrow(draw, [(1135, 915), (1135, 950), (800, 950), (800, 975)])
    labeled_box(draw, (475, 985, 1125, 1075), "混合召回、候选扩展与语义重排序", "融合向量分、关键词分与重排序分", "#E8F0F7", "#6C9AC1")
    arrow(draw, [(800, 1075), (800, 1110)])

    rounded_box(draw, (475, 1120, 1125, 1205), "#FFF8E8", "#C99B3B")
    centered(draw, (800, 1150), "双阈值证据筛选", BOX, "#725511")
    centered(draw, (800, 1182), "最终得分 + 原始重排分，并控制来源多样性", BOX_SUB, "#725511")

    arrow(draw, [(475, 1162), (330, 1162), (330, 1235)], color="#C14B50")
    centered(draw, (405, 1138), "无有效证据", SMALL, "#B33F45")
    rounded_box(draw, (85, 1245, 575, 1330), "#FCEDEF", "#C14B50")
    centered(draw, (330, 1273), "可信拒答 / 保守回复", BOX, "#9C3036")
    centered(draw, (330, 1305), "请用户补充情境，或连接人工支持", BOX_SUB, "#9C3036")

    arrow(draw, [(1125, 1162), (1270, 1162), (1270, 1235)], color="#3F9477")
    centered(draw, (1195, 1138), "获得有效证据", SMALL, "#2F8066")
    rounded_box(draw, (1025, 1245, 1515, 1330), "#EAF7F3", "#57A78D")
    centered(draw, (1270, 1273), "扩展父级上下文并生成回答", BOX, "#226C56")
    centered(draw, (1270, 1305), "附加真实结构化引用", BOX_SUB, "#226C56")

    draw.line([(295, 555), (295, 1360), (800, 1360)], fill="#71889D", width=4)
    draw.line([(330, 1330), (330, 1360)], fill="#C14B50", width=4)
    draw.line([(1270, 1330), (1270, 1360)], fill="#3F9477", width=4)

    # Compact audit footer overlays the three merged branches without crowding the main flow.
    rounded_box(draw, (485, 1335, 1115, 1392), "#244F73", "#244F73", radius=16, width=2)
    centered(draw, (800, 1355), "写入检索轨迹与审计记录", AUDIT, "#FFFFFF")
    centered(draw, (800, 1380), "检索阶段 · 证据状态 · 引用来源 · 降级原因", AUDIT_SUB, "#DCEAF5")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, dpi=(220, 220), optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
