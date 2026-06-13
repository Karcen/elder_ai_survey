#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成模拟数据的简单脚本，不依赖 tkinter"""
import sys
from pathlib import Path

# 添加项目根目录
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from main import load_config, setup_logging
from modules import report_generator
from modules.questionnaire_engine import Questionnaire


def main():
    config = load_config()
    setup_logging(config)
    
    print("正在生成 200 份模拟数据...")
    q = Questionnaire.load(config=config, base_dir=BASE_DIR)
    count = report_generator.generate_sample_data(
        config=config, q=q, n=200, reset=True, base_dir=BASE_DIR
    )
    print(f"✅ 已生成 {count} 份模拟答卷！")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
