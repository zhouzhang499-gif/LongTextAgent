"""
LLM 客户端封装
支持 DeepSeek (OpenAI 兼容接口)
"""

import os
from openai import OpenAI
from typing import Optional
import tiktoken


class LLMClient:
    """统一的 LLM 调用接口"""
    
    def __init__(
        self,
        provider: str = "deepseek",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 4096
    ):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # 获取 API Key
        if api_key and not api_key.startswith("${"):
            self.api_key = api_key
        else:
            # 从环境变量读取
            env_var = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
            self.api_key = os.getenv(env_var)
            if not self.api_key:
                raise ValueError(f"请设置环境变量 {env_var} 或在配置中提供 api_key")
        
        # 设置 base_url
        if base_url:
            self.base_url = base_url
        elif provider == "deepseek":
            self.base_url = "https://api.deepseek.com"
        else:
            self.base_url = None
        
        # 初始化客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Token 计数器（使用 cl100k_base 作为近似）
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        生成文本
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            max_tokens: 最大生成 Token 数（可选，默认使用初始化时的值）
        
        Returns:
            生成的文本内容
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens
        )
        
        return response.choices[0].message.content
    
    def summarize(self, text: str, max_words: int = 300) -> str:
        """
        生成文本摘要
        
        Args:
            text: 要摘要的文本
            max_words: 摘要最大字数
        
        Returns:
            摘要文本
        """
        prompt = f"""请为以下内容生成一个简洁的摘要，控制在{max_words}字以内。
摘要应包含：主要事件、人物行动、情节发展。

【原文】
{text}

【摘要】"""
        
        return self.generate(prompt, max_tokens=1024)
    
    def count_tokens(self, text: str) -> int:
        """
        估算文本的 Token 数量
        
        Args:
            text: 要计算的文本
        
        Returns:
            估算的 Token 数量
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # 粗略估算：中文约 1.5 token/字，英文约 0.25 token/word
            chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
            other_chars = len(text) - chinese_chars
            return int(chinese_chars * 1.5 + other_chars * 0.3)
