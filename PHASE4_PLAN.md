# Phase 4 架构方案 — 能力扩展

> 目标：Token 智能裁剪、MCP 客户端接入、Skills 语义技能系统、工具扩展、System Prompt 优化。
> 实现顺序建议：Token 裁剪 → Prompt 优化 → 工具扩展 → MCP → Skills

---

## 1. Token 计数与智能裁剪

### 问题

当前 `ContextBuilder` 按消息条数截断（`max_history_turns * 2`），无法感知实际 token 消耗。长对话 + 工具结果容易超出模型上下文窗口。

### 设计

```
src/agent_xi/brain/tokenizer.py   ← 新模块
```

**接口：**

```python
class TokenCounter:
    """Token 计数器（估算）。"""

    def count(self, text: str) -> int:
        """估算文本 token 数。"""
        ...

    def count_messages(self, messages: list[Message]) -> int:
        """估算消息列表总 token 数。"""
        ...
```

**实现策略：**
- 不引入 tiktoken（DeepSeek 有自己的 tokenizer，Claude 也不同）
- 采用启发式估算：中文 ≈ 1.5 token/字，英文 ≈ 0.75 token/word
- 保守估计（宁少勿多），预留安全边距

**裁剪逻辑改造（`ContextBuilder.build_request`）：**

```python
def build_request(self, history, *, memory_context="", tools=None, ...):
    budget = self._max_context_tokens  # 如 128000
    reserved_output = 4096

    # 1. 固定开销：system prompt + memory + tools schema
    fixed = count(system) + count(memory_context) + count(tools_json)
    available = budget - reserved_output - fixed

    # 2. 从最新消息向前贪心填充
    selected = []
    used = 0
    for msg in reversed(history):
        msg_tokens = counter.count_message(msg)
        if used + msg_tokens > available:
            break
        selected.insert(0, msg)
        used += msg_tokens

    # 3. 保证最后一条 user 消息一定在（即使超预算也保留）
    ...
```

**配置新增（`config/default.yaml`）：**

```yaml
app:
  max_context_tokens: 128000   # 模型上下文窗口
  reserved_output_tokens: 4096
```

---

## 2. System Prompt 优化

### 设计

将 system prompt 从单字符串改为结构化模板，支持动态注入能力描述。

```
config/prompt.md              ← 主 prompt 模板（Markdown）
src/agent_xi/brain/prompt.py  ← Prompt 组装器
```

**prompt.md 结构：**

```markdown
# 身份
你是 Xi，一个有温度、有记忆的 AI 伙伴。

# 性格
- 好奇、幽默、偶尔毒舌但本质善良
- 说话简洁，不啰嗦

# 能力
{capabilities}          ← 动态注入（已注册工具列表）

# 记忆
{memory_instruction}    ← 有记忆时注入相关指引

# 工具使用规范
- 优先用工具获取实时信息，不要编造
- 执行敏感操作前告知用户
- 工具结果要消化后用自己的话说，不要原样粘贴
```

**PromptBuilder：**

```python
class PromptBuilder:
    def __init__(self, template_path: Path): ...

    def build(self, *, tools: list[ToolDefinition], has_memory: bool) -> str:
        """渲染最终 system prompt。"""
        ...
```

好处：prompt 可独立迭代，不需要改代码；工具列表自动同步。

---

## 3. 工具扩展

### 新增内置工具

| 工具名 | 安全级别 | 说明 |
|--------|----------|------|
| `write_file` | SENSITIVE | 写入/追加文件内容 |
| `http_request` | SENSITIVE | 发送 HTTP 请求（GET/POST） |
| `calculator` | SAFE | 数学表达式计算（用 Python eval 沙箱） |
| `list_dir` | SAFE | 列出目录内容 |

### 工具发现机制

```python
# tools/builtins/__init__.py 自动扫描
def load_all_builtins() -> list[Tool]:
    """自动发现并实例化 builtins 目录下所有 Tool 子类。"""
    ...
```

这样新增工具只需在 `builtins/` 下加文件，无需手动注册。

---

## 4. MCP 客户端接入（stdio）

### 架构

```
src/agent_xi/mcp/
├── __init__.py
├── protocol.py      ← JSON-RPC 2.0 消息定义
├── client.py        ← MCP Client（stdio 子进程管理）
├── bridge.py        ← MCP Tool → Tool ABC 适配器
└── config.py        ← MCP server 配置加载
```

### 核心流程

```
config/mcp.yaml:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "D:/"]
    - name: github
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: "${GITHUB_TOKEN}"
```

**MCPClient 生命周期：**

```python
class MCPClient:
    """单个 MCP Server 的客户端连接。"""

    async def start(self) -> None:
        """启动子进程，发送 initialize 握手。"""
        ...

    async def list_tools(self) -> list[MCPToolDef]:
        """获取 server 提供的工具列表。"""
        ...

    async def call_tool(self, name: str, arguments: dict) -> str:
        """调用 server 上的工具。"""
        ...

    async def stop(self) -> None:
        """关闭子进程。"""
        ...
```

**协议要点（JSON-RPC 2.0 over stdio）：**
- 消息格式：`Content-Length: N\r\n\r\n{json}`（类似 LSP）
- 握手：`initialize` → `initialized` notification
- 工具：`tools/list` → `tools/call`
- 每条消息有 `jsonrpc: "2.0"`, `id`, `method`, `params`

