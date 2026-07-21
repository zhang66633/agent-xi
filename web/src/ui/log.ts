/**
 * 系统日志（中栏主区域）
 * 渲染时间戳 + 类型徽章 + 内容
 */
import type { LogEntry, LogType } from '../types';

const TYPE_LABEL: Record<LogType, string> = {
  system: '系统',
  info: '信息',
  warn: '警告',
  error: '错误',
  tool: '工具',
  chat: '对话',
};

const MAX_LOGS = 500;

export class LogPanel {
  private listEl: HTMLElement;
  private logs: LogEntry[] = [];
  private currentStreamEl: HTMLElement | null = null;
  private streamBuffer = '';
  private autoScroll = true;

  constructor() {
    this.listEl = document.getElementById('log-list')!;
    this._bindScroll();
  }

  /** 追加一条日志 */
  append(entry: LogEntry): void {
    this.logs.push(entry);
    if (this.logs.length > MAX_LOGS) this.logs.shift();
    this._renderEntry(entry);
    this._maybeScroll();
  }

  /** 追加文本到当前流式日志（若无则创建一条 chat 类型） */
  appendStream(text: string, opts: { type?: LogType; source?: string; time?: string } = {}): void {
    if (!this.currentStreamEl) {
      const entry: LogEntry = {
        id: `stream-${Date.now()}`,
        time: opts.time ?? this._now(),
        type: opts.type ?? 'chat',
        source: opts.source,
        text: '',
      };
      this.logs.push(entry);
      this.currentStreamEl = this._renderEntry(entry);
      this.currentStreamEl.querySelector('.log-text')?.classList.add('typing');
      this.streamBuffer = '';
    }
    this.streamBuffer += text;
    const textEl = this.currentStreamEl.querySelector('.log-text');
    if (textEl) textEl.textContent = this.streamBuffer;
    this._maybeScroll();
  }

  /** 结束当前流式 */
  finalizeStream(): void {
    if (this.currentStreamEl) {
      this.currentStreamEl.querySelector('.log-text')?.classList.remove('typing');
      this.currentStreamEl = null;
      this.streamBuffer = '';
    }
  }

  /** 清空日志 */
  clear(): void {
    this.logs = [];
    this.listEl.innerHTML = '';
    this.currentStreamEl = null;
    this.streamBuffer = '';
  }

  // ─── 内部 ─────────────────────────────────────────────
  private _bindScroll(): void {
    this.listEl.addEventListener('scroll', () => {
      const atBottom = this.listEl.scrollTop + this.listEl.clientHeight >= this.listEl.scrollHeight - 20;
      this.autoScroll = atBottom;
    });
  }

  private _renderEntry(entry: LogEntry): HTMLElement {
    const row = document.createElement('div');
    row.className = `log-row log-${entry.type}`;
    row.dataset.id = entry.id;

    const sourcePrefix = entry.source ? `${entry.source} ` : '';
    row.innerHTML = `
      <span class="log-time">${entry.time}</span>
      <span class="log-type log-type-${entry.type}">${TYPE_LABEL[entry.type]}</span>
      <span class="log-text">${this._escape(sourcePrefix + entry.text)}</span>
    `;

    this.listEl.appendChild(row);
    return row;
  }

  private _maybeScroll(): void {
    if (this.autoScroll) {
      requestAnimationFrame(() => {
        this.listEl.scrollTop = this.listEl.scrollHeight;
      });
    }
  }

  private _now(): string {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  private _escape(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}
