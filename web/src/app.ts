/**
 * Agent Xi 控制台 v2.7 — 应用控制器
 *
 * 后端接入：
 *   - REST /api/health       → 连接状态轮询
 *   - REST /api/memory/stats → Xi 的 EN/友好度/累计任务
 *   - REST /api/tools        → 详情面板"可用工具"
 *   - REST /api/skills       → 详情面板"已装技能"
 *   - WS   /ws/chat          → 系统日志流式 + 工具调用 → 任务公告板
 *
 * 数据映射：
 *   Xi 智能体（id='xi'）由后端 memory stats 实时驱动
 *   其他演示智能体保留为"模拟"（后端不支持多智能体）
 *   工具调用动态生成任务条目
 */
import { WsClient } from './net/ws_client';
import { api, mapXiAgent, toolCallToQuest, type ToolInfo, type SkillInfo } from './net/api';
import { WS_URL, CONSOLE_VERSION, CONSOLE_CONTEXT } from './config';
import { RosterPanel } from './ui/roster';
import { LogPanel } from './ui/log';
import { DetailPanel } from './ui/detail';
import { CommandInput, detectCommandType } from './ui/command';
import { StatusBar } from './ui/statusbar';
import { ToolConfirmDialog } from './ui/tool_confirm';
import type { Agent, LogEntry, Quest, LogType } from './types';

// 后端轮询间隔
const POLL_INTERVAL = 15_000;

// 演示智能体（后端不支持多智能体，其余为模拟）
const DEMO_AGENTS: Agent[] = [
  { id: 'aife', name: '艾芙', role: '协调者', level: 15, state: 'active', en: 78, hearts: 8, emoji: '艾', currentTask: '统筹调度子智能体', totalTasks: 247 },
  { id: 'xingchen', name: '星辰', role: '分析师', level: 12, state: 'running', en: 45, hearts: 7, emoji: '星', currentTask: '批次_07 异常数据分析', totalTasks: 156 },
  { id: 'liefeng', name: '猎风', role: '探查者', level: 9, state: 'active', en: 90, hearts: 6, emoji: '猎', currentTask: '扫描 192.168.0.0/24', totalTasks: 89 },
  { id: 'nuanguang', name: '暖光', role: '信使', level: 6, state: 'idle', en: 100, hearts: 9, emoji: '暖', currentTask: '待命', totalTasks: 42 },
  { id: 'tiechui', name: '铁锤', role: '执行者', level: 11, state: 'error', en: 12, hearts: 5, emoji: '铁', currentTask: '连接超时 #4402', totalTasks: 178 },
  { id: 'mojuan', name: '墨卷', role: '记录者', level: 20, state: 'active', en: 66, hearts: 10, emoji: '墨', currentTask: '会话事件归档', totalTasks: 412 },
];

export class App {
  private ws!: WsClient;
  private roster!: RosterPanel;
  private log!: LogPanel;
  private detail!: DetailPanel;
  private cmd!: CommandInput;
  private status!: StatusBar;
  private confirmDialog!: ToolConfirmDialog;

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private currentAgentId: string | null = null;
  private quests: Quest[] = [];
  private tools: ToolInfo[] = [];
  private skills: SkillInfo[] = [];
  private currentRunningTool: string | null = null;
  private backendOnline = false;

  init(): void {
    // 初始化 WS
    this.ws = new WsClient(WS_URL);
    this.confirmDialog = new ToolConfirmDialog(this.ws);
    this.ws.connect();

    // 初始化 UI
    this.roster = new RosterPanel();
    this.log = new LogPanel();
    this.detail = new DetailPanel();
    this.cmd = new CommandInput();
    this.status = new StatusBar();
    this.status.start();
    this.status.setBottomContext(CONSOLE_CONTEXT);

    // 绑定事件
    this._bindRoster();
    this._bindCommand();
    this._bindWs();
    this._bindConnection();

    // 启动：先放 Xi 占位 + 演示智能体，再尝试连后端
    this._initRoster();

    // 启动消息
    this.log.append({
      id: `sys-${Date.now()}`,
      time: this._now(),
      type: 'system',
      text: `智能体控制台 ${CONSOLE_VERSION} 启动`,
    });

    // 立即拉一次后端数据，之后轮询
    this._pollBackend();
    this.pollTimer = setInterval(() => this._pollBackend(), POLL_INTERVAL);
  }

