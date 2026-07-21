/**
 * 商店视图 — MCP 服务器 + 技能包的安装/卸载
 *
 * 数据来源：GET /api/market/mcp、/api/market/skills
 * 安装：MCP 带 env 的弹 Modal 填环境变量；无 env 的直接装；技能直接装
 * 卸载：确认 Modal → POST /api/market/uninstall
 * 状态：MCP 安装后显示"已安装·待重启"（不支持热加载）；技能即时生效
 */
import { api, type MarketItem } from '../net/api';
import { Modal } from './modal';

export type MarketTab = 'mcp' | 'skill';
export type MarketEventHandler = (text: string, kind: 'system' | 'error') => void;

export class MarketView {
  private root: HTMLElement;
  private gridEl!: HTMLElement;
  private tabBtns: HTMLElement[] = [];
  private modal: Modal;
  private tab: MarketTab = 'mcp';
  private mcpItems: MarketItem[] = [];
  private skillItems: MarketItem[] = [];
  private loading = false;
  private onEvent: MarketEventHandler | null = null;

  constructor() {
    const el = document.getElementById('view-market');
    if (!el) throw new Error('缺少 #view-market 容器');
    this.root = el;
    this._buildShell();
    this.modal = new Modal();
  }

  /** 日志联动回调（安装/卸载结果推送到控制台日志） */
  setEventHandler(handler: MarketEventHandler): void {
    this.onEvent = handler;
  }

