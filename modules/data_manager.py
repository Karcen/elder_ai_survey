# -*- coding: utf-8 -*-
"""
data_manager.py · 数据层

职责：
    1. 统一解析项目路径与配置；
    2. 答卷数据「CSV + SQLite」双重存储，互为备份与导出；
    3. 答卷读取、筛选、删除；
    4. 答卷扁平化为 pandas.DataFrame（供统计/大屏/AI 使用）；
    5. 自动备份；
    6. 生成模拟答卷（科交会展示 / 测试用）。

所有方法均带异常处理与日志，CSV 与 SQLite 任一可用即可工作。
"""
from __future__ import annotations

import csv
import itertools
import json
import logging
import random
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("data_manager")

# 项目根目录：modules/ 的上一级
BASE_DIR = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# 配置加载
# ----------------------------------------------------------------------
def load_config(base_dir: Path = BASE_DIR) -> Dict[str, Any]:
    """加载 config/config.json；失败时返回空字典。"""
    path = base_dir / "config" / "config.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.error("配置文件不存在：%s", path)
    except json.JSONDecodeError as exc:
        log.error("配置文件解析失败：%s", exc)
    return {}


# ----------------------------------------------------------------------
# 答卷记录数据结构（约定）
#   {
#     "response_id": str,
#     "questionnaire_id": str,
#     "started_at": "YYYY-MM-DD HH:MM:SS",
#     "finished_at": "YYYY-MM-DD HH:MM:SS",
#     "duration_seconds": float,
#     "completed": bool,
#     "answers": { "Q1": value, "Q7": [v1, v2], ... }
#   }
# ----------------------------------------------------------------------
RESERVED_COLUMNS = [
    "response_id", "questionnaire_id", "started_at",
    "finished_at", "duration_seconds", "completed",
]
MULTI_SEP = "|"  # 多选答案在 CSV 中的分隔符


