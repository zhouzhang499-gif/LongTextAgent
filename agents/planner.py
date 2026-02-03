"""
Planner Agent - 大纲规划与任务分解
基于 AgentWrite 思路，将长文本任务分解为可管理的子任务
支持多种文档类型：小说、报告、文章、技术文档等
"""

from dataclasses import dataclass, field
from typing import List, Optional
import re
import yaml

from utils.llm_client import LLMClient


@dataclass
class SubTask:
    """子任务数据结构"""
    id: int
    chapter_id: int
    title: str
    description: str
    target_words: int
    context_hint: str = ""  # 上下文提示（与前文的衔接）


@dataclass
class Chapter:
    """章节数据结构"""
    id: int
    title: str
    brief: str  # 章节简介
    target_words: int
    subtasks: List[SubTask] = field(default_factory=list)


@dataclass
class ContentPlan:
    """内容规划数据结构（通用）"""
    title: str
    total_target_words: int
    content_type: str = "novel"  # novel, report, article, document, custom
    chapters: List[Chapter] = field(default_factory=list)
    settings: dict = field(default_factory=dict)  # 背景设定


# 别名，保持向后兼容
NovelPlan = ContentPlan


class Planner:
    """
    大纲规划器
    
    负责：
    1. 解析用户提供的大纲
    2. 将每章拆分为 2000-3000 字的子任务
    3. 分配字数目标
    """
    
    def __init__(
        self,
        llm: LLMClient,
        words_per_section: int = 2500,
        min_tolerance: float = 0.8,
        max_tolerance: float = 1.2
    ):
        self.llm = llm
        self.words_per_section = words_per_section
        self.min_words = int(words_per_section * min_tolerance)
        self.max_words = int(words_per_section * max_tolerance)
    
    def parse_outline(self, outline_text: str, target_words: int = 10000) -> NovelPlan:
        """
        解析大纲文本，生成小说规划
        
        Args:
            outline_text: 大纲文本（YAML 格式或自然语言）
            target_words: 目标总字数
        
        Returns:
            NovelPlan 对象
        """
        # 尝试解析 YAML 格式
        try:
            outline_data = yaml.safe_load(outline_text)
            if isinstance(outline_data, dict):
                return self._parse_yaml_outline(outline_data, target_words)
        except yaml.YAMLError:
            pass
        
        # 使用 LLM 解析自然语言大纲
        return self._parse_natural_outline(outline_text, target_words)
    
    def _parse_yaml_outline(self, data: dict, target_words: int) -> NovelPlan:
        """解析 YAML 格式的大纲"""
        title = data.get('title', '未命名作品')
        settings = data.get('settings', {})
        chapters_data = data.get('chapters', [])
        
        # 计算每章平均字数
        num_chapters = len(chapters_data)
        words_per_chapter = target_words // num_chapters if num_chapters > 0 else target_words
        
        chapters = []
        for i, ch in enumerate(chapters_data):
            if isinstance(ch, str):
                # 简单格式：只有章节名
                chapter = Chapter(
                    id=i + 1,
                    title=f"第{i + 1}章",
                    brief=ch,
                    target_words=words_per_chapter
                )
            else:
                # 详细格式
                chapter = Chapter(
                    id=i + 1,
                    title=ch.get('title', f"第{i + 1}章"),
                    brief=ch.get('brief', ch.get('description', '')),
                    target_words=ch.get('words', words_per_chapter)
                )
            chapters.append(chapter)
        
        return ContentPlan(
            title=title,
            total_target_words=target_words,
            content_type=data.get('type', 'novel'),
            chapters=chapters,
            settings=settings
        )
    
    def _parse_natural_outline(self, outline_text: str, target_words: int) -> NovelPlan:
        """使用 LLM 解析自然语言大纲"""
        prompt = f"""请分析以下大纲，提取结构化信息。

【大纲内容】
{outline_text}

【目标总字数】
{target_words} 字

请以 YAML 格式输出，包含以下结构：
```yaml
title: 作品标题
chapters:
  - title: 第一章标题
    brief: 本章主要内容简介（50-100字）
    words: 预计字数
  - title: 第二章标题
    brief: 本章主要内容简介
    words: 预计字数
  # ... 更多章节
```

只输出 YAML 代码块，不要其他内容。"""

        response = self.llm.generate(prompt)
        
        # 提取 YAML 代码块
        yaml_match = re.search(r'```yaml\s*(.*?)\s*```', response, re.DOTALL)
        if yaml_match:
            yaml_text = yaml_match.group(1)
        else:
            yaml_text = response
        
        try:
            data = yaml.safe_load(yaml_text)
            return self._parse_yaml_outline(data, target_words)
        except Exception as e:
            # 解析失败，创建默认单章节
            return ContentPlan(
                title="未命名作品",
                total_target_words=target_words,
                chapters=[
                    Chapter(
                        id=1,
                        title="第一章",
                        brief=outline_text[:500],
                        target_words=target_words
                    )
                ]
            )
    
    def decompose_chapter(self, chapter: Chapter) -> List[SubTask]:
        """
        将章节分解为子任务
        
        Args:
            chapter: 章节对象
        
        Returns:
            子任务列表
        """
        target_words = chapter.target_words
        
        # 计算需要多少个子任务
        num_subtasks = max(1, target_words // self.words_per_section)
        words_per_subtask = target_words // num_subtasks
        
        # 如果只需要一个子任务
        if num_subtasks == 1:
            return [
                SubTask(
                    id=1,
                    chapter_id=chapter.id,
                    title=f"{chapter.title}",
                    description=chapter.brief,
                    target_words=target_words
                )
            ]
        
        # 需要多个子任务，使用 LLM 进行细分
        return self._decompose_with_llm(chapter, num_subtasks, words_per_subtask)
    
    def _decompose_with_llm(
        self,
        chapter: Chapter,
        num_subtasks: int,
        words_per_subtask: int
    ) -> List[SubTask]:
        """使用 LLM 将章节分解为多个子任务"""
        
        prompt = f"""请将以下章节内容分解为 {num_subtasks} 个写作子任务。

【章节信息】
- 标题：{chapter.title}
- 内容简介：{chapter.brief}
- 总字数目标：{chapter.target_words} 字
- 每个子任务约：{words_per_subtask} 字

请以 YAML 格式输出子任务列表：
```yaml
subtasks:
  - title: 子任务1标题（如：开场/发展/冲突/高潮/结尾）
    description: 这部分要写什么内容
    context_hint: 与前文如何衔接
  - title: 子任务2标题
    description: 这部分要写什么内容
    context_hint: 与前文如何衔接
```

只输出 YAML 代码块。"""

        response = self.llm.generate(prompt)
        
        # 提取 YAML
        yaml_match = re.search(r'```yaml\s*(.*?)\s*```', response, re.DOTALL)
        if yaml_match:
            yaml_text = yaml_match.group(1)
        else:
            yaml_text = response
        
        try:
            data = yaml.safe_load(yaml_text)
            subtasks_data = data.get('subtasks', [])
            
            subtasks = []
            for i, st in enumerate(subtasks_data):
                subtasks.append(SubTask(
                    id=i + 1,
                    chapter_id=chapter.id,
                    title=st.get('title', f"部分{i + 1}"),
                    description=st.get('description', ''),
                    target_words=words_per_subtask,
                    context_hint=st.get('context_hint', '')
                ))
            
            return subtasks if subtasks else self._create_default_subtasks(chapter, num_subtasks, words_per_subtask)
            
        except Exception:
            return self._create_default_subtasks(chapter, num_subtasks, words_per_subtask)
    
    def _create_default_subtasks(
        self,
        chapter: Chapter,
        num_subtasks: int,
        words_per_subtask: int
    ) -> List[SubTask]:
        """创建默认子任务划分"""
        subtask_names = ["开篇", "发展", "转折", "高潮", "收尾"]
        
        subtasks = []
        for i in range(num_subtasks):
            name = subtask_names[i] if i < len(subtask_names) else f"部分{i + 1}"
            subtasks.append(SubTask(
                id=i + 1,
                chapter_id=chapter.id,
                title=f"{chapter.title} - {name}",
                description=f"{chapter.brief} 的{name}部分",
                target_words=words_per_subtask
            ))
        
        return subtasks
    
    def create_full_plan(self, outline_text: str, target_words: int = 10000) -> NovelPlan:
        """
        创建完整的写作计划
        
        Args:
            outline_text: 大纲文本
            target_words: 目标总字数
        
        Returns:
            包含所有子任务的 NovelPlan
        """
        # 解析大纲
        plan = self.parse_outline(outline_text, target_words)
        
        # 为每章分解子任务
        for chapter in plan.chapters:
            chapter.subtasks = self.decompose_chapter(chapter)
        
        return plan
