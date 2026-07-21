/**
 * 附件管理器 — P4 多模态上传
 *
 * 职责：
 * - 附件按钮（回形针）→ 原生多选文件
 * - 日志区域拖拽上传（dragover 金色高亮）
 * - 待发送附件预览条（图片 48px 缩略图 / 文件芯片 + × 移除）
 * - 发送时 uploadAll() → POST /api/upload → AttachmentMeta[]
 */
import { api } from '../net/api';
import type { AttachmentMeta } from '../types';

// 单文件上限（与后端 uploads.MAX_UPLOAD_SIZE 对齐）
const MAX_SIZE = 20 * 1024 * 1024;

interface PendingFile {
  localId: string;
  file: File;
  url: string | null;   // 图片缩略图 object URL
}

type AttachEventHandler = (text: string, kind: 'info' | 'error') => void;

export class AttachmentManager {
  private pending: PendingFile[] = [];
  private previewEl: HTMLElement;
  private dropZone: HTMLElement;
  private inputEl: HTMLInputElement;
  private handler: AttachEventHandler | null = null;
  private uploading = false;

  constructor() {
    const previewEl = document.getElementById('attach-preview');
    const dropZone = document.getElementById('log-panel');
    if (!previewEl || !dropZone) {
      throw new Error('[AttachmentManager] 缺少 #attach-preview 或 #log-panel 元素');
    }
    this.previewEl = previewEl;
    this.dropZone = dropZone;

    // 隐藏的原生文件选择框
    this.inputEl = document.createElement('input');
    this.inputEl.type = 'file';
    this.inputEl.multiple = true;
    this.inputEl.hidden = true;
    document.body.appendChild(this.inputEl);

    this._bindButton();
    this._bindInput();
    this._bindDragDrop();
  }

  setEventHandler(h: AttachEventHandler): void {
    this.handler = h;
  }

  get pendingCount(): number {
    return this.pending.length;
  }

  /** 添加文件（选择或拖入），超限/空文件剔除并提示 */
  addFiles(files: FileList | File[]): void {
    for (const file of Array.from(files)) {
      if (file.size > MAX_SIZE) {
        this._emit(`「${file.name}」超过 20MB 限制，已跳过`, 'error');
        continue;
      }
      if (file.size === 0) {
        this._emit(`「${file.name}」是空文件，已跳过`, 'error');
        continue;
      }
      const url = file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
      this.pending.push({
        localId: `f-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        file,
        url,
      });
    }
    this._render();
  }

  /** 上传全部待发附件；任一失败则中止并保留 pending（错误已推送日志） */
  async uploadAll(sessionId: string): Promise<AttachmentMeta[] | null> {
    if (this.uploading || this.pending.length === 0) return null;
    this.uploading = true;
    this.previewEl.classList.add('uploading');
    try {
      const metas: AttachmentMeta[] = [];
      for (const p of this.pending) {
        const res = await api.upload(p.file, sessionId);
        if (!res.ok || !res.file_id) {
          this._emit(`「${p.file.name}」上传失败：${res.error ?? '未知错误'}`, 'error');
          return null;
        }
        metas.push({
          file_id: res.file_id,
          name: res.name ?? p.file.name,
          size: res.size ?? p.file.size,
          mime: res.mime ?? p.file.type ?? 'application/octet-stream',
          url: p.url ?? undefined,
        });
      }
      this.clear();
      return metas;
    } finally {
      this.uploading = false;
      this.previewEl.classList.remove('uploading');
    }
  }

  /** 清空待发附件（释放 object URL） */
  clear(): void {
    for (const p of this.pending) {
      if (p.url) URL.revokeObjectURL(p.url);
    }
    this.pending = [];
    this._render();
  }

  // ─── 内部 ─────────────────────────────────────────────

  private _bindButton(): void {
    const btn = document.getElementById('attach-btn');
    btn?.addEventListener('click', () => this.inputEl.click());
  }

  private _bindInput(): void {
    this.inputEl.addEventListener('change', () => {
      if (this.inputEl.files?.length) this.addFiles(this.inputEl.files);
      this.inputEl.value = '';   // 允许再次选择同名文件
    });
  }

  private _bindDragDrop(): void {
    let depth = 0;

    this.dropZone.addEventListener('dragenter', (e) => {
      if (!this._hasFiles(e)) return;
      e.preventDefault();
      depth++;
      this.dropZone.classList.add('drag-over');
    });

    this.dropZone.addEventListener('dragover', (e) => {
      if (!this._hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    });

    this.dropZone.addEventListener('dragleave', (e) => {
      if (!this._hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) this.dropZone.classList.remove('drag-over');
    });

    this.dropZone.addEventListener('drop', (e) => {
      if (!this._hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      this.dropZone.classList.remove('drag-over');
      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        this.addFiles(files);
        this._emit(`已添加 ${files.length} 个附件`, 'info');
      }
    });
  }

  private _hasFiles(e: DragEvent): boolean {
    return !!e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files');
  }

  private _remove(localId: string): void {
    const idx = this.pending.findIndex((p) => p.localId === localId);
    if (idx < 0) return;
    const [p] = this.pending.splice(idx, 1);
    if (p.url) URL.revokeObjectURL(p.url);
    this._render();
  }

  private _render(): void {
    if (this.pending.length === 0) {
      this.previewEl.hidden = true;
      this.previewEl.innerHTML = '';
      return;
    }
    this.previewEl.hidden = false;
    this.previewEl.innerHTML = this.pending
      .map((p) => {
        const name = this._escape(p.file.name);
        if (p.file.type.startsWith('image/') && p.url) {
          return `<div class="attach-item" data-id="${p.localId}">
            <img class="attach-thumb" src="${p.url}" alt="${name}" title="${name}" />
            <button class="attach-remove" data-id="${p.localId}" title="移除">×</button>
          </div>`;
        }
        return `<div class="attach-item attach-file" data-id="${p.localId}">
          <span class="attach-icon">${this._typeIcon(p.file.name)}</span>
          <span class="attach-name" title="${name}">${name}</span>
          <span class="attach-size">${this._fmtSize(p.file.size)}</span>
          <button class="attach-remove" data-id="${p.localId}" title="移除">×</button>
        </div>`;
      })
      .join('');

    this.previewEl
      .querySelectorAll<HTMLButtonElement>('.attach-remove')
      .forEach((btn) => {
        btn.addEventListener('click', () => this._remove(btn.dataset.id ?? ''));
      });
  }

  /** 按扩展名选像素风类型符号 */
  private _typeIcon(name: string): string {
    const ext = name.split('.').pop()?.toLowerCase() ?? '';
    if (ext === 'pdf') return '▤';
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '▦';
    if (['mp3', 'wav', 'flac', 'ogg'].includes(ext)) return '♫';
    if (['mp4', 'mkv', 'avi', 'mov', 'webm'].includes(ext)) return '▶';
    if (['js', 'ts', 'py', 'json', 'html', 'css', 'md', 'yaml', 'yml', 'toml', 'txt', 'log'].includes(ext)) return '≡';
    return '◈';
  }

  private _fmtSize(bytes: number): string {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  }

  private _escape(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  private _emit(text: string, kind: 'info' | 'error'): void {
    this.handler?.(text, kind);
  }
}
