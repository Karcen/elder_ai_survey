#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV → JSON 转换工具（随访子系统）。

学生名单与受试者名单都通过 CSV 上传，本脚本把它们转成统一的 JSON。
纯标准库，无第三方依赖。列名做容错别名映射，兼容中英文表头与 Excel 导出。

用法：
    python csv_to_json.py <输入.csv> <输出.json> [--kind students|subjects]

    --kind 可省略：省略时按原样转换（保留所有列）；
    指定时会把列名规范化为标准字段，并补全缺失字段。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

# 列名别名 → 标准字段名（全部转小写、去空格后匹配）
ALIASES: Dict[str, str] = {
    # 学生
    "student_id": "student_id", "studentid": "student_id", "学生id": "student_id",
    "工号": "student_id", "编号": "student_id",
    "student_name": "student_name", "studentname": "student_name",
    "学生": "student_name", "学生姓名": "student_name",
    # 受试者
    "subject_id": "subject_id", "subjectid": "subject_id", "受试者id": "subject_id",
    "subject_name": "subject_name", "subjectname": "subject_name",
    "受试者": "subject_name", "受试者姓名": "subject_name", "老人姓名": "subject_name",
    # 通用
    "id": "id", "name": "name", "姓名": "name", "名字": "name",
    "phone": "phone", "tel": "phone", "telephone": "phone", "mobile": "phone",
    "电话": "phone", "手机": "phone", "手机号": "phone", "联系电话": "phone",
    "email": "email", "邮箱": "email", "e-mail": "email",
    "note": "note", "备注": "note", "remark": "note", "remarks": "note",
}


def _norm(key: str) -> str:
    """把表头规范化：去空格、去 BOM、转小写，再查别名表。"""
    k = (key or "").strip().lstrip("﻿").lower()
    return ALIASES.get(k, k)


def _read_rows(csv_path: Path) -> List[Dict[str, str]]:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for raw in reader:
            row = {}
            for k, v in raw.items():
                if k is None:
                    continue
                row[_norm(k)] = (v or "").strip()
            # 跳过完全空白的行
            if any(row.values()):
                rows.append(row)
    return rows


def _coerce(rows: List[Dict[str, str]], kind: str) -> List[Dict[str, str]]:
    """按类型规范化为标准字段，补全缺失 id，统一 *_name / phone。"""
    name_key = f"{kind[:-1]}_name"  # students→student_name, subjects→subject_name
    id_key = f"{kind[:-1]}_id"
    prefix = "stu" if kind == "students" else "sub"
    out = []
    for i, row in enumerate(rows, 1):
        name = row.get(name_key) or row.get("name") or ""
        sid = row.get(id_key) or row.get("id") or f"{prefix}_{i:03d}"
        rec = {
            id_key: sid,
            name_key: name,
            "phone": row.get("phone", ""),
        }
        if kind == "students" and row.get("email"):
            rec["email"] = row["email"]
        if kind == "subjects":
            rec["note"] = row.get("note", "")
        out.append(rec)
    return out


def csv_to_json(src: str, dst: str, kind: str | None = None) -> int:
    """转换 CSV 为 JSON，返回记录数。"""
    src_p, dst_p = Path(src), Path(dst)
    if not src_p.exists():
        raise FileNotFoundError(f"找不到 CSV 文件：{src_p}")
    rows = _read_rows(src_p)
    if kind in ("students", "subjects"):
        rows = _coerce(rows, kind)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    with open(dst_p, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return len(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="CSV → JSON 转换（随访子系统）")
    p.add_argument("input", help="输入 CSV 路径")
    p.add_argument("output", help="输出 JSON 路径")
    p.add_argument("--kind", choices=["students", "subjects"], default=None,
                   help="规范化为学生/受试者标准字段（省略则原样转换）")
    args = p.parse_args(argv)
    try:
        n = csv_to_json(args.input, args.output, args.kind)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 转换失败：{exc}", file=sys.stderr)
        return 1
    print(f"✅ 转换完成：{args.output}（共 {n} 条记录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
