"""
增强版摘要存储系统
支持智能摘要压缩、层级摘要管理
"""

from typing import List, Optional, Dict
from dataclasses import dataclass, field
import json
import os

from utils.llm_client import LLMClient


@dataclass
class SummaryEntry:
    """摘要条目"""
    id: int
    level: str  # 'section', 'chapter', 'volume'
    title: str
    summary: str
    word_count: int
    key_points: List[str] = field(default_factory=list)
    characters_involved: List[str] = field(default_factory=list)
    timestamp: str = ""


class SummaryStore:
    """
    增强版摘要存储
    
    特性：
    1. 层级摘要管理（段落→章节→卷）
    2. 智能压缩（当摘要过多时自动合并）
    3. 关键信息提取（人物、事件、地点）
    """
    
    def __init__(
        self,
        llm: LLMClient,
        max_section_summaries: int = 10,
        max_chapter_summaries: int = 20,
        compression_threshold: int = 8
    ):
        self.llm = llm
        self.max_section_summaries = max_section_summaries
        self.max_chapter_summaries = max_chapter_summaries
        self.compression_threshold = compression_threshold
        
        # 三层摘要存储
        self.section_summaries: List[SummaryEntry] = []  # 段落级
        self.chapter_summaries: List[SummaryEntry] = []  # 章节级
        self.volume_summary: Optional[SummaryEntry] = None  # 卷级（全局）
        
        self._id_counter = 0
    
    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter
    
    def add_section_summary(
        self,
        title: str,
        content: str,
        word_count: int = 0
    ) -> SummaryEntry:
        """
        添加段落级摘要
        
        Args:
            title: 段落标题
            content: 段落内容
            word_count: 字数
        
        Returns:
            创建的摘要条目
        """
        # 生成摘要
        summary = self._generate_summary(content, max_words=150)
        key_points = self._extract_key_points(content)
        characters = self._extract_characters(content)
        
        entry = SummaryEntry(
            id=self._next_id(),
            level='section',
            title=title,
            summary=summary,
            word_count=word_count,
            key_points=key_points,
            characters_involved=characters
        )
        
        self.section_summaries.append(entry)
        
        # 检查是否需要压缩
        if len(self.section_summaries) >= self.compression_threshold:
            self._compress_section_summaries()
        
        return entry
    
    def add_chapter_summary(
        self,
        chapter_id: int,
        title: str,
        content: str,
        word_count: int = 0
    ) -> SummaryEntry:
        """
        添加章节级摘要
        
        Args:
            chapter_id: 章节ID
            title: 章节标题
            content: 章节内容
            word_count: 字数
        
        Returns:
            创建的摘要条目
        """
        summary = self._generate_summary(content, max_words=300)
        key_points = self._extract_key_points(content)
        characters = self._extract_characters(content)
        
        entry = SummaryEntry(
            id=chapter_id,
            level='chapter',
            title=title,
            summary=summary,
            word_count=word_count,
            key_points=key_points,
            characters_involved=characters
        )
        
        self.chapter_summaries.append(entry)
        
        # 检查是否需要更新卷级摘要
        if len(self.chapter_summaries) >= self.compression_threshold:
            self._update_volume_summary()
        
        return entry
    
    def _generate_summary(self, content: str, max_words: int = 200) -> str:
        """生成摘要"""
        if len(content) < max_words * 2:
            return content[:max_words * 2]
        
        prompt = f"""请为以下内容生成简洁摘要，控制在{max_words}字以内。
摘要应保留关键信息：主要事件、人物行动、重要转折。

【原文】
{content[:3000]}  # 限制输入长度

【摘要】"""
        
        return self.llm.generate(prompt, max_tokens=1024)
    
    def _extract_key_points(self, content: str) -> List[str]:
        """提取关键点"""
        prompt = f"""从以下内容中提取3-5个关键点，每点不超过20字。
只输出关键点列表，每行一个，以"- "开头。

【内容】
{content[:2000]}

【关键点】"""
        
        result = self.llm.generate(prompt, max_tokens=512)
        
        # 解析结果
        points = []
        for line in result.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                points.append(line[2:])
            elif line.startswith('-'):
                points.append(line[1:].strip())
        
        return points[:5]
    
    def _extract_characters(self, content: str) -> List[str]:
        """提取涉及的人物"""
        prompt = f"""从以下内容中提取出现的人物名称。
只输出人物名列表，每行一个，以"- "开头。
如果没有明确的人物，输出"无"。

【内容】
{content[:2000]}

【人物】"""
        
        result = self.llm.generate(prompt, max_tokens=256)
        
        if '无' in result:
            return []
        
        characters = []
        for line in result.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                characters.append(line[2:])
            elif line.startswith('-'):
                characters.append(line[1:].strip())
        
        return characters[:10]
    
    def _compress_section_summaries(self):
        """压缩段落级摘要"""
        if len(self.section_summaries) < self.compression_threshold:
            return
        
        # 将旧的段落摘要合并为一个章节摘要
        old_summaries = self.section_summaries[:self.compression_threshold - 2]
        self.section_summaries = self.section_summaries[self.compression_threshold - 2:]
        
        # 合并内容
        combined_text = "\n".join([
            f"【{s.title}】{s.summary}" for s in old_summaries
        ])
        
        # 生成合并摘要
        compressed = self._generate_summary(combined_text, max_words=400)
        
        # 合并关键点和人物
        all_points = []
        all_characters = set()
        for s in old_summaries:
            all_points.extend(s.key_points)
            all_characters.update(s.characters_involved)
        
        # 创建压缩后的章节摘要
        entry = SummaryEntry(
            id=self._next_id(),
            level='chapter',
            title=f"合并摘要 ({old_summaries[0].title} - {old_summaries[-1].title})",
            summary=compressed,
            word_count=sum(s.word_count for s in old_summaries),
            key_points=all_points[:10],
            characters_involved=list(all_characters)
        )
        
        self.chapter_summaries.append(entry)
    
    def _update_volume_summary(self):
        """更新卷级摘要"""
        if len(self.chapter_summaries) < 3:
            return
        
        # 合并所有章节摘要
        combined_text = "\n".join([
            f"【{s.title}】{s.summary}" for s in self.chapter_summaries
        ])
        
        summary = self._generate_summary(combined_text, max_words=500)
        
        # 合并关键点和人物
        all_points = []
        all_characters = set()
        for s in self.chapter_summaries:
            all_points.extend(s.key_points)
            all_characters.update(s.characters_involved)
        
        self.volume_summary = SummaryEntry(
            id=0,
            level='volume',
            title="全文摘要",
            summary=summary,
            word_count=sum(s.word_count for s in self.chapter_summaries),
            key_points=all_points[:15],
            characters_involved=list(all_characters)
        )
    
    def get_context_for_writing(self, max_tokens: int = 2000) -> str:
        """
        获取用于写作的上下文
        
        智能选择：优先返回最近的详细摘要，
        如果内容太多则返回压缩后的高层摘要
        """
        context_parts = []
        
        # 1. 如果有卷级摘要，添加作为背景
        if self.volume_summary:
            context_parts.append(f"【全文背景】\n{self.volume_summary.summary}")
        
        # 2. 添加最近的章节摘要
        recent_chapters = self.chapter_summaries[-3:] if self.chapter_summaries else []
        if recent_chapters:
            chapter_text = "\n".join([
                f"- {s.title}: {s.summary}" for s in recent_chapters
            ])
            context_parts.append(f"【近期章节】\n{chapter_text}")
        
        # 3. 添加最近的段落摘要
        recent_sections = self.section_summaries[-5:] if self.section_summaries else []
        if recent_sections:
            section_text = "\n".join([
                f"- {s.title}: {s.summary}" for s in recent_sections
            ])
            context_parts.append(f"【最近内容】\n{section_text}")
        
        return "\n\n".join(context_parts)
    
    def get_all_characters(self) -> List[str]:
        """获取所有出现过的人物"""
        characters = set()
        for s in self.section_summaries + self.chapter_summaries:
            characters.update(s.characters_involved)
        return list(characters)
    
    def get_all_key_points(self) -> List[str]:
        """获取所有关键点"""
        points = []
        for s in self.chapter_summaries:
            points.extend(s.key_points)
        return points
    
    def save_to_file(self, filepath: str):
        """保存到文件"""
        data = {
            'section_summaries': [
                {
                    'id': s.id,
                    'level': s.level,
                    'title': s.title,
                    'summary': s.summary,
                    'word_count': s.word_count,
                    'key_points': s.key_points,
                    'characters_involved': s.characters_involved
                }
                for s in self.section_summaries
            ],
            'chapter_summaries': [
                {
                    'id': s.id,
                    'level': s.level,
                    'title': s.title,
                    'summary': s.summary,
                    'word_count': s.word_count,
                    'key_points': s.key_points,
                    'characters_involved': s.characters_involved
                }
                for s in self.chapter_summaries
            ],
            'volume_summary': {
                'id': self.volume_summary.id,
                'level': self.volume_summary.level,
                'title': self.volume_summary.title,
                'summary': self.volume_summary.summary,
                'word_count': self.volume_summary.word_count,
                'key_points': self.volume_summary.key_points,
                'characters_involved': self.volume_summary.characters_involved
            } if self.volume_summary else None,
            'id_counter': self._id_counter
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filepath: str):
        """从文件加载"""
        if not os.path.exists(filepath):
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.section_summaries = [
            SummaryEntry(**s) for s in data.get('section_summaries', [])
        ]
        self.chapter_summaries = [
            SummaryEntry(**s) for s in data.get('chapter_summaries', [])
        ]
        
        if data.get('volume_summary'):
            self.volume_summary = SummaryEntry(**data['volume_summary'])
        
        self._id_counter = data.get('id_counter', 0)
