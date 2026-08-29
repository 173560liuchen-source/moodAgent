from __future__ import annotations

from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1600, 1360
OUT = Path(__file__).resolve().parents[1] / "docs" / "competition" / "intervention-closed-loop.png"


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
SMALL = font(17)
DECISION = font(22, True)
BRANCH = font(18, True)
FOOT = font(23, True)
FOOT_SUB = font(16)


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


def labeled_box(draw, rect, title, subtitle, fill, outline, title_color="#17324D") -> None:
    rounded_box(draw, rect, fill, outline)
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    centered(draw, (cx, cy - 14), title, BOX, title_color)
    centered(draw, (cx, cy + 23), subtitle, BOX_SUB, title_color)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((54, 42, 68, 119), radius=7, fill="#3973A5")
    draw.text((91, 48), "风险、画像、趋势与干预闭环", font=TITLE, fill="#17324D")
    draw.text((92, 99), "状态分析驱动方案生成，动作反馈驱动方案演化与版本追踪", font=SUBTITLE, fill="#66798C")

    labeled_box(
        draw,
        (430, 145, 1170, 230),
        "多源状态输入",
        "危机信号 · 当前情绪 · 历史时间点 · 既有画像与方案",
        "#EDF5FA",
        "#8CB6D3",
    )
    arrow(draw, [(800, 230), (800, 270)])

    analysis_boxes = [
        ((115, 290, 515, 395), "Trend Agent", "7天/30天趋势与干预前后比较", "#EEF3FA", "#6C91BF"),
        ((600, 290, 1000, 395), "Risk Agent", "危机硬规则 + 情绪风险 + 趋势风险", "#FFF8E8", "#C99B3B"),
        ((1085, 290, 1485, 395), "Profile Agent", "生成有来源、证据和置信度的画像补丁", "#F4F0FA", "#8B72B6"),
    ]
    for rect, title, subtitle, fill, outline in analysis_boxes:
        labeled_box(draw, rect, title, subtitle, fill, outline)
    arrow(draw, [(800, 270), (315, 270), (315, 290)])
    arrow(draw, [(515, 342), (600, 342)])
    arrow(draw, [(1000, 342), (1085, 342)])

    rounded_box(draw, (1080, 425, 1490, 500), "#FCEDEF", "#C14B50")
    centered(draw, (1285, 449), "危机安全硬约束", BOX, "#9C3036")
    centered(draw, (1285, 478), "高危直接安全响应并要求人工复核", SMALL, "#9C3036")
    arrow(draw, [(900, 395), (900, 463), (1080, 463)], color="#C14B50")

    arrow(draw, [(1285, 395), (1285, 410), (800, 410), (800, 450)])
    labeled_box(
        draw,
        (475, 465, 1125, 560),
        "Intervention Agent：生成结构化干预方案",
        "风险分级 · 画像适配 · 真实RAG证据 · 稳定action_id",
        "#EAF7F3",
        "#57A78D",
        "#226C56",
    )

    rounded_box(draw, (95, 465, 395, 560), "#F3F6F8", "#8295A7")
    centered(draw, (245, 496), "RAG证据", BOX, "#496177")
    centered(draw, (245, 530), "仅支持建议，不降低风险", BOX_SUB, "#496177")
    arrow(draw, [(395, 512), (475, 512)], color="#71889D")

    arrow(draw, [(800, 560), (800, 600)])
    labeled_box(
        draw,
        (475, 610, 1125, 700),
        "用户执行方案并提交动作级反馈",
        "execution_status · outcome_status · difficulty · feedback_note",
        "#EDF5FA",
        "#6C9AC1",
    )
    arrow(draw, [(800, 700), (800, 740)])

    labeled_box(
        draw,
        (475, 750, 1125, 840),
        "FollowUp Agent：执行与效果评估",
        "结构化反馈优先，文本反馈作为兼容回退",
        "#F4F0FA",
        "#8B72B6",
    )
    arrow(draw, [(800, 840), (800, 875)])

    diamond = [(800, 875), (1045, 950), (800, 1025), (555, 950)]
    draw.polygon([(x + 5, y + 7) for x, y in diamond], fill="#DCE4EB")
    draw.polygon(diamond, fill="#FFF8E8", outline="#C99B3B", width=3)
    centered(draw, (800, 934), "反馈对应的", DECISION, "#17324D")
    centered(draw, (800, 969), "方案调整决策", DECISION, "#17324D")

    decision_boxes = [
        ((70, 1065, 390, 1150), "保持 keep", "完成且改善", "#EAF7F3", "#57A78D", "#226C56"),
        ((450, 1065, 770, 1150), "调整 adjust", "未执行、部分执行或负担高", "#EEF3FA", "#6C91BF", "#244F73"),
        ((830, 1065, 1150, 1150), "替换 replace", "完成但没有改善", "#F4F0FA", "#8B72B6", "#60458C"),
        ((1210, 1065, 1530, 1150), "升级 escalate", "状态恶化或中高风险", "#FCEDEF", "#C14B50", "#9C3036"),
    ]
    centers = []
    bus_y = 1045
    draw.line([(230, bus_y), (1370, bus_y)], fill="#3973A5", width=4)
    arrow(draw, [(800, 1025), (800, bus_y)])
    for rect, title, subtitle, fill, outline, color in decision_boxes:
        cx = (rect[0] + rect[2]) / 2
        centers.append(cx)
        arrow(draw, [(cx, bus_y), (cx, rect[1])], color=outline)
        rounded_box(draw, rect, fill, outline, radius=16)
        centered(draw, (cx, 1094), title, BOX, color)
        centered(draw, (cx, 1128), subtitle, BOX_SUB, color)

    merge_y = 1180
    draw.line([(centers[0], merge_y), (centers[-1], merge_y)], fill="#3973A5", width=4)
    for cx in centers:
        draw.line([(cx, 1150), (cx, merge_y)], fill="#3973A5", width=4)
    arrow(draw, [(800, merge_y), (800, 1205)])

    rounded_box(draw, (380, 1215, 1220, 1300), "#244F73", "#244F73")
    centered(draw, (800, 1243), "Java端保存新方案与跟进记录", FOOT, "#FFFFFF")
    centered(draw, (800, 1275), "parent_plan_id · revision_no · decision_source · 审计证据", FOOT_SUB, "#DCEAF5")

    # The versioned plan becomes context for the next conversation, completing the loop.
    arrow(draw, [(380, 1258), (45, 1258), (45, 187), (420, 187)], color="#2F8066", width=5, head=16)
    draw.rounded_rectangle((76, 720, 330, 790), radius=16, fill="#EAF7F3", outline="#57A78D", width=2)
    centered(draw, (203, 744), "下一轮上下文", BOX, "#226C56")
    centered(draw, (203, 771), "最新画像 · 趋势 · 方案版本", SMALL, "#226C56")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, dpi=(220, 220), optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
