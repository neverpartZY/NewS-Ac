# -*- coding: utf-8 -*-
"""数据契约：Candidate（采集→过滤→去重）与 Article（加工后入库/出报）。

用 dataclass 而非裸 dict：字段拼错在运行期直接 AttributeError，杜绝「字符串字段契约」屎山。
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Candidate:
    """一条候选新闻，随流水线逐步充实字段。"""
    title: str = ""
    url: str = ""
    date: str = ""            # 发布日期（YYYY-MM-DD 或引擎原始）
    site: str = ""
    snippet: str = ""
    engine: str = ""          # serper / tavily / gzh / site
    lang: str = "zh"
    # 过滤阶段填充
    nd_date: bool = False     # 无日期降级保留
    score: float = 0.0        # LLM 相关性分
    reason: str = ""          # 相关性判断理由
    # 去重阶段填充
    url_hash: str = ""
    embedding: Optional[List[float]] = None
    dup_sim: float = 0.0
    # 采集任务维度预标注（P1-2 规则兜底）
    scope_hint: str = ""      # chemical / rpet / general / ""(未知，交 LLM)

    def text(self) -> str:
        return f"{self.title} {self.snippet}"


@dataclass
class Article:
    """加工后的情报条目（入库 + 出报消费）。"""
    url_hash: str = ""
    title: str = ""           # 原始标题
    title_zh: str = ""        # 中文主标题
    summary_zh: str = ""
    category: str = "general"  # policy / market / tech / enterprise / global
    scope: str = "general"    # chemical / rpet / general
    importance: int = 3
    tags: List[str] = field(default_factory=list)
    source: str = ""          # 采集引擎（同 Candidate.engine）
    site: str = ""
    url: str = ""
    published_at: str = ""
    collected_at: str = ""
    embedding: Optional[List[float]] = None
    is_price: bool = False


def scope_hint_from_dim(dim: str) -> str:
    """从采集任务的维度编码推 scope（V4=化学回收 / V5=再生PET / 其余=综合）。"""
    d = (dim or "").strip()
    if d.startswith("V4"):
        return "chemical"
    if d.startswith("V5"):
        return "rpet"
    return "general"
