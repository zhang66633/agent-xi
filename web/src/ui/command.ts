/**
 * 命令输入栏（中栏底部）
 * 处理：输入发送、执行按钮、命令历史
 */
import type { LogType } from '../types';

type CommandHandler = (text: string) => void;
type InterruptHandler = () => void;

interface CmdEntry { name: string; desc: string }

const SLASH_COMMANDS: CmdEntry[] = [
  { name: '/clear', desc: '清空对话' },
  { name: '/undo', desc: '撤销上一轮回复' },
  { name: '/history', desc: '查看对话轮次' },
  { name: '/mode ', desc: '切换模式 plan/code/review' },
  { name: '/agent ', desc: '启动子Agent(planner/coder/reviewer)' },
  { name: '/status', desc: '系统状态总览' },
  { name: '/memory', desc: '记忆统计' },
  { name: '/skills', desc: '已装技能列表' },
  { name: '/search ', desc: '联网搜索关键词' },
  { name: '/remember ', desc: '记住一条信息' },
  { name: '/allow ', desc: '临时放行工具' },
  { name: '/export', desc: '导出对话 Markdown' },
  { name: '/help', desc: '显示帮助' },
];

export class CommandInput {
  private inputEl: HTMLInputElement;
  private execBtn: HTMLButtonElement;
  private dropdownEl: HTMLElement;
  private handler: CommandHandler | null = null;
  private interruptHandler: InterruptHandler | null = null;
  private history: string[] = [];
  private historyIdx = -1;
  private allowEmptySend: (() => boolean) | null = null;
  private _mode: 'run' | 'stop' = 'run';
  private _dropdownIdx = -1;
  private _filteredCmds: CmdEntry[] = [];

  constructor() {
    const inputEl = document.getElementById('command-input');
    const execBtn = document.getElementById('command-exec');
    const dropdownEl = document.getElementById('cmd-dropdown');
    if (!(inputEl instanceof HTMLInputElement) || !(execBtn instanceof HTMLButtonElement)) {
      throw new Error('[CommandInput] 缺少 #command-input 或 #command-exec 元素');
    }
    this.inputEl = inputEl;
    this.dropdownEl = dropdownEl!;
    this.execBtn = execBtn;
    this._bind();
  }

  onCommand(handler: CommandHandler): void {
    this.handler = handler;
  }

  onInterrupt(handler: InterruptHandler): void {
    this.interruptHandler = handler;
  }

  /** 切换按钮模式：run → 执行, stop → 停止 */
  setMode(mode: 'run' | 'stop'): void {
    this._mode = mode;
    if (mode === 'stop') {
      this.execBtn.textContent = '停止';
      this.execBtn.classList.add('btn-stop');
    } else {
      this.execBtn.textContent = '执行';
      this.execBtn.classList.remove('btn-stop');
    }
  }

  get mode(): 'run' | 'stop' { return this._mode; }

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
      const dropdownOpen = !this.dropdownEl.hidden;

      // 下拉列表导航
      if (dropdownOpen && e.key === 'ArrowDown') {
        e.preventDefault();
        this._dropdownIdx = Math.min(this._dropdownIdx + 1, this._filteredCmds.length - 1);
        this._renderDropdown();
        return;
      }
      if (dropdownOpen && e.key === 'ArrowUp') {
        e.preventDefault();
        this._dropdownIdx = Math.max(this._dropdownIdx - 1, 0);
        this._renderDropdown();
        return;
      }
      if (dropdownOpen && (e.key === 'Tab' || e.key === 'Enter')) {
        e.preventDefault();
        this._selectDropdown();
        return;
      }
      if (dropdownOpen && e.key === 'Escape') {
        e.preventDefault();
        this._hideDropdown();
        return;
      }

      if (e.key === 'Enter') {
        e.preventDefault();
        this._hideDropdown();
        this._exec();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this._historyNav(-1);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        this._historyNav(1);
      } else if (e.key === 'Escape') {
        this.inputEl.value = '';
        this._hideDropdown();
      }
    });

    // 输入事件：检测 / 开头 → 显示补全
    this.inputEl.addEventListener('input', () => {
      const text = this.inputEl.value;
      if (text.startsWith('/')) {
        const q = text.toLowerCase();
        this._filteredCmds = SLASH_COMMANDS.filter(
          c => c.name.toLowerCase().startsWith(q) || c.desc.includes(q.slice(1))
        );
        if (this._filteredCmds.length > 0) {
          this._dropdownIdx = 0;
          this._renderDropdown();
          this.dropdownEl.hidden = false;
          return;
        }
      }
      this._hideDropdown();
    });

    // 全局快捷键 + 点击外部关闭下拉
    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        this.focus();
      }
    });
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      if (!target.closest('#command-bar') && !target.closest('.cmd-dropdown')) {
        this._hideDropdown();
      }
    });
  }

  private _showDropdown(): void { this.dropdownEl.hidden = false; }
  private _hideDropdown(): void { this.dropdownEl.hidden = true; this._dropdownIdx = -1; }

  private _renderDropdown(): void {
    this.dropdownEl.innerHTML = this._filteredCmds.map((c, i) => {
      const cls = i === this._dropdownIdx ? 'cmd-dropdown-item active' : 'cmd-dropdown-item';
      return `<div class="${cls}" data-idx="${i}">
        <span class="cmd-name">${c.name}</span>
        <span class="cmd-desc">${c.desc}</span>
      </div>`;
    }).join('');
    // 滚动到选中项
    const active = this.dropdownEl.querySelector('.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
    // 点击补全
    this.dropdownEl.querySelectorAll('.cmd-dropdown-item').forEach(el => {
      el.addEventListener('click', () => {
        this._dropdownIdx = parseInt((el as HTMLElement).dataset.idx || '0');
        this._selectDropdown();
      });
    });
  }

  private _selectDropdown(): void {
    if (this._dropdownIdx >= 0 && this._dropdownIdx < this._filteredCmds.length) {
      this.inputEl.value = this._filteredCmds[this._dropdownIdx].name;
      this._hideDropdown();
      this.inputEl.focus();
    }
  }

  private _exec(): void {
    // 停止模式：触发中断
    if (this._mode === 'stop') {
      this.interruptHandler?.();
      return;
    }
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
