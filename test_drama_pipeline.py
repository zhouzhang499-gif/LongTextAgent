import os
from pipeline.novel_pipeline import NovelPipeline

# Setup test outline
outline = """
# 霸总复仇记
# 核心：黄金三秒、极度视觉化

第一回：订婚宴上的巴掌
- 顾凌天在订婚宴上，被未婚妻当众悔婚并羞辱。
- 顾凌天并不生气，反而掏出了一份文件，反转甩在未婚妻脸上。
"""

settings = {
    "characters": ["顾凌天: 隐藏首富，冷酷，喜欢用动作表达情绪", "未婚妻: 势利眼，愚蠢"],
    "style": "爽文，短剧速度，视觉化",
}

if __name__ == "__main__":
    print("Initializing pipeline in 'drama' mode...")
    pipeline = NovelPipeline(mode="drama", enable_consistency_check=False)
    
    print("Starting pipeline run...")
    content = pipeline.run(
        outline=outline,
        settings=settings,
        target_words=1000,
        title="霸总短剧测试"
    )
    
    print("\n--- FINAL CONTENT ---")
    print(content)
