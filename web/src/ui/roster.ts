/**
 * 冒险者名册（左栏）
 * 显示所有智能体卡片，支持选中
 */
import type { Agent, AgentState, StatusCounts } from '../types';

type SelectListener = (agent: Agent | null) => void;

export class RosterPanel {
  private listEl: HTMLElement;
  private agents: Agent[] = [];
  private selectedId: string | null = null;
  private listeners: Set<SelectListener> = new Set();

  constructor() {
    this.listEl = document.getElementById('roster-list')!;
  }

  /** 设置智能体列表 */
  setAgents(agents: Agent[]): void {
    this.agents = agents;
    if (this.selectedId && !agents.find((a) => a.id === this.selectedId)) {
      this.selectedId = agents[0]?.id ?? null;
    }
    if (!this.selectedId && agents.length > 0) {
      this.selectedId = agents[0].id;
    }
    this._render();
    this._emitSelected();
  }

  /** 追加/更新单个智能体 */
  upsertAgent(agent: Agent): void {
    const idx = this.agents.findIndex((a) => a.id === agent.id);
    if (idx >= 0) this.agents[idx] = agent;
    else this.agents.push(agent);
    this._render();
    this._emitSelected();
  }

  /** 选中某智能体 */
  select(id: string): void {
    if (id === this.selectedId) return;
    this.selectedId = id;
    this._render();
    this._emitSelected();
  }

  /** 获取当前选中 */
  getSelected(): Agent | null {
    return this.agents.find((a) => a.id === this.selectedId) ?? null;
  }

  /** 获取状态计数 */
  getStatusCounts(): StatusCounts {
    return {
      online: this.agents.filter((a) => a.state === 'active' || a.state === 'running').length,
      idle: this.agents.filter((a) => a.state === 'idle').length,
      error: this.agents.filter((a) => a.state === 'error').length,
    };
  }

  onSelect(listener: SelectListener): () => void {
    this.listeners.add(listener);
    listener(this.getSelected());
    return () => this.listeners.delete(listener);
  }

  // ─── 渲染 ─────────────────────────────────────────────
  private _render(): void {
    this.listEl.innerHTML = '';
    this.agents.forEach((agent) => {
      const card = document.createElement('div');
      card.className = `agent-card${agent.id === this.selectedId ? ' selected' : ''}`;
      card.dataset.id = agent.id;

      // 心形：只渲染实际 hearts 数（避免卡片溢出）
      const hearts = '♥'.repeat(agent.hearts);

      card.innerHTML = `
        <div class="agent-avatar">${agent.avatar ? `<img src="${agent.avatar}" alt="${agent.name}">` : (agent.emoji ?? agent.name.charAt(0))}</div>
        <div class="agent-head">
          <span class="agent-name">${agent.name}</span>
          <span class="agent-state state-${agent.state}">${this._stateText(agent.state)}</span>
        </div>
        <div class="agent-role">${agent.role} · Lv.${agent.level}</div>
        <div class="agent-stats">
          <span class="agent-en-label">EN</span>
          <span class="agent-en-value">${agent.en}</span>
          <span class="agent-hearts" title="友好度 ${agent.hearts}/10">${hearts}</span>
        </div>
      `;

      card.addEventListener('click', () => this.select(agent.id));
      this.listEl.appendChild(card);
    });

    if (this.agents.length === 0) {
      this.listEl.innerHTML = '<div class="detail-empty">暂无智能体<br>请连接后端</div>';
    }
  }

  private _stateText(s: AgentState): string {
    return { active: '活跃', running: '执行中', idle: '待机', error: '故障' }[s];
  }

  private _emitSelected(): void {
    const sel = this.getSelected();
    this.listeners.forEach((fn) => fn(sel));
  }
}
