"""
LongTextAgent - 长文本生成 Agent
主入口脚本（多模式版本）
"""

import argparse
import os
import sys
import yaml
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from pipeline.novel_pipeline import ContentPipeline
from utils.llm_client import list_providers
from rich.console import Console
from rich.table import Table

console = Console()

# 支持的模式列表
AVAILABLE_MODES = {
    'novel': '小说/故事 - 适用于各类虚构作品',
    'report': '研究报告 - 适用于市场调研、行业分析等',
    'article': '文章/博客 - 适用于公众号、博客帖子等',
    'document': '技术文档 - 适用于产品手册、API文档等',
    'custom': '自定义 - 可在大纲文件中覆盖配置'
}


def show_modes():
    """显示所有可用模式"""
    table = Table(title="可用生成模式")
    table.add_column("模式", style="cyan")
    table.add_column("说明", style="white")
    
    for mode, desc in AVAILABLE_MODES.items():
        table.add_row(mode, desc)
    
    console.print(table)


def show_providers():
    """Show all supported LLM providers"""
    table = Table(title="Supported LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Description", style="white")
    
    for provider, desc in list_providers().items():
        table.add_row(provider, desc)
    
    console.print(table)


def load_outline(filepath: str) -> tuple[str, dict]:
    """
    加载大纲文件
    
    Args:
        filepath: 大纲文件路径（YAML 或纯文本）
    
    Returns:
        (大纲文本, 设定字典)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 尝试解析 YAML
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            outline = ""
            settings = {}
            
            # 提取大纲
            if 'outline' in data:
                outline = data['outline']
            elif 'chapters' in data:
                chapters = data['chapters']
                outline_parts = []
                for i, ch in enumerate(chapters, 1):
                    if isinstance(ch, str):
                        outline_parts.append(f"第{i}章: {ch}")
                    elif isinstance(ch, dict):
                        title = ch.get('title', f'第{i}章')
                        brief = ch.get('brief', '')
                        outline_parts.append(f"{title}: {brief}")
                outline = "\n".join(outline_parts)
            
            # 提取设定
            if 'settings' in data:
                settings = data['settings']
            elif 'characters' in data or 'world' in data:
                settings = {
                    k: v for k, v in data.items() 
                    if k not in ['outline', 'chapters', 'title', 'type']
                }
            
            return outline if outline else content, settings
    except yaml.YAMLError:
        pass
    
    # 纯文本大纲
    return content, {}


def main():
    parser = argparse.ArgumentParser(
        description='长文本生成 Agent - 支持多种文档类型的长文本生成工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 生成小说（默认模式）
  python main.py --outline examples/sample_outline.yaml --target-words 10000

  # 生成研究报告
  python main.py --mode report --outline report_outline.yaml --title "市场分析报告"

  # 生成技术文档
  python main.py --mode document --outline api_outline.yaml --title "API使用指南"

  # 查看所有可用模式
  python main.py --list-modes
        """
    )
    
    parser.add_argument(
        '--outline', '-o',
        help='大纲文件路径（支持 YAML 或纯文本）'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=list(AVAILABLE_MODES.keys()),
        default='novel',
        help='生成模式（默认: novel）'
    )
    
    parser.add_argument(
        '--target-words', '-w',
        type=int,
        default=10000,
        help='目标总字数（默认: 10000）'
    )
    
    parser.add_argument(
        '--title', '-t',
        default='未命名作品',
        help='作品标题（默认: 未命名作品）'
    )
    
    parser.add_argument(
        '--config', '-c',
        default='config/settings.yaml',
        help='配置文件路径（默认: config/settings.yaml）'
    )
    
    parser.add_argument(
        '--modes-config',
        default='config/modes.yaml',
        help='模式配置文件路径（默认: config/modes.yaml）'
    )
    
    parser.add_argument(
        '--output-dir',
        default='./output',
        help='输出目录（默认: ./output）'
    )
    
    parser.add_argument(
        '--no-check',
        action='store_true',
        help='禁用一致性检查'
    )
    
    parser.add_argument(
        '--list-modes',
        action='store_true',
        help='Show all available modes'
    )
    
    parser.add_argument(
        '--provider', '-p',
        choices=['deepseek', 'openai', 'claude', 'qwen', 'glm', 'moonshot', 'ollama', 'custom'],
        help='LLM provider (overrides config)'
    )
    
    parser.add_argument(
        '--model',
        help='Model name (overrides config)'
    )
    
    parser.add_argument(
        '--list-providers',
        action='store_true',
        help='Show all supported LLM providers'
    )
    
    args = parser.parse_args()
    
    # Show modes
    if args.list_modes:
        show_modes()
        return
    
    # Show providers
    if args.list_providers:
        show_providers()
        return
    
    # 检查大纲文件
    if not args.outline:
        console.print("[red]错误: 请指定大纲文件 (--outline)[/red]")
        console.print("使用 --help 查看帮助信息")
        sys.exit(1)
    
    if not os.path.exists(args.outline):
        console.print(f"[red]错误: 大纲文件不存在: {args.outline}[/red]")
        sys.exit(1)
    
    # 加载大纲
    console.print(f"[cyan]加载大纲: {args.outline}[/cyan]")
    console.print(f"[cyan]生成模式: {args.mode} ({AVAILABLE_MODES[args.mode].split(' - ')[0]})[/cyan]")
    outline, settings = load_outline(args.outline)
    
    # 创建管道
    try:
        pipeline = ContentPipeline(
            config_path=args.config,
            modes_path=args.modes_config,
            mode=args.mode,
            enable_consistency_check=not args.no_check
        )
    except ValueError as e:
        console.print(f"[red]配置错误: {e}[/red]")
        console.print("[yellow]提示: 请设置环境变量 DEEPSEEK_API_KEY[/yellow]")
        sys.exit(1)
    
    # 运行生成
    try:
        result = pipeline.run(
            outline=outline,
            settings=settings,
            target_words=args.target_words,
            title=args.title
        )
        
        console.print("\n[green]✓ 生成成功！[/green]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]生成失败: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
