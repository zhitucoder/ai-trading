#!/home/rick/miniconda3/envs/aitrading/bin/python
"""命令行：全市场画像计算"""
import sys
sys.path.insert(0, '/home/rick/workspace/ai-trading')
from src.app.profile_batch import run_batch

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='批量计算全市场股票画像')
    parser.add_argument('--date', type=str, help='K线数据截止日期 (YYYY-MM-DD)，默认当天')
    args = parser.parse_args()
    result = run_batch(report_date=args.date)
    if result:
        print(f"Done: {result['computed']}/{result['total']} computed, {result['errors']} errors")
