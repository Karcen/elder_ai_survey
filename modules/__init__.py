"""
ElderAI Survey Platform - 功能模块包

包含：
    questionnaire_engine : 问卷引擎（加载/校验/逻辑跳转）
    validation_engine    : 问卷校验引擎
    data_manager         : 数据存储（CSV + SQLite 双重存储）
    survey_gui           : 适老化老人答题端
    analytics            : 数据分析中心
    dashboard            : 科交会展示大屏
    ai_engine            : AI 分析引擎（离线规则 + 联网 LLM）
    report_generator     : 报告导出（Excel / PDF / Word）
    speech_engine        : 语音播报与识别
"""

__version__ = "1.0.0"
__all__ = [
    "questionnaire_engine",
    "validation_engine",
    "data_manager",
    "survey_gui",
    "analytics",
    "dashboard",
    "ai_engine",
    "report_generator",
    "speech_engine",
]
