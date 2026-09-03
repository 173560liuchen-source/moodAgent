from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


KnowledgeParent = Literal["压力管理", "睡眠管理", "情绪支持", "危机干预", "校园资源"]


class HierarchyMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_category: KnowledgeParent
    child_categories: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class HierarchyClassification(BaseModel):
    """仅分类，不产生检索过滤条件，供下一阶段接入分层检索。"""

    query: str
    matches: list[HierarchyMatch] = Field(default_factory=list)  #匹配到的分类结构
    classifier_version: str = "hierarchy-rules-1.0.0"


class KnowledgeHierarchyClassifier:
    """可解释的规则分类器；一条问题允许同时落入多个父类与子类。"""

    version = "1.0.0"

    _RULES: tuple[tuple[KnowledgeParent, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
        ("危机干预", (
            ("自伤", ("自伤", "割腕", "伤害自己", "结束生命")),
            ("自杀", ("自杀", "不想活", "去死", "轻生")),
            ("伤人", ("伤人", "杀了他", "伤害他人", "报复")),
            ("紧急求助", ("急救", "报警", "热线", "紧急", "现在就", "马上", "手边有药", "准备好了", "已经拿到")),
            ("危机识别", ("活不下去", "绝望", "遗书", "告别", "计划", "工具")),
        )),
        ("睡眠管理", (
            ("入睡困难", ("睡不着", "入睡", "失眠", "难以入睡")),
            ("早醒", ("早醒", "醒得太早")),
            ("夜醒", ("夜醒", "半夜醒", "醒来很多次")),
            ("作息紊乱", ("熬夜", "昼夜颠倒", "作息", "睡眠规律", "补觉")),
        )),
        ("压力管理", (
            ("学业", ("考试", "学习", "作业", "论文", "绩点", "考研")),
            ("家庭", ("父母", "家庭", "家里", "家人")),
            ("就业", ("就业", "找工作", "实习", "面试", "求职")),
            ("经济", ("钱", "经济", "房租", "学费", "负债")),
        )),
        ("情绪支持", (
            ("焦虑", ("焦虑", "紧张", "担心", "害怕", "恐慌")),
            ("低落", ("低落", "难过", "抑郁", "没动力", "沮丧")),
            ("孤独", ("孤独", "没人理解", "没有朋友", "寂寞")),
            ("人际困扰", ("人际", "室友", "同学", "朋友", "社交", "被排斥")),
            ("测评与动态监测", ("SAS", "SDS", "量表", "测评", "趋势", "情绪记录")),
            ("认知与自我评价", ("思维模式", "不如别人", "自我评价", "自卑")),
        )),
        ("校园资源", (
            ("心理中心", ("心理中心", "心理咨询", "心理老师")),
            ("辅导员", ("辅导员", "班主任")),
            ("校医院", ("校医院", "校医")),
            ("热线", ("热线", "求助电话")),
            ("预约与转介", ("预约", "满约", "准备什么", "报告", "向学校", "校内渠道")),
        )),
    )

    def classify(self, query: str) -> HierarchyClassification:
        text = (query or "").strip().lower()
        matches: list[HierarchyMatch] = []
        for parent, child_rules in self._RULES:
            children: list[str] = []
            reasons: list[str] = []
            for child, terms in child_rules:
                hits = [term for term in terms if term.lower() in text]
                if hits:
                    children.append(child)
                    reasons.append(f"{child}：命中“{'、'.join(hits[:3])}”")
            if children:
                confidence = min(0.95, round(0.60 + 0.10 * len(children) + 0.03 * len(reasons), 2))
                #基础值：0.60；  每增加一个子项：增加 0.10；  每增加一个原因：增加 0.03；  上限限制：最大为 0.95（通过 min 函数限制）
                
                matches.append(HierarchyMatch(
                    parent_category=parent,
                    child_categories=children,
                    confidence=confidence,
                    reasons=reasons,
                ))
        return HierarchyClassification(query=query, matches=matches)
