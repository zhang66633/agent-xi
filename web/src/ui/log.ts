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
  private _renderTimer: number = 0;
  private searchBar: HTMLElement | null = null;
  private searchIdx = -1;
  private searchHits: HTMLElement[] = [];

  constructor() {
    this.listEl = document.getElementById('log-list')!;
    this._bindScroll();
    this._bindContextMenu();
  }

  /** 右键复制文本 */
  private _bindContextMenu(): void {
    this.listEl.addEventListener('contextmenu', (e) => {
      const row = (e.target as HTMLElement).closest('.log-row') as HTMLElement | null;
      if (!row) return;
      e.preventDefault();
      const textEl = row.querySelector('.log-text');
      const text = textEl?.textContent ?? '';
      if (text) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
    });
  }

  /** 追加一条日志 */
  append(entry: LogEntry): void {
    this.logs.push(entry);
    if (this.logs.length > MAX_LOGS) this.logs.shift();
    this._renderEntry(entry);
    this._maybeScroll();
  }

  /** 追加文本到当前流式日志（实时 Markdown 渲染） */
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
      this._renderTimer = 0;
    }
    this.streamBuffer += text;
    const textEl = this.currentStreamEl.querySelector('.log-text');
    if (textEl) {
      // 节流：每 80ms 渲染一次 Markdown
      if (!this._renderTimer) {
        this._renderTimer = window.setTimeout(() => {
          this._renderTimer = 0;
          textEl.innerHTML = this._renderRichText(this.streamBuffer);
          this._maybeScroll();
        }, 80);
      }
    }
    this._maybeScroll();
  }

  /** 结束当前流式 */
  finalizeStream(): void {
    if (this.currentStreamEl) {
      if (this._renderTimer) {
        clearTimeout(this._renderTimer);
        this._renderTimer = 0;
      }
      const textEl = this.currentStreamEl.querySelector('.log-text');
      if (textEl) {
        textEl.classList.remove('typing');
        textEl.innerHTML = this._renderRichText(this.streamBuffer);
      }
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
    this._removeSearchBar();
  }

  /** 切换搜索栏 */
  toggleSearch(): void {
    if (this.searchBar) { this._removeSearchBar(); return; }
    this._showSearchBar();
  }

  private _showSearchBar(): void {
    this.searchBar = document.createElement('div');
    this.searchBar.className = 'log-search-bar';
    this.searchBar.innerHTML = `
      <input class="log-search-input" placeholder="搜索日志..." autocomplete="off" />
      <span class="log-search-count"></span>
      <button class="log-search-btn" title="上一个">▲</button>
      <button class="log-search-btn" title="下一个">▼</button>
      <button class="log-search-btn" title="关闭">×</button>
    `;
    const panel = this.listEl.parentElement!;
    panel.insertBefore(this.searchBar, this.listEl);

    const input = this.searchBar.querySelector('.log-search-input') as HTMLInputElement;
    const count = this.searchBar.querySelector('.log-search-count') as HTMLElement;
    const btnPrev = this.searchBar.querySelectorAll('.log-search-btn')[0] as HTMLElement;
    const btnNext = this.searchBar.querySelectorAll('.log-search-btn')[1] as HTMLElement;
    const btnClose = this.searchBar.querySelectorAll('.log-search-btn')[2] as HTMLElement;

    const doSearch = () => {
      const q = input.value.toLowerCase();
      // 清除旧高亮
      this.listEl.querySelectorAll('.log-search-hit').forEach(el => el.classList.remove('log-search-hit'));
      this.searchHits = [];
      this.searchIdx = -1;
      if (!q) { count.textContent = ''; return; }
      this.listEl.querySelectorAll('.log-text,.log-diff-line').forEach(el => {
        const text = el.textContent?.toLowerCase() || '';
        if (text.includes(q)) {
          this.searchHits.push(el as HTMLElement);
          el.classList.add('log-search-hit');
        }
      });
      count.textContent = this.searchHits.length ? `1/${this.searchHits.length}` : '无';
      if (this.searchHits.length > 0) this._navSearch(1);
    };

    const nav = (dir: 1 | -1) => {
      if (!this.searchHits.length) return;
      this._navSearch(dir);
      count.textContent = `${this.searchIdx + 1}/${this.searchHits.length}`;
    };

    input.addEventListener('input', doSearch);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') nav(1); if (e.key === 'Escape') this._removeSearchBar(); });
    btnPrev.addEventListener('click', () => nav(-1));
    btnNext.addEventListener('click', () => nav(1));
    btnClose.addEventListener('click', () => this._removeSearchBar());
    input.focus();
  }

  private _navSearch(dir: 1 | -1): void {
    if (!this.searchHits.length) return;
    this.searchHits.forEach(el => el.classList.remove('log-search-active'));
    this.searchIdx = (this.searchIdx + dir + this.searchHits.length) % this.searchHits.length;
    this.searchHits[this.searchIdx].classList.add('log-search-active');
    this.searchHits[this.searchIdx].scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  private _removeSearchBar(): void {
    this.listEl.querySelectorAll('.log-search-hit,.log-search-active').forEach(el => {
      el.classList.remove('log-search-hit', 'log-search-active');
    });
    if (this.searchBar) { this.searchBar.remove(); this.searchBar = null; }
    this.searchHits = [];
    this.searchIdx = -1;
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

    const sourceHtml = entry.source
      ? `<span class="log-source">${this._escape(entry.source)}</span>`
      : '';
    row.innerHTML = `
      <span class="log-time">${entry.time}</span>
      <span class="log-type log-type-${entry.type}">${TYPE_LABEL[entry.type]}</span>
      ${sourceHtml}
      <span class="log-text">${this._renderRichText(entry.text)}</span>
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

  /** 渲染富文本：代码块语法高亮 + diff 渲染 + Markdown */
  private _renderRichText(text: string): string {
    // 1. 先检测 diff 输出
    if (this._isDiffContent(text)) {
      return this._renderDiff(text);
    }

    // 2. 代码块语法高亮
    const re = /```([^\n`]*)\n([\s\S]*?)```/g;
    const out: string[] = [];
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) out.push(this._renderMarkdown(text.slice(last, m.index)));
      const lang = m[1].trim();
      const code = m[2].replace(/\n+$/, '');
      const label = lang ? `<span class="log-code-lang">${this._escape(lang)}</span>` : '';
      // 语法高亮
      let highlighted = this._escape(code);
      try {
        if (typeof (window as any).hljs !== 'undefined') {
          const hljs = (window as any).hljs;
          if (lang && hljs.getLanguage(lang)) {
            highlighted = hljs.highlight(code, { language: lang }).value;
          } else {
            highlighted = hljs.highlightAuto(code).value;
          }
        }
      } catch { /* highlight.js 不可用时保持纯文本 */ }
      out.push(
        `<span class="log-code-wrap">${label}<code class="log-code">${highlighted}</code></span>`,
      );
      last = re.lastIndex;
    }
    if (last < text.length) out.push(this._renderMarkdown(text.slice(last)));
    return out.join('');
  }

  /** 检测是否是 diff 内容 */
  private _isDiffContent(text: string): boolean {
    const lines = text.split('\n');
    let diffCount = 0;
    for (const line of lines.slice(0, 30)) {
      if (/^diff --git|^---\s|^\+\+\+\s|^@@\s/.test(line)) diffCount++;
    }
    return diffCount >= 3;
  }

  /** 渲染 diff 输出（+/- 行样式） */
  private _renderDiff(text: string): string {
    const lines = text.split('\n');
    const blocks: string[] = ['<span class="log-diff-wrap">'];
    for (const line of lines) {
      const escaped = this._escape(line);
      if (line.startsWith('diff --git') || line.startsWith('--- ') || line.startsWith('+++ ')) {
        blocks.push(`<span class="log-diff-line log-diff-hdr">${escaped}</span>`);
      } else if (line.startsWith('@@')) {
        blocks.push(`<span class="log-diff-line log-diff-meta">${escaped}</span>`);
      } else if (line.startsWith('+') && !line.startsWith('+++')) {
        blocks.push(`<span class="log-diff-line log-diff-add">${escaped}</span>`);
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        blocks.push(`<span class="log-diff-line log-diff-del">${escaped}</span>`);
      } else {
        blocks.push(`<span class="log-diff-line">${escaped}</span>`);
      }
    }
    blocks.push('</span>');
    return blocks.join('');
  }

  /** 轻量 Markdown 渲染：标题/列表/引用/分隔线（块级）+ 粗斜体/行内代码/链接（行内） */
  private _renderMarkdown(raw: string): string {
    const lines = raw.split('\n');
    const blocks: string[] = [];
    let para: string[] = [];
    let i = 0;

    const flushPara = () => {
      if (para.length) {
        blocks.push(
          `<span class="md-p">${para.map((l) => this._inline(this._escape(l))).join('<br>')}</span>`,
        );
        para = [];
      }
    };

    while (i < lines.length) {
      const t = lines[i].trim();

      if (t === '') { flushPara(); i++; continue; }

      // 标题 #~####
      const h = /^(#{1,4})\s+(.*)$/.exec(t);
      if (h) {
        flushPara();
        blocks.push(
          `<span class="md-h md-h${h[1].length}">${this._inline(this._escape(h[2]))}</span>`,
        );
        i++; continue;
      }

      // 分隔线
      if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(t)) {
        flushPara();
        blocks.push('<span class="md-hr"></span>');
        i++; continue;
      }

      // 引用 >
      if (t.startsWith('> ')) {
        flushPara();
        const quote: string[] = [];
        while (i < lines.length && lines[i].trim().startsWith('> ')) {
          quote.push(lines[i].trim().slice(2));
          i++;
        }
        blocks.push(
          `<span class="md-quote">${quote.map((l) => this._inline(this._escape(l))).join('<br>')}</span>`,
        );
        continue;
      }

      // 无序列表 - / *
      if (/^[-*]\s+/.test(t)) {
        flushPara();
        const items: string[] = [];
        while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^[-*]\s+/, ''));
          i++;
        }
        blocks.push(
          `<span class="md-ul">${items
            .map((it) => `<span class="md-li">${this._inline(this._escape(it))}</span>`)
            .join('')}</span>`,
        );
        continue;
      }

      // 表格：当前行含 |，下一行是分隔行（|---|---|）
      if (t.includes('|') && i + 1 < lines.length && this._isTableSep(lines[i + 1].trim())) {
        flushPara();
        const header = this._splitTableRow(t);
        i += 2; // 跳过表头 + 分隔行
        const rows: string[][] = [];
        while (i < lines.length && lines[i].trim().includes('|')) {
          rows.push(this._splitTableRow(lines[i].trim()));
          i++;
        }
        blocks.push(this._renderTable(header, rows));
        continue;
      }

      // 有序列表 1. / 1)
      if (/^\d+[.)]\s+/.test(t)) {
        flushPara();
        const items: string[] = [];
        while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^\d+[.)]\s+/, ''));
          i++;
        }
        blocks.push(
          `<span class="md-ol">${items
            .map(
              (it, idx) =>
                `<span class="md-li"><span class="md-ol-num">${idx + 1}.</span>${this._inline(
                  this._escape(it),
                )}</span>`,
            )
            .join('')}</span>`,
        );
        continue;
      }

      // 普通段落行
      para.push(lines[i]);
      i++;
    }
    flushPara();
    return blocks.join('');
  }

  /** 判断是否为表格分隔行（|---|:---:| 形式） */
  private _isTableSep(s: string): boolean {
    return s.includes('|') && s.includes('-') && /^[\s|:\-]+$/.test(s);
  }

  /** 拆分表格行：去掉首尾 | 后按 | 切分 */
  private _splitTableRow(line: string): string[] {
    let s = line.trim();
    if (s.startsWith('|')) s = s.slice(1);
    if (s.endsWith('|')) s = s.slice(0, -1);
    return s.split('|').map((c) => c.trim());
  }

  /** 渲染表格为 span 结构（display:table 布局） */
  private _renderTable(header: string[], rows: string[][]): string {
    const headRow = `<span class="md-tr md-tr-head">${header
      .map((c) => `<span class="md-td">${this._inline(this._escape(c))}</span>`)
      .join('')}</span>`;
    const bodyRows = rows
      .map(
        (r) =>
          `<span class="md-tr">${r
            .map((c) => `<span class="md-td">${this._inline(this._escape(c))}</span>`)
            .join('')}</span>`,
      )
      .join('');
    return `<span class="md-table">${headRow}${bodyRows}</span>`;
  }

  /** 行内格式（输入已转义）：行内代码 / 粗体 / 斜体 / 链接 */
  private _inline(escaped: string): string {
    // 先把行内代码抽出来用占位符保护，避免被粗斜体规则误伤
    const codes: string[] = [];
    let s = escaped.replace(/`([^`]+)`/g, (_m, c: string) => {
      codes.push(c);
      return `\u0000${codes.length - 1}\u0000`;
    });
    // 粗体 **x** / __x__
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    // 斜体 *x*（前后不贴 *）
    s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    // 链接 [x](url)，仅允许 http/https/mailto
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, label: string, url: string) => {
      const safe = /^(?:https?:\/\/|mailto:)/i.test(url) ? url : '#';
      return `<a class="md-link" href="${safe}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    });
    // 还原行内代码
    s = s.replace(/\u0000(\d+)\u0000/g, (_m, idx: string) => `<code class="md-inline">${codes[Number(idx)]}</code>`);
    return s;
  }

  private _escape(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}
