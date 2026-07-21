/**
 * 通用模态弹窗
 * 用于：任务详情、工具确认
 */
export class Modal {
  private overlay: HTMLElement;
  private dialog: HTMLElement;
  private titleEl: HTMLElement;
  private bodyEl: HTMLElement;
  private closeBtn: HTMLElement;
  private onCloseHandler: (() => void) | null = null;
  private keydownHandler = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && !this.overlay.hidden) this.close();
  };

  constructor() {
    this.overlay = document.createElement('div');
    this.overlay.className = 'modal-overlay';
    this.overlay.hidden = true;

    this.dialog = document.createElement('div');
    this.dialog.className = 'modal-dialog px-border';

    this.titleEl = document.createElement('div');
    this.titleEl.className = 'modal-title';

    const closeWrap = document.createElement('div');
    closeWrap.className = 'modal-close-wrap';
    this.closeBtn = document.createElement('button');
    this.closeBtn.className = 'modal-close';
    this.closeBtn.textContent = '×';
    this.closeBtn.title = '关闭';
    closeWrap.appendChild(this.closeBtn);

    this.bodyEl = document.createElement('div');
    this.bodyEl.className = 'modal-body';

    this.dialog.appendChild(closeWrap);
    this.dialog.appendChild(this.titleEl);
    this.dialog.appendChild(this.bodyEl);
    this.overlay.appendChild(this.dialog);
    document.body.appendChild(this.overlay);

    // 关闭事件
    this.closeBtn.addEventListener('click', () => this.close());
    this.overlay.addEventListener('click', (e) => {
      if (e.target === this.overlay) this.close();
    });
    document.addEventListener('keydown', this.keydownHandler);
  }

  /**
   * 显示弹窗
   * 注意：bodyHtml 会直接进 innerHTML，调用方必须自行转义外部数据
   */
  show(title: string, bodyHtml: string, onClose?: () => void): void {
    this.titleEl.textContent = title;
    this.bodyEl.innerHTML = bodyHtml;
    this.onCloseHandler = onClose ?? null;
    this.overlay.hidden = false;
    // 触发动画
    requestAnimationFrame(() => {
      this.overlay.classList.add('visible');
      this.dialog.classList.add('visible');
    });
  }

  /** 销毁实例：移除全局监听 + 从 DOM 摘除 */
  dispose(): void {
    document.removeEventListener('keydown', this.keydownHandler);
    this.overlay.remove();
    this.onCloseHandler = null;
  }

  close(): void {
    this.overlay.classList.remove('visible');
    this.dialog.classList.remove('visible');
    // 等动画完再隐藏
    setTimeout(() => {
      this.overlay.hidden = true;
      this.onCloseHandler?.();
      this.onCloseHandler = null;
    }, 200);
  }

  get isOpen(): boolean {
    return !this.overlay.hidden;
  }

  /** 内容容器（供调用方查询弹窗内的表单元素） */
  get body(): HTMLElement {
    return this.bodyEl;
  }
}
