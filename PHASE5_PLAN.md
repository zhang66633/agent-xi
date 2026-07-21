# Phase 5 架构方案 — WebSocket Server + 像素风 Web UI

> 目标：浏览器中的像素游戏风 AI 伙伴界面。
> 技术栈：FastAPI WebSocket + Phaser 3 + rexUI + 像素美术。

---

## 整体架构

```
┌─────────────────────────────────────────────────────┐
│  Browser (Phaser 3 Game)                            │
│  ┌───────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ ChatScene │ │MarketScene│ │  AdminScene       │  │
│  │ (主对话)  │ │(插件市场) │ │(记忆/技能/历史)  │  │
│  └─────┬─────┘ └────┬─────┘ └────────┬──────────┘  │
│        │             │                │              │
│        └─────────────┴────────────────┘              │
│                      │ WebSocket + REST              │
└──────────────────────┼──────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────┐
│  FastAPI Server      │                              │
│  ┌───────────────────┴────────────────────────┐     │
│  │  /ws/chat     — WebSocket 流式对话         │     │
│  │  /api/market  — 插件市场 registry          │     │
│  │  /api/install — 安装 MCP/Skill             │     │
│  │  /api/memory  — 记忆浏览/管理              │     │
│  │  /api/skills  — 技能列表/CRUD              │     │
│  │  /api/history — 对话历史                    │     │
│  └────────────────────────────────────────────┘     │
│                      │                              │
│  ┌───────────────────┴────────────────────────┐     │
│  │  Agent Xi Core (Brain + Memory + Tools)     │     │
│  └────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

---

## 1. 后端：FastAPI WebSocket Server

```
src/agent_xi/server/
├── __init__.py
├── app.py          ← FastAPI 应用 + 路由注册
├── ws_chat.py      ← WebSocket 对话处理
├── api_market.py   ← 插件市场 REST API
├── api_admin.py    ← 管理面板 REST API
└── session.py      ← 会话管理（多用户支持）
```

### WebSocket 协议

```json
// 客户端 → 服务端
{"type": "chat", "content": "你好"}
{"type": "command", "content": "/memory"}
{"type": "confirm_tool", "tool_id": "xxx", "allowed": true}

// 服务端 → 客户端（流式）
{"type": "text_delta", "text": "你"}
{"type": "tool_use_start", "tool_name": "get_time"}
{"type": "tool_result", "tool_name": "get_time", "preview": "..."}
{"type": "tool_confirm_request", "tool_id": "xxx", "tool_name": "execute_shell", "args": {...}}
{"type": "done", "usage": {...}}
{"type": "error", "message": "..."}
```

### 关键设计

- 复用现有 `Brain.chat()` 的 `AsyncIterator[StreamEvent]`，逐事件序列化为 JSON 推送
- 工具确认：WS 推送 confirm_request → 等待客户端回复 → 通过 `asyncio.Event` 唤醒 Brain
- 会话隔离：每个 WS 连接一个独立 Brain 实例（共享 Memory/Tools）

---

## 2. 前端：Phaser 3 像素游戏 UI

```
web/
├── index.html
├── package.json
├── vite.config.ts
├── src/
│   ├── main.ts              ← Phaser 游戏入口
│   ├── config.ts            ← 游戏配置（分辨率、缩放）
│   ├── scenes/
│   │   ├── BootScene.ts     ← 资源加载
│   │   ├── ChatScene.ts     ← 主对话场景
│   │   ├── MarketScene.ts   ← 插件市场
│   │   └── AdminScene.ts    ← 管理面板
│   ├── ui/
│   │   ├── ChatBox.ts       ← 对话框组件（9-slice 边框）
│   │   ├── InputBox.ts      ← 文本输入（HTML overlay）
│   │   ├── MessageBubble.ts ← 消息气泡
│   │   ├── ToolPanel.ts     ← 工具调用状态面板
│   │   └── PixelButton.ts   ← 像素按钮
│   ├── characters/
│   │   ├── XiSprite.ts      ← Xi 角色动画控制
│   │   └── animations.ts    ← 动画定义
│   ├── net/
│   │   └── ws_client.ts     ← WebSocket 客户端封装
│   └── assets/              ← 像素素材
│       ├── xi/              ← Xi 角色 sprite sheet
│       ├── ui/              ← UI 元素（边框、按钮、图标）
│       ├── bg/              ← 背景场景
│       └── fonts/           ← 像素字体
└── public/
```

### 游戏配置

```typescript
const config: Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,
  width: 960,
  height: 640,
  pixelArt: true,  // 关键：保持像素锐利
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
  scene: [BootScene, ChatScene, MarketScene, AdminScene],
};
```

### 场景设计

**ChatScene（主界面）**：
- 背景：像素风房间/花园（类似星露谷室内）
- 左侧/中央：Xi 角色 sprite（idle/talk/think/happy 动画）
- 右侧：对话面板（9-slice 像素边框，滚动消息列表）
- 底部：输入框（HTML textarea overlay，支持中文 IME）
- 工具调用时：Xi 播放 "think" 动画 + 弹出工具状态小面板

**MarketScene（插件市场）**：
- 像素风商店界面（像星露谷的商店）
- 左侧：商品列表（MCP/Skill 卡片，像素图标）
- 右侧：详情面板 + "安装" 按钮
- 顶部：搜索栏 + 分类标签

**AdminScene（管理面板）**：
- 标签页：记忆 / 技能 / 历史 / 设置
- 像素风表格/列表
- 记忆可视化（时间线或节点图）

### 文本输入方案

Canvas 不原生支持中文 IME，标准做法：

```typescript
// 在 canvas 上叠加一个透明 HTML textarea
const inputEl = document.createElement('textarea');
inputEl.style.cssText = 'position:absolute; opacity:0; pointer-events:none;';
document.body.appendChild(inputEl);

