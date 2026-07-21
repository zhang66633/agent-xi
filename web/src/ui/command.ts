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

  constructor() {
    this.inputEl = document.getElementById('command-input') as HTMLInputElement;
    this.execBtn = document.getElementById('command-exec') as HTMLButtonElement;
    this._bind();
  }

  onCommand(handler: CommandHandler): void {
    this.handler = handler;
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
    if (!text) return;
    this.history.push(text);
    this.historyIdx = this.history.length;
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
