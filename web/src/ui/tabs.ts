/**
 * 会话标签栏 — 多会话管理
 *
 * 对标 cc-haha 的 tabbed sessions。
 * localStorage 持久化会话列表。
 */

const TAB_STORAGE_KEY = 'agent_xi_tabs';

export interface TabInfo {
  id: string;
  name: string;
  createdAt: number;
}

export type TabHandler = (tabId: string) => void;

export class TabManager {
  private listEl: HTMLElement;
  private newBtn: HTMLElement;
  private tabs: TabInfo[] = [];
  private activeId: string | null = null;
  private onSwitch: TabHandler | null = null;
  private onNew: (() => string) | null = null;
  private onClose: TabHandler | null = null;

  constructor() {
    this.listEl = document.getElementById('tab-list')!;
    this.newBtn = document.getElementById('tab-new')!;
    this._loadTabs();
    this._bind();
  }

  /** 注册回调：切换标签 */
  onTabSwitch(handler: TabHandler): void { this.onSwitch = handler; }

  /** 注册回调：新建会话（返回新 session_id） */
  onTabNew(handler: () => string): void { this.onNew = handler; }

  /** 注册回调：关闭会话 */
  onTabClose(handler: TabHandler): void { this.onClose = handler; }

  /** 当前活动会话 ID */
  get active(): string | null { return this.activeId; }

  /** 添加标签 */
  addTab(id: string, name?: string): void {
    if (this.tabs.find(t => t.id === id)) return;
    this.tabs.push({
      id,
      name: name || `会话 ${this.tabs.length + 1}`,
      createdAt: Date.now(),
    });
    this._saveTabs();
    this.render();
  }

  /** 更新标签名（用户发第一条消息时调用） */
  updateName(id: string, name: string): void {
    const tab = this.tabs.find(t => t.id === id);
    if (tab && tab.name.startsWith('会话 ')) {
      tab.name = name.slice(0, 30);
      this._saveTabs();
      this.render();
    }
  }

  /** 切换到指定标签 */
  switchTo(id: string): void {
    if (!this.tabs.find(t => t.id === id)) return;
    if (this.activeId === id) return;
    this.activeId = id;
    this.render();
    this.onSwitch?.(id);
  }

  /** 关闭标签 */
  closeTab(id: string): void {
    const idx = this.tabs.findIndex(t => t.id === id);
    if (idx < 0) return;
    // 不能关闭最后一个标签
    if (this.tabs.length === 1) return;
    this.tabs.splice(idx, 1);
    if (this.activeId === id) {
      this.activeId = this.tabs[Math.min(idx, this.tabs.length - 1)].id;
      this.onSwitch?.(this.activeId);
    }
    this._saveTabs();
    this.render();
    this.onClose?.(id);
  }

  /** 渲染标签栏 */
  render(): void {
    this.listEl.innerHTML = this.tabs.map(t => {
      const isActive = t.id === this.activeId;
      const cls = isActive ? 'tab-item active' : 'tab-item';
      return `<div class="${cls}" data-id="${t.id}">
        <span class="tab-name" title="${this._esc(t.name)}">${this._esc(t.name)}</span>
        <span class="tab-close" data-close="${t.id}">×</span>
      </div>`;
    }).join('');

    // 绑定事件
    this.listEl.querySelectorAll('.tab-item').forEach(el => {
      const clickEl = el as HTMLElement;
      clickEl.addEventListener('click', (e) => {
        const target = e.target as HTMLElement;
        if (target.classList.contains('tab-close')) {
          e.stopPropagation();
          this.closeTab(target.dataset.close!);
          return;
        }
        this.switchTo(clickEl.dataset.id!);
      });
    });
  }

  private _bind(): void {
    this.newBtn.addEventListener('click', () => {
      if (this.onNew) {
        const id = this.onNew();
        this.addTab(id);
        this.switchTo(id);
      }
    });
  }

  private _loadTabs(): void {
    try {
      const data = localStorage.getItem(TAB_STORAGE_KEY);
      if (data) this.tabs = JSON.parse(data);
    } catch { /* ignore */ }
  }

  private _saveTabs(): void {
    try {
      localStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(this.tabs.slice(-10)));
    } catch { /* ignore */ }
  }

  private _esc(s: string): string {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
}
