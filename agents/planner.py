"""
Planner Agent - 大纲规划与任务分解
基于 AgentWrite 思路，将长文本任务分解为可管理的子任务
支持多种文档类型：小说、报告、文章、技术文档等
"""

from dataclasses import dataclass, field
from typing import List, Optional
import os
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
        
        # 加载外部提示词模板
        self.prompts = {}
        try:
            prompts_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "prompts.yaml")
            if os.path.exists(prompts_path):
                with open(prompts_path, 'r', encoding='utf-8') as f:
                    self.prompts = yaml.safe_load(f).get("planner", {})
        except Exception as e:
            print(f"[-] 警告：加载 planner 提示词模板失败 ({e})，将使用默认内置模板。")
    
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
    
    def _parse_natural_outline(self, outline_text: str, target_words: int) -> ContentPlan:
        """使用 LLM 分块并行解析自然语言大纲 (方案一)"""
        import concurrent.futures
        
        # 1. 物理切片大纲 (Chunking)
        # 按常见的分卷/分章标识符进行粗略分块，避免大模型单次吞吐量过大导致截断变形
        chunks = self._chunk_outline(outline_text)
        
        # 计算每块的预估字数配额
        words_per_chunk = target_words // len(chunks) if chunks else target_words
        
        parsed_chapters = []
        global_title = "未命名作品"
        
        def _parse_chunk(chunk_idx: int, chunk_text: str) -> list:
            default_prompt = f"""请分析以下大纲片段，提取结构化章节信息。

【大纲片段内容】
{chunk_text}

【目标总字数（本片段配额）】
{words_per_chunk} 字

请严格以 YAML 格式输出本片段包含的章节：
```yaml
chapters:
  - title: 章节标题 (如: 第一章 相遇)
    brief: 本章主要内容简介（50-100字，尽量详细提取片段中提及的剧情）
    words: 预计字数
```

注意：
1. 只输出 YAML 代码块，不要有任何其他解释文字。
2. 即使片段只有一句话，也帮我构造出一个合理的章节结构。
3. 保持原大纲的章节顺序。"""

            template = self.prompts.get("parse_chunk", default_prompt)
            # 简单的模板替换（如果模板包含对应占位符）
            try:
                # 若外部模板未定义参数，使用 format 可能抛出 KeyError，这里做回退
                prompt = template.format(chunk_text=chunk_text, words_per_chunk=words_per_chunk)
            except Exception as e:
                import logging
                logging.debug(f"parse_chunk 模板格式化失败（{e}），回退默认 prompt")
                prompt = default_prompt

            response = self.llm.generate(prompt, max_tokens=2048)
            
            yaml_match = re.search(r'```yaml\s*(.*?)\s*```', response, re.DOTALL)
            yaml_text = yaml_match.group(1) if yaml_match else response
            
            try:
                data = yaml.safe_load(yaml_text)
                return data.get('chapters', []) if isinstance(data, dict) else []
            except Exception as e:
                # 容错：如果单块解析彻底失败，生成一个保底单章
                print(f"解析大纲块 {chunk_idx} 失败: {e}")
                return [{
                    'title': f"解析修复章节 (块 {chunk_idx})",
                    'brief': chunk_text[:200],
                    'words': words_per_chunk
                }]

        # 3. 并行解析所有块 (Parallel Processing)
        # 使用线程池并发向 LLM 发送局部大纲，极大提升速度并防止超长文本导致 Attention 机制崩溃
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(chunks))) as executor:
            future_to_chunk = {
                executor.submit(_parse_chunk, i, chunk): i 
                for i, chunk in enumerate(chunks)
            }
            
            # 按顺序收集结果
            chunk_results = [[] for _ in range(len(chunks))]
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    chunk_results[chunk_idx] = future.result()
                except Exception as e:
                    print(f"大纲块 {chunk_idx} 并发抛出异常: {e}")
                    
        # 4. 合并章节结果
        all_chapters_data = []
        for res in chunk_results:
            if isinstance(res, list):
                all_chapters_data.extend(res)
                
        # 5. 组装成最终的 Plan
        # 尝试从全文提取书名（轻量级）
        title_prompt = f"请为以下大纲提取或拟定一个作品标题：\n{outline_text[:1000]}\n只输出标题字符串，不要任何引号或多余文字。"
        global_title = "未命名作品"  # 默认值，防止 try 失败后变量未定义
        try:
            global_title = self.llm.generate(title_prompt, max_tokens=50).strip(' "【】\n')
        except Exception as e:
            import logging
            logging.warning(f"自动提取作品标题失败: {e}，使用默认标题")

            
        final_yaml_struct = {
            'title': global_title,
            'type': 'novel',
            'chapters': all_chapters_data
        }
        
        return self._parse_yaml_outline(final_yaml_struct, target_words)
        
    def _chunk_outline(self, outline_text: str) -> List[str]:
        """将长篇自然语言大纲进行物理分块，避免大模型截断"""
        import re
        
        # 如果文本本来就不长 (< 1500 字)，没必要分块，直接作为一个 Chunk
        if len(outline_text) < 1500:
            return [outline_text]
            
        chunks = []
        # 尝试按常见的章节标志进行分割 (比如：第X章、卷X、Chapter X、大纲片段等)
        # 这里使用一种安全的分割策略：寻找明显的分段标志，如果两个标志相隔超过 800 字，就在该标志处切割
        
        # 预编译常见的标题分割正则
        split_pattern = re.compile(r'(?=\n(?:第[一二三四五六七八九十百千万\w]+[章卷回节幕]|Chapter\s*\d+|【第[一二三四五六七八九十百千万\w]+[章卷回节幕]】|#+\s+第))')
        
        raw_chunks = split_pattern.split(outline_text)
        
        current_chunk = ""
        # 聚合成理想大小的块 (约 1000 - 2000 字符一块)
        for part in raw_chunks:
            if not part.strip(): continue
            if len(current_chunk) + len(part) > 2000 and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = part
            else:
                current_chunk += ("\n" + part if current_chunk else part)
                
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        # 如果正则没有起效（比如完全没用“第X章”的格式，是一大坨纯文本），做一次蛮力按字数切割（以防万一）
        if len(chunks) == 1 and len(chunks[0]) > 3000:
            forced_chunks = []
            text = chunks[0]
            step = 2500
            for i in range(0, len(text), step):
                # 尽量在换行符处切断
                end = min(i + step, len(text))
                if end < len(text):
                    next_newline = text.find('\n', end)
                    if next_newline != -1 and next_newline - end < 500:
                        end = next_newline + 1
                forced_chunks.append(text[i:end].strip())
            return forced_chunks
            
        return chunks
    
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
        
        default_prompt = f"""请将以下章节内容分解为 {num_subtasks} 个写作子任务。

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

        template = self.prompts.get("decompose_chapter", default_prompt)
        try:
            prompt = template.format(
                num_subtasks=num_subtasks,
                chapter_title=chapter.title,
                chapter_brief=chapter.brief,
                target_words=chapter.target_words,
                words_per_subtask=words_per_subtask
            )
        except Exception as e:
            import logging
            logging.debug(f"decompose_chapter 模板格式化失败（{e}），回退默认 prompt")
            prompt = default_prompt

        response = self.llm.generate(prompt)
        
        # 提取 YAML
        yaml_match = re.search(r'```yaml\s*(.*?)\s*```', response, re.DOTALL)
        if yaml_match:
            yaml_text = yaml_match.group(1)
        else:
            yaml_text = response
        
        try:
            data = yaml.safe_load(yaml_text)
            # 安全检查：yaml.safe_load 可能返回 None（空内容）或非 dict（纯字符串）
            if not isinstance(data, dict):
                import logging
                logging.warning(f"LLM 返回的子任务 YAML 格式无效，回退默认子任务划分")
                return self._create_default_subtasks(chapter, num_subtasks, words_per_subtask)
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
