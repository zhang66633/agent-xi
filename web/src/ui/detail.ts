/**
 * 冒险者详情 + 任务公告板（右栏）
 * 选中智能体后展示详情；下方展示任务列表
 * Xi 智能体额外显示：可用工具 + 已装技能
 */
import type { Agent, Quest, QuestState } from '../types';
import type { ToolInfo, SkillInfo } from '../net/api';

const QUEST_STATE_LABEL: Record<QuestState, string> = {
  running: '进行中',
  pending: '等待中',
  done: '已完成',
  failed: '失败',
};

const SECURITY_LABEL: Record<string, string> = {
  safe: '安全',
  sensitive: '敏感',
  caution: '谨慎',
  dangerous: '危险',
};

const SECURITY_CLASS: Record<string, string> = {
  safe: 'sec-safe',
  sensitive: 'sec-caution',
  caution: 'sec-caution',
  dangerous: 'sec-danger',
};

export class DetailPanel {
  private contentEl: HTMLElement;
  private questListEl: HTMLElement;
  private extrasEl: HTMLElement | null = null;
  private talkBtnHandler: ((agent: Agent) => void) | null = null;

  constructor() {
    this.contentEl = document.getElementById('detail-content')!;
    this.questListEl = document.getElementById('quest-list')!;
    this._renderEmpty();
  }

  /** 渲染选中智能体详情 */
  renderAgent(agent: Agent | null): void {
    if (!agent) {
      this._renderEmpty();
      return;
    }

    const hearts = '♥'.repeat(agent.hearts);

    this.contentEl.innerHTML = `
      <div class="detail-name">${agent.name}</div>
      <div class="detail-role">${agent.role} · Lv.${agent.level}</div>
      <div class="detail-state-row">
        <span class="agent-state state-${agent.state}">${this._stateText(agent.state)}</span>
      </div>
      <div class="detail-stat">
        <span class="stat-label">友好度</span>
        <span class="stat-value hearts">${hearts} <small>${agent.hearts}/10</small></span>
      </div>
      <div class="detail-stat">
        <span class="stat-label">EN</span>
        <span class="stat-value en">${agent.en}</span>
      </div>
      <div class="detail-stat">
        <span class="stat-label">当前任务</span>
        <span class="stat-value">${agent.currentTask ?? '—'}</span>
      </div>
      <div class="detail-stat">
        <span class="stat-label">累计任务</span>
        <span class="stat-value">${agent.totalTasks ?? 0} 次</span>
      </div>
      <button class="btn-talk" id="btn-talk">对话调度</button>
    `;

    const talkBtn = document.getElementById('btn-talk');
    if (talkBtn) {
      talkBtn.addEventListener('click', () => this.talkBtnHandler?.(agent));
    }

    // 清空扩展区
    this._clearExtras();
  }

  /** 设置对话按钮回调 */
  onTalk(handler: (agent: Agent) => void): void {
    this.talkBtnHandler = handler;
  }

  /** 渲染任务列表 */
  renderQuests(quests: Quest[]): void {
    if (quests.length === 0) {
      this.questListEl.innerHTML = '<div class="detail-empty">暂无任务</div>';
      return;
    }

    this.questListEl.innerHTML = '';
    quests.forEach((q) => {
      const card = document.createElement('div');
      card.className = `quest-card q-${q.state}`;
      const stars = '★'.repeat(q.stars) + '☆'.repeat(Math.max(0, 5 - q.stars));

      card.innerHTML = `
        <div class="quest-head">
          <span class="quest-stars">${stars}</span>
          <span class="quest-name">${q.name}</span>
          <span class="quest-state q-${q.state}">${QUEST_STATE_LABEL[q.state]}</span>
        </div>
        <div class="quest-meta">
          <span>负责人: ${q.assignee} ${q.reward}</span>
          <span>${q.progress}%</span>
        </div>
        <div class="quest-progress">
          <div class="quest-progress-fill" style="width:${q.progress}%"></div>
        </div>
      `;
      this.questListEl.appendChild(card);
    });
  }

  /** 渲染扩展信息（工具 + 技能，仅 Xi 用） */
  renderExtras(tools: ToolInfo[], skills: SkillInfo[]): void {
    this._clearExtras();
    this.extrasEl = document.createElement('div');
    this.extrasEl.className = 'extras-block';

    let html = '';

    // 工具
    if (tools.length > 0) {
      html += '<div class="extras-title">◆ 可用工具</div>';
      html += '<div class="extras-list">';
      tools.forEach((t) => {
        const secClass = SECURITY_CLASS[t.security_level] ?? 'sec-safe';
        const secLabel = SECURITY_LABEL[t.security_level] ?? t.security_level;
        html += `
          <div class="extras-item">
            <span class="extras-name">${t.name}</span>
            <span class="sec-badge ${secClass}">${secLabel}</span>
          </div>
        `;
      });
      html += '</div>';
    }

    // 技能
    if (skills.length > 0) {
      html += '<div class="extras-title">◆ 已装技能</div>';
      html += '<div class="extras-list">';
      skills.forEach((s) => {
        html += `
          <div class="extras-item">
            <span class="extras-name">${s.name}</span>
            <span class="extras-count">×${s.use_count}</span>
          </div>
        `;
      });
      html += '</div>';
    }

    this.extrasEl.innerHTML = html;
    this.contentEl.appendChild(this.extrasEl);
  }

  // ─── 内部 ─────────────────────────────────────────────
  private _clearExtras(): void {
    if (this.extrasEl) {
      this.extrasEl.remove();
      this.extrasEl = null;
    }
  }

  private _renderEmpty(): void {
    this.contentEl.innerHTML = `
      <div class="detail-empty">
        ◇ 未选中智能体<br><br>
        请从左侧名册中选择
      </div>
    `;
  }

  private _stateText(s: Agent['state']): string {
    return { active: '活跃', running: '执行中', idle: '待机', error: '故障' }[s];
  }
}
