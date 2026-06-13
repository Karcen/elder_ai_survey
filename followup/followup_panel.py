#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随访管理面板（tkinter）— 任务5：一切从 main GUI 启动。

提供一个独立窗口，把随访全流程串起来：
    ① 上传学生 CSV → 转 JSON
    ② 上传受试者 CSV → 转 JSON
    ③ 打开分配系统（allocation.html）
    ④ 导入分配结果（allocation.json）
    ⑤ 填写短信模板 → 生成学生查询页（query.html）→ 打开
    ⑥ 打开完成情况统计（completion.html）

由 main.py 的「回访管理」卡片调用：followup_panel.launch(config, master)。
仅依赖标准库（tkinter / subprocess / shutil / webbrowser）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# 与 main.py 的启动器一致的配色（亮/暗）
THEMES = {
    "light": {"bg": "#f5f7fa", "card": "#ffffff", "border": "#e2e8f0",
              "title": "#1f2937", "muted": "#64748b", "accent": "#2563eb"},
    "dark": {"bg": "#0d1320", "card": "#151c2c", "border": "#26324a",
             "title": "#e6ebf3", "muted": "#9aa7bd", "accent": "#4f8cff"},
}

STEPS = [
    ("①", "上传学生名单 CSV", "选择学生 CSV，自动转换为 students.json", "upload_students"),
    ("②", "上传受试者名单 CSV", "选择受试者 CSV，自动转换为 subjects.json", "upload_subjects"),
    ("③", "打开分配系统", "在浏览器里平均分配、微调，导出 allocation.json", "open_allocation"),
    ("④", "导入分配结果", "选择导出的 allocation.json，存入 data/", "import_allocation"),
    ("⑤", "填短信 · 生成查询页", "填写统一短信模板，生成并打开学生查询页", "make_query"),
    ("⑥", "打开完成情况统计", "粘贴接龙文本，统计谁没发", "open_completion"),
]


