"""
Writer Agent - 内容生成器（多模式版本）
支持多种文档类型：小说、报告、文章、技术文档等
"""

import concurrent.futures
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import os
import yaml

from utils.llm_client import LLMClient
from utils.text_utils import count_words
from agents.planner import SubTask, Chapter, ContentPlan
from agents.drama_evaluator import DramaEvaluator, RejectionException


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
        evaluator_llm: Optional[LLMClient] = None,
        mode: str = "novel",
        mode_config: Optional[ModeConfig] = None,
        max_context_tokens: int = 8000
    ):
        self.llm = llm
        # 对抗性博弈：评估节点可以配置为不同于生成节点的更高阶模型
        self.evaluator_llm = evaluator_llm or llm 
        
        # 模式配置
        self.mode_config = mode_config or ModeConfig()
        self.set_mode(mode)
        
        self.max_context_tokens = max_context_tokens
        self.evaluator = DramaEvaluator(self.evaluator_llm)
        
        # 加载外部提示词模板
        self.prompts = {}
        try:
            prompts_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "prompts.yaml")
            if os.path.exists(prompts_path):
                with open(prompts_path, 'r', encoding='utf-8') as f:
                    self.prompts = yaml.safe_load(f).get("writer", {})
        except Exception as e:
            print(f"[-] 警告：加载 writer 提示词模板失败 ({e})，将使用默认内置模板。")
    
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
        style_guide: str = "",
        max_retries: int = 2
    ) -> GeneratedSection:
        """
        生成单个段落，结合 ToT 质量验证与滑动窗口续写状态机，绝对保证字数达标。
        """
        system_prompt = self.get_system_prompt(style_guide)
        
        target_words = subtask.target_words
        # 初次生成目标设为总目标的 80%，减少续写次数（原来固定 1200 字导致平均 3~4 次续写）
        initial_target = min(int(target_words * 0.8), target_words)

        user_prompt_base = f"""{context}

请开始创作本章节的【开篇与核心冲突】部分，目标字数约 {initial_target} 字左右。
剧情尚未结束，请务必留下悬念，不要急于写结局！
直接输出内容，不需要标题或其他说明。
警告：绝对禁止在正文中夹杂任何诸如【黄金三秒】、【拒绝水文】、【反转】等结构性标签或元注释，必须只输出纯粹沉浸的故事正文！"""

        retries = 0
        current_feedback_directive = ""
        final_content = ""

        # ToT 分支数量
        number_of_branches = 3 if self.mode == 'drama' else 1
        
        try:
            from rich.console import Console
            console = Console()
        except ImportError:
            class DummyConsole:
                def print(self, *args, **kwargs): pass
            console = DummyConsole()

        # ==========================================
        # 第一阶段：初始高潮爆点生成 (Tree of Thoughts)
        # ==========================================
        while retries <= max_retries:
            current_user_prompt = user_prompt_base
            if current_feedback_directive:
                current_user_prompt += f"\n\n【注意！这是重写请求。此前所有版本均未达标。裁判总监集体批示】：\n{current_feedback_directive}\n请务必吸收以上意见进行多分支探索重写！"

            if self.mode == 'drama':
                console.print(f"      [dim]正在迸发灵感... (并行生成 {number_of_branches} 个剧情走向，第 {retries+1} 次迭代)[/dim]")
                
            branches = []
            
            def _generate_branch(branch_idx):
                branch_prompt = current_user_prompt
                if number_of_branches > 1:
                    branch_prompt += f"\n(这是分支思路方案 #{branch_idx + 1}，请放开思考，给出你觉得最爽快、最炸裂的发展)"
                
                return self.llm.generate(
                    prompt=branch_prompt,
                    system_prompt=system_prompt,
                    max_tokens=initial_target * 2
                )

            # 多线程并发生成分支
            with concurrent.futures.ThreadPoolExecutor(max_workers=number_of_branches) as executor:
                future_to_branch = {executor.submit(_generate_branch, i): i for i in range(number_of_branches)}
                for future in concurrent.futures.as_completed(future_to_branch):
                    try:
                        branches.append(future.result())
                    except Exception as e:
                        console.print(f"      [red]分支生成失败: {e}[/red]")
                        
            if not branches:
                current_feedback_directive = "生成请求全部失败，请重试。"
                retries += 1
                if retries > max_retries:
                    console.print("      [red]❌ 致命错误：达到最大重试次数，且所有的生成请求均失败！[/red]")
                    final_content = "【系统提示：因大模型 API 多次调用失败，此处内容生成缺失，请检查网络或 API 密钥配置。】"
                    break
                continue

            # 只有非 drama 才直接跳出
            if self.mode != 'drama':
                final_content = branches[0]
                break
                
            # Drama 模式下的 ToT 评估
            console.print(f"      [dim]开始对 {len(branches)} 条分支进行严苛打分...[/dim]")
            evaluated_branches = []
            
            def _evaluate(content):
                return self.evaluator.evaluate_section(content) + (content,)
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(branches)) as executor:
                eval_futures = [executor.submit(_evaluate, b) for b in branches]
                for future in concurrent.futures.as_completed(eval_futures):
                    try:
                        evaluated_branches.append(future.result())
                    except Exception as e:
                        import logging
                        logging.warning(f"Drama分支评分线程崩溃: {e}")
            
            if not evaluated_branches:
                current_feedback_directive = "评估过程异常，请重试。"
                retries += 1
                if retries > max_retries:
                    console.print("      [yellow]⚠️ 评估完全失效且达到最大重试次数，被迫采纳未评估的分支。[/yellow]")
                    final_content = branches[0] if branches else "【系统提示：内容生成了但评估彻底失效】"
                    break
                continue
                
            evaluated_branches.sort(key=lambda x: x[1], reverse=True)
            best_branch = evaluated_branches[0]
            passed, score, feedback, directive, content = best_branch
            
            if passed:
                console.print(f"      [green]✓ 选出最佳分支通过审核！ (总分: {score})[/green]")
                final_content = content
                break
            else:
                console.print(f"      [red]✗ 本轮所有分支均被总监打回，最优异的也仅有: {score}分[/red]")
                # 聚合 directive
                aggregated_directives = [f"【分支 {idx+1} ({b[1]}分) 问题】: {b[3]}" for idx, b in enumerate(evaluated_branches)]
                current_feedback_directive = "\n".join(aggregated_directives)
                
                retries += 1
                if retries > max_retries:
                    console.print("      [yellow]⚠️ 达到最大重试次数，被迫采纳当前最优（虽不达标）的分支。[/yellow]")
                    final_content = content
                    break

        # ==========================================
        # 第二阶段：滑动窗口状态机（字数强制膨胀引擎）
        # ==========================================
        accumulated_content = final_content
        current_words = count_words(accumulated_content)
        
        continuation_retries = 0
        max_continuations = 8 # 允许最多膨胀 8 次
        
        while current_words < target_words and continuation_retries < max_continuations:
            console.print(f"      [blue]📊 测算字数: {current_words} / {target_words}。未达标，启动状态机片段续写 (第 {continuation_retries+1} 次膨胀)...[/blue]")
            
            # 取最后 3000 个字符作为滑动窗口上下文（此前仅为 600，导致视野狭窄、逻辑断层）
            sliding_window = accumulated_content[-3000:]
            remaining_words = target_words - current_words
            
            # 判定是否为最后一次绝杀收尾
            is_final_chunk = (remaining_words < 500) or (continuation_retries == max_continuations - 1)
            
            if is_final_chunk:
                action_instruction = f"字数即将达标。请紧接最后一句往下写，给当前这个大片段平稳收尾，留下一个悬念钩子即可。"
            else:
                action_instruction = f"距离本段落设定目标还有 {remaining_words} 字的缺口。请紧接最后一句往下写，**绝对不要收尾！** 可以在这里加入新的拉扯反转、增加环境动作细节、或爆出新的矛盾以扩充篇幅。"
            
            continue_prompt = f"""【本作全局设定与本章任务锚点（防止由于截断导致人物设定失忆）】：
{context}

---

【前文结尾回顾（用于无缝拼接）】：
...{sliding_window}

【系统强制指令】：
以上是你刚才写的一半剧情，剧情还没完。
{action_instruction}
（注意：必须直接输出接续的正文文本，绝对不要包含任何开场白、说明文字或重复前文最后一句，确保能与上面的结尾完美自然拼接在同一段。此外，绝对禁止输出任何【黄金三秒】等提示词标签！）
"""
            # 使用单线程单次请求快速膨胀，不再经过耗时的评分
            continuation_chunk = self.llm.generate(
                prompt=continue_prompt,
                system_prompt=system_prompt,
                max_tokens=remaining_words * 2 if remaining_words < 2500 else 4000
            )
            
            if continuation_chunk:
                # 去除可能存在的重复片段或前置空白
                clean_chunk = continuation_chunk.strip()
                accumulated_content += "\n\n" + clean_chunk
                current_words = count_words(accumulated_content)
                
            continuation_retries += 1
            
        if current_words >= target_words:
            console.print(f"      [bold green]🎉 字数强制膨胀成功！最终字数: {current_words} 完美达标[/bold green]")
        else:
            console.print(f"      [yellow]⚠️ 触发安全阀，强行结束膨胀。最终字数: {current_words}[/yellow]")
        
        return GeneratedSection(
            subtask_id=subtask.id,
            chapter_id=subtask.chapter_id,
            content=accumulated_content,
            word_count=current_words
        )
    
    def summarize_section(self, content: str, max_words: int = 300) -> str:
        """生成章节摘要"""
        default_prompt = f"""请为以下章节内容生成一个简明扼要的摘要，控制在 {max_words} 字以内。
如果内容包含人物行动、情节发展、关键信息，请务必提取。

【原文】
{content}

【摘要】"""
        
        template = self.prompts.get("summarize_section", default_prompt)
        try:
            prompt = template.format(max_words=max_words, content=content)
        except Exception:
            prompt = default_prompt
            
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
