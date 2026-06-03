#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ElderAI Survey Platform - 统一启动入口
适老化智能问卷与AI数据分析平台

用法：
    python main.py            # 启动图形化主控台（启动器）
    python main.py --check    # 自检模式：仅校验环境与配置，不打开窗口
    python main.py --builder  # 直接用浏览器打开问卷设计器
    python main.py --survey   # 直接进入老人答题端
    python main.py --analytics# 直接进入数据分析中心
    python main.py --dashboard# 直接进入科交会大屏

设计原则：
    各功能模块采用“惰性导入”，单个模块缺失或报错不影响启动器本身，
    便于分阶段开发与自检。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# 项目根目录（main.py 所在目录），统一以此解析相对路径
BASE_DIR = Path(__file__).resolve().parent
# 把项目根目录加入模块搜索路径，保证 `import modules.xxx` 可用
sys.path.insert(0, str(BASE_DIR))


# ======================================================================
# 配置加载
# ======================================================================
def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载全局配置 config/config.json。

    Args:
        config_path: 配置文件路径，默认 BASE_DIR/config/config.json

    Returns:
        配置字典；文件缺失或解析失败时返回空字典并记录日志。
    """
    if config_path is None:
        config_path = BASE_DIR / "config" / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("配置文件不存在：%s", config_path)
    except json.JSONDecodeError as exc:
        logging.error("配置文件 JSON 解析失败：%s", exc)
    return {}


# ======================================================================
# 日志系统
# ======================================================================
def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """初始化日志系统：同时输出到控制台与 logs/app.log（滚动）。"""
    log_dir = BASE_DIR / config.get("paths", {}).get("logs", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    level = logging.DEBUG if config.get("app", {}).get("debug") else logging.INFO

    logger = logging.getLogger()
    logger.setLevel(level)
    # 避免重复添加 handler（多次调用时）
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    return logger


# ======================================================================
# 启动器主控台（tkinter）
# ======================================================================
class LauncherApp:
    """图形化主控台：一个窗口集中启动 5 大模块。

    各模块按钮点击时才惰性导入对应模块，缺失则弹出友好提示，
    不会导致启动器崩溃。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        import tkinter as tk  # 局部导入，--check 模式无需 GUI 依赖

        self.config = config
        self.log = logging.getLogger("launcher")
        self.tk = tk

        self.root = tk.Tk()
        self.root.title(config.get("app", {}).get("name_zh", "适老化智能问卷平台"))
        self.root.geometry("760x640")
        self.root.configure(bg="#0d1b2a")
        self._build_ui()

    def _build_ui(self) -> None:
        tk = self.tk
        app_name = self.config.get("app", {}).get("name_zh", "适老化智能问卷平台")
        version = self.config.get("app", {}).get("version", "1.0.0")

        tk.Label(
            self.root, text="🧓  " + app_name, font=("Microsoft YaHei", 26, "bold"),
            fg="#e0e1dd", bg="#0d1b2a",
        ).pack(pady=(36, 4))
        tk.Label(
            self.root, text=f"ElderAI Survey Platform  v{version}",
            font=("Arial", 13), fg="#778da9", bg="#0d1b2a",
        ).pack(pady=(0, 28))

        buttons = [
            ("📝  问卷设计器", "管理员可视化设计问卷，生成 questionnaire.json", self.open_builder),
            ("🧓  老人答题端", "适老化大字体、高对比、语音播报答题界面", self.open_survey),
            ("📊  数据分析中心", "查看 / 筛选 / 统计 / 交叉分析 / 导出", self.open_analytics),
            ("📺  科交会大屏", "全屏数据驾驶舱，自动轮播与实时刷新", self.open_dashboard),
            ("🤖  AI分析报告", "生成调查结论、洞察并导出 Excel/PDF/Word", self.open_ai_report),
        ]

        frame = tk.Frame(self.root, bg="#0d1b2a")
        frame.pack(expand=True, fill="both", padx=60)

        for title, desc, handler in buttons:
            btn = tk.Button(
                frame, text=f"{title}\n{desc}", font=("Microsoft YaHei", 15, "bold"),
                fg="#0d1b2a", bg="#e0e1dd", activebackground="#778da9",
                relief="flat", justify="left", anchor="w", cursor="hand2",
                command=handler,
            )
            btn.pack(fill="x", pady=8, ipady=10, ipadx=12)

        tk.Label(
            self.root, text="支持离线运行 · 联网增强 · 本地部署",
            font=("Arial", 10), fg="#415a77", bg="#0d1b2a",
        ).pack(side="bottom", pady=(0, 10))
        self._build_credit(self.root)

    def _build_credit(self, parent) -> None:
        """页脚署名 + 可点击的联系链接。"""
        tk = self.tk
        about = self.config.get("about", {})
        # 课题组/单位名称：优先 about.organization，其次复用 export.company_name，最后兜底
        org = (about.get("organization")
               or self.config.get("export", {}).get("company_name")
               or "课题组")
        author = about.get("author", "Jiacheng Zheng")
        credit = about.get("credit", "使用 Claude Code 辅助开发")
        label = about.get("contact_label", "联系我")
        url = about.get("contact_url", "")

        footer = tk.Frame(parent, bg="#0d1b2a")
        footer.pack(side="bottom", pady=(0, 4))
        tk.Label(footer, text=f"© {org}  ·  {author} {credit}  ·  ",
                 font=("Microsoft YaHei", 10), fg="#778da9", bg="#0d1b2a").pack(side="left")
        link = tk.Label(footer, text=label, font=("Microsoft YaHei", 10, "underline"),
                        fg="#22d3ee", bg="#0d1b2a", cursor="hand2")
        link.pack(side="left")
        if url:
            link.bind("<Button-1>", lambda e: webbrowser.open(url))
            link.bind("<Enter>", lambda e: link.configure(fg="#67e8f9"))
            link.bind("<Leave>", lambda e: link.configure(fg="#22d3ee"))

    # ---- 模块入口（惰性导入，缺失则提示开发中）----
    def _safe_launch(self, importer, label: str) -> None:
        """统一的惰性启动包装：捕获导入/运行异常并提示。"""
        from tkinter import messagebox
        try:
            importer()
        except ImportError as exc:
            self.log.warning("模块尚未就绪 [%s]：%s", label, exc)
            messagebox.showinfo("提示", f"【{label}】模块尚在开发阶段。\n\n详情：{exc}")
        except Exception as exc:  # noqa: BLE001  顶层兜底，避免启动器崩溃
            self.log.exception("启动 [%s] 失败", label)
            messagebox.showerror("错误", f"启动【{label}】失败：\n{exc}")

    def open_builder(self) -> None:
        self._safe_launch(lambda: open_builder_in_browser(self.config), "问卷设计器")

    def open_survey(self) -> None:
        def _run() -> None:
            from modules import survey_gui
            survey_gui.launch(self.config, master=self.root)
        self._safe_launch(_run, "老人答题端")

    def open_analytics(self) -> None:
        def _run() -> None:
            from modules import analytics
            analytics.launch(self.config, master=self.root)
        self._safe_launch(_run, "数据分析中心")

    def open_dashboard(self) -> None:
        def _run() -> None:
            from modules import dashboard
            dashboard.launch(self.config, master=self.root)
        self._safe_launch(_run, "科交会大屏")

    def open_ai_report(self) -> None:
        def _run() -> None:
            from modules import report_generator
            report_generator.launch(self.config, master=self.root)
        self._safe_launch(_run, "AI分析报告")

    def run(self) -> None:
        self.root.mainloop()