  /** 释放资源（清定时器 / 断 WS），防止 HMR 叠加实例 */
  destroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.status?.stop();
    this.ws?.disconnect();
  }

  // ─── 名册初始化 ─────────────────────────────────────────
  private _initRoster(): void {
    // Xi 占位（待后端数据填充真实状态）
    const xiPlaceholder: Agent = {
      id: 'xi', name: 'Xi', role: '智能体', level: 1,
      state: 'idle', en: 0, hearts: 1, emoji: '✦',
      currentTask: '连接中...', totalTasks: 0,
    };
    this.roster.setAgents([xiPlaceholder, ...DEMO_AGENTS]);
    this.roster.select('xi');
    this.status.setCounts(this.roster.getStatusCounts());
  }

  // ─── 后端轮询 ─────────────────────────────────────────
  private async _pollBackend(): Promise<void> {
    const [health, stats, tools, skills] = await Promise.allSettled([
      api.health(),
      api.memoryStats(),
      api.listTools(),
      api.listSkills(),
    ]);

    if (tools.status === 'fulfilled') this.tools = tools.value;
    if (skills.status === 'fulfilled') this.skills = skills.value;
    this.backendOnline = health.status === 'fulfilled' && health.value.status === 'ok';

    if (stats.status === 'fulfilled') {
      // 更新 Xi 智能体卡片
      const xiAgent = mapXiAgent(stats.value, this.tools, this.skills);
      if (this.backendOnline) {
        xiAgent.state = this.currentRunningTool ? 'running' : 'active';
      } else {
        xiAgent.state = 'error';
        xiAgent.currentTask = '后端异常';
      }
      this.roster.upsertAgent(xiAgent);
      this.status.setCounts(this.roster.getStatusCounts());

      // 如果当前选中的是 Xi，刷新详情
      if (this.currentAgentId === 'xi') {
        this._renderXiDetail(xiAgent);
      }
    } else if (!this.backendOnline) {
      // stats 和 health 都失败才标记离线
      const xi = this.roster.getSelected();
      if (xi && xi.id === 'xi') {
        this.roster.upsertAgent({ ...xi, state: 'idle', currentTask: '后端未连接' });
      }
    }
  }

  // ─── 名册事件 ─────────────────────────────────────────
  private _bindRoster(): void {
    this.roster.onSelect((agent) => {
      this.currentAgentId = agent?.id ?? null;
      if (!agent) {
        this.detail.renderAgent(null);
        this.detail.renderQuests([]);
        return;
      }

      if (agent.id === 'xi') {
        // Xi 显示真实数据
        this._renderXiDetail(agent);
      } else {
        // 演示智能体
        this.detail.renderAgent(agent);
        this.detail.renderQuests(this._genDemoQuests(agent));
      }
    });

    this.detail.onTalk((agent) => {
      this.cmd.focus();
      const input = document.getElementById('command-input');
      if (input instanceof HTMLInputElement) {
        input.value = agent.id === 'xi' ? '' : `@${agent.name} `;
      }
    });
  }

  /** 渲染 Xi 详情（含真实工具/技能） */
  private _renderXiDetail(xi: Agent): void {
    // 注入扩展数据到 detail：用 currentTask 显示工具/技能数
    const enriched: Agent = {
      ...xi,
      currentTask: this.tools.length > 0
        ? `${this.tools.length} 工具 · ${this.skills.length} 技能`
        : '待命',
    };
    this.detail.renderAgent(enriched);
    this.detail.renderQuests(this.quests);
    // 追加真实工具/技能列表
    this.detail.renderExtras(this.tools, this.skills);
  }

  // ─── 命令事件 ─────────────────────────────────────────
  private _bindCommand(): void {
    this.cmd.onCommand((text) => {
      const { type, isCommand } = detectCommandType(text);

      this.log.append({
        id: `cmd-${Date.now()}`,
        time: this._now(),
        type,
        source: '指挥官',
        text,
      });

      if (isCommand) {
        const cmd = text.slice(1).toLowerCase();
        if (cmd.startsWith('clear')) {
          this.log.clear();
          return;
        }
        this.ws.sendCommand(text);
      } else {
        this.ws.sendChat(text);
      }
    });
  }

  // ─── WS 事件 → UI ────────────────────────────────────
  private _bindWs(): void {
    // 会话恢复：后端确认了带历史的会话 → 拉取记录重建日志
    this.ws.on('session_init', async (msg) => {
      if (!msg.restored || !msg.session_id) return;
      const messages = await api.history(msg.session_id);
      if (messages.length === 0) return;
      this.log.append({
        id: `sys-${Date.now()}`,
        time: this._now(),
        type: 'system',
        text: `已恢复上次会话（${msg.turns ?? 0} 轮对话）`,
      });
      for (const m of messages) {
        if (m.role === 'user') {
          this.log.append({
            id: `hist-u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            time: this._now(),
            type: 'info',
            source: '指挥官',
            text: m.text,
          });
        } else {
          this.log.append({
            id: `hist-a-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            time: this._now(),
            type: 'chat',
            source: 'Xi',
            text: m.text,
          });
        }
      }
    });

    this.ws.on('text_delta', (msg) => {
      this.log.appendStream(msg.text ?? '', { type: 'chat', source: 'Xi' });
    });

    this.ws.on('done', () => {
      this.log.finalizeStream();
      // 完成当前运行中的工具任务
      if (this.currentRunningTool) {
        this._updateQuest(this.currentRunningTool, 'done', 100);
        this.currentRunningTool = null;
      }
    });

    this.ws.on('error', (msg) => {
      this.log.finalizeStream();
      this.log.append({
        id: `err-${Date.now()}`,
        time: this._now(),
        type: 'error',
        text: msg.message ?? '发生错误',
      });
      if (this.currentRunningTool) {
        this._updateQuest(this.currentRunningTool, 'failed', 0);
        this.currentRunningTool = null;
      }
    });

    this.ws.on('system', (msg) => {
      this.log.append({
        id: `sys-${Date.now()}`,
        time: this._now(),
        type: 'system',
        text: msg.message ?? '',
      });
    });

    this.ws.on('tool_use_start', (msg) => {
      this.log.finalizeStream();
      const toolName = msg.tool_name ?? '工具';
      this.currentRunningTool = toolName;
      this.log.append({
        id: `tool-${Date.now()}`,
        time: this._now(),
        type: 'tool',
        source: 'Xi',
        text: `[调用] ${toolName}`,
      });
      // 添加到任务公告板
      this._addQuest(toolCallToQuest(toolName, 'running', 10));
    });

    this.ws.on('tool_executing', (msg) => {
      const toolName = msg.tool_name ?? '工具';
      this.log.append({
        id: `tool-${Date.now()}`,
        time: this._now(),
        type: 'tool',
        source: 'Xi',
        text: `[执行中] ${toolName}`,
      });
      this._updateQuest(toolName, 'running', 50);
    });

    this.ws.on('tool_result', (msg) => {
      const toolName = msg.tool_name ?? '工具';
      const preview = msg.preview ? ` → ${msg.preview.slice(0, 120)}` : '';
      this.log.append({
        id: `tool-${Date.now()}`,
        time: this._now(),
        type: 'tool',
        source: 'Xi',
        text: `[完成] ${toolName}${preview}`,
      });
      this._updateQuest(toolName, 'done', 100);
      this.currentRunningTool = null;
    });

    // tool_confirm_request 由 ToolConfirmDialog 统一处理（弹窗 + sendConfirm 回复）

    this.ws.on('tool_denied', (msg) => {
      this.log.append({
        id: `denied-${Date.now()}`,
        time: this._now(),
        type: 'warn',
        text: `[已拒绝] ${msg.tool_name ?? '工具'}`,
      });
    });
  }

  // ─── 连接状态 ─────────────────────────────────────────
  private _bindConnection(): void {
    this.ws.on('connected', () => {
      this.log.append({
        id: `conn-${Date.now()}`,
        time: this._now(),
        type: 'system',
        text: '已连接到 Agent Xi 后端',
      });
      // 立即拉一次数据
      this._pollBackend();
    });

    this.ws.on('disconnected', () => {
      this.log.finalizeStream();
      this.log.append({
        id: `disc-${Date.now()}`,
        time: this._now(),
        type: 'error',
        text: '与后端连接断开，正在重连...',
      });
      // Xi 标记为 idle
      const xi = this.roster.getSelected();
      if (xi && xi.id === 'xi') {
        this.roster.upsertAgent({ ...xi, state: 'idle', currentTask: '重连中' });
      }
      this.status.setCounts(this.roster.getStatusCounts());
    });
  }

  // ─── 任务公告板操作 ───────────────────────────────────
  private _addQuest(quest: Quest): void {
    this.quests.unshift(quest);
    if (this.quests.length > 20) this.quests.pop();
    if (this.currentAgentId === 'xi') {
      this.detail.renderQuests(this.quests);
    }
  }

  private _updateQuest(toolName: string, state: Quest['state'], progress: number): void {
    const q = this.quests.find((x) => x.name === toolName && x.state === 'running');
    if (q) {
      q.state = state;
      q.progress = progress;
      if (this.currentAgentId === 'xi') {
        this.detail.renderQuests(this.quests);
      }
    }
  }

  // ─── 辅助 ─────────────────────────────────────────────
  private _now(): string {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  private _genDemoQuests(agent: Agent): Quest[] {
    return [
      { id: `${agent.id}-q1`, name: `${agent.role}日常`, stars: 3, state: 'running', assignee: agent.name, reward: '◆×5', progress: 63 },
      { id: `${agent.id}-q2`, name: '深度任务', stars: 4, state: 'pending', assignee: agent.name, reward: '◆×3', progress: 0 },
      { id: `${agent.id}-q3`, name: '归档', stars: 2, state: 'done', assignee: agent.name, reward: '◆×2', progress: 100 },
    ];
  }
}
