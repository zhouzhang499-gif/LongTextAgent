"""
LongTextAgent API Server
用于对接华为小艺工作流模式的 API 服务
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# 添加项目路径
import sys
from pathlib import Path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from pipeline.novel_pipeline import ContentPipeline
from utils.llm_client import list_providers

# ==================== API Models ====================

class GenerateRequest(BaseModel):
    """生成请求"""
    outline: str = Field(..., description="大纲内容")
    title: str = Field(default="未命名作品", description="作品标题")
    target_words: int = Field(default=5000, ge=500, le=100000, description="目标字数")
    mode: str = Field(default="novel", description="生成模式: novel/report/article/document")
    settings: Optional[dict] = Field(default=None, description="背景设定")
    enable_check: bool = Field(default=False, description="是否启用一致性检查")


class GenerateResponse(BaseModel):
    """生成响应"""
    task_id: str
    status: str  # pending, running, completed, failed
    content: Optional[str] = None
    word_count: Optional[int] = None
    message: Optional[str] = None


class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    status: str
    progress: Optional[str] = None
    content: Optional[str] = None
    word_count: Optional[int] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class QuickGenerateRequest(BaseModel):
    """快速生成请求（简化版，适合小艺对话）"""
    prompt: str = Field(..., description="用户输入的描述")
    words: int = Field(default=3000, description="目标字数")
    type: str = Field(default="article", description="内容类型")


# ==================== App Setup ====================

app = FastAPI(
    title="LongTextAgent API",
    description="长文本生成 Agent API 服务 - 支持对接华为小艺",
    version="1.0.0"
)

# CORS 配置（允许小艺平台调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 任务存储（生产环境应使用 Redis）
tasks_store = {}


# ==================== Helper Functions ====================

def create_pipeline(mode: str = "novel") -> ContentPipeline:
    """创建生成管道"""
    return ContentPipeline(
        config_path="config/settings.yaml",
        modes_path="config/modes.yaml",
        mode=mode,
        enable_consistency_check=False
    )


def run_generation_task(task_id: str, request: GenerateRequest):
    """后台运行生成任务"""
    try:
        tasks_store[task_id]["status"] = "running"
        
        pipeline = create_pipeline(request.mode)
        
        content = pipeline.run(
            outline=request.outline,
            settings=request.settings,
            target_words=request.target_words,
            title=request.title
        )
        
        # 计算字数
        word_count = len(content)
        
        tasks_store[task_id].update({
            "status": "completed",
            "content": content,
            "word_count": word_count,
            "completed_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        tasks_store[task_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "service": "LongTextAgent API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "generate": "/api/generate",
            "quick": "/api/quick",
            "status": "/api/task/{task_id}",
            "modes": "/api/modes",
            "providers": "/api/providers"
        }
    }


@app.get("/api/modes")
async def get_modes():
    """获取支持的生成模式"""
    return {
        "modes": {
            "novel": "小说/故事 - 适用于各类虚构作品",
            "report": "研究报告 - 适用于市场调研、行业分析",
            "article": "文章/博客 - 适用于公众号、博客帖子",
            "document": "技术文档 - 适用于产品手册、API文档"
        }
    }


@app.get("/api/providers")
async def get_providers():
    """获取支持的 LLM 提供商"""
    return {"providers": list_providers()}


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    异步生成长文本
    
    适用于大型生成任务，返回 task_id 用于查询进度
    """
    task_id = str(uuid.uuid4())
    
    # 创建任务记录
    tasks_store[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": "等待开始",
        "content": None,
        "word_count": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "completed_at": None
    }
    
    # 添加后台任务
    background_tasks.add_task(run_generation_task, task_id, request)
    
    return GenerateResponse(
        task_id=task_id,
        status="pending",
        message="任务已创建，请使用 task_id 查询进度"
    )


@app.get("/api/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """查询任务状态"""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskStatus(**tasks_store[task_id])


@app.post("/api/quick")
async def quick_generate(request: QuickGenerateRequest):
    """
    快速生成（同步）
    
    适用于小艺对话场景，直接返回生成结果
    注意：大文本可能超时，建议 words <= 5000
    """
    # 将用户描述转换为大纲
    outline = f"""
主题：{request.prompt}

内容要求：
- 围绕"{request.prompt}"展开
- 内容详实，逻辑清晰
- 语言流畅，易于理解
"""
    
    # 选择模式
    mode_map = {
        "article": "article",
        "novel": "novel", 
        "story": "novel",
        "report": "report",
        "document": "document",
        "doc": "document"
    }
    mode = mode_map.get(request.type, "article")
    
    try:
        pipeline = create_pipeline(mode)
        content = pipeline.run(
            outline=outline,
            target_words=request.words,
            title=request.prompt[:20]
        )
        
        return {
            "success": True,
            "content": content,
            "word_count": len(content),
            "mode": mode
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/xiaoyi")
async def xiaoyi_interface(request: dict):
    """
    华为小艺专用接口
    
    符合小艺工作流插件规范
    """
    try:
        # 解析小艺请求
        user_input = request.get("query", request.get("text", ""))
        params = request.get("params", {})
        
        words = params.get("words", 3000)
        content_type = params.get("type", "article")
        
        # 构建大纲
        outline = f"主题：{user_input}\n请围绕这个主题进行创作。"
        
        # 生成
        pipeline = create_pipeline(content_type)
        content = pipeline.run(
            outline=outline,
            target_words=words,
            title=user_input[:20]
        )
        
        # 返回小艺格式响应
        return {
            "code": 0,
            "message": "success",
            "data": {
                "reply": content[:500] + "..." if len(content) > 500 else content,
                "full_content": content,
                "word_count": len(content)
            }
        }
        
    except Exception as e:
        return {
            "code": -1,
            "message": str(e),
            "data": None
        }


# ==================== Health Check ====================

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ==================== Main ====================

if __name__ == "__main__":
    print("=" * 50)
    print("LongTextAgent API Server")
    print("=" * 50)
    print("Endpoints:")
    print("  - http://localhost:8000/api/quick    (快速生成)")
    print("  - http://localhost:8000/api/generate (异步生成)")
    print("  - http://localhost:8000/api/xiaoyi   (小艺专用)")
    print("  - http://localhost:8000/docs         (API文档)")
    print("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
