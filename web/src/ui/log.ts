/**
 * 系统日志（中栏主区域）
 * 渲染时间戳 + 类型徽章 + 内容 + 附件芯片/缩略图
 */
import type { AttachmentMeta, LogEntry, LogType } from '../types';
import { Modal } from './modal';

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
  private previewModal: Modal | null = null;

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

    if (entry.attachments && entry.attachments.length > 0) {
      row.appendChild(this._renderAttachments(entry.attachments));
    }

    this.listEl.appendChild(row);
    return row;
  }

  /** 附件区：图片缩略图（点击放大）/ 文件芯片 */
  private _renderAttachments(attachments: AttachmentMeta[]): HTMLElement {
    const wrap = document.createElement('div');
    wrap.className = 'log-attach';
    for (const att of attachments) {
      if (att.mime.startsWith('image/') && att.url) {
        const img = document.createElement('img');
        img.className = 'log-attach-thumb';
        img.src = att.url;
        img.alt = att.name;
        img.title = `${att.name}（点击放大）`;
        img.addEventListener('click', () => this._previewImage(att));
        wrap.appendChild(img);
      } else {
        const chip = document.createElement('span');
        chip.className = 'log-attach-chip';
        chip.title = att.name;
        chip.textContent = `◈ ${att.name} · ${this._fmtSize(att.size)}`;
        wrap.appendChild(chip);
      }
    }
    return wrap;
  }

  /** 图片放大预览（懒加载 Modal 实例） */
  private _previewImage(att: AttachmentMeta): void {
    if (!this.previewModal) this.previewModal = new Modal();
    // url 是本地创建的 blob: URL，非用户内容，可安全入 innerHTML；name 转义
    this.previewModal.show(
      att.name,
      `<img class="attach-preview-img" src="${att.url}" alt="${this._escape(att.name)}" />`,
    );
  }

  private _fmtSize(bytes: number): string {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
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
