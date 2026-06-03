# -*- coding: utf-8 -*-
"""
questionnaire_engine.py · 问卷引擎

职责：
    1. 加载并解析 questionnaire.json；
    2. 逻辑跳转引擎 next_id()（与设计器 builder.js 的 computeNext 保持一致）；
    3. 答案校验 validate_answer()（必答 / 取值范围 / 字数等）；
    4. 题目与选项的便捷访问。

整个系统（老人端 / 分析端 / 大屏）统一通过本引擎读取同一份问卷配置，
做到「问卷不写死在代码里」。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("questionnaire_engine")

BASE_DIR = Path(__file__).resolve().parent.parent

OPTION_TYPES = {"single", "multiple", "yesno"}
NUMERIC_TYPES = {"number", "rating"}
ALL_TYPES = {"single", "multiple", "yesno", "rating", "text", "number", "date"}


class Questionnaire:
    """问卷对象：封装题目访问、逻辑跳转与答案校验。"""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.raw: Dict[str, Any] = data or {}
        self.meta: Dict[str, Any] = self.raw.get("meta", {})
        self.settings: Dict[str, Any] = self.raw.get("settings", {})
        self.questions: List[Dict[str, Any]] = self.raw.get("questions", [])
        self._by_id: Dict[str, Dict[str, Any]] = {q.get("id"): q for q in self.questions}
        self._order: List[str] = [q.get("id") for q in self.questions]

    # ---------------- 构造 ----------------
    @classmethod
    def load(cls, path: Optional[Path] = None,
             config: Optional[Dict[str, Any]] = None,
             base_dir: Path = BASE_DIR) -> "Questionnaire":
        """从 JSON 文件加载问卷。优先使用 path，其次 config 中的路径。"""
        if path is None:
            rel = (config or {}).get("paths", {}).get(
                "questionnaire", "survey/questionnaire.json")
            path = base_dir / rel
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            log.info("已加载问卷：%s（%d 题）",
                     data.get("meta", {}).get("title", "?"),
                     len(data.get("questions", [])))
            return cls(data)
        except FileNotFoundError:
            log.error("问卷文件不存在：%s", path)
        except json.JSONDecodeError as exc:
            log.error("问卷 JSON 解析失败：%s", exc)
        return cls({"meta": {}, "settings": {}, "questions": []})

    # ---------------- 访问 ----------------
    def __len__(self) -> int:
        return len(self.questions)

    def get(self, qid: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(qid)

    def first_id(self) -> Optional[str]:
        return self._order[0] if self._order else None

    def index_of(self, qid: str) -> int:
        return self._order.index(qid) if qid in self._order else -1

    def title(self) -> str:
        return self.meta.get("title", "未命名问卷")

    def option_label(self, qid: str, value: Any) -> str:
        """把选项 value 翻译成展示用 label；找不到则原样返回。"""
        q = self.get(qid)
        if not q:
            return str(value)
        for o in q.get("options", []):
            if str(o.get("value")) == str(value):
                return o.get("label", str(value))
        return str(value)

    def answer_display(self, qid: str, value: Any) -> str:
        """把答案（含多选列表）转为可读中文。"""
        if value is None or value == "":
            return ""
        if isinstance(value, list):
            return "、".join(self.option_label(qid, v) for v in value)
        return self.option_label(qid, value)

    # ---------------- 逻辑跳转引擎 ----------------
    def next_id(self, qid: str, answer: Any) -> Optional[str]:
        """根据当前题目答案计算下一题 id。

        规则：按顺序逐条匹配 logic 规则，命中即跳转其 goto；
        若都不命中，则顺序进入下一题；末题则返回 "END"。
        """
        q = self.get(qid)
        if not q:
            return "END"
        for rule in q.get("logic", []) or []:
            if evaluate_rule(rule, answer):
                return rule.get("goto", "END")
        idx = self.index_of(qid)
        if idx < 0 or idx >= len(self._order) - 1:
            return "END"
        return self._order[idx + 1]

    def walk_default_path(self) -> List[str]:
        """返回不触发任何跳转时的默认题目顺序（用于展示/估算）。"""
        return list(self._order)

    # ---------------- 答案校验 ----------------
    def validate_answer(self, qid: str, answer: Any) -> Tuple[bool, str]:
        """校验单题答案是否合法。返回 (是否通过, 提示信息)。"""
        q = self.get(qid)
        if not q:
            return False, f"题目 {qid} 不存在"

        required = q.get("required", False)
        empty = (
            answer is None or answer == ""
            or (isinstance(answer, list) and len(answer) == 0)
        )
        if required and empty:
            return False, "这是必答题，请先作答"
        if empty:
            return True, ""  # 非必答允许留空

        qtype = q.get("type")
        if qtype in ("single", "yesno"):
            valid = {str(o.get("value")) for o in q.get("options", [])}
            if str(answer) not in valid:
                return False, "请选择有效选项"
        elif qtype == "multiple":
            if not isinstance(answer, list):
                return False, "多选答案格式不正确"
            valid = {str(o.get("value")) for o in q.get("options", [])}
            if any(str(a) not in valid for a in answer):
                return False, "包含无效选项"
        elif qtype == "rating":
            try:
                v = float(answer)
            except (TypeError, ValueError):
                return False, "评分必须是数字"
            if not (1 <= v <= int(q.get("scale", 5))):
                return False, f"评分需在 1~{q.get('scale', 5)} 之间"
        elif qtype == "number":
            try:
                v = float(answer)
            except (TypeError, ValueError):
                return False, "请输入数字"
            lo, hi = q.get("min"), q.get("max")
            if lo is not None and v < float(lo):
                return False, f"不能小于 {lo}"
            if hi is not None and v > float(hi):
                return False, f"不能大于 {hi}"
        elif qtype == "text":
            maxlen = q.get("max_length")
            if maxlen and len(str(answer)) > int(maxlen):
                return False, f"最多 {maxlen} 个字"
        # date 不做强校验
        return True, ""


# ----------------------------------------------------------------------
# 逻辑规则求值（与 builder.js evalRule 完全一致）
# ----------------------------------------------------------------------
def evaluate_rule(rule: Dict[str, Any], answer: Any) -> bool:
    """判断答案是否满足某条跳转规则。"""
    op = rule.get("op")
    value = rule.get("value")
    try:
        if op == "equals":
            return answer in value if isinstance(answer, list) else str(answer) == str(value)
        if op == "not_equals":
            return value not in answer if isinstance(answer, list) else str(answer) != str(value)
        if op == "contains":
            if isinstance(answer, list):
                return value in answer
            return str(value) in str(answer if answer is not None else "")
        if op == "greater_than":
            return _to_num(answer) is not None and _to_num(answer) > float(value)
        if op == "less_than":
            return _to_num(answer) is not None and _to_num(answer) < float(value)
        if op == "between":
            n = _to_num(answer)
            return (
                n is not None and isinstance(value, (list, tuple)) and len(value) == 2
                and float(value[0]) <= n <= float(value[1])
            )
    except (TypeError, ValueError):
        return False
    return False


def _to_num(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------
def load_questionnaire(config: Optional[Dict[str, Any]] = None,
                       base_dir: Path = BASE_DIR) -> Questionnaire:
    return Questionnaire.load(config=config, base_dir=base_dir)
