/**
 * 设置视图 — API Keys / 平台连接 / 记忆统计
 *
 * Keys：masked 展示 + 保存写入 .env（提示重启生效）
 * 平台：纯状态展示占位（QQ/微信 Bot 阶段 6 再做）
 * 记忆：统计数字 + 最近 5 条语义记忆（只读）
 */
import { api, type KeyInfo } from '../net/api';
import { WS_URL } from '../config';

export type SettingsEventHandler = (text: string, kind: 'system' | 'error') => void;

export class SettingsView {
  private root: HTMLElement;
  private keysEl!: HTMLElement;
  private memoryEl!: HTMLElement;
  private onEvent: SettingsEventHandler | null = null;

  constructor() {
    const el = document.getElementById('view-settings');
    if (!el) throw new Error('缺少 #view-settings 容器');
    this.root = el;
    this._buildShell();
  }

  /** 日志联动回调（保存结果推送到控制台日志） */
  setEventHandler(handler: SettingsEventHandler): void {
    this.onEvent = handler;
  }

  /** 进入视图时拉取最新数据 */
  async refresh(): Promise<void> {
    await Promise.allSettled([this._loadKeys(), this._loadMemory()]);
  }

  // ─── DOM 构建 ─────────────────────────────────────────

  private _buildShell(): void {
    this.root.innerHTML = `
      <div class="settings-scroll">
        <section class="set-panel">
          <div class="set-panel-title">◆ API Keys</div>
          <div class="set-panel-note">保存后写入 .env，需重启后端生效</div>
          <div class="set-keys"></div>
        </section>

        <section class="set-panel">
          <div class="set-panel-title">◆ 平台连接</div>
          <div class="set-plats">
            <div class="set-plat-row">
              <span class="set-plat-dot on"></span>
              <span class="set-plat-name">Web 控制台</span>
              <span class="set-plat-detail">已连接 · ${this._escape(WS_URL)}</span>
            </div>
            <div class="set-plat-row">
              <span class="set-plat-dot on"></span>
              <span class="set-plat-name">CLI</span>
              <span class="set-plat-detail">可用 · python -m agent_xi</span>
            </div>
            <div class="set-plat-row">
              <span class="set-plat-dot off"></span>
              <span class="set-plat-name">QQ Bot</span>
              <span class="set-plat-detail">未配置 · 阶段 6</span>
            </div>
            <div class="set-plat-row">
              <span class="set-plat-dot off"></span>
              <span class="set-plat-name">微信 Bot</span>
              <span class="set-plat-detail">未配置 · 阶段 6</span>
            </div>
          </div>
        </section>

        <section class="set-panel">
          <div class="set-panel-title">◆ 记忆统计</div>
          <div class="set-memory"></div>
        </section>
      </div>
    `;
    this.keysEl = this.root.querySelector('.set-keys') as HTMLElement;
    this.memoryEl = this.root.querySelector('.set-memory') as HTMLElement;
  }

  // ─── API Keys ─────────────────────────────────────────

  private async _loadKeys(): Promise<void> {
    try {
      const keys = await api.settingsKeys();
      this._renderKeys(keys);
    } catch {
      this.keysEl.innerHTML =
        '<div class="set-empty">无法获取 Key 列表（后端未连接？）</div>';
    }
  }

  private _renderKeys(keys: KeyInfo[]): void {
    if (keys.length === 0) {
      this.keysEl.innerHTML = '<div class="set-empty">暂无可配置项</div>';
      return;
    }
    this.keysEl.innerHTML = keys.map((k) => `
      <div class="set-key-row">
        <div class="set-key-info">
          <div class="set-key-name">${this._escape(k.name)}</div>
          <div class="set-key-desc">${this._escape(k.desc)}</div>
        </div>
        <div class="set-key-state${k.configured ? '' : ' unset'}">
          ${k.configured ? this._escape(k.masked) : '未配置'}
        </div>
        <div class="set-key-form">
          <input type="password" class="set-key-input" data-var="${this._escape(k.var)}"
                 placeholder="输入新 Key…" autocomplete="off" />
          <button class="mc-btn set-save-btn" data-var="${this._escape(k.var)}">保存</button>
        </div>
      </div>
    `).join('');

    this.keysEl.querySelectorAll<HTMLElement>('.set-save-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const varName = btn.getAttribute('data-var') ?? '';
        const input = this.keysEl.querySelector<HTMLInputElement>(
          `.set-key-input[data-var="${varName}"]`);
        const value = input?.value.trim() ?? '';
        if (!value) {
          input?.focus();
          return;
        }
        void this._saveKey(varName, value, btn);
      });
    });
  }

  private async _saveKey(varName: string, key: string, btn: HTMLElement): Promise<void> {
    btn.setAttribute('disabled', 'disabled');
    btn.textContent = '…';
    try {
      const result = await api.saveKey(varName, key);
      if (result.ok) {
        this._emit(result.message ?? '已保存', 'system');
      } else {
        this._emit(`保存失败：${result.error ?? '未知错误'}`, 'error');
      }
    } catch (e) {
      this._emit(`保存失败：${e instanceof Error ? e.message : String(e)}`, 'error');
    }
    btn.removeAttribute('disabled');
    btn.textContent = '保存';
    await this._loadKeys();
  }

  // ─── 记忆统计 ─────────────────────────────────────────

  private async _loadMemory(): Promise<void> {
    try {
      const [stats, profile] = await Promise.all([
        api.memoryStats(),
        api.memoryProfile(),
      ]);

      const profileHtml = profile
        ? `<div class="set-mem-profile">${this._escape(profile)}</div>`
        : '<div class="set-empty">尚未建立用户画像（对话结束后自动更新）</div>';

      this.memoryEl.innerHTML = `
        <div class="set-mem-stats">
          <div class="set-mem-num">情景记忆 <b>${stats.episodic_count}</b> 条</div>
          <div class="set-mem-num">用户画像 <b>${stats.profile_ready ? '已建立' : '未建立'}</b></div>
        </div>
        <div class="set-mem-subtitle">Xi 对你的认知</div>
        ${profileHtml}
      `;
    } catch {
      this.memoryEl.innerHTML =
        '<div class="set-empty">无法获取记忆数据（后端未连接？）</div>';
    }
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