// 点击游戏内输入框时，focus 到 textarea
// 监听 input/compositionend 事件获取中文输入
// 在 canvas 中用 BitmapText 渲染已输入文本
```

---

## 3. 像素美术方案

### 需要的素材清单

| 素材 | 尺寸 | 来源 |
|------|------|------|
| Xi 角色 sprite sheet | 32x32 或 48x48，4方向 × 4帧 | AI 生成 + Aseprite 修 |
| Xi 表情（对话用） | 64x64 头像，6种表情 | AI 生成 |
| UI 边框 tile | 16x16（9-slice 用） | AI 生成 / 素材包 |
| 像素按钮 | 32x16 normal/hover/pressed | CSS 或 sprite |
| 背景场景 | 960x640 tilemap | AI 生成 / 素材包 |
| 工具图标 | 16x16 每个 | 素材包 / AI |
| 像素字体 | Zpix（中文）+ Press Start 2P（英文） | 开源 |

### 获取方式

1. **AI 生成**：用图像生成模型出 32x32/64x64 像素角色和图标
2. **素材包**：itch.io 搜 "pixel UI"、"RPG dialog"、"cozy interior tileset"
3. **字体**：Zpix（最像素）开源免费，Press Start 2P Google Fonts

### Xi 角色动画状态

```
idle    → 站立呼吸（2帧循环）
talk    → 说话嘴巴动（4帧循环）
think   → 摸头/抬头（工具执行时）
happy   → 开心跳（任务完成时）
wave    → 挥手（打招呼/告别）
```

---

## 4. 实现顺序

```
Phase 5a: FastAPI WS Server（复用 Brain，~1.5h）
Phase 5b: Phaser 项目搭建 + BootScene + 基础 UI 组件（~1h）
Phase 5c: ChatScene 完整对话流（WS 连接 + 消息渲染 + 输入）（~2h）
Phase 5d: Xi 角色 sprite + 动画状态机（~1h，含 AI 生图）
Phase 5e: MarketScene + 安装 API（~1.5h）
Phase 5f: AdminScene（记忆/技能/历史）（~1h）
Phase 5g: 打磨（音效、过渡动画、响应式）（~1h）
```

---

## 5. 依赖

**Python 新增**：
```
fastapi
uvicorn[standard]
websockets
```

**前端**：
```
phaser@3.80+
@rexui/phaser3-plugin  (或 phaser3-rex-plugins)
vite
typescript
```

---

## 6. 启动方式

```bash
# 后端
.venv\Scripts\python.exe -m agent_xi.server

# 前端（开发）
cd web && npm run dev

# 生产：FastAPI 直接 serve 静态文件
```
