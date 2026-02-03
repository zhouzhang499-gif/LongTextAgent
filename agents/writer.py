"""
Writer Agent - 内容生成器（多模式版本）
支持多种文档类型：小说、报告、文章、技术文档等
"""

from typing import List, Optional, Dict
from dataclasses import dataclass
import os
import yaml

from utils.llm_client import LLMClient
from utils.text_utils import count_words
from agents.planner import SubTask, Chapter, ContentPlan


@dataclass
class GeneratedSection:
    """生成的段落"""
    subtask_id: int
    chapter_id: int
    content: str
    word_count: int
    summary: str = ""


class ModeConfig:
    """模式配置加载器"""
    
    def __init__(self, modes_path: str = "config/modes.yaml"):
        self.modes = {}
        self.default_mode = "novel"
        self._load_modes(modes_path)
    
    def _load_modes(self, path: str):
        """加载模式配置"""
        if not os.path.exists(path):
            # 使用默认配置
            self._set_default_modes()
            return
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        self.modes = data.get('modes', {})
        self.default_mode = data.get('default_mode', 'novel')
    
    def _set_default_modes(self):
        """设置默认模式"""
        self.modes = {
            'novel': {
                'name': '小说/故事',
                'system_prompt': '你是一位专业的小说作家。请根据提供的上下文创作高质量的小说内容。',
                'summary_prompt': '请为以下内容生成简洁摘要，包含主要事件和人物行动。'
            },
            'report': {
                'name': '研究报告',
                'system_prompt': '你是一位专业的研究分析师。请撰写逻辑清晰、数据准确的报告内容。',
                'summary_prompt': '请为以下内容生成简洁摘要，包含核心观点和关键结论。'
            },
            'article': {
                'name': '文章/博客',
                'system_prompt': '你是一位资深内容创作者。请撰写引人入胜、有价值的文章内容。',
                'summary_prompt': '请为以下内容生成简洁摘要，包含核心论点和主要观点。'
            },
            'document': {
                'name': '技术文档',
                'system_prompt': '你是一位专业的技术文档工程师。请撰写清晰准确的技术文档。',
                'summary_prompt': '请为以下内容生成简洁摘要，包含涵盖的功能和关键步骤。'
            }
        }
    
    def get_mode(self, mode_name: str) -> dict:
        """获取指定模式配置"""
        return self.modes.get(mode_name, self.modes.get(self.default_mode, {}))
    
    def list_modes(self) -> List[str]:
        """列出所有可用模式"""
        return list(self.modes.keys())


