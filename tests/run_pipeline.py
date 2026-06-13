#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随访子系统 · 端到端流水线自测（headless）。

用一份模拟数据把整条链路跑通，方便你确认每一步都正常：

    ① CSV → JSON           （csv_to_json）
    ② 平均分配 → allocation.json   （模拟 allocation.html 的「平均分配」）
    ③ 生成 query.html        （generate_query）
    ④ 完成情况统计           （模拟 completion.html 的判定逻辑）

所有产物写入 tests/out/，不会改动 followup/ 下的正式文件，也不弹浏览器。
跑完会打印每一步的结果摘要；任何一步异常都会以非 0 退出码失败。

用法：
    python tests/run_pipeline.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
DATA = TESTS / "data"
OUT = TESTS / "out"

# 让 `from followup import ...` 可用
sys.path.insert(0, str(REPO))
from followup import csv_to_json as c2j        # noqa: E402
from followup import generate_query as gq       # noqa: E402


def line(title: str) -> None:
    print(f"\n{'─' * 56}\n{title}\n{'─' * 56}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("随访流水线自测  ·  数据目录:", DATA)

    # ── ① CSV → JSON ───────────────────────────────────────────
    line("① CSV → JSON（csv_to_json，含中文表头容错）")
    ns = c2j.csv_to_json(str(DATA / "students.csv"), str(OUT / "students.json"), "students")
    nb = c2j.csv_to_json(str(DATA / "subjects.csv"), str(OUT / "subjects.json"), "subjects")
    students = json.loads((OUT / "students.json").read_text(encoding="utf-8"))
    subjects = json.loads((OUT / "subjects.json").read_text(encoding="utf-8"))
    print(f"  学生 {ns} 人  ·  受试者 {nb} 人")
    print(f"  受试者示例: {subjects[0]['subject_name']} / {subjects[0]['phone']}"
          f"（备注: {subjects[0].get('note') or '—'}）")
    assert ns == 8 and nb == 40, "示例数据条数不符，请检查 tests/data/*.csv"
    assert subjects[0]["subject_name"], "受试者姓名解析失败（列名容错可能有问题）"

    # ── ② 平均分配 → allocation.json ───────────────────────────
    line("② 平均分配 → allocation.json（模拟 allocation.html）")
    assignments = []
    for i, sub in enumerate(subjects):
        stu = students[i % len(students)]          # 轮询均分
        assignments.append({
            "subject_id": sub["subject_id"], "subject_name": sub["subject_name"],
            "phone": sub["phone"], "note": sub.get("note", ""),
            "student_id": stu["student_id"], "student_name": stu["student_name"],
        })
    allocation = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "students": [{"student_id": s["student_id"], "student_name": s["student_name"],
                      "phone": s["phone"]} for s in students],
        "assignments": assignments,
        "unassigned": [],
    }
    (OUT / "allocation.json").write_text(
        json.dumps(allocation, ensure_ascii=False, indent=2), encoding="utf-8")
    counts: dict[str, int] = {s["student_name"]: 0 for s in students}
    for a in assignments:
        counts[a["student_name"]] += 1
    print("  每位学生分配数:")
    for name, c in counts.items():
        print(f"    {name}: {c}")
    print(f"  合计 {len(assignments)} / {nb}  ·  未分配 {len(allocation['unassigned'])}")
    assert sum(counts.values()) == nb, "分配总数与受试者数不一致"

    # ── ③ 生成 query.html ──────────────────────────────────────
    line("③ 生成学生查询页 query.html（generate_query）")
    sms_tpl = (DATA / "sms_template.txt").read_text(encoding="utf-8").strip()
    css = (REPO / "followup" / "assets" / "theme.css").read_text(encoding="utf-8")
    html = gq.build_html(allocation, sms_tpl, css)
    (OUT / "query.html").write_text(html, encoding="utf-8")
    # 校验：数据已内联、短信占位已替换
    assert "const DATA =" in html and css[:40] in html, "query.html 未正确内联数据/样式"
    sample = next(a for a in assignments if a["student_name"] == students[0]["student_name"])
    expect_sms = sms_tpl.replace("{姓名}", sample["subject_name"])
    assert expect_sms in html, "短信模板姓名占位未正确替换"
    mine = [a["subject_name"] for a in assignments
            if a["student_name"] == students[0]["student_name"]]
    print(f"  query.html 已生成（{len(assignments)} 条任务）")
    print(f"  例：学生「{students[0]['student_name']}」名下 {len(mine)} 人 → {('、'.join(mine))}")
    print(f"  其短信将渲染为：{expect_sms[:30]}…")

    # ── ④ 完成情况统计 ─────────────────────────────────────────
    line("④ 完成情况统计（模拟 completion.html · 对照学生名单）")
    thread = (DATA / "sample_thread.txt").read_text(encoding="utf-8")
    roster = [s["student_name"] for s in students]
    done = [n for n in roster if n in thread]
    miss = [n for n in roster if n not in thread]
    print(f"  接龙文本来源: tests/data/sample_thread.txt")
    print(f"  总人数 {len(roster)}  ·  已完成 {len(done)}  ·  未完成 {len(miss)}")
    print(f"  ✅ 已完成: {'、'.join(done)}")
    print(f"  ⚠️  未完成: {'、'.join(miss) or '（无）'}")
    assert miss == ["杨光", "孙磊"], f"完成统计结果不符，实际未完成={miss}"

    # ── 收尾 ───────────────────────────────────────────────────
    line("✅ 全流程跑通")
    print("  产物目录:", OUT)
    for p in ["students.json", "subjects.json", "allocation.json", "query.html"]:
        print("    ·", (OUT / p))
    print("\n  在浏览器查看（macOS）:")
    print(f"    open '{OUT / 'query.html'}'")
    print(f"    open '{REPO / 'followup' / 'allocation.html'}'   # 上传 tests/data 里的两份 CSV")
    print(f"    open '{REPO / 'followup' / 'completion.html'}'   # 粘贴 tests/data/sample_thread.txt")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\n❌ 自测失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
