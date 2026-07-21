# Agent Xi

> 一个内核，多个面孔——在 CLI、Web、IDE、IM 里都是同一个 AI 伙伴。

Agent Xi 不是一个"聊完即忘"的 chatbot，而是一个有**持续记忆**、能**调用工具**、有**稳定人格**的 AI 智能体内核。所有前端（命令行 / 网页 / 未来的 IM）通过 WebSocket 连接同一个常驻进程，共享记忆、状态与正在执行的任务。

## 它和普通 Chatbot 的区别

| 普通 Chatbot | Agent Xi |
|---|---|
| 每次对话独立，失忆 | 跨平台、跨会话的持续记忆（情景 + 语义双层） |
| 每个平台独立部署，互不相通 | 一个内核，所有平台共享状态 |
| 被动回答问题 | ReAct 循环自主调用工具完成任务 |
| 无个性，可被 prompt 重置 | 稳定的人格与行为准则 |

## 核心特性

**记忆系统**
- 情景记忆（LanceDB 向量检索）："上次我们聊过什么"
- 语义记忆（SQLite）："用户喜欢简洁回答"这类长期事实
- 双通道写入：正则快捕 + 对话结束时 LLM 深度提取

**工具调用（Inner Loop）**
- ReAct 循环：意图理解 → 工具决策 → 执行 → 观察 → 继续（上限 5 轮）
- 三级安全分级：`SAFE` 自动执行 / `SENSITIVE` 需确认 / `DANGEROUS` 需确认 + 平台白名单
- WebSocket 双向确认：危险操作在前端弹窗，用户点头才执行

**技能 & MCP**
- 技能系统：SQLite + LanceDB 混合匹配，按意图自动装载
- MCP stdio 客户端：可接入任意 MCP Server 扩展能力
- 插件市场 API：安装 / 卸载 MCP 与技能的全链路

**Web 控制台（像素 RPG 风格）**
- 三栏布局：冒险者名册 / 系统日志 / 详情 + 任务公告板
- 商店视图（MCP / 技能管理）、设置视图（API Keys / 记忆统计）
- 多模态上传：拖拽 / 按钮上传文件，LLM 收到文件路径并可调用工具读取
- 会话持久化：刷新页面自动恢复历史对话

## 架构

```
                     ┌──────────────┐
                     │   LLM APIs   │
                     │ DeepSeek/Claude │
                     └──────┬───────┘
                            │ httpx（流式）
                ┌───────────┴───────────┐
                │      Agent Core       │
                │  Brain（ReAct 引擎）   │
                │  Memory（情景+语义）   │
                │  Tool Registry（分级） │
                │  Skills / MCP Client  │
                │  Personality（人格）   │
                └───────────┬───────────┘
                            │ ws://localhost:9731（JSON 协议）
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
        ┌───────┐      ┌─────────┐    ┌──────────┐
        │  CLI  │      │   Web   │    │ IM（规划）│
        │ Rich  │      │ Vite+TS │    │ QQ/微信   │
        └───────┘      └─────────┘    └──────────┘
```

设计原则：**前端只是翻译层**。每个平台适配器只负责 I/O 转换，不包含任何业务逻辑；记忆、状态、任务在内核中实时共享。

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ / TypeScript | 后端 asyncio，前端零框架 |
| Web 服务 | FastAPI + uvicorn | REST / WS 同进程，自动文档 |
| 向量库 | LanceDB | 纯本地零配置，Windows 友好 |
| 结构化存储 | SQLite | 零配置，标准库 |
| LLM 接入 | httpx 直调 | 不引入 LangChain 等重框架 |
| 前端 | Vite + 原生 TS | 像素风 CSS + Houdini worklets |

## 快速开始

### 后端

```bash
# 1. 创建虚拟环境并安装
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"

# 2. 配置环境变量
copy .env.example .env
# 编辑 .env，填入你的 DeepSeek / Claude API Key

# 3. 启动服务（默认 9731 端口）
agent-xi-server
```

### 前端

```bash
cd web
npm install
npm run dev        # http://localhost:5180
```

打开浏览器访问 `http://localhost:5180`，即可与 Xi 对话。

### 生产构建

```bash
cd web
npm run build      # 产物在 web/dist/
```

### CLI

```bash
agent-xi           # 终端里直接对话
```

## 项目结构

```
agent_xi_project/
├── src/agent_xi/          # 内核（pip installable）
│   ├── brain/             # ReAct 推理引擎 + 上下文构建 + token 预算
│   ├── memory/            # 情景记忆（LanceDB）+ 语义记忆（SQLite）
│   ├── tools/             # 工具注册中心 + 三级安全 + 内置工具
│   ├── skills/            # 技能存储与匹配
│   ├── mcp/               # MCP stdio JSON-RPC 客户端
│   ├── llm/               # LLM 抽象层（DeepSeek / Claude provider）
│   ├── server/            # FastAPI 应用 / WS / 会话 / 市场 / 上传
│   └── cli/               # Rich 命令行应用
├── web/                   # 前端（Vite + 原生 TypeScript）
│   ├── src/
│   │   ├── net/           # WS 客户端 + REST API
│   │   ├── ui/            # 名册 / 日志 / 详情 / 商店 / 设置 / 附件
│   │   └── ...
│   └── public/            # 像素字体 / 纹理 / worklets
├── config/                # 人格 prompt / 默认配置 / MCP 配置
├── tests/                 # pytest（36 通过）
└── pyproject.toml
```

## 测试

```bash
pytest                 # 36 个测试，覆盖 brain / memory / server / uploads
```

## 路线图

- [x] 阶段 1 — 内核原型（LLM 抽象层 + Brain + CLI）
- [x] 阶段 2 — 记忆系统（情景 + 语义）
- [x] 阶段 3 — 工具调用（ReAct Inner Loop + 安全分级）
- [x] 阶段 4 — 架构拆分 + 技能 / MCP
- [x] 阶段 5 — Web 前端 + 服务化
- [x] 阶段 5.5 — 稳定化冲刺（会话持久化 / 冒烟测试 / E2E）
- [ ] 阶段 6 — IM 接入（QQ / 微信）
- [ ] 阶段 7 — 打磨 & 生产化
- [ ] 阶段 8 — 自主循环（Outer Loop：目标拆解 → 执行 → 验证 → 续跑）
- [ ] 阶段 9 — 多智能体协作（planner / coder / reviewer）

## License

私人项目，暂未开源协议。