class FollowupPanel:
    def __init__(self, config: Dict[str, Any], master=None) -> None:
        import tkinter as tk
        self.tk = tk
        self.config = config or {}
        theme = self.config.get("ui", {}).get("theme", "light")
        self.c = THEMES.get(theme, THEMES["light"])

        self.win = tk.Toplevel(master) if master else tk.Tk()
        self.win.title("随访管理")
        self.win.configure(bg=self.c["bg"])
        self.win.minsize(560, 600)
        self._build()

    # ---- UI ----
    def _build(self) -> None:
        tk, c = self.tk, self.c
        head = tk.Frame(self.win, bg=c["card"])
        head.pack(fill="x")
        tk.Label(head, text="📞  随访管理", font=("Microsoft YaHei", 18, "bold"),
                 bg=c["card"], fg=c["title"]).pack(anchor="w", padx=22, pady=(20, 2))
        tk.Label(head, text="把完成问卷的受试者分配给学生 · 查询 · 完成统计",
                 font=("Microsoft YaHei", 10), bg=c["card"], fg=c["muted"]).pack(anchor="w", padx=22, pady=(0, 18))

        body = tk.Frame(self.win, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=14)
        for icon, title, desc, handler in STEPS:
            self._step_card(body, icon, title, desc, getattr(self, handler))

        self.status = tk.Label(self.win, text="就绪", anchor="w",
                               font=("Microsoft YaHei", 10), bg=c["bg"], fg=c["muted"])
        self.status.pack(fill="x", side="bottom", padx=22, pady=(0, 12))

    def _step_card(self, parent, icon, title, desc, handler) -> None:
        tk, c = self.tk, self.c
        card = tk.Frame(parent, bg=c["card"], highlightthickness=1,
                        highlightbackground=c["border"], cursor="hand2")
        card.pack(fill="x", pady=5)
        ic = tk.Label(card, text=icon, font=("Arial", 20), bg=c["card"], fg=c["accent"])
        ic.pack(side="left", padx=(16, 10), pady=12)
        txt = tk.Frame(card, bg=c["card"])
        txt.pack(side="left", fill="both", expand=True, pady=10)
        t = tk.Label(txt, text=title, font=("Microsoft YaHei", 13, "bold"),
                     bg=c["card"], fg=c["title"], anchor="w")
        t.pack(anchor="w")
        d = tk.Label(txt, text=desc, font=("Microsoft YaHei", 10),
                     bg=c["card"], fg=c["muted"], anchor="w")
        d.pack(anchor="w")
        arr = tk.Label(card, text="›", font=("Arial", 22, "bold"), bg=c["card"], fg=c["accent"])
        arr.pack(side="right", padx=16)
        for w in (card, ic, txt, t, d, arr):
            w.bind("<Button-1>", lambda e, h=handler: h())

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)
        self.win.update_idletasks()

    def _info(self, title, msg):
        from tkinter import messagebox
        messagebox.showinfo(title, msg, parent=self.win)

    def _error(self, title, msg):
        from tkinter import messagebox
        messagebox.showerror(title, msg, parent=self.win)

    # ---- 步骤处理 ----
    def _run_convert(self, src: Path, kind: str) -> int:
        """调用 csv_to_json.py，返回记录数（失败抛异常）。"""
        dst = DATA / f"{kind}.csv"
        DATA.mkdir(parents=True, exist_ok=True)
        if Path(src).resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        out_json = DATA / f"{kind}.json"
        proc = subprocess.run(
            [sys.executable, str(HERE / "csv_to_json.py"), str(dst), str(out_json), "--kind", kind],
            capture_output=True, text=True, cwd=str(HERE),
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "转换失败")
        import json
        return len(json.loads(out_json.read_text(encoding="utf-8")))

    def _upload(self, kind: str, label: str) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self.win, title=f"选择{label} CSV",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            n = self._run_convert(Path(path), kind)
            self._set_status(f"✅ {label}已转换：{n} 条 → data/{kind}.json")
            self._info("转换完成", f"{label}已转换为 JSON，共 {n} 条记录。\n\n保存于：\n{DATA / (kind + '.json')}")
        except Exception as exc:  # noqa: BLE001
            self._error("转换失败", str(exc))

    def upload_students(self) -> None:
        self._upload("students", "学生名单")

    def upload_subjects(self) -> None:
        self._upload("subjects", "受试者名单")

    def open_allocation(self) -> None:
        self._open_html(HERE / "allocation.html", "分配系统")

    def import_allocation(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self.win, title="选择 allocation.json",
            initialdir=str(Path.home() / "Downloads"),
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            import json
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            DATA.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, DATA / "allocation.json")
            n = len(data.get("assignments", []))
            un = len(data.get("unassigned", []))
            tip = f"已导入分配结果：{n} 条任务" + (f"，{un} 人未分配" if un else "")
            self._set_status("✅ " + tip)
            self._info("导入完成", tip + "\n\n保存于：\n" + str(DATA / "allocation.json"))
        except Exception as exc:  # noqa: BLE001
            self._error("导入失败", f"不是有效的 allocation.json：\n{exc}")

    def make_query(self) -> None:
        alloc = DATA / "allocation.json"
        if not alloc.exists():
            self._error("缺少分配结果", "请先完成「④ 导入分配结果」。")
            return
        self._sms_dialog()

    def _sms_dialog(self) -> None:
        """弹出短信模板编辑框，确认后生成 query.html。"""
        tk, c = self.tk, self.c
        dlg = tk.Toplevel(self.win)
        dlg.title("填写短信内容")
        dlg.configure(bg=c["bg"])
        dlg.transient(self.win)
        dlg.grab_set()
        tk.Label(dlg, text="统一短信模板（用 {姓名} 作占位，生成时自动替换为受试者姓名）",
                 font=("Microsoft YaHei", 11), bg=c["bg"], fg=c["title"]).pack(anchor="w", padx=18, pady=(18, 8))
        txt = tk.Text(dlg, width=54, height=6, font=("Microsoft YaHei", 11),
                      wrap="word", bg=c["card"], fg=c["title"], insertbackground=c["title"],
                      highlightthickness=1, highlightbackground=c["border"], relief="flat")
        txt.pack(padx=18)
        tpl_file = DATA / "sms_template.txt"
        default = (tpl_file.read_text(encoding="utf-8") if tpl_file.exists()
                   else "{姓名}您好，我是适老化调研项目的随访人员，想跟您确认问卷回访事宜，方便时请回复，谢谢！")
        txt.insert("1.0", default)

        btns = tk.Frame(dlg, bg=c["bg"])
        btns.pack(fill="x", padx=18, pady=16)

        def confirm():
            content = txt.get("1.0", "end").strip()
            if not content:
                self._error("内容为空", "请填写短信内容。")
                return
            tpl_file.parent.mkdir(parents=True, exist_ok=True)
            tpl_file.write_text(content, encoding="utf-8")
            dlg.destroy()
            self._generate_query(tpl_file)

        tk.Button(btns, text="生成并打开查询页", command=confirm,
                  font=("Microsoft YaHei", 11, "bold"), bg=c["accent"], fg="#ffffff",
                  relief="flat", padx=16, pady=6, cursor="hand2").pack(side="right")
        tk.Button(btns, text="取消", command=dlg.destroy,
                  font=("Microsoft YaHei", 11), bg=c["card"], fg=c["muted"],
                  relief="flat", padx=14, pady=6, cursor="hand2").pack(side="right", padx=(0, 10))

    def _generate_query(self, tpl_file: Path) -> None:
        out = HERE / "query.html"
        proc = subprocess.run(
            [sys.executable, str(HERE / "generate_query.py"),
             "--allocation", str(DATA / "allocation.json"),
             "--sms-file", str(tpl_file), "--out", str(out)],
            capture_output=True, text=True, cwd=str(HERE),
        )
        if proc.returncode != 0:
            self._error("生成失败", proc.stderr.strip() or "未知错误")
            return
        self._set_status("✅ 已生成 query.html 并在浏览器打开")
        webbrowser.open(out.as_uri())

    def open_completion(self) -> None:
        self._open_html(HERE / "completion.html", "完成情况统计")

    def _open_html(self, path: Path, label: str) -> None:
        if not path.exists():
            self._error("文件缺失", f"{label}文件不存在：\n{path}")
            return
        webbrowser.open(path.as_uri())
        self._set_status(f"已在浏览器打开{label}")

    def run(self) -> None:
        self.win.mainloop()


def launch(config: Optional[Dict[str, Any]] = None, master=None) -> FollowupPanel:
    """供 main.py 调用的入口。"""
    panel = FollowupPanel(config or {}, master=master)
    if master is None:
        panel.run()
    return panel


if __name__ == "__main__":
    launch()
