"""
小说生成管道（增强版）
整合 Planner、Writer、ContextManager、Checker，支持一致性检查
"""

import os
import yaml
from datetime import datetime
from typing import Optional, Callable, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

from utils.llm_client import LLMClient
from utils.text_utils import count_words
from agents.planner import Planner, ContentPlan, Chapter
from agents.writer import Writer, ModeConfig, GeneratedSection
from agents.checker import ConsistencyChecker, CheckResult
from memory.context_manager import ContextManager
from memory.summary_store import SummaryStore
from memory.settings_store import SettingsStore


console = Console()

# 模式名称映射（中文显示）
MODE_NAMES = {
    'novel': '📚 小说/故事',
    'report': '📊 研究报告',
    'article': '📝 文章/博客',
    'document': '📋 技术文档',
    'custom': '🔧 自定义'
}


class ContentPipeline:
    """
    内容生成管道（增强版）
    
    工作流程：
    1. 加载配置和设定
    2. 解析大纲，分解任务
    3. 根据模式调整写作风格
    4. 逐章生成，记录摘要
    5. 一致性检查（可选）
    6. 输出最终结果
    """
    
    def __init__(
        self,
        config_path: str = "config/settings.yaml",
        modes_path: str = "config/modes.yaml",
        mode: str = "novel",
        enable_consistency_check: bool = True
    ):
        """
        初始化管道
        
        Args:
            config_path: 配置文件路径
            modes_path: 模式配置文件路径
            mode: 生成模式 (novel/report/article/document/custom)
            enable_consistency_check: 是否启用一致性检查
        """
        self.config = self._load_config(config_path)
        self.mode = mode
        self.enable_consistency_check = enable_consistency_check
        
        # 初始化 LLM 客户端
        llm_config = self.config.get('llm', {})
        self.llm = LLMClient(
            provider=llm_config.get('provider', 'deepseek'),
            api_key=llm_config.get('api_key'),
            base_url=llm_config.get('base_url'),
            model=llm_config.get('model', 'deepseek-chat'),
            temperature=llm_config.get('temperature', 0.7),
            max_tokens=llm_config.get('max_tokens', 4096)
        )
        
        # 加载模式配置
        self.mode_config = ModeConfig(modes_path)
        
        # 初始化各组件
        gen_config = self.config.get('generation', {})
        ctx_config = self.config.get('context', {})
        
        self.planner = Planner(
            llm=self.llm,
            words_per_section=gen_config.get('words_per_section', 2500)
        )
        
        self.writer = Writer(
            llm=self.llm,
            mode=mode,
            mode_config=self.mode_config,
            max_context_tokens=ctx_config.get('max_context_tokens', 8000)
        )
        
        # 基础上下文管理器
        self.context_manager = ContextManager(
            max_summaries=ctx_config.get('recent_summaries_count', 5)
        )
        
        # 增强版摘要存储
        self.summary_store = SummaryStore(
            llm=self.llm,
            max_section_summaries=10,
            max_chapter_summaries=20
        )
        
        # 设定存储
        self.settings_store = SettingsStore()
        
        # 一致性检查器
        self.checker = ConsistencyChecker(
            llm=self.llm,
            settings_store=self.settings_store
        )
        
        # 输出配置
        self.output_config = self.config.get('output', {})
        self.output_dir = self.output_config.get('directory', './output')
        
        # 一致性检查结果
        self.check_results: List[CheckResult] = []
    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        if not os.path.exists(config_path):
            console.print(f"[yellow]警告: 配置文件 {config_path} 不存在，使用默认配置[/yellow]")
            return {}
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 处理环境变量
        if 'llm' in config and 'api_key' in config['llm']:
            api_key = config['llm']['api_key']
            if isinstance(api_key, str) and api_key.startswith('${') and api_key.endswith('}'):
                env_var = api_key[2:-1]
                config['llm']['api_key'] = os.getenv(env_var)
        
        return config
    
    def set_mode(self, mode: str):
        """切换生成模式"""
        self.mode = mode
        self.writer.set_mode(mode)
    
    def run(
        self,
        outline: str,
        settings: Optional[dict] = None,
        target_words: int = 10000,
        title: str = "未命名作品",
        on_progress: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        运行生成管道
        
        Args:
            outline: 大纲文本
            settings: 背景设定
            target_words: 目标总字数
            title: 作品标题
            on_progress: 进度回调函数
        
        Returns:
            生成的完整文本
        """
        mode_display = MODE_NAMES.get(self.mode, self.mode)
        check_status = "✓ 已启用" if self.enable_consistency_check else "✗ 已禁用"
        
        console.print(Panel.fit(
            f"[bold cyan]长文本生成 Agent（增强版）[/bold cyan]\n"
            f"模式: {mode_display}\n"
            f"标题: {title}\n"
            f"目标字数: {target_words} 字\n"
            f"一致性检查: {check_status}",
            title="🚀 开始生成"
        ))
        
        # 设置上下文
        if settings:
            self.context_manager.set_settings(settings)
            self.settings_store.set_world_settings(settings)
            
            # 提取人物信息
            if 'characters' in settings:
                chars = settings['characters']
                if isinstance(chars, list):
                    for char in chars:
                        if isinstance(char, str):
                            self.settings_store.add_character(name=char)
                        elif isinstance(char, dict):
                            self.settings_store.add_character(
                                name=char.get('name', '未知'),
                                description=char.get('description', ''),
                                traits=char.get('traits', [])
                            )
                elif isinstance(chars, dict):
                    for name, desc in chars.items():
                        self.settings_store.add_character(name=name, description=str(desc))
        
        # 1. 规划阶段
        console.print("\n[bold]📋 阶段一: 规划[/bold]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("解析大纲并分解任务...", total=None)
            plan = self.planner.create_full_plan(outline, target_words)
            plan.title = title
            plan.content_type = self.mode
            if settings:
                plan.settings = settings
            progress.update(task, completed=True)
        
        # 显示规划结果
        console.print(f"  ✓ 标题: {plan.title}")
        console.print(f"  ✓ 章节数: {len(plan.chapters)}")
        total_subtasks = sum(len(ch.subtasks) for ch in plan.chapters)
        console.print(f"  ✓ 子任务数: {total_subtasks}")
        
        # 2. 生成阶段
        console.print("\n[bold]✍️ 阶段二: 生成[/bold]")
        chapters_content = []
        previous_content = ""
        
        for i, chapter in enumerate(plan.chapters, 1):
            console.print(f"\n  [cyan]第 {i}/{len(plan.chapters)} 章: {chapter.title}[/cyan]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                # 为每个子任务创建进度
                for j, subtask in enumerate(chapter.subtasks, 1):
                    task = progress.add_task(
                        f"  生成 {subtask.title} ({subtask.target_words}字)...",
                        total=None
                    )
                
                # 生成章节
                content, summary = self.writer.generate_chapter(
                    chapter=chapter,
                    settings=plan.settings,
                    previous_summaries=self.context_manager.get_recent_summaries()
                )
                
                # 记录摘要
                word_count = count_words(content)
                self.context_manager.add_chapter_summary(
                    chapter_id=chapter.id,
                    title=chapter.title,
                    summary=summary,
                    word_count=word_count
                )
                
                # 增强版摘要存储
                self.summary_store.add_chapter_summary(
                    chapter_id=chapter.id,
                    title=chapter.title,
                    content=content,
                    word_count=word_count
                )
                
                # 一致性检查（如果启用）
                if self.enable_consistency_check:
                    check_result = self.checker.check_content(
                        content=content,
                        chapter_id=chapter.id,
                        previous_content=previous_content
                    )
                    self.check_results.append(check_result)
                    
                    if not check_result.passed:
                        console.print(f"    [yellow]⚠️ 发现 {len(check_result.issues)} 个问题[/yellow]")
                
                # 保存章节
                full_chapter = f"# {chapter.title}\n\n{content}"
                chapters_content.append(full_chapter)
                previous_content = content
                
                console.print(f"    ✓ 完成 ({word_count} 字)")
                
                if on_progress:
                    on_progress(f"完成第 {i} 章: {chapter.title}")
        
        # 3. 显示检查结果
        if self.enable_consistency_check and self.check_results:
            console.print("\n[bold]🔍 阶段三: 一致性检查[/bold]")
            self._display_check_summary()
        
        # 4. 合并输出
        console.print("\n[bold]📄 阶段四: 输出[/bold]")
        full_content = f"# {plan.title}\n\n" + "\n\n---\n\n".join(chapters_content)
        
        total_words = count_words(full_content)
        console.print(f"  ✓ 总字数: {total_words}")
        
        # 保存到文件
        output_path = self.save_output(full_content, title)
        console.print(f"  ✓ 已保存: {output_path}")
        
        # 保存检查报告（如果有问题）
        if self.check_results:
            report_path = self._save_check_report(title)
            if report_path:
                console.print(f"  ✓ 检查报告: {report_path}")
        
        console.print(Panel.fit(
            f"[bold green]生成完成![/bold green]\n"
            f"模式: {mode_display}\n"
            f"总字数: {total_words}\n"
            f"文件: {output_path}",
            title="✅ 完成"
        ))
        
        return full_content
    
    def _display_check_summary(self):
        """显示检查摘要"""
        total_issues = sum(len(r.issues) for r in self.check_results)
        passed_chapters = sum(1 for r in self.check_results if r.passed)
        total_chapters = len(self.check_results)
        
        table = Table(title="一致性检查摘要")
        table.add_column("项目", style="cyan")
        table.add_column("结果", style="white")
        
        table.add_row("检查章节", f"{total_chapters}")
        table.add_row("通过章节", f"{passed_chapters}/{total_chapters}")
        table.add_row("发现问题", f"{total_issues}")
        
        console.print(table)
        
        # 显示主要问题
        if total_issues > 0:
            console.print("\n  [yellow]主要问题：[/yellow]")
            shown = 0
            for result in self.check_results:
                for issue in result.issues:
                    if shown < 5:  # 最多显示5个
                        console.print(f"    • {issue.type.value}: {issue.description[:60]}...")
                        shown += 1
    
    def _save_check_report(self, title: str) -> Optional[str]:
        """保存检查报告"""
        all_issues = []
        for i, result in enumerate(self.check_results, 1):
            for issue in result.issues:
                all_issues.append({
                    'chapter': i,
                    'type': issue.type.value,
                    'severity': issue.severity.value,
                    'description': issue.description,
                    'suggestion': issue.suggestion
                })
        
        if not all_issues:
            return None
        
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.output_dir, f"{title}_检查报告_{timestamp}.md")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# {title} - 一致性检查报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"总问题数: {len(all_issues)}\n\n")
            f.write("---\n\n")
            
            for i, issue in enumerate(all_issues, 1):
                f.write(f"## 问题 {i}\n\n")
                f.write(f"- **章节**: 第 {issue['chapter']} 章\n")
                f.write(f"- **类型**: {issue['type']}\n")
                f.write(f"- **严重程度**: {issue['severity']}\n")
                f.write(f"- **描述**: {issue['description']}\n")
                f.write(f"- **建议**: {issue['suggestion']}\n\n")
        
        return report_path
    
    def save_output(self, content: str, title: str) -> str:
        """保存输出到文件"""
        os.makedirs(self.output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{title}_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
    
    def save_context(self, filepath: str):
        """保存上下文（用于断点续写）"""
        self.context_manager.save_to_file(filepath)
    
    def load_context(self, filepath: str):
        """加载上下文（用于断点续写）"""
        self.context_manager.load_from_file(filepath)
    
    def check_existing_content(self, content: str) -> CheckResult:
        """检查已有内容的一致性"""
        return self.checker.check_content(content)


# 别名，保持向后兼容
NovelPipeline = ContentPipeline