class Writer:
    """
    内容生成器（多模式版本）
    
    负责：
    1. 构建写作上下文（设定 + 前情摘要）
    2. 根据模式调整写作风格
    3. 逐段生成内容
    4. 处理段落过渡
    """
    
    def __init__(
        self,
        llm: LLMClient,
        mode: str = "novel",
        mode_config: Optional[ModeConfig] = None,
        max_context_tokens: int = 8000
    ):
        self.llm = llm
        self.max_context_tokens = max_context_tokens
        
        # 加载模式配置
        self.mode_config = mode_config or ModeConfig()
        self.set_mode(mode)
    
    def set_mode(self, mode: str):
        """设置写作模式"""
        self.mode = mode
        self.current_mode_config = self.mode_config.get_mode(mode)
    
    def get_system_prompt(self, custom_style: str = "") -> str:
        """获取当前模式的系统提示"""
        base_prompt = self.current_mode_config.get('system_prompt', '')
        if custom_style:
            base_prompt += f"\n\n特殊风格要求：{custom_style}"
        return base_prompt
    
    def build_context(
        self,
        settings: dict,
        previous_summaries: List[str],
        current_subtask: SubTask,
        recent_content: str = ""
    ) -> str:
        """
        构建写作上下文
        
        Args:
            settings: 背景设定
            previous_summaries: 前面章节的摘要列表
            current_subtask: 当前子任务
            recent_content: 最近生成的内容（用于衔接）
        
        Returns:
            格式化的上下文字符串
        """
        # 尝试使用模式的上下文模板
        template = self.current_mode_config.get('context_template')
        
        if template:
            # 使用模板
            return self._build_from_template(
                template, settings, previous_summaries, 
                current_subtask, recent_content
            )
        else:
            # 使用默认格式
            return self._build_default_context(
                settings, previous_summaries, 
                current_subtask, recent_content
            )
    
    def _build_from_template(
        self,
        template: str,
        settings: dict,
        previous_summaries: List[str],
        current_subtask: SubTask,
        recent_content: str
    ) -> str:
        """使用模板构建上下文"""
        settings_text = self._format_settings(settings) if settings else "（无）"
        summaries_text = "\n".join([f"- {s}" for s in previous_summaries[-5:]]) if previous_summaries else "（无）"
        recent_text = recent_content[-500:] if len(recent_content) > 500 else recent_content if recent_content else "（无）"
        
        return template.format(
            settings=settings_text,
            summaries=summaries_text,
            recent_content=recent_text,
            task_title=current_subtask.title,
            task_description=current_subtask.description,
            target_words=current_subtask.target_words,
            context_hint=current_subtask.context_hint or '自然过渡'
        )
    
    def _build_default_context(
        self,
        settings: dict,
        previous_summaries: List[str],
        current_subtask: SubTask,
        recent_content: str
    ) -> str:
        """使用默认格式构建上下文"""
        context_parts = []
        
        # 1. 背景/设定
        if settings:
            settings_text = self._format_settings(settings)
            context_parts.append(f"【背景信息】\n{settings_text}")
        
        # 2. 前情摘要
        if previous_summaries:
            summaries_text = "\n".join([
                f"- {summary}" for summary in previous_summaries[-5:]
            ])
            context_parts.append(f"【前文摘要】\n{summaries_text}")
        
        # 3. 最近内容（用于衔接）
        if recent_content:
            recent_excerpt = recent_content[-500:] if len(recent_content) > 500 else recent_content
            context_parts.append(f"【上文结尾（用于衔接）】\n...{recent_excerpt}")
        
        # 4. 当前任务
        task_info = f"""【当前写作任务】
- 任务：{current_subtask.title}
- 内容要求：{current_subtask.description}
- 目标字数：{current_subtask.target_words} 字
- 衔接提示：{current_subtask.context_hint or '自然过渡'}"""
        context_parts.append(task_info)
        
        return "\n\n".join(context_parts)
    
    def _format_settings(self, settings: dict) -> str:
        """格式化设定信息"""
        parts = []
        
        # 主要角色（小说模式）
        if 'characters' in settings:
            chars = settings['characters']
            if isinstance(chars, list):
                char_text = "\n".join([f"  - {c}" for c in chars])
            elif isinstance(chars, dict):
                char_text = "\n".join([f"  - {name}: {desc}" for name, desc in chars.items()])
            else:
                char_text = str(chars)
            parts.append(f"【主要角色】\n{char_text}")
        
        # 世界观/背景
        if 'world' in settings:
            parts.append(f"【背景】\n{settings['world']}")
        
        # 风格
        if 'style' in settings:
            parts.append(f"【风格】\n{settings['style']}")
        
        # 目标受众（报告/文章模式）
        if 'audience' in settings:
            parts.append(f"【目标受众】\n{settings['audience']}")
        
        # 技术栈（文档模式）
        if 'tech_stack' in settings:
            parts.append(f"【技术栈】\n{settings['tech_stack']}")
        
        # 其他设定
        known_keys = ['characters', 'world', 'style', 'audience', 'tech_stack']
        for key, value in settings.items():
            if key not in known_keys:
                parts.append(f"【{key}】\n{value}")
        
        return "\n".join(parts) if parts else str(settings)
    
    def write_section(
        self,
        subtask: SubTask,
        context: str,
        style_guide: str = ""
    ) -> GeneratedSection:
        """
        生成单个段落
        
        Args:
            subtask: 子任务
            context: 上下文信息
            style_guide: 写作风格指导（可选）
        
        Returns:
            GeneratedSection 对象
        """
        system_prompt = self.get_system_prompt(style_guide)
        
        user_prompt = f"""{context}

请开始创作，目标字数约 {subtask.target_words} 字。
直接输出内容，不需要标题或其他说明。"""

        # 生成内容
        content = self.llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=subtask.target_words * 2
        )
        
        # 统计字数
        word_count = count_words(content)
        
        return GeneratedSection(
            subtask_id=subtask.id,
            chapter_id=subtask.chapter_id,
            content=content,
            word_count=word_count
        )
    
    def summarize_section(self, content: str, max_words: int = 300) -> str:
        """生成章节摘要"""
        summary_prompt_template = self.current_mode_config.get(
            'summary_prompt',
            '请为以下内容生成简洁摘要，控制在{max_words}字以内。'
        )
        
        prompt = f"""{summary_prompt_template.format(max_words=max_words)}

【内容】
{content}

【摘要】"""
        
        return self.llm.generate(prompt, max_tokens=1024)
    
    def generate_chapter(
        self,
        chapter: Chapter,
        settings: dict,
        previous_summaries: List[str],
        on_section_complete: Optional[callable] = None
    ) -> tuple[str, str]:
        """
        生成完整章节
        
        Args:
            chapter: 章节对象（包含子任务）
            settings: 背景设定
            previous_summaries: 前面章节的摘要
            on_section_complete: 每段完成时的回调函数
        
        Returns:
            (章节内容, 章节摘要)
        """
        sections = []
        recent_content = ""
        
        for subtask in chapter.subtasks:
            # 构建上下文
            context = self.build_context(
                settings=settings,
                previous_summaries=previous_summaries,
                current_subtask=subtask,
                recent_content=recent_content
            )
            
            # 生成段落
            section = self.write_section(subtask, context)
            sections.append(section)
            
            # 更新最近内容
            recent_content = section.content
            
            # 回调
            if on_section_complete:
                on_section_complete(section)
        
        # 合并所有段落
        chapter_content = "\n\n".join([s.content for s in sections])
        
        # 生成章节摘要
        chapter_summary = self.summarize_section(chapter_content)
        
        return chapter_content, chapter_summary
    
    def generate_full_content(
        self,
        plan: ContentPlan,
        on_chapter_complete: Optional[callable] = None,
        on_section_complete: Optional[callable] = None
    ) -> str:
        """
        生成完整内容
        
        Args:
            plan: 内容规划
            on_chapter_complete: 每章完成时的回调
            on_section_complete: 每段完成时的回调
        
        Returns:
            完整文本
        """
        chapters_content = []
        all_summaries = []
        
        for chapter in plan.chapters:
            # 生成章节
            content, summary = self.generate_chapter(
                chapter=chapter,
                settings=plan.settings,
                previous_summaries=all_summaries,
                on_section_complete=on_section_complete
            )
            
            # 添加章节标题
            full_chapter = f"# {chapter.title}\n\n{content}"
            chapters_content.append(full_chapter)
            
            # 记录摘要
            all_summaries.append(f"{chapter.title}: {summary}")
            
            # 回调
            if on_chapter_complete:
                on_chapter_complete(chapter, content, summary)
        
        # 合并所有章节
        return f"# {plan.title}\n\n" + "\n\n---\n\n".join(chapters_content)
