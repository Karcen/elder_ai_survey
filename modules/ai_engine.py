# -*- coding: utf-8 -*-
"""
ai_engine.py · AI 分析引擎

两种模式（由 config.ai.mode 控制：auto / online / offline）：
    离线：基于统计结果的规则分析（始终可用，零依赖）；
    联网：调用 LLM（OpenAI / DeepSeek / Qwen / OpenRouter，均为 OpenAI 兼容接口）。
          联网失败、超时、无 Key 时**自动降级**到离线规则分析。

产出：
    调查结论、用户画像、趋势预测、改进建议、风险提示，
    以及 ≥10 条「智能洞察」。所有结果均为结构化 dict / list，
    供大屏与报告模块复用。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules.analytics import Analyzer
from modules.questionnaire_engine import Questionnaire

log = logging.getLogger("ai_engine")

OPTION_TYPES = {"single", "multiple", "yesno"}


class AIEngine:
    """问卷数据的 AI 分析引擎（离线规则 + 联网 LLM）。"""

    def __init__(self, config: Dict[str, Any], questionnaire: Questionnaire,
                 analyzer: Analyzer) -> None:
        self.config = config or {}
        self.q = questionnaire
        self.analyzer = analyzer
        self.ai_conf = self.config.get("ai", {})
        self.mode = self.ai_conf.get("mode", "auto")
        self.min_insights = int(self.ai_conf.get("min_insights", 10))

    # ==================================================================
    # 对外主接口
    # ==================================================================
    def generate_report(self) -> Dict[str, Any]:
        """生成完整分析报告（结构化）。联网失败自动降级离线。"""
        offline = self._offline_report()
        if self._should_try_online():
            online = self._online_report(offline)
            if online:
                return online
        return offline

    def generate_insights(self) -> List[str]:
        """生成 ≥min_insights 条洞察（供大屏滚动展示）。"""
        return self.generate_report().get("insights", [])

    # ==================================================================
    # 离线规则分析
    # ==================================================================
    def _offline_report(self) -> Dict[str, Any]:
        s = self.analyzer.summary()
        stats = self.analyzer.all_question_stats()
        report = {
            "title": self.q.title() + " · AI 分析报告",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "offline",
            "summary": s,
            "conclusions": self._conclusions(s, stats),
            "persona": self._persona(stats),
            "trends": self._trends(s),
            "suggestions": self._suggestions(stats),
            "risks": self._risks(stats),
            "crosstab_findings": self._crosstab_findings(),
            "question_stats": stats,
        }
        report["insights"] = self._compose_insights(report)
        return report

    # ---- 调查结论 ----
    def _conclusions(self, s: Dict[str, Any], stats: List[Dict[str, Any]]) -> List[str]:
        out = [
            f"本次共回收问卷 {s['total']} 份，其中完整作答 {s['completed']} 份，"
            f"完成率 {s['completion_rate']*100:.1f}%，平均填写时长 {s['avg_duration_text']}。"
        ]
        for st in stats:
            if st.get("type") in ("single", "yesno") and st.get("top") and st["answered"]:
                top = st["top"]
                if top["ratio"] >= 0.6:
                    out.append(f"在「{st['title'][:24]}」上，{top['ratio']*100:.0f}% 的受访者选择「{top['label']}」，倾向明显。")
                elif top["ratio"] <= 0.45 and len(st.get("distribution", [])) >= 2:
                    out.append(f"「{st['title'][:24]}」的回答较为分散，最高项「{top['label']}」也仅占 {top['ratio']*100:.0f}%。")
            elif st.get("type") == "rating" and st.get("n"):
                level = "偏高" if st["mean"] >= st.get("scale", 5) * 0.7 else (
                        "偏低" if st["mean"] <= st.get("scale", 5) * 0.45 else "中等")
                out.append(f"「{st['title'][:24]}」平均得分 {st['mean']}（满分 {st.get('scale',5)}），总体{level}。")
        return out

    # ---- 用户画像 ----
    def _persona(self, stats: List[Dict[str, Any]]) -> List[str]:
        out: List[str] = []
        singles = [st for st in stats if st.get("type") in ("single", "yesno") and st.get("top")]
        if singles:
            desc = "、".join(f"{st['top']['label']}（{st['title'][:10]}）"
                             for st in singles[:4] if st.get("answered"))
            out.append("典型受访者画像：" + desc + "。")
        ratings = [st for st in stats if st.get("type") == "rating" and st.get("n")]
        if ratings:
            avg = sum(st["mean"] for st in ratings) / len(ratings)
            attitude = "对智能技术总体接受度较高" if avg >= 3.5 else "对智能技术仍存在较多顾虑"
            out.append(f"综合各项评分（均值约 {avg:.1f}），该群体{attitude}。")
        if not out:
            out.append("样本量较小，用户画像有待更多数据支撑。")
        return out

    # ---- 趋势预测 ----
    def _trends(self, s: Dict[str, Any]) -> List[str]:
        by_date = s.get("by_date", {})
        out: List[str] = []
        if len(by_date) >= 2:
            counts = list(by_date.values())
            avg_per_day = sum(counts) / len(counts)
            recent = counts[-1]
            direction = "上升" if recent > avg_per_day else ("回落" if recent < avg_per_day else "平稳")
            out.append(f"近 {len(by_date)} 天日均回收 {avg_per_day:.1f} 份，最新一天为 {recent} 份，呈{direction}态势。")
            out.append(f"按当前速度预计未来一周可新增约 {avg_per_day*7:.0f} 份问卷。")
        else:
            out.append("数据采集时间较短，趋势预测需积累更多每日数据。")
        if s["completion_rate"] < 0.85 and s["total"] > 0:
            out.append(f"完成率为 {s['completion_rate']*100:.0f}%，存在中途退出，建议优化题量或增加引导以提升完成率。")
        return out

    # ---- 改进建议 ----
    def _suggestions(self, stats: List[Dict[str, Any]]) -> List[str]:
        out: List[str] = []
        # 多选题中“希望改进/困难”类的高频项
        for st in stats:
            if st.get("type") == "multiple" and st.get("distribution"):
                tops = [d for d in st["distribution"] if d["count"] > 0][:3]
                if tops:
                    items = "、".join(f"{d['label']}（{d['ratio']*100:.0f}%）" for d in tops)
                    out.append(f"针对「{st['title'][:20]}」，高频项为：{items}，应优先改进。")
        # 低分评分题
        for st in stats:
            if st.get("type") == "rating" and st.get("n") and st["mean"] <= st.get("scale", 5) * 0.5:
                out.append(f"「{st['title'][:20]}」评分偏低（{st['mean']}），建议作为重点优化方向。")
        if not out:
            out.append("建议结合开放题反馈，持续优化适老化界面的字体、操作与防骗提示。")
        out.append("普遍建议：加大字体与按钮、简化操作路径、加强语音引导与防诈骗提醒、提供线下专人帮扶。")
        return out

    # ---- 风险提示 ----
    def _risks(self, stats: List[Dict[str, Any]]) -> List[str]:
        out: List[str] = []
        for st in stats:
            title = st.get("title", "")
            if st.get("type") == "rating" and st.get("n"):
                if ("诈骗" in title or "防范" in title) and st["mean"] <= st.get("scale", 5) * 0.6:
                    out.append(f"防诈骗意识评分偏低（{st['mean']}），老年群体存在较高受骗风险，需加强宣教。")
            if st.get("type") in ("single", "yesno"):
                for d in st.get("distribution", []):
                    if d["label"] in ("干脆放弃不用", "完全抗拒", "从来不用") and d["ratio"] >= 0.2:
                        out.append(f"「{title[:18]}」中有 {d['ratio']*100:.0f}% 选择「{d['label']}」，存在数字鸿沟扩大的风险。")
        if not out:
            out.append("暂未发现显著风险项，仍需关注独居与高龄群体的数字弱势问题。")
        return out

    # ---- 交叉发现 ----
    def _crosstab_findings(self) -> List[str]:
        out: List[str] = []
        for a, b in self.analyzer.suggested_crosstabs():
            ct = self.analyzer.crosstab(a, b)
            if not ct or ct["total"] < 5:
                continue
            # 找出行内占比最突出的单元
            best = None
            for i, rl in enumerate(ct["row_labels"]):
                rt = ct["row_totals"][i]
                if rt < 2:
                    continue
                for j, cl in enumerate(ct["col_labels"]):
                    ratio = ct["matrix"][i][j] / rt
                    if best is None or ratio > best[0]:
                        best = (ratio, rl, cl)
            if best and best[0] >= 0.5:
                out.append(f"交叉发现：「{ct['row_title'][:14]}」为「{best[1]}」的群体中，"
                           f"有 {best[0]*100:.0f}% 在「{ct['col_title'][:14]}」上选择「{best[2]}」。")
            if len(out) >= 3:
                break
        return out

    # ---- 汇总洞察（≥min_insights） ----
    def _compose_insights(self, report: Dict[str, Any]) -> List[str]:
        pool: List[str] = []
        pool += report["conclusions"]
        pool += report["crosstab_findings"]
        pool += report["risks"]
        pool += report["suggestions"]
        pool += report["trends"]
        pool += report["persona"]
        # 去重保序
        seen, insights = set(), []
        for p in pool:
            if p and p not in seen:
                seen.add(p)
                insights.append(p)
        # 不足则用逐题统计补足
        if len(insights) < self.min_insights:
            for st in report["question_stats"]:
                if st.get("type") in ("single", "yesno") and st.get("top") and st.get("answered"):
                    line = f"「{st['title'][:22]}」选择最多的是「{st['top']['label']}」（{st['top']['ratio']*100:.0f}%）。"
                elif st.get("type") == "rating" and st.get("n"):
                    line = f"「{st['title'][:22]}」平均 {st['mean']} 分，中位数 {st['median']}。"
                elif st.get("type") == "multiple" and st.get("distribution"):
                    top = max(st["distribution"], key=lambda d: d["count"], default=None)
                    line = f"「{st['title'][:22]}」中被选最多的是「{top['label']}」。" if top else ""
                else:
                    continue
                if line and line not in seen:
                    seen.add(line)
                    insights.append(line)
                if len(insights) >= self.min_insights:
                    break
        return insights

    # ==================================================================
    # 联网 LLM 分析
    # ==================================================================
    def _should_try_online(self) -> bool:
        if self.mode == "offline":
            return False
        provider = self._active_provider()
        if not provider:
            log.info("未配置可用的 AI provider，使用离线分析。")
            return False
        if not provider.get("api_key"):
            log.info("AI provider 缺少 api_key，使用离线分析。")
            return False
        return True

    def _active_provider(self) -> Optional[Dict[str, Any]]:
        name = self.ai_conf.get("active_provider")
        providers = self.ai_conf.get("providers", {})
        prov = providers.get(name)
        if prov and prov.get("enabled", False):
            return prov
        # 退而求其次：任选一个 enabled 且有 key 的
        for p in providers.values():
            if p.get("enabled") and p.get("api_key"):
                return p
        return None

    def _online_report(self, offline_fallback: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            import requests  # 延迟导入
        except ImportError:
            log.warning("requests 未安装，无法联网，使用离线分析。")
            return None

        provider = self._active_provider()
        try:
            payload_stats = {
                "title": self.q.title(),
                "summary": self.analyzer.summary(),
                "questions": [
                    {k: st.get(k) for k in ("id", "title", "type", "answered", "mean", "median", "top", "distribution")
                     if k in st}
                    for st in self.analyzer.all_question_stats()
                ],
            }
            system = ("你是一名资深的适老化数字鸿沟研究数据分析师。请基于给定的问卷统计数据，"
                      "用简体中文输出严格的 JSON，字段包括："
                      "conclusions(结论,数组), persona(用户画像,数组), trends(趋势预测,数组), "
                      "suggestions(改进建议,数组), risks(风险提示,数组), insights(洞察,数组,至少10条)。"
                      "只输出 JSON，不要额外解释。")
            user = "问卷统计数据如下：\n" + json.dumps(payload_stats, ensure_ascii=False)
            content = self._call_llm(requests, provider, system, user)
            data = self._parse_llm_json(content)
            if not data:
                return None
            report = dict(offline_fallback)  # 复用 summary / question_stats 等
            report["mode"] = "online"
            report["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for key in ("conclusions", "persona", "trends", "suggestions", "risks", "insights"):
                if isinstance(data.get(key), list) and data[key]:
                    report[key] = [str(x) for x in data[key]]
            # 保证洞察数量
            if len(report.get("insights", [])) < self.min_insights:
                report["insights"] = self._compose_insights(report)
            log.info("已使用联网 AI（%s）生成报告。", provider.get("model"))
            return report
        except Exception as exc:  # noqa: BLE001  联网任何异常都降级
            log.warning("联网 AI 失败，降级离线分析：%s", exc)
            return None

    def _call_llm(self, requests, provider: Dict[str, Any], system: str, user: str) -> str:
        url = provider.get("base_url", "").rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.get('api_key')}",
            "Content-Type": "application/json",
        }
        body = {
            "model": provider.get("model"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
        }
        timeout = int(self.ai_conf.get("timeout_seconds", 30))
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_llm_json(content: str) -> Optional[Dict[str, Any]]:
        if not content:
            return None
        text = content.strip()
        # 去掉可能的 ```json 包裹
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        # 截取第一个 { 到最后一个 }
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("LLM 返回内容无法解析为 JSON。")
            return None


# 便捷函数
def analyze(config: Dict[str, Any], questionnaire: Questionnaire,
            analyzer: Analyzer) -> Dict[str, Any]:
    return AIEngine(config, questionnaire, analyzer).generate_report()
