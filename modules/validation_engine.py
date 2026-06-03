# -*- coding: utf-8 -*-
"""
validation_engine.py · 问卷结构校验引擎（Python 端）

与设计器 builder.js 的 validateSurvey 保持一致，用于：
    - 命令行 / 加载时校验 questionnaire.json 是否规范；
    - 检查：重复ID、空题目、缺失选项、非法逻辑、死循环、孤立题、无终点路径。

用法：
    python -m modules.validation_engine            # 校验默认问卷
    python -m modules.validation_engine path.json  # 校验指定文件
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

log = logging.getLogger("validation_engine")

OPTION_TYPES = {"single", "multiple", "yesno"}
NUMERIC_TYPES = {"number", "rating"}
TYPE_LABELS = {
    "single": "单选题", "multiple": "多选题", "yesno": "是否题",
    "rating": "评分题", "text": "文本题", "number": "数字题", "date": "日期题",
}


def validate_questionnaire(survey: Dict[str, Any]) -> Dict[str, Any]:
    """校验问卷结构，返回 {'errors': [...], 'warnings': [...], 'ok': bool}。"""
    errors: List[str] = []
    warnings: List[str] = []
    questions: List[Dict[str, Any]] = survey.get("questions", [])
    ids = [q.get("id") for q in questions]

    if not questions:
        errors.append("问卷为空：至少需要一道题目。")

    # 重复 ID
    seen: Dict[str, int] = {}
    for qid in ids:
        seen[qid] = seen.get(qid, 0) + 1
    for qid, c in seen.items():
        if c > 1:
            errors.append(f"重复的题目 ID：{qid}")

    for q in questions:
        qid = q.get("id", "?")
        qtype = q.get("type")
        if qtype not in TYPE_LABELS:
            errors.append(f"{qid}：未知题型 {qtype}")
        if not (q.get("title") or "").strip():
            errors.append(f"{qid}：题目标题为空。")

        if qtype in OPTION_TYPES:
            options = q.get("options", []) or []
            if qtype == "yesno" and len(options) != 2:
                errors.append(f"{qid}：是否题需要正好 2 个选项。")
            if qtype in ("single", "multiple") and len(options) < 2:
                errors.append(f"{qid}：{TYPE_LABELS[qtype]}至少需要 2 个选项。")
            for i, o in enumerate(options, 1):
                if not (o.get("label") or "").strip():
                    errors.append(f"{qid}：第 {i} 个选项文字为空。")
                if not str(o.get("value") or "").strip():
                    errors.append(f"{qid}：第 {i} 个选项值为空。")
            vals = [o.get("value") for o in options]
            if len(set(vals)) != len(vals):
                errors.append(f"{qid}：存在重复的选项值。")

        if qtype == "rating" and int(q.get("scale", 0) or 0) < 2:
            errors.append(f"{qid}：评分上限至少为 2。")

        # 逻辑规则
        for i, r in enumerate(q.get("logic", []) or [], 1):
            tag = f"{qid} 第{i}条规则"
            goto = r.get("goto")
            if goto != "END" and goto not in ids:
                errors.append(f"{tag}：跳转目标 {goto} 不存在。")
            op = r.get("op")
            val = r.get("value")
            if op == "between":
                if not (isinstance(val, (list, tuple)) and len(val) == 2 and _all_num(val)):
                    errors.append(f"{tag}：「介于」需要两个数值。")
            if op in ("greater_than", "less_than") and _to_num(val) is None:
                errors.append(f"{tag}：该比较的值必须是数字。")
            if qtype in OPTION_TYPES and op in ("equals", "not_equals", "contains"):
                vals = [str(o.get("value")) for o in q.get("options", [])]
                if str(val) not in vals:
                    warnings.append(f"{tag}：比较值「{val}」不在选项列表中。")

    # 图分析（仅在无重复 ID 且非空时）
    if questions and all(c == 1 for c in seen.values()):
        graph = _build_graph(questions)
        reach = _bfs(graph, questions[0]["id"])
        for q in questions[1:]:
            if q["id"] not in reach:
                errors.append(f"孤立题目：{q['id']} 从问卷开头无法到达。")
        can_end = _bfs(_reverse(graph), "END")
        for q in questions:
            if q["id"] not in can_end:
                errors.append(f"无终点路径：{q['id']} 无法走到问卷结束。")
        cyc = _find_cycle(graph)
        if cyc:
            errors.append("检测到死循环跳转：" + " → ".join(cyc))

    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    return {"errors": errors, "warnings": warnings, "ok": len(errors) == 0}


# ---------------- 图算法 ----------------
def _build_graph(questions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    ids = [q["id"] for q in questions]
    g: Dict[str, List[str]] = {}
    for i, q in enumerate(questions):
        edges: Set[str] = set()
        for r in q.get("logic", []) or []:
            edges.add("END" if r.get("goto") == "END" else r.get("goto"))
        edges.add(ids[i + 1] if i < len(questions) - 1 else "END")
        g[q["id"]] = [t for t in edges if t == "END" or t in ids]
    g["END"] = []
    return g


def _bfs(g: Dict[str, List[str]], start: str) -> Set[str]:
    seen, stack = {start}, [start]
    while stack:
        for n in g.get(stack.pop(), []):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def _reverse(g: Dict[str, List[str]]) -> Dict[str, List[str]]:
    rev: Dict[str, List[str]] = {k: [] for k in g}
    for u, vs in g.items():
        for v in vs:
            rev.setdefault(v, []).append(u)
    return rev


def _find_cycle(g: Dict[str, List[str]]) -> List[str] | None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in g}
    parent: Dict[str, str] = {}
    cycle: List[str] = []

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in g.get(u, []):
            if color.get(v, WHITE) == WHITE:
                parent[v] = u
                if dfs(v):
                    return True
            elif color.get(v) == GRAY:
                path = [v]
                x = u
                while x != v and x is not None:
                    path.append(x)
                    x = parent.get(x)
                path.append(v)
                path.reverse()
                cycle.extend(path)
                return True
        color[u] = BLACK
        return False

    for n in list(g.keys()):
        if color[n] == WHITE and dfs(n):
            return cycle
    return None


def _to_num(x: Any):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _all_num(seq) -> bool:
    return all(_to_num(v) is not None for v in seq)


# ---------------- 命令行入口 ----------------
def _main(argv: List[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = Path(argv[1]) if len(argv) > 1 else BASE / "survey" / "questionnaire.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            survey = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ 无法读取问卷：{exc}")
        return 2

    result = validate_questionnaire(survey)
    print(f"问卷：{survey.get('meta', {}).get('title', '?')}  共 {len(survey.get('questions', []))} 题")
    if result["ok"] and not result["warnings"]:
        print("🎉 校验通过，没有发现问题。")
    for e in result["errors"]:
        print("❌ " + e)
    for w in result["warnings"]:
        print("⚠️  " + w)
    print(f"\n结论：{'通过' if result['ok'] else str(len(result['errors'])) + ' 个错误需修复'}")
    return 0 if result["ok"] else 1


BASE = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
