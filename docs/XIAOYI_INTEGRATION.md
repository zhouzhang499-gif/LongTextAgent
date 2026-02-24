# 小艺工作流对接指南

## 概述

本指南介绍如何将 LongTextAgent 部署为 API 服务，并对接到华为小艺工作流。

## 架构

```text
用户语音 → 小艺 → 工作流 → 你的API服务 → 返回生成内容 → 小艺播报
```

## 第一步：本地测试

### 1. 安装依赖

```bash
pip install fastapi uvicorn
```

### 2. 启动服务

```bash
# 设置 API Key (以 DeepSeek 为例，如果是其他模型请设置对应的 Key 环境变量，如 OPENAI_API_KEY)
set DEEPSEEK_API_KEY=sk-your-key


# 启动服务
python api_server.py
```

### 3. 测试接口

打开浏览器访问: <http://localhost:8000/docs>

或使用 curl 测试:

```bash
# 快速生成
curl -X POST http://localhost:8000/api/quick \
  -H "Content-Type: application/json" \
  -d '{"prompt": "写一篇关于人工智能的文章", "words": 2000}'

# 小艺专用接口
curl -X POST http://localhost:8000/api/xiaoyi \
  -H "Content-Type: application/json" \
  -d '{"query": "帮我写一篇关于健康饮食的文章", "params": {"words": 3000}}'
```

## 第二步：部署到云服务器

### 推荐：华为云 ECS

1. 购买华为云 ECS（推荐 2核4G）
2. 安装 Python 3.10+
3. 上传代码并安装依赖
4. 使用 systemd 管理服务

```bash
# /etc/systemd/system/longtextagent.service
[Unit]
Description=LongTextAgent API
After=network.target

[Service]
User=root
WorkingDirectory=/opt/LongTextAgent
Environment="DEEPSEEK_API_KEY=sk-xxx"
ExecStart=/usr/bin/python3 api_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable longtextagent
systemctl start longtextagent
```

### 配置 HTTPS（必须）

小艺要求 HTTPS，使用 Nginx 反向代理:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 第三步：配置小艺工作流

### 1. 登录小艺开放平台

访问: <https://developer.huawei.com/consumer/cn/hiai>

### 2. 创建技能

1. 进入控制台 → 创建技能
2. 选择"工作流模式"
3. 添加"HTTP插件"节点

### 3. 配置 HTTP 插件

| 配置项      | 值                                                     |
|------------|--------------------------------------------------------|
| 请求地址   | `https://your-domain.com/api/xiaoyi`                   |
| 请求方式   | POST                                                   |
| Content-Type| application/json                                      |
| 请求体      | `{"query": "{{用户输入}}", "params": {"words": 3000}}` |

### 4. 配置响应解析

```text
回复内容: {{data.reply}}
```

### 5. 测试发布

1. 在测试环境验证
2. 提交审核
3. 发布上线

## API 接口说明

### /api/xiaoyi (小艺专用)

**请求:**

```json
{
  "query": "用户输入的文本",
  "params": {
    "words": 3000,
    "type": "article"
  }
}
```

**响应:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "reply": "生成内容摘要...",
    "full_content": "完整生成内容",
    "word_count": 3000
  }
}
```

### /api/quick (快速生成)

**请求:**

```json
{
  "prompt": "主题描述",
  "words": 3000,
  "type": "article"
}
```

### /api/generate (异步生成)

适用于大型生成任务，返回 task_id。

## 注意事项

1. **超时问题**: 小艺默认超时 10 秒，建议字数 <= 5000
2. **并发限制**: 生产环境需要配置多进程
3. **成本控制**: 设置 API 调用频率限制
4. **日志监控**: 添加请求日志便于排查问题

## 联系方式

如有问题，请在 GitHub 提交 Issue。