# ======================================================================
# 问卷设计器：用默认浏览器打开纯前端 HTML
# ======================================================================
def open_builder_in_browser(config: Dict[str, Any]) -> None:
    """用系统默认浏览器打开 builder/survey_builder.html。"""
    html = BASE_DIR / "builder" / "survey_builder.html"
    if not html.exists():
        raise ImportError(f"设计器文件不存在：{html}")
    webbrowser.open(html.as_uri())
    logging.getLogger("launcher").info("已在浏览器打开问卷设计器：%s", html)


# ======================================================================
# 自检模式
# ======================================================================
def run_self_check(config: Dict[str, Any]) -> int:
    """环境与配置自检，返回 0 表示通过，非 0 表示存在问题。"""
    log = logging.getLogger("self-check")
    problems = 0

    log.info("===== 开始自检 =====")

    # 1) Python 版本
    if sys.version_info < (3, 9):
        log.error("Python 版本过低：%s（需 3.9+）", sys.version.split()[0])
        problems += 1
    else:
        log.info("Python 版本：%s ✓", sys.version.split()[0])

    # 2) 配置
    if not config:
        log.error("配置加载失败")
        problems += 1
    else:
        log.info("配置加载：%s ✓", config.get("app", {}).get("name", "?"))

    # 3) 关键目录
    for key in ("exports", "backup", "logs"):
        d = BASE_DIR / config.get("paths", {}).get(key, key)
        d.mkdir(parents=True, exist_ok=True)
        log.info("目录就绪：%s ✓", d.relative_to(BASE_DIR))

    # 4) 问卷文件
    q_path = BASE_DIR / config.get("paths", {}).get(
        "questionnaire", "survey/questionnaire.json"
    )
    if not q_path.exists():
        log.error("问卷文件缺失：%s", q_path)
        problems += 1
    else:
        try:
            with open(q_path, "r", encoding="utf-8") as f:
                q = json.load(f)
            n = len(q.get("questions", []))
            log.info("问卷加载：《%s》共 %d 题 ✓", q.get("meta", {}).get("title", "?"), n)
        except json.JSONDecodeError as exc:
            log.error("问卷 JSON 解析失败：%s", exc)
            problems += 1

    # 5) tkinter 可用性（仅尝试导入，不创建窗口）
    try:
        import tkinter  # noqa: F401
        log.info("tkinter 可用 ✓")
    except Exception as exc:  # noqa: BLE001
        log.warning("tkinter 不可用（图形界面将无法启动）：%s", exc)

    # 6) 可选依赖巡检（缺失不算错误，仅提示降级）
    optional = {
        "pandas": "数据分析", "numpy": "数值计算", "matplotlib": "图表",
        "openpyxl": "Excel导出", "reportlab": "PDF导出", "docx": "Word导出",
        "pyttsx3": "离线语音", "requests": "联网AI",
    }
    for mod, usage in optional.items():
        try:
            __import__(mod)
            log.info("可选依赖 %-10s 可用 ✓（%s）", mod, usage)
        except ImportError:
            log.warning("可选依赖 %-10s 缺失（%s 将降级或不可用）", mod, usage)

    log.info("===== 自检结束：%s =====", "全部通过" if problems == 0 else f"{problems} 项需处理")
    return problems


