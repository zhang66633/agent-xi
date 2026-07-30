# Agent Xi

> 一个内核，多个面孔——在 CLI、Web、IDE、IM 里都是同一个 AI 伙伴。

Agent Xi 是一个有**持续记忆**、能**调用工具**、有**稳定人格**的 AI 智能体内核。基于 cc-haha (Claude Code) 架构深度参考构建，对标 Anthropic 官方 agent 的引擎设计。

## 核心特性

### 引擎架构（对标 Claude Code QueryEngine）
- **ReAct 循环**：意图理解 → 工具决策 → 执行 → 观察 → 继续（上限 **30 轮**，对标 Claude Code 的 20-80 次工具调用）
- **中断/Abort**：`Brain.interrupt()` 随时中止正在进行的操作，流中检查 + 循环检查点
- **上下文压缩**：超 70% token 预算自动 LLM 摘要压缩（对标 snip/compact）
- **并行工具执行**：SAFE 工具 `asyncio.gather` 并行，速度提升 3-5x
- **权限拒绝追踪**：5 分钟冷却期 + LLM 自动感知
- **错误回滚**：历史快照，出错自动回滚
- **流重试**：stream 失败后非流式 fallback

### 多模型支持
- **DeepSeek** — 默认 provider（OpenAI 兼容 API）
- **Claude** — Anthropic Messages API 原生支持
- **OpenAI** — GPT-4o / O1 等模型
- **Ollama** — 本地模型推理（qwen2.5 / llama 等）

### 工具系统（16+ 工具，对标 Claude Code 核心集）
| 工具 | 功能 |
|------|------|
| `grep` | ripgrep 内容搜索（正则、上下文、分页） |
| `glob` | 文件模式匹配（`**/*.py`，mtime 排序） |
| `read_file` | 文件读取（offset/limit，50000 字符上限） |
| `write_file` | 文件写入/覆盖 |
| `edit_file` | 精确字符串替换编辑（对标 Claude Code Edit） |
| `git_diff` | Git 变更查看（unstaged/staged/commit） |
| `execute_shell` | Shell 命令执行 |
| `task` | 任务清单管理（对标 TodoWrite） |
| `web_search` | 网页搜索 |
| `screenshot` | 桌面截图 |
| `computer_use` | 鼠标/键盘桌面控制 |
| `calculator` | 数学计算 |
| `get_time` | 时间查询 |
| `http_request` | HTTP 请求 |
| `list_dir` | 目录浏览 |

### 安全分级（5 级，对标 cc-haha）
| 级别 | 行为 |
|------|------|
| `SAFE` | 自动执行 |
| `ALLOW_ONCE` | 本次会话允许一次 |
| `SENSITIVE` | 每次确认 |
| `ASK_EVERY` | 每次确认 + 不记忆 |
| `DANGEROUS` | 确认 + 冷却期拒绝拦截 |

### 记忆系统
- **情景记忆**（LanceDB 向量检索）：跨会话语义召回
- **用户画像**（`config/service.md`）：LLM 整体重写 + 版本快照
- **三段式人设**：`identity.md` / `personality.md` / `service.md`

### 多智能体协作
- **Planner** — 需求拆解
- **Coder** — 代码执行
- **Reviewer** — 质量审查
- **Coordinator** — 编排协调
- **Outer Loop** — 目标分解 → 执行 → 验证 → 续跑（状态外置 + 断点续跑）

### 主题系统
- 4 种主题：木色暗色 / 亮色纸 / 暖色经典 / 终端绿
- CSS 变量驱动 + localStorage 持久化

### 技能市场 & MCP
- 15+ 可安装技能（代码审查、翻译、数据分析、安全审计等）
- 10+ MCP 服务器（Filesystem、GitHub、SQLite、PostgreSQL 等）
- 技能标签/分类系统
- MCP stdio JSON-RPC 客户端

### 用量追踪 & 成本估算
- Token 用量实时追踪（SQLite）
- 按 model 定价估算费用
- 前端柱状图展示趋势

### 定时任务
- Cron 表达式调度
- 独立会话执行
- 运行日志持久化

## 架构

