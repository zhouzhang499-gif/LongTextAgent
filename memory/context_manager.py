"""
上下文管理器
管理写作过程中的上下文信息，包括摘要、设定等
"""

from typing import List, Optional, Dict
from dataclasses import dataclass, field
import json
import os


@dataclass
class ChapterSummary:
    """章节摘要"""
    chapter_id: int
    title: str
    summary: str
    word_count: int = 0


class ContextManager:
    """
    上下文管理器
    
    负责：
    1. 管理章节摘要
    2. 管理设定信息
    3. 控制上下文大小
    """
    
    def __init__(
        self,
        max_summaries: int = 10,
        max_context_tokens: int = 8000
    ):
        self.max_summaries = max_summaries
        self.max_context_tokens = max_context_tokens
        
        self.summaries: List[ChapterSummary] = []
        self.settings: Dict = {}
        self.character_states: Dict = {}  # 角色状态追踪
    
    def add_chapter_summary(
        self,
        chapter_id: int,
        title: str,
        summary: str,
        word_count: int = 0
    ):
        """添加章节摘要"""
        self.summaries.append(ChapterSummary(
            chapter_id=chapter_id,
            title=title,
            summary=summary,
            word_count=word_count
        ))
        
        # 如果超过最大数量，压缩旧摘要
        if len(self.summaries) > self.max_summaries:
            self._compress_old_summaries()
    
    def _compress_old_summaries(self):
        """压缩旧的摘要，保留最近的"""
        # 保留最近的 max_summaries 条
        self.summaries = self.summaries[-self.max_summaries:]
    
    def get_recent_summaries(self, count: int = 5) -> List[str]:
        """获取最近的摘要"""
        recent = self.summaries[-count:] if count else self.summaries
        return [f"【{s.title}】{s.summary}" for s in recent]
    
    def get_all_summaries_text(self) -> str:
        """获取所有摘要的文本形式"""
        if not self.summaries:
            return ""
        
        lines = ["【前情提要】"]
        for s in self.summaries:
            lines.append(f"- {s.title}: {s.summary}")
        
        return "\n".join(lines)
    
    def set_settings(self, settings: Dict):
        """设置世界观/人物设定"""
        self.settings = settings
    
    def get_settings(self) -> Dict:
        """获取设定"""
        return self.settings
    
    def update_character_state(self, character: str, state: Dict):
        """更新角色状态"""
        if character not in self.character_states:
            self.character_states[character] = {}
        self.character_states[character].update(state)
    
    def get_character_state(self, character: str) -> Dict:
        """获取角色状态"""
        return self.character_states.get(character, {})
    
    def save_to_file(self, filepath: str):
        """保存上下文到文件"""
        data = {
            'summaries': [
                {
                    'chapter_id': s.chapter_id,
                    'title': s.title,
                    'summary': s.summary,
                    'word_count': s.word_count
                }
                for s in self.summaries
            ],
            'settings': self.settings,
            'character_states': self.character_states
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filepath: str):
        """从文件加载上下文"""
        if not os.path.exists(filepath):
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.summaries = [
            ChapterSummary(**s) for s in data.get('summaries', [])
        ]
        self.settings = data.get('settings', {})
        self.character_states = data.get('character_states', {})
    
    def get_total_word_count(self) -> int:
        """获取已生成的总字数"""
        return sum(s.word_count for s in self.summaries)
    
    def clear(self):
        """清空上下文"""
        self.summaries = []
        self.character_states = {}