**Bridge 适配器：**

```python
class MCPToolAdapter(Tool):
    """将 MCP Server 的工具适配为 Agent Xi 的 Tool 接口。"""

    def __init__(self, mcp_client: MCPClient, tool_def: MCPToolDef): ...

    @property
    def name(self) -> str:
        return f"mcp_{self._server_name}_{self._tool_def.name}"

    @property
    def security_level(self) -> SecurityLevel:
        # MCP 工具默认 SENSITIVE（外部系统交互）
        return SecurityLevel.SENSITIVE

    async def execute(self, **kwargs) -> ToolResult:
        result = await self._client.call_tool(self._tool_def.name, kwargs)
        return ToolResult(success=True, output=result)
```

**启动流程（`__main__.py`）：**

```python
# 加载 MCP 配置 → 启动各 server → 获取工具 → 注册到 registry
mcp_manager = MCPManager(config_path)
await mcp_manager.start_all()
for tool in mcp_manager.get_adapted_tools():
    registry.register(tool)
```

---

## 5. Skills 语义技能系统

### 架构

```
src/agent_xi/skills/
├── __init__.py
├── models.py        ← Skill 数据模型
├── store.py         ← SQLite 元数据 + LanceDB 向量
├── matcher.py       ← 语义匹配引擎
├── executor.py      ← 技能执行器（步骤注入）
└── builtin/         ← 预置技能文件
    ├── code_review.md
    ├── daily_summary.md
    └── ...
```

### 数据模型

```python
@dataclass
class Skill:
    id: str
    name: str                    # 技能名（如 "代码审查"）
    description: str             # 一句话描述（用于语义匹配）
    trigger_keywords: list[str]  # 触发关键词
    steps: str                   # Markdown 格式的步骤说明
    parameters: dict[str, Any]   # 可选参数 schema
    created_at: float
    last_used: float
    use_count: int
```

### 存储

- **SQLite**（`skills.db`）：元数据 CRUD、关键词索引
- **LanceDB**（复用情景记忆的 embedding client）：description 向量化，语义检索

### 匹配流程

```python
class SkillMatcher:
    async def match(self, user_input: str) -> list[Skill]:
        """混合匹配：关键词命中 + 语义相似度。"""
        # 1. 关键词快速过滤
        keyword_hits = self._store.search_by_keywords(user_input)
        # 2. 语义检索 top-K
        semantic_hits = await self._semantic_search(user_input, top_k=5)
        # 3. 合并去重，按综合分排序
        return self._merge_and_rank(keyword_hits, semantic_hits)
```

### 执行方式

技能不是"代码执行"，而是**流程知识注入**：

1. 匹配到技能后，将 `steps` 注入当前对话上下文（类似 memory_context）
2. LLM 按照步骤指引执行，结合已有工具完成任务
3. 执行完成后更新 `last_used` 和 `use_count`

```python
# Brain.chat() 中的注入点
skill_context = await self._skill_matcher.get_context(user_input)
# 与 memory_context 合并后传给 ContextBuilder
```

### 技能学习

```python
class SkillLearner:
    async def propose_from_conversation(self, history: list[Message]) -> Skill | None:
        """对话结束后，LLM 判断是否有可提炼为新技能的流程。"""
        ...

    async def save_skill(self, skill: Skill) -> str:
        """存储新技能（SQLite + embedding）。"""
        ...
```

触发时机：`/save-skill <名称>` 命令 或 对话结束时自动提议。

---

## 6. 实现顺序与依赖

```
Phase 4a: Token 裁剪（独立，无依赖）         ~1h
Phase 4b: Prompt 优化（独立）                ~30min
Phase 4c: 工具扩展 + 自动发现（独立）         ~1h
Phase 4d: MCP 客户端（依赖 Tool ABC）        ~2-3h
Phase 4e: Skills 系统（依赖 Embedding + DB）  ~2h
```

4a/4b/4c 可并行，4d/4e 依赖现有基础设施但彼此独立。

---

## 7. 文件变更总览

| 操作 | 路径 |
|------|------|
| 新增 | `src/agent_xi/brain/tokenizer.py` |
| 新增 | `src/agent_xi/brain/prompt.py` |
| 新增 | `config/prompt.md` |
| 新增 | `config/mcp.yaml` |
| 新增 | `src/agent_xi/mcp/` (4 files) |
| 新增 | `src/agent_xi/skills/` (5 files) |
| 新增 | `src/agent_xi/tools/builtins/write_file.py` |
| 新增 | `src/agent_xi/tools/builtins/http_request.py` |
| 新增 | `src/agent_xi/tools/builtins/calculator.py` |
| 新增 | `src/agent_xi/tools/builtins/list_dir.py` |
| 修改 | `src/agent_xi/brain/context.py`（token 裁剪） |
| 修改 | `src/agent_xi/brain/engine.py`（skill 注入点） |
| 修改 | `src/agent_xi/config.py`（新配置项） |
| 修改 | `src/agent_xi/__main__.py`（MCP 启动 + skill 初始化） |
| 修改 | `src/agent_xi/tools/builtins/__init__.py`（自动发现） |