```
                     ┌──────────────┐
                     │   LLM APIs   │
                     │ DeepSeek/Claude/OpenAI/Ollama │
                     └──────┬───────┘
                            │ httpx（流式 + 重试）
                ┌───────────┴───────────┐
                │      Agent Core       │
                │  Brain（ReAct 引擎）   │ ← Inner Loop (中断/压缩/并行/回滚)
                │  Memory（情景+画像）   │
                │  Tool Registry（5级）  │
                │  Skills / MCP / Agents │
                │  Loop（Outer Loop）    │ ← 目标拆解→执行→验证→续跑
                │  Scheduler（定时任务） │
                └───────────┬───────────┘
                            │ ws://localhost:9731（JSON 协议）
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
        ┌───────┐      ┌─────────┐    ┌──────────┐
        │  CLI  │      │   Web   │    │ IM（规划）│
        │ Rich  │      │ Vite+TS │    │ QQ/微信   │
        └───────┘      └─────────┘    └──────────┘
```

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ / TypeScript | 后端 asyncio，前端零框架 |
| Web 服务 | FastAPI + uvicorn | REST / WS 同进程 |
| 向量库 | LanceDB | 纯本地零配置，Windows 友好 |
| 结构化存储 | SQLite | 零配置，标准库 |
| LLM 接入 | httpx 直调 | 不引入 LangChain 等重框架 |
| 前端 | Vite + 原生 TS | 像素风 CSS + 4 主题 |

## 快速开始

### 一键启动（Windows）
```bat
# 双击 start.bat
# 打开 http://localhost:9731
```

### 开发模式
```bat
# 双击 start-dev.bat
# 后端 http://localhost:9731 + 前端热更新 http://localhost:5180
```

### 手动启动

**后端**
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -e ".[dev]"

# 配置 API Key
copy .env.example .env
# 编辑 .env：DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY

# 启动
agent-xi-server                 # 后端 http://localhost:9731
```

**前端**
```bash
cd web && npm install
npm run dev                     # 开发模式 http://localhost:5180
npm run build                   # 生产构建 → web/dist/
```

**CLI**
```bash
agent-xi                        # 终端里直接对话
```

**Docker**
```bash
docker compose up -d --build    # http://localhost:9731
```

## 项目结构

```
agent_xi_project/
├── src/agent_xi/          # 内核
│   ├── brain/             # ReAct 引擎 + 上下文 + token 预算 + 压缩
│   ├── memory/            # 情景记忆（LanceDB）+ 用户画像
│   ├── tools/             # 工具注册中心 + 5 级安全 + 16 内置工具
│   ├── skills/            # 技能存储（SQLite + LanceDB）与匹配
│   ├── agents/            # 多智能体角色（Planner/Coder/Reviewer/Coordinator）
│   ├── loop/              # Outer Loop 编排器（目标分解 + 续跑）
│   ├── scheduler/         # 定时任务系统
│   ├── mcp/               # MCP stdio JSON-RPC 客户端
│   ├── llm/               # LLM 抽象层（DeepSeek/Claude/OpenAI/Ollama）
│   ├── server/            # FastAPI / WS / 会话 / 市场 / 用量 / 上传
│   └── cli/               # Rich 命令行应用
├── web/                   # 前端（Vite + TypeScript）
│   └── src/
│       ├── net/           # WS 客户端 + REST API
│       └── ui/            # 名册 / 日志 / 详情 / 商店 / 设置
├── config/                # 人格 / MCP / Outer Loop / 多智能体配置
├── tests/                 # pytest（84 通过）
├── start.bat / start-dev.bat  # Windows 启动脚本
├── start.sh               # Linux/macOS 启动脚本
├── Dockerfile / docker-compose.yml
└── pyproject.toml
```

## 测试

```bash
pytest                     # 84 个测试：brain / memory / server / loop / agents / tools / usage
```

## 路线图

- [x] 阶段 1-5.5 — 内核原型、记忆、工具、Web 前端、稳定化
- [x] **对标 cc-haha 优化 R1** — 多模型、多智能体、Computer Use、主题、技能市场、用量追踪
- [x] **对标 cc-haha 优化 R2** — 引擎中断、上下文压缩、并行工具、权限追踪、ReAct 30 轮、grep/glob/edit/task
- [x] **对标 cc-haha 优化 R3** — Tool 基类升级（buildTool 模式）、三态权限管道、tool_prompt 注入、结构化输出
- [ ] 阶段 6 — IM 接入（Telegram Bot 预留 / QQ / 微信）
- [ ] 阶段 7 — 打磨 & 生产化（桌面宠物动画 / 前端 diff 渲染 / 多会话标签页）

## 参考项目

本项目架构深度参考 [cc-haha](https://github.com/NanmiCoder/cc-haha)（Claude Code 开源桌面工作空间，13.7k stars），包括其 QueryEngine 引擎设计、buildTool 工厂模式、权限管道、上下文压缩、skill 系统等核心模式。

## License

MIT License — 详见 [LICENSE](./LICENSE)
