/**
 * 工具确认弹窗
 * WS tool_confirm_request → 弹窗让用户选择允许/拒绝
 * 用户选择 → 通过 ws.sendConfirm 回复后端
 */
import type { WsIncoming } from '../net/ws_client';
import type { WsClient } from '../net/ws_client';
import { Modal } from './modal';

export class ToolConfirmDialog {
  private modal: Modal;
  private ws: WsClient;
  private pendingTool: { name: string; args: Record<string, unknown> } | null = null;

  constructor(ws: WsClient) {
    this.ws = ws;
    this.modal = new Modal();

    this.ws.on('tool_confirm_request', (msg) => this._onRequest(msg));
    this.ws.on('tool_denied', () => this._dismiss());
  }

  private _onRequest(msg: WsIncoming): void {
    const toolName = msg.tool_name ?? '未知工具';
    const args = msg.args ?? {};
    this.pendingTool = { name: toolName, args };

    const argsJson = Object.keys(args).length > 0
      ? JSON.stringify(args, null, 2)
      : '（无参数）';

    const body = `
      <div class="confirm-warning">▲ 工具请求执行权限</div>
      <div class="confirm-tool-name">${this._escape(toolName)}</div>
      <div class="quest-detail-section">
        <div class="qd-section-title">参数</div>
        <pre class="qd-code">${this._escape(argsJson)}</pre>
      </div>
      <div class="confirm-actions">
        <button class="btn-confirm btn-deny" id="confirm-deny">拒绝</button>
        <button class="btn-confirm btn-allow" id="confirm-allow">允许</button>
      </div>
    `;

    this.modal.show(`工具确认`, body, () => {
      // 弹窗关闭时如果还没回复，默认拒绝
      if (this.pendingTool) {
        this.ws.sendConfirm(false);
        this.pendingTool = null;
      }
    });

    // 绑定按钮
    document.getElementById('confirm-allow')?.addEventListener('click', () => {
      this.ws.sendConfirm(true);
      this.pendingTool = null;
      this.modal.close();
    });
    document.getElementById('confirm-deny')?.addEventListener('click', () => {
      this.ws.sendConfirm(false);
      this.pendingTool = null;
      this.modal.close();
    });
  }

  private _dismiss(): void {
    if (this.modal.isOpen) {
      this.pendingTool = null;
      this.modal.close();
    }
  }

  private _escape(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
