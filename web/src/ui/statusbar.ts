/**
 * 顶部 + 底部状态栏
 * - 顶部：状态徽章计数 + 季节 + 时钟
 * - 底部：版本号 + 上下文
 */
import type { StatusCounts } from '../types';

export class StatusBar {
  private onlineEl: HTMLElement;
  private idleEl: HTMLElement;
  private errorEl: HTMLElement;
  private seasonEl: HTMLElement;
  private clockEl: HTMLElement;
  private bottomCtxEl: HTMLElement;
  private clockTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.onlineEl = this._req('cnt-online');
    this.idleEl = this._req('cnt-idle');
    this.errorEl = this._req('cnt-error');
    this.seasonEl = this._req('season-text');
    this.clockEl = this._req('clock-text');
    this.bottomCtxEl = this._req('bottom-context');
  }

  start(): void {
    this._tickClock();
    this.clockTimer = setInterval(() => this._tickClock(), 30_000);
  }

  stop(): void {
    if (this.clockTimer) {
      clearInterval(this.clockTimer);
      this.clockTimer = null;
    }
  }

  /** 更新状态徽章计数 */
  setCounts(counts: StatusCounts): void {
    this.onlineEl.textContent = String(counts.online);
    this.idleEl.textContent = String(counts.idle);
    this.errorEl.textContent = String(counts.error);
  }

  /** 设置季节文本（如 "夏季 7月21日"；默认由时钟按真实日期驱动） */
  setSeason(text: string): void {
    this.seasonEl.textContent = text;
  }

  /** 设置底部上下文（如 "Agent Xi 内核 · localhost:9731"） */
  setBottomContext(text: string): void {
    this.bottomCtxEl.textContent = text;
  }

  // ─── 内部 ─────────────────────────────────────────────
  private _req(id: string): HTMLElement {
    const el = document.getElementById(id);
    if (!el) throw new Error(`[StatusBar] 缺少 #${id} 元素`);
    return el;
  }

  private _tickClock(): void {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    this.clockEl.textContent = `${hh}:${mm}`;
    this.seasonEl.textContent = `${StatusBar._seasonOf(d.getMonth() + 1)} ${d.getMonth() + 1}月${d.getDate()}日`;
  }

  /** 按月份映射季节（像素农场风味，数据为真） */
  private static _seasonOf(month: number): string {
    if (month >= 3 && month <= 5) return '春季';
    if (month >= 6 && month <= 8) return '夏季';
    if (month >= 9 && month <= 11) return '秋季';
    return '冬季';
  }
}