class DataManager:
    """答卷数据管理器：CSV + SQLite 双重存储。"""

    # 进程级自增计数器，保证同一毫秒内生成的编号也唯一
    _id_counter = itertools.count(1)

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 base_dir: Path = BASE_DIR,
                 question_ids: Optional[List[str]] = None) -> None:
        self.config = config or load_config(base_dir)
        self.base_dir = base_dir
        paths = self.config.get("paths", {})
        self.csv_path = base_dir / paths.get("answers_csv", "survey/answers.csv")
        self.db_path = base_dir / paths.get("database", "database/survey.db")
        self.backup_dir = base_dir / paths.get("backup", "backup")
        # 用于 CSV 列顺序；可由问卷题目 id 提供，缺省则按出现顺序累积
        self.question_ids: List[str] = list(question_ids or [])
        self._lock = threading.Lock()  # 多线程（答题端自动保存）安全

        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ---------------- SQLite ----------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS responses (
                        response_id      TEXT PRIMARY KEY,
                        questionnaire_id TEXT,
                        started_at       TEXT,
                        finished_at      TEXT,
                        duration_seconds REAL,
                        completed        INTEGER,
                        answers_json     TEXT,
                        created_at       TEXT
                    )
                    """
                )
        except sqlite3.Error as exc:
            log.error("初始化数据库失败：%s", exc)

    # ---------------- 写入 ----------------
    def save_response(self, record: Dict[str, Any]) -> bool:
        """保存一份答卷到 SQLite 与 CSV（双重存储）。返回是否成功。"""
        record = self._normalize_record(record)
        ok_db = self._save_to_db(record)
        ok_csv = self._append_to_csv(record)
        if ok_db or ok_csv:
            log.info("已保存答卷 %s（db=%s csv=%s）", record["response_id"], ok_db, ok_csv)
            return True
        log.error("答卷 %s 保存失败（db 与 csv 均失败）", record.get("response_id"))
        return False

    def _normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        rec = dict(record)
        rec.setdefault("response_id", self.new_response_id())
        rec.setdefault("questionnaire_id", "")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rec.setdefault("started_at", now)
        rec.setdefault("finished_at", now)
        rec.setdefault("duration_seconds", 0.0)
        rec.setdefault("completed", True)
        rec.setdefault("answers", {})
        # 累积题目 id 顺序，用于 CSV 列
        for qid in rec["answers"]:
            if qid not in self.question_ids:
                self.question_ids.append(qid)
        return rec

    def _save_to_db(self, rec: Dict[str, Any]) -> bool:
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO responses
                       (response_id, questionnaire_id, started_at, finished_at,
                        duration_seconds, completed, answers_json, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        rec["response_id"], rec["questionnaire_id"], rec["started_at"],
                        rec["finished_at"], float(rec["duration_seconds"]),
                        1 if rec["completed"] else 0,
                        json.dumps(rec["answers"], ensure_ascii=False),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            return True
        except sqlite3.Error as exc:
            log.error("写入 SQLite 失败：%s", exc)
            return False

    def _append_to_csv(self, rec: Dict[str, Any]) -> bool:
        try:
            with self._lock:
                columns = RESERVED_COLUMNS + self.question_ids
                new_file = not self.csv_path.exists()
                # 若题目列有新增，重写表头需要整体改写；这里采用“宽表追加”策略：
                # 为简单与稳健，始终按当前 columns 读旧数据并整体重写。
                rows = []
                if not new_file:
                    # 按 response_id 去重（与 SQLite 的 INSERT OR REPLACE 语义一致）
                    rows = [r for r in self._read_csv_rows()
                            if r.get("response_id") != rec["response_id"]]
                rows.append(self._record_to_flat(rec))
                with open(self.csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
                    writer.writeheader()
                    for r in rows:
                        writer.writerow({c: r.get(c, "") for c in columns})
            return True
        except OSError as exc:
            log.error("写入 CSV 失败：%s", exc)
            return False

    def _record_to_flat(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """把答卷记录扁平化为一行（多选用 | 连接）。"""
        flat = {
            "response_id": rec["response_id"],
            "questionnaire_id": rec["questionnaire_id"],
            "started_at": rec["started_at"],
            "finished_at": rec["finished_at"],
            "duration_seconds": rec["duration_seconds"],
            "completed": 1 if rec["completed"] else 0,
        }
        for qid, val in rec["answers"].items():
            flat[qid] = MULTI_SEP.join(map(str, val)) if isinstance(val, list) else val
        return flat

    # ---------------- 读取 ----------------
    def _read_csv_rows(self) -> List[Dict[str, Any]]:
        if not self.csv_path.exists():
            return []
        try:
            with open(self.csv_path, "r", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        except OSError as exc:
            log.error("读取 CSV 失败：%s", exc)
            return []

    def load_responses(self) -> List[Dict[str, Any]]:
        """读取全部答卷（优先 SQLite，失败回退 CSV）。返回标准记录列表。"""
        records = self._load_from_db()
        if records:
            return records
        log.warning("SQLite 无数据或不可用，回退读取 CSV。")
        return self._load_from_csv()

    def _load_from_db(self) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                cur = conn.execute("SELECT * FROM responses ORDER BY started_at")
                out = []
                for row in cur.fetchall():
                    answers = json.loads(row["answers_json"] or "{}")
                    for qid in answers:
                        if qid not in self.question_ids:
                            self.question_ids.append(qid)
                    out.append({
                        "response_id": row["response_id"],
                        "questionnaire_id": row["questionnaire_id"],
                        "started_at": row["started_at"],
                        "finished_at": row["finished_at"],
                        "duration_seconds": row["duration_seconds"],
                        "completed": bool(row["completed"]),
                        "answers": answers,
                    })
                return out
        except sqlite3.Error as exc:
            log.error("读取 SQLite 失败：%s", exc)
            return []

    def _load_from_csv(self) -> List[Dict[str, Any]]:
        out = []
        for row in self._read_csv_rows():
            answers = {}
            for k, v in row.items():
                if k in RESERVED_COLUMNS or v in ("", None):
                    continue
                answers[k] = v.split(MULTI_SEP) if isinstance(v, str) and MULTI_SEP in v else v
            out.append({
                "response_id": row.get("response_id", ""),
                "questionnaire_id": row.get("questionnaire_id", ""),
                "started_at": row.get("started_at", ""),
                "finished_at": row.get("finished_at", ""),
                "duration_seconds": float(row.get("duration_seconds") or 0),
                "completed": str(row.get("completed")) in ("1", "True", "true"),
                "answers": answers,
            })
        return out

    def load_dataframe(self):
        """把全部答卷扁平化为 pandas.DataFrame（一行一份，列为题目 id）。

        多选题展开为「| 连接的字符串」；缺失为空。pandas 缺失时抛 ImportError。
        """
        import pandas as pd  # 延迟导入，缺失则由调用方处理
        records = self.load_responses()
        rows = [self._record_to_flat(r) for r in records]
        columns = RESERVED_COLUMNS + [q for q in self.question_ids]
        df = pd.DataFrame(rows)
        # 保证列齐全且有序
        for c in columns:
            if c not in df.columns:
                df[c] = None
        return df[columns] if not df.empty else df

    # ---------------- 删除 / 统计 ----------------
    def delete_response(self, response_id: str) -> bool:
        ok = False
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM responses WHERE response_id=?", (response_id,))
            ok = True
        except sqlite3.Error as exc:
            log.error("从 SQLite 删除失败：%s", exc)
        # 同步重写 CSV
        try:
            rows = [r for r in self._read_csv_rows() if r.get("response_id") != response_id]
            columns = RESERVED_COLUMNS + self.question_ids
            with open(self.csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                for r in rows:
                    writer.writerow({c: r.get(c, "") for c in columns})
            ok = True
        except OSError as exc:
            log.error("同步删除 CSV 失败：%s", exc)
        if ok:
            log.info("已删除答卷 %s", response_id)
        return ok

    def count(self) -> int:
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) AS n FROM responses").fetchone()["n"]
        except sqlite3.Error:
            return len(self._read_csv_rows())

    def clear_all(self) -> None:
        """清空所有答卷（先备份）。谨慎使用。"""
        self.backup()
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM responses")
        except sqlite3.Error as exc:
            log.error("清空 SQLite 失败：%s", exc)
        if self.csv_path.exists():
            self.csv_path.unlink()
        log.warning("已清空全部答卷（已备份）。")

    # ---------------- 备份 ----------------
    def backup(self) -> Optional[Path]:
        """把当前 CSV 与 DB 备份到 backup/ 目录，返回备份子目录。"""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"backup_{stamp}"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            if self.csv_path.exists():
                (dest / "answers.csv").write_bytes(self.csv_path.read_bytes())
            if self.db_path.exists():
                (dest / "survey.db").write_bytes(self.db_path.read_bytes())
            log.info("已备份到 %s", dest)
            return dest
        except OSError as exc:
            log.error("备份失败：%s", exc)
            return None

    # ---------------- 工具 ----------------
    @staticmethod
    def new_response_id() -> str:
        # 时间戳(到微秒) + 自增序号，杜绝批量生成时的编号碰撞
        seq = next(DataManager._id_counter)
        return "R" + datetime.now().strftime("%Y%m%d%H%M%S%f") + f"{seq:05d}"

    # ---------------- 模拟数据（展示 / 测试） ----------------
    def simulate_responses(self, questionnaire, n: int = 200,
                           days_back: int = 14) -> int:
        """根据问卷结构生成 n 份带逻辑跳转的模拟答卷并保存。返回成功条数。

        Args:
            questionnaire: Questionnaire 实例（来自 questionnaire_engine）
            n: 生成份数
            days_back: 时间分散在最近多少天内
        """
        saved = 0
        for _ in range(n):
            rec = self._make_simulated_record(questionnaire, days_back)
            if self.save_response(rec):
                saved += 1
        log.info("已生成模拟答卷 %d/%d 份", saved, n)
        return saved

    def _make_simulated_record(self, questionnaire, days_back: int) -> Dict[str, Any]:
        """按问卷的逻辑跳转走一遍，随机但带倾向地作答。"""
        answers: Dict[str, Any] = {}
        qid = questionnaire.first_id()
        steps = 0
        while qid and qid != "END" and steps < len(questionnaire.questions) + 5:
            q = questionnaire.get(qid)
            if not q:
                break
            ans = _simulate_answer(q)
            if ans is not None:
                answers[qid] = ans
            qid = questionnaire.next_id(qid, ans)
            steps += 1

        start = datetime.now() - timedelta(
            days=random.uniform(0, days_back), hours=random.uniform(0, 12))
        duration = random.uniform(120, 600)  # 2~10 分钟
        finished = start + timedelta(seconds=duration)
        completed = random.random() > 0.08  # 约 92% 完成率
        return {
            "response_id": self.new_response_id(),
            "questionnaire_id": questionnaire.meta.get("id", ""),
            "started_at": start.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(duration, 1),
            "completed": completed,
            "answers": answers,
        }


# 各题型的模拟作答（带轻微倾向，让分布更真实）
def _simulate_answer(q: Dict[str, Any]) -> Any:
    qtype = q.get("type")
    options = q.get("options", [])
    if qtype in ("single", "yesno"):
        if not options:
            return None
        weights = _skew_weights(len(options))
        return random.choices([o["value"] for o in options], weights=weights)[0]
    if qtype == "multiple":
        if not options:
            return None
        k = random.randint(1, max(1, min(3, len(options))))
        return random.sample([o["value"] for o in options], k)
    if qtype == "rating":
        scale = int(q.get("scale", 5))
        # 偏中高分
        return random.choices(range(1, scale + 1),
                              weights=[1, 2, 3, 4, 3][:scale] or None)[0]
    if qtype == "number":
        lo, hi = int(q.get("min", 0)), int(q.get("max", 10))
        return random.randint(lo, max(lo, min(hi, lo + 5)))
    if qtype == "date":
        return (datetime.now() - timedelta(days=random.randint(0, 3650))).strftime("%Y-%m-%d")
    if qtype == "text":
        samples = ["希望字体更大一些", "操作能再简单点就好", "担心被骗", "挺好的没什么意见",
                   "希望有人能教教我们", "语音功能很需要", ""]
        return random.choice(samples)
    return None


def _skew_weights(n: int) -> List[int]:
    """生成一组带倾向的权重，避免均匀分布显得呆板。"""
    base = list(range(n, 0, -1))  # 前面的选项略多
    random.shuffle(base)
    return [b + 1 for b in base]
