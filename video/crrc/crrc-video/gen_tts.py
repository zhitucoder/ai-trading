import asyncio, edge_tts

VOICE = "zh-CN-YunjianNeural"
RATE = "-5%"  # 稍慢，财经解说

# 场景口播稿（与视频时间轴对齐）
SCENES = [
    ("s1", "你坐的高铁，可能是它造的。中国中车，全球轨道交通第一。"),
    ("s2", "一年营收两千七百多亿，净利一百三十多亿。全球每卖出三辆高铁动车，就有一辆来自中车。复兴号、雅万高铁、中老铁路，全是它的名片。"),
    ("s3", "但很多人不知道，中车早就不只是造火车。它把高铁的电机、芯片、材料技术，平移到风电、储能、光伏——现在每三块钱收入里，就有一块来自新能源。风电叶片全球前三，储能系统全国第一，数据中心发电用的曲轴，全球只有三家能造。"),
    ("s4", "过去五年它股价低迷，但分红从不手软——一年分红六十多亿，分红率超过一半，还发了上市以来首次中期分红。核心利润率连续五年改善，账上六百亿净现金。"),
    ("s5", "中车不是夕阳产业，是轨道加清洁能源的双赛道隐形冠军。想看更多公司深度分析？开源项目地址在简介里，雪球搜浩哥AI量化财报，更多财报分析等你来看。"),
]

async def gen(name, text):
    out = f"audio/{name}.mp3"
    tts = edge_tts.Communicate(text, VOICE, rate=RATE)
    await tts.save(out)
    print(f"generated {out}")

async def main():
    for name, text in SCENES:
        await gen(name, text)

asyncio.run(main())
