/**
 * 命令输入栏（中栏底部）
 * 处理：输入发送、执行按钮、命令历史
 */
import type { LogType } from '../types';

type CommandHandler = (text: string) => void;

export class CommandInput {
  private inputEl: HTMLInputElement;
  private execBtn: HTMLButtonElement;
  private handler: CommandHandler | null = null;
  private history: string[] = [];
  private historyIdx = -1;
  private allowEmptySend: (() => boolean) | null = null;

  constructor() {
    const inputEl = document.getElementById('command-input');
    const execBtn = document.getElementById('command-exec');
    if (!(inputEl instanceof HTMLInputElement) || !(execBtn instanceof HTMLButtonElement)) {
      throw new Error('[CommandInput] 缺少 #command-input 或 #command-exec 元素');
    }
    this.inputEl = inputEl;
    this.execBtn = execBtn;
    this._bind();
  }

  onCommand(handler: CommandHandler): void {
    this.handler = handler;
  }

  /** 设置"允许空文本发送"谓词（有待发附件时返回 true） */
  setAllowEmptySend(predicate: () => boolean): void {
    this.allowEmptySend = predicate;
  }

  focus(): void {
    this.inputEl.focus();
  }

  // ─── 内部 ─────────────────────────────────────────────
  private _bind(): void {
    this.execBtn.addEventListener('click', () => this._exec());

    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        this._exec();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this._historyNav(-1);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        this._historyNav(1);
      }
    });
  }

  private _exec(): void {
    const text = this.inputEl.value.trim();
    const canEmpty = this.allowEmptySend?.() ?? false;
    if (!text && !canEmpty) return;
    if (text) {
      this.history.push(text);
      this.historyIdx = this.history.length;
    }
    this.inputEl.value = '';
    this.handler?.(text);
  }

  private _historyNav(dir: -1 | 1): void {
    if (this.history.length === 0) return;
    this.historyIdx = Math.max(0, Math.min(this.history.length, this.historyIdx + dir));
    const item = this.historyIdx < this.history.length ? this.history[this.historyIdx] : '';
    this.inputEl.value = item;
  }
}

/** 推断命令类型（基于前缀） */
export function detectCommandType(text: string): { type: LogType; isCommand: boolean } {
  if (!text.startsWith('/')) return { type: 'chat', isCommand: false };
  const cmd = text.slice(1).toLowerCase();
  if (cmd.startsWith('clear') || cmd.startsWith('reset')) return { type: 'system', isCommand: true };
  if (cmd.startsWith('status')) return { type: 'info', isCommand: true };
  if (cmd.startsWith('restart')) return { type: 'warn', isCommand: true };
  return { type: 'system', isCommand: true };
}