# ======================================================================
# 入口
# ======================================================================
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="适老化智能问卷与AI数据分析平台")
    parser.add_argument("--check", action="store_true", help="自检模式，不打开窗口")
    parser.add_argument("--seed", nargs="?", const=200, type=int, metavar="N",
                        help="生成 N 份模拟答卷用于展示（默认 200，会清空已有数据）")
    parser.add_argument("--builder", action="store_true", help="直接打开问卷设计器")
    parser.add_argument("--survey", action="store_true", help="直接进入老人答题端")
    parser.add_argument("--analytics", action="store_true", help="直接进入数据分析中心")
    parser.add_argument("--dashboard", action="store_true", help="直接进入科交会大屏")
    args = parser.parse_args(argv)

    config = load_config()
    setup_logging(config)
    log = logging.getLogger("main")

    if args.check:
        return run_self_check(config)

    if args.seed is not None:
        from modules import report_generator
        count = report_generator.generate_sample_data(config, n=args.seed, reset=True)
        log.info("已生成 %d 份模拟答卷（用于展示）。", count)
        return 0

    # 直达模式
    try:
        if args.builder:
            open_builder_in_browser(config)
            return 0
        if args.survey:
            from modules import survey_gui
            survey_gui.launch(config)
            return 0
        if args.analytics:
            from modules import analytics
            analytics.launch(config)
            return 0
        if args.dashboard:
            from modules import dashboard
            dashboard.launch(config)
            return 0
    except ImportError as exc:
        log.error("该模块尚未就绪：%s", exc)
        return 1

    # 默认：图形化启动器
    try:
        app = LauncherApp(config)
    except Exception as exc:  # noqa: BLE001
        log.error("无法创建图形界面（可能无显示环境）：%s", exc)
        log.info("可使用 `python main.py --check` 进行无界面自检。")
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
