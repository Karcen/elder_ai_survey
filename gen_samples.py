#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成模拟数据，不依赖 tkinter"""
import sys
from pathlib import Path

# 添加项目根目录
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from main import load_config, setup_logging
from modules import data_manager as dm
from modules.questionnaire_engine import Questionnaire


def main():
    config = load_config()
    setup_logging(config)
    
    print("正在加载问卷...")
    q = Questionnaire.load(config=config, base_dir=BASE_DIR)
    mgr = dm.DataManager(
        config=config,
        base_dir=BASE_DIR,
        question_ids=[x.get("id") for x in q.questions]
    )
    
    print("正在清空现有数据...")
    mgr.clear_all()
    
    print("正在生成 200 份模拟数据...")
    count = mgr.simulate_responses(q, n=200)
    print(f"✅ 已生成 {count} 份模拟答卷！")
    
    print(f"\n当前数据：{mgr.count()} 份")
    
    # 显示一些数据
    responses = mgr.load_responses()
    if responses:
        print(f"最新答卷: {responses[-1]['response_id']} - {responses[-1]['started_at']}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
