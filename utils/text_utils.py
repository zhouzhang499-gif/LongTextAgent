"""
文本工具函数
"""

import re
from typing import List


def count_chinese_words(text: str) -> int:
    """
    统计中文字数（包括标点）
    
    Args:
        text: 输入文本
    
    Returns:
        字符数量
    """
    # 移除空白字符后计算长度
    text = re.sub(r'\s+', '', text)
    return len(text)


def count_words(text: str) -> int:
    """
    智能统计字数（中英混合）
    - 中文按字符数
    - 英文按单词数
    
    Args:
        text: 输入文本
    
    Returns:
        等效字数
    """
    # 分离中文和非中文部分
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    
    # 英文单词
    text_no_chinese = re.sub(r'[\u4e00-\u9fff]', ' ', text)
    english_words = text_no_chinese.split()
    
    return len(chinese_chars) + len(english_words)


def split_into_paragraphs(text: str) -> List[str]:
    """
    将文本分割为段落
    
    Args:
        text: 输入文本
    
    Returns:
        段落列表
    """
    # 按空行分割
    paragraphs = re.split(r'\n\s*\n', text)
    # 过滤空段落
    return [p.strip() for p in paragraphs if p.strip()]


def truncate_text(text: str, max_chars: int, suffix: str = "...") -> str:
    """
    截断文本到指定长度
    
    Args:
        text: 输入文本
        max_chars: 最大字符数
        suffix: 截断后缀
    
    Returns:
        截断后的文本
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars - len(suffix)] + suffix


def extract_chapter_title(text: str) -> str:
    """
    从章节文本中提取标题
    
    Args:
        text: 章节文本
    
    Returns:
        章节标题，如果没有找到则返回前20字
    """
    # 尝试匹配常见的章节标题格式
    patterns = [
        r'^第[一二三四五六七八九十\d]+章[：:\s]*(.+?)$',
        r'^Chapter\s+\d+[：:\s]*(.+?)$',
        r'^#+\s*(.+?)$',
    ]
    
    lines = text.strip().split('\n')
    for line in lines[:3]:  # 只检查前三行
        line = line.strip()
        for pattern in patterns:
            match = re.match(pattern, line, re.MULTILINE)
            if match:
                return match.group(1).strip() if match.groups() else line
    
    # 如果没找到，返回前20个字符
    return truncate_text(text.strip().split('\n')[0], 20)
