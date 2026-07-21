/**
 * Hash 路由器 — 零依赖视图切换
 *
 * 路由表：#/console（默认）、#/market、#/settings
 * 切换时显隐对应 <section>，带像素风 steps() 过渡动画。
 * WS 连接挂在 App 层，不受视图切换影响。
 */

export type ViewId = 'console' | 'market' | 'settings';

const VALID_VIEWS: ViewId[] = ['console', 'market', 'settings'];
const DEFAULT_VIEW: ViewId = 'console';

type ViewChangeHandler = (view: ViewId, prev: ViewId | null) => void;

export class Router {
  private current: ViewId | null = null;
  private handlers: Set<ViewChangeHandler> = new Set();
  private _onHashChange = () => this._resolve();

  /** 启动路由：监听 hashchange + 立即解析当前 hash */
  start(): void {
    window.addEventListener('hashchange', this._onHashChange);
    this._resolve();
  }

  /** 释放监听（App.destroy 调用，防 HMR 叠加） */
  destroy(): void {
    window.removeEventListener('hashchange', this._onHashChange);
    this.handlers.clear();
  }

  /** 编程式导航 */
  navigate(view: ViewId): void {
    window.location.hash = `#/${view}`;
  }

  /** 当前视图 */
  get view(): ViewId {
    return this.current ?? DEFAULT_VIEW;
  }

  /** 注册视图变更回调，返回取消函数 */
  onChange(handler: ViewChangeHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private _resolve(): void {
    const hash = window.location.hash.replace(/^#\/?/, '');
    const view = (VALID_VIEWS.includes(hash as ViewId) ? hash : DEFAULT_VIEW) as ViewId;

    if (view === this.current) return;

    const prev = this.current;
    this.current = view;
    this._applyView(view, prev);
    this.handlers.forEach((h) => h(view, prev));
  }

  /** 切换 section 显隐 + 过渡动画 */
  private _applyView(view: ViewId, prev: ViewId | null): void {
    // 隐藏旧视图
    if (prev) {
      const oldEl = document.getElementById(`view-${prev}`);
      if (oldEl) {
        oldEl.classList.add('view-exit');
        oldEl.addEventListener('animationend', () => {
          oldEl.hidden = true;
          oldEl.classList.remove('view-exit');
        }, { once: true });
        // 兜底：动画被 reduce-motion 禁用时直接隐藏
        setTimeout(() => { oldEl.hidden = true; oldEl.classList.remove('view-exit'); }, 200);
      }
    } else {
      // 首次解析：HTML 默认只写了 console 不带 hidden，
      // 若直接加载 #/market 等需把其余视图全部隐藏
      for (const v of VALID_VIEWS) {
        if (v === view) continue;
        const el = document.getElementById(`view-${v}`);
        if (el) el.hidden = true;
      }
    }

    // 显示新视图
    const newEl = document.getElementById(`view-${view}`);
    if (newEl) {
      newEl.hidden = false;
      newEl.classList.add('view-enter');
      newEl.addEventListener('animationend', () => {
        newEl.classList.remove('view-enter');
      }, { once: true });
      setTimeout(() => newEl.classList.remove('view-enter'), 200);
    }

    // 更新图标栏高亮
    document.querySelectorAll('.nav-icon').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-view') === view);
    });
  }
}
