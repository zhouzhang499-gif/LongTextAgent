# LongTextAgent 📚

基于 **AgentWrite** 思路的长文本生成 Agent，支持多种文档类型，具备记忆管理和一致性检查能力。

## ✨ 特性

- 🎯 **多模式支持** - 小说、研究报告、博客文章、技术文档
- 🧠 **智能记忆** - 层级摘要管理，突破上下文限制
- 🔍 **一致性检查** - 人物/设定/连续性自动检查
- 📝 **任务分解** - 自动将长文拆分为 2000-3000 字的子任务
- 🔧 **灵活配置** - YAML 配置，支持自定义模式

## 🚀 快速开始

### 安装依赖

```bash
pip install openai pyyaml tiktoken rich
```

### 设置 API Key

```bash
# Linux/Mac
export DEEPSEEK_API_KEY="sk-your-key"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-your-key"
```

### 运行生成

```bash
# 生成小说（默认模式）
python main.py --mode novel --outline examples/sample_outline.yaml --title "我的小说" -w 10000

# 生成研究报告
python main.py --mode report --outline examples/report_outline.yaml --title "行业报告" -w 8000

# 生成博客文章
python main.py --mode article --outline examples/article_outline.yaml --title "技术文章" -w 5000

# 查看所有模式
python main.py --list-modes
### 自我矫正 (Self-Correction)

```bash
# 生成后自动进行检查
python main.py --outline outline.yaml --auto-check

# 检查已有文件
python main.py --check-file output/novel.md
```

## 📋 支持的模式

| 模式 | 命令 | 适用场景 |
|------|------|----------|
| 📚 novel | `--mode novel` | 小说、故事、剧本 |
| 📊 report | `--mode report` | 研究报告、行业分析、市场调研 |
| 📝 article | `--mode article` | 公众号、博客、专栏文章 |
| 📋 document | `--mode document` | API文档、用户指南、产品手册 |
| 🔧 custom | `--mode custom` | 自定义配置 |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
│              大纲 + 设定 + 目标字数 + 模式                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   📋 阶段一: 规划 (Planner)                  │
│         解析大纲 → 识别章节 → 分解子任务 → 分配字数           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   ✍️ 阶段二: 生成 (Writer)                   │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐       │
│  │ 构建上下文 │ → │ 调用 LLM │ → │ 记录摘要到 Memory │       │
│  └──────────┘    └──────────┘    └──────────────────┘       │
│       ↑                                    │                 │
│       └────────── 循环直到完成 ─────────────┘                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 🔍 阶段三: 一致性检查 (Checker)               │
│      人物名称 → 行为一致性 → 连续性 → 设定冲突 → 报告         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     📄 阶段四: 输出                          │
│              合并章节 → 保存文件 → 生成检查报告               │
└─────────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
LongTextAgent/
├── config/
│   ├── settings.yaml      # 基础配置 (LLM、生成参数)
│   └── modes.yaml         # 5种模式的提示词配置
├── agents/
│   ├── planner.py         # 大纲解析、任务分解
│   ├── writer.py          # 多模式内容生成
│   └── checker.py         # 一致性检查器
├── memory/
│   ├── context_manager.py # 基础上下文管理
│   ├── summary_store.py   # 层级摘要 (段落→章节→卷)
│   └── settings_store.py  # 人物档案、伏笔、时间线
├── pipeline/
│   └── novel_pipeline.py  # 主生成管道
├── utils/
│   ├── llm_client.py      # LLM 客户端 (DeepSeek)
│   └── text_utils.py      # 文本处理工具
├── examples/
│   ├── sample_outline.yaml   # 小说大纲示例
│   ├── report_outline.yaml   # 报告大纲示例
│   └── article_outline.yaml  # 文章大纲示例
├── main.py                # 命令行入口
├── requirements.txt       # 依赖列表
└── README.md              # 本文档
```

## 📝 大纲格式

### YAML 格式（推荐）

```yaml
title: 我的小说

settings:
  world: |
    现代都市背景，灵气复苏的世界
  characters:
    林晓: 主角，程序员，意外觉醒异能
    苏然: 神秘组织成员，负责招募觉醒者

chapters:
  - title: 第一章 觉醒
    brief: 主角在加班时意外觉醒异能
    words: 3000
  
  - title: 第二章 接触
    brief: 神秘组织找上门来
    words: 3000
```

### 纯文本格式

```
第一章：主角觉醒异能
第二章：神秘组织接触
第三章：第一次战斗
```

## ⚙️ 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--outline, -o` | 大纲文件路径 | (必填) |
| `--mode, -m` | 生成模式 | `novel` |
| `--target-words, -w` | 目标字数 | `10000` |
| `--title, -t` | 作品标题 | `未命名作品` |
| `--config, -c` | 配置文件 | `config/settings.yaml` |
| `--no-check` | 禁用一致性检查 | `False` |
| `--list-modes` | 显示所有模式 | - |

## 🧠 核心算法

### AgentWrite 思路

1. **任务分解** - 将长文本目标拆分为多个 2000-3000 字的子任务
2. **逐段生成** - 为每个子任务构建上下文并调用 LLM 生成
3. **摘要压缩** - 将已生成内容压缩为摘要，保持上下文窗口可控
4. **拼接输出** - 合并所有生成内容

### 上下文构建

```
上下文 = 世界观设定 (固定)
       + 最近5条章节摘要 (滚动更新)
       + 前文500字 (衔接参考)
       + 当前任务描述 (动态)
```

## 🔍 一致性检查

系统自动检查以下内容：

| 检查项 | 说明 |
|--------|------|
| 人物名称 | 检测名称变体/笔误 |
| 行为一致性 | 人物行为是否符合设定性格 |
| 连续性 | 场景过渡、状态衔接是否自然 |
| 设定冲突 | 内容是否与世界观矛盾 |
| 逻辑漏洞 | LLM 深度检查前后矛盾 |

发现问题时自动生成检查报告。

## 🔧 配置说明

### config/settings.yaml

```yaml
llm:
  provider: deepseek
  api_key: ${DEEPSEEK_API_KEY}  # 从环境变量读取
  model: deepseek-chat
  temperature: 0.7

generation:
  words_per_section: 2500  # 每个子任务的目标字数
  min_tolerance: 0.8       # 最小字数容差
  max_tolerance: 1.2       # 最大字数容差

context:
  max_context_tokens: 8000
  recent_summaries_count: 5

output:
  directory: ./output
```

## 📊 性能参考

| 目标字数 | 章节数 | 预计耗时 | API 调用次数 |
|----------|--------|----------|--------------|
| 5,000 | 2-3 | 3-5 分钟 | ~10 |
| 10,000 | 4-5 | 8-12 分钟 | ~20 |
| 30,000 | 10-15 | 30-45 分钟 | ~60 |

*实际耗时取决于网络和 API 响应速度*

## 🛠️ 开发计划

- [ ] 支持更多 LLM 提供商（OpenAI、Claude、通义千问）
- [ ] 添加 Web UI 界面
- [ ] 支持断点续写
- [ ] 添加 RAG 检索增强
- [ ] 多 Agent 协作模式

## 📄 License

MIT License

## 🙏 致谢

- 灵感来源：[AgentWrite](https://arxiv.org/abs/2407.21500) 论文
- LLM 提供：[DeepSeek](https://www.deepseek.com/)
