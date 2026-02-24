"""
LLM 客户端封装
支持多个提供商：DeepSeek、OpenAI、Claude、通义千问、智谱GLM、Moonshot
"""

import os
import time
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
import tiktoken

# 配置基本日志，如果外部没有配置的话
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("llm_client")

def with_retry(max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0):
    """
    带指数退避的重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = base_delay
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(f"函数 {func.__name__} 经过 {max_retries} 次重试后仍失败: {str(e)}")
                        raise e
                    
                    # 针对特定的可能不需要重试的错误可以添加过滤，比如 auth 错误 (401/403)
                    # 此处目前为了简单和健同时，捕获所有基础异常进行重试
                    logger.warning(f"函数 {func.__name__} 调用失败 ({str(e)})。正在进行第 {retries}/{max_retries} 次重试，等待 {delay} 秒...")
                    time.sleep(delay)
                    
                    # 指数退避，并设置上限
                    delay = min(delay * 2, max_delay)
        return wrapper
    return decorator

# 提供商配置
PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat"
    },
    "openai": {
        "base_url": None,  # 使用默认
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini"
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-3-5-sonnet-20241022"
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus"
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_key": "ZHIPU_API_KEY",
        "default_model": "glm-4-flash"
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "env_key": "MOONSHOT_API_KEY",
        "default_model": "moonshot-v1-8k"
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key": None,
        "default_model": "llama3.2"
    },
    "custom": {
        "base_url": None,
        "env_key": "LLM_API_KEY",
        "default_model": "gpt-3.5-turbo"
    }
}


def list_providers() -> Dict[str, str]:
    """列出所有支持的提供商"""
    return {
        "deepseek": "DeepSeek - 性价比高，中文优秀",
        "openai": "OpenAI GPT - 综合能力强",
        "claude": "Anthropic Claude - 长文本和推理优秀",
        "qwen": "通义千问 - 阿里云，中文优秀",
        "glm": "智谱GLM - 清华系，中文优秀",
        "moonshot": "Moonshot Kimi - 长上下文",
        "ollama": "Ollama - 本地部署",
        "custom": "自定义 - 兼容 OpenAI 格式的任意接口"
    }


class LLMClient:
    """统一的 LLM 调用接口，支持多提供商"""
    
    def __init__(
        self,
        provider: str = "deepseek",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ):
        """
        初始化 LLM 客户端
        
        Args:
            provider: 提供商名称 (deepseek/openai/claude/qwen/glm/moonshot/ollama/custom)
            api_key: API Key（可选，默认从环境变量读取）
            base_url: API 地址（可选，默认使用提供商配置）
            model: 模型名称（可选，默认使用提供商配置）
            temperature: 温度参数
            max_tokens: 最大生成 Token 数
        """
        self.provider = provider.lower()
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # 获取提供商配置
        if self.provider not in PROVIDER_CONFIG:
            raise ValueError(f"不支持的提供商: {provider}。支持的提供商: {list(PROVIDER_CONFIG.keys())}")
        
        config = PROVIDER_CONFIG[self.provider]
        
        # 设置模型
        self.model = model or config["default_model"]
        
        # 获取 API Key
        if api_key and not api_key.startswith("${"):
            self.api_key = api_key
        else:
            env_var = config["env_key"]
            if env_var:
                self.api_key = os.getenv(env_var)
                if not self.api_key:
                    raise ValueError(f"请设置环境变量 {env_var} 或在配置中提供 api_key")
            else:
                self.api_key = "ollama"  # Ollama 不需要真实 key
        
        # 设置 base_url
        self.base_url = base_url or config["base_url"]
        
        # 根据提供商选择客户端
        if self.provider == "claude":
            self._init_anthropic_client()
        else:
            self._init_openai_client()
        
        # Token 计数器
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None
    
    def _init_openai_client(self):
        """初始化 OpenAI 兼容客户端"""
        from openai import OpenAI
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.client_type = "openai"
    
    def _init_anthropic_client(self):
        """初始化 Anthropic 客户端"""
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
            self.client_type = "anthropic"
        except ImportError:
            # 如果没有安装 anthropic，尝试使用 OpenAI 格式
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.client_type = "openai"
    
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
            max_tokens: 最大生成 Token 数（可选）
        
        Returns:
            生成的文本内容
        """
        if self.client_type == "anthropic":
            return self._generate_anthropic(prompt, system_prompt, max_tokens)
        else:
            return self._generate_openai(prompt, system_prompt, max_tokens)
    
    @with_retry(max_retries=3, base_delay=2.0)
    def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """使用 OpenAI 格式生成"""
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
    
    @with_retry(max_retries=3, base_delay=2.0)
    def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """使用 Anthropic 格式生成"""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        if system_prompt:
            kwargs["system"] = system_prompt
        
        response = self.client.messages.create(**kwargs)
        
        return response.content[0].text
    
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
            # 粗略估算
            chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
            other_chars = len(text) - chinese_chars
            return int(chinese_chars * 1.5 + other_chars * 0.3)
    
    def get_info(self) -> Dict[str, Any]:
        """获取客户端信息"""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