  /** 拉取最新列表并渲染（进入视图时调用） */
  async refresh(): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    try {
      const [mcp, skills] = await Promise.allSettled([
        api.marketMcp(),
        api.marketSkills(),
      ]);
      if (mcp.status === 'fulfilled') this.mcpItems = mcp.value;
      if (skills.status === 'fulfilled') this.skillItems = skills.value;
      this._render();
    } finally {
      this.loading = false;
    }
  }

  // ─── DOM 构建 ─────────────────────────────────────────

  private _buildShell(): void {
    this.root.innerHTML = `
      <div class="market-header">
        <div class="market-tabs">
          <button class="market-tab active" data-tab="mcp">MCP 服务器</button>
          <button class="market-tab" data-tab="skill">技能包</button>
        </div>
        <div class="market-hint">MCP 变更需重启后端生效 · 技能即装即用</div>
      </div>
      <div class="market-grid"></div>
    `;
    this.gridEl = this.root.querySelector('.market-grid') as HTMLElement;
    this.tabBtns = [...this.root.querySelectorAll<HTMLElement>('.market-tab')];
    this.tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab') as MarketTab;
        if (tab && tab !== this.tab) {
          this.tab = tab;
          this.tabBtns.forEach((b) =>
            b.classList.toggle('active', b.getAttribute('data-tab') === tab));
          this._render();
        }
      });
    });
  }

  // ─── 渲染 ─────────────────────────────────────────────

  private _render(): void {
    const items = this.tab === 'mcp' ? this.mcpItems : this.skillItems;
    if (items.length === 0) {
      this.gridEl.innerHTML =
        '<div class="market-empty">暂无数据（后端未连接？）</div>';
      return;
    }
    this.gridEl.innerHTML = items
      .map((item) => this._cardHtml(item))
      .join('');

    // 绑定卡片按钮
    this.gridEl.querySelectorAll<HTMLElement>('.mc-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id') ?? '';
        const action = btn.getAttribute('data-action');
        const item = items.find((x) => x.id === id);
        if (!item) return;
        if (action === 'install') this._onInstall(item);
        else if (action === 'uninstall') this._onUninstall(item);
      });
    });
  }

  private _cardHtml(item: MarketItem): string {
    const type = this.tab;
    const pendingRestart = item.installed && item.needs_restart;

    let status: string;
    let button: string;
    if (!item.installed) {
      status = '<span class="mc-status">未安装</span>';
      button = `<button class="mc-btn" data-action="install" data-id="${this._escape(item.id)}">安装</button>`;
    } else if (pendingRestart) {
      status = '<span class="mc-status mc-pending">已安装·待重启</span>';
      button = `<button class="mc-btn mc-btn-danger" data-action="uninstall" data-id="${this._escape(item.id)}">卸载</button>`;
    } else {
      status = '<span class="mc-status mc-installed">已安装</span>';
      button = `<button class="mc-btn mc-btn-danger" data-action="uninstall" data-id="${this._escape(item.id)}">卸载</button>`;
    }

    const envHint = item.env && Object.keys(item.env).length > 0
      ? `<div class="mc-env">需配置 ${Object.keys(item.env).map((k) => this._escape(k)).join(' / ')}</div>`
      : '';

    return `
      <div class="market-card${item.installed ? ' installed' : ''}" data-type="${type}">
        <div class="mc-head">
          <span class="mc-icon">${this._escape(item.icon)}</span>
          <span class="mc-name">${this._escape(item.name)}</span>
        </div>
        <div class="mc-desc">${this._escape(item.description)}</div>
        ${envHint}
        <div class="mc-foot">
          ${status}
          ${button}
        </div>
      </div>
    `;
  }

  // ─── 安装流程 ─────────────────────────────────────────

  private _onInstall(item: MarketItem): void {
    const hasEnv = this.tab === 'mcp'
      && item.env && Object.keys(item.env).length > 0;

    if (hasEnv) {
      this._showEnvModal(item);
    } else {
      void this._doInstall(item);
    }
  }

  /** 带 env 的 MCP：先弹 Modal 收集环境变量 */
  private _showEnvModal(item: MarketItem): void {
    const keys = Object.keys(item.env ?? {});
    const fields = keys.map((k) => `
      <label class="env-field">
        <span class="env-key">${this._escape(k)}</span>
        <input type="password" class="env-input" data-key="${this._escape(k)}"
               placeholder="输入 ${this._escape(k)}" autocomplete="off" />
      </label>
    `).join('');

    this.modal.show(`安装 ${item.name}`, `
      <div class="market-modal-desc">${this._escape(item.name)} 需要配置以下环境变量：</div>
      <div class="env-form">${fields}</div>
      <div class="market-modal-note">写入 config/mcp.yaml，重启后端后生效</div>
      <div class="confirm-actions">
        <button class="btn-confirm btn-cancel" id="market-cancel">取消</button>
        <button class="btn-confirm btn-allow" id="market-confirm">安装</button>
      </div>
    `);

    document.getElementById('market-cancel')?.addEventListener('click', () => {
      this.modal.close();
    });
    document.getElementById('market-confirm')?.addEventListener('click', () => {
      const env: Record<string, string> = {};
      this.modal.body.querySelectorAll<HTMLInputElement>('.env-input').forEach((input) => {
        const key = input.getAttribute('data-key');
        if (key && input.value.trim()) env[key] = input.value.trim();
      });
      this.modal.close();
      void this._doInstall(item, env);
    });
  }

  private async _doInstall(item: MarketItem, env?: Record<string, string>): Promise<void> {
    try {
      const result = await api.marketInstall(this.tab, item.id, env);
      if (result.ok) {
        this._emit(result.message ?? `${item.name} 已安装`, 'system');
      } else {
        this._emit(`安装失败：${result.error ?? '未知错误'}`, 'error');
      }
    } catch (e) {
      this._emit(`安装失败：${e instanceof Error ? e.message : String(e)}`, 'error');
    }
    await this.refresh();
  }

  // ─── 卸载流程 ─────────────────────────────────────────

  private _onUninstall(item: MarketItem): void {
    const note = this.tab === 'mcp'
      ? '将从 config/mcp.yaml 移除，重启后端后生效'
      : '将从技能库删除，立即生效';

    this.modal.show('确认卸载', `
      <div class="confirm-warning">▲ 卸载操作</div>
      <div class="confirm-tool-name">${this._escape(item.name)}</div>
      <div class="market-modal-desc">${note}</div>
      <div class="confirm-actions">
        <button class="btn-confirm btn-cancel" id="market-cancel">取消</button>
        <button class="btn-confirm btn-deny" id="market-confirm">卸载</button>
      </div>
    `);

    document.getElementById('market-cancel')?.addEventListener('click', () => {
      this.modal.close();
    });
    document.getElementById('market-confirm')?.addEventListener('click', () => {
      this.modal.close();
      void this._doUninstall(item);
    });
  }

  private async _doUninstall(item: MarketItem): Promise<void> {
    try {
      const result = await api.marketUninstall(this.tab, item.id);
      if (result.ok) {
        this._emit(result.message ?? `${item.name} 已卸载`, 'system');
      } else {
        this._emit(`卸载失败：${result.error ?? '未知错误'}`, 'error');
      }
    } catch (e) {
      this._emit(`卸载失败：${e instanceof Error ? e.message : String(e)}`, 'error');
    }
    await this.refresh();
  }

  // ─── 辅助 ─────────────────────────────────────────────

  private _emit(text: string, kind: 'system' | 'error'): void {
    this.onEvent?.(text, kind);
  }

  private _escape(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}
