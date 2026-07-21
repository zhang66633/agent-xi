/**
 * ChatScene — 主对话界面（星露谷像素风）
 *
 * 功能：
 * - 流式打字机效果
 * - 鼠标滚轮滚动消息
 * - 工具确认弹窗（像素风）
 * - 消息裁剪（只显示面板区域内）
 * - 工具执行状态提示
 */
import Phaser from 'phaser';
import { COLORS, GAME_WIDTH, GAME_HEIGHT } from '../config';
import { WsClient, WsIncoming } from '../net/ws_client';
import { WS_URL } from '../config';
import { XiSprite } from '../characters/XiSprite';

// ─── 布局常量 ─────────────────────────────────────────────────
const PADDING = 12;
const TOP_BAR_H = 36;
const INPUT_BAR_H = 52;
const SIDEBAR_W = 180;

const MSG_AREA = {
  x: SIDEBAR_W + PADDING,
  y: TOP_BAR_H + PADDING,
  w: GAME_WIDTH - SIDEBAR_W - PADDING * 2,
  h: GAME_HEIGHT - TOP_BAR_H - INPUT_BAR_H - PADDING * 2,
};

// ─── 消息类型 ─────────────────────────────────────────────────
interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  text: string;
}

export class ChatScene extends Phaser.Scene {
  private ws!: WsClient;
  private messages: ChatMessage[] = [];

  // 渲染相关
  private msgContainer!: Phaser.GameObjects.Container;
  private scrollOffset = 0;
  private maxScroll = 0;
  private contentHeight = 0;

  // 流式状态
  private isStreaming = false;
  private streamBuffer = '';
  private streamTextObj: Phaser.GameObjects.Text | null = null;

  // 工具确认
  private confirmOverlay: Phaser.GameObjects.Container | null = null;

  // UI 引用
  private inputEl!: HTMLTextAreaElement;
  private statusDot!: Phaser.GameObjects.Arc;
  private statusText!: Phaser.GameObjects.Text;
  private typingIndicator!: Phaser.GameObjects.Text;
  private xiSprite!: XiSprite;

  constructor() {
    super({ key: 'ChatScene' });
  }

  create(): void {
    this.cameras.main.fadeIn(200);
    this._drawBackground();
    this._drawTopBar();
    this._drawSidebar();
    this._drawMessagePanel();
    this._createInputOverlay();
    this._connectWs();
    this._setupScroll();

    // 确保输入框可见（从其他场景回来时）
    const overlay = document.getElementById('input-overlay');
    if (overlay) overlay.style.display = 'flex';

    // 欢迎消息
    this._addMessage('assistant', '你好！我是 Agent Xi，你的 AI 伙伴。有什么可以帮你的？');

    // 场景切换时隐藏/显示输入框
    this.events.on('shutdown', () => {
      const overlay = document.getElementById('input-overlay');
      if (overlay) overlay.style.display = 'none';
      this.ws?.disconnect();
    });
    this.events.on('wake', () => {
      const overlay = document.getElementById('input-overlay');
      if (overlay) overlay.style.display = 'flex';
      this._connectWs();
    });
  }

  // ─── 绘制 UI ────────────────────────────────────────────────

  private _drawBackground(): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(0x000000, 0.06);
    for (let y = 0; y < GAME_HEIGHT; y += 4) {
      gfx.fillRect(0, y, GAME_WIDTH, 1);
    }
  }

  private _drawTopBar(): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(COLORS.panelBorder, 1);
    gfx.fillRect(0, 0, GAME_WIDTH, TOP_BAR_H);
    gfx.fillStyle(COLORS.panelDark, 1);
    gfx.fillRect(2, 2, GAME_WIDTH - 4, TOP_BAR_H - 4);

    this.add.text(12, TOP_BAR_H / 2, '☀ Agent Xi', {
      fontSize: '12px',
      color: '#F5DEB3',
      fontFamily: 'monospace',
    }).setOrigin(0, 0.5);

    // 市场导航按钮
    const marketBtn = this.add.text(GAME_WIDTH / 2 - 40, TOP_BAR_H / 2, '🏪 市场', {
      fontSize: '10px',
      color: '#F4D03F',
      fontFamily: 'monospace',
    }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    marketBtn.on('pointerdown', () => this.scene.start('MarketScene'));
    marketBtn.on('pointerover', () => marketBtn.setColor('#FFFFFF'));
    marketBtn.on('pointerout', () => marketBtn.setColor('#F4D03F'));

    // 管理面板按钮
    const adminBtn = this.add.text(GAME_WIDTH / 2 + 40, TOP_BAR_H / 2, '⚙ 管理', {
      fontSize: '10px',
      color: '#F4D03F',
      fontFamily: 'monospace',
    }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    adminBtn.on('pointerdown', () => this.scene.start('AdminScene'));
    adminBtn.on('pointerover', () => adminBtn.setColor('#FFFFFF'));
    adminBtn.on('pointerout', () => adminBtn.setColor('#F4D03F'));

    // 连接状态
    this.statusDot = this.add.circle(GAME_WIDTH - 80, TOP_BAR_H / 2, 4, COLORS.accentRed);
    this.statusText = this.add.text(GAME_WIDTH - 70, TOP_BAR_H / 2, '离线', {
      fontSize: '10px',
      color: '#F5DEB3',
      fontFamily: 'monospace',
    }).setOrigin(0, 0.5);
  }

  private _drawSidebar(): void {
    const gfx = this.add.graphics();
    const x = PADDING;
    const y = TOP_BAR_H + PADDING;
    const w = SIDEBAR_W - PADDING;
    const h = GAME_HEIGHT - TOP_BAR_H - INPUT_BAR_H - PADDING * 2;

    this._drawPixelPanel(gfx, x, y, w, h);

    // 银狼角色 sprite
    const cx = x + w / 2;
    const cy = y + 65;
    this.xiSprite = new XiSprite(this, cx, cy);

    this.add.text(cx, cy + 55, '银狼', {
      fontSize: '10px', color: '#3C2814', fontFamily: 'monospace',
    }).setOrigin(0.5);

    // 状态条
    this._drawStatusBar(gfx, x + 16, y + 120, w - 32, 'HP', COLORS.accentGreen, 0.8);
    this._drawStatusBar(gfx, x + 16, y + 148, w - 32, 'MP', COLORS.wolfBlue, 0.6);

    this.add.text(cx, y + h - 20, 'Lv.1 AI Partner', {
      fontSize: '9px', color: '#6B4C2E', fontFamily: 'monospace',
    }).setOrigin(0.5);
  }

  private _drawMessagePanel(): void {
    const gfx = this.add.graphics();
    this._drawPixelPanel(gfx, MSG_AREA.x, MSG_AREA.y, MSG_AREA.w, MSG_AREA.h);

    // 消息容器（带裁剪遮罩）
    this.msgContainer = this.add.container(0, 0);

    // 用 Graphics 做遮罩
    const mask = this.add.graphics();
    mask.fillStyle(0xffffff, 1);
    mask.fillRect(MSG_AREA.x + 4, MSG_AREA.y + 4, MSG_AREA.w - 8, MSG_AREA.h - 8);
    mask.setVisible(false);
    const maskObj = mask.createGeometryMask();
    this.msgContainer.setMask(maskObj);

    // 打字指示器
    this.typingIndicator = this.add.text(
      MSG_AREA.x + 12, MSG_AREA.y + MSG_AREA.h - 20, '▌', {
        fontSize: '12px', color: '#3C2814', fontFamily: 'monospace',
      }
    ).setAlpha(0);
  }

  private _drawPixelPanel(
    gfx: Phaser.GameObjects.Graphics,
    x: number, y: number, w: number, h: number
  ): void {
    gfx.fillStyle(COLORS.panelBorder, 1);
    gfx.fillRect(x, y, w, h);
    gfx.fillStyle(COLORS.panelBg, 1);
    gfx.fillRect(x + 3, y + 3, w - 6, h - 6);
    gfx.fillStyle(COLORS.panelDark, 0.4);
    gfx.fillRect(x + 3, y + 3, w - 6, 2);
    gfx.fillRect(x + 3, y + 3, 2, h - 6);
    gfx.fillStyle(0xd2a86e, 0.6);
    gfx.fillRect(x + 3, y + h - 5, w - 6, 2);
    gfx.fillRect(x + w - 5, y + 3, 2, h - 6);
  }

  private _drawStatusBar(
    gfx: Phaser.GameObjects.Graphics,
    x: number, y: number, w: number,
    label: string, color: number, ratio: number
  ): void {
    this.add.text(x, y - 2, label, {
      fontSize: '8px', color: '#3C2814', fontFamily: 'monospace',
    });
    gfx.fillStyle(0x000000, 0.3);
    gfx.fillRect(x, y + 10, w, 8);
    gfx.fillStyle(color, 1);
    gfx.fillRect(x + 1, y + 11, (w - 2) * ratio, 6);
  }

  // ─── 输入覆盖层 ─────────────────────────────────────────────

  private _createInputOverlay(): void {
    const container = document.getElementById('game-container');
    if (!container) return;

    const wrapper = document.createElement('div');
    wrapper.id = 'input-overlay';
    wrapper.style.cssText = `
      position: absolute;
      bottom: 10px;
      left: 50%;
      transform: translateX(-50%);
      width: ${GAME_WIDTH - PADDING * 2}px;
      display: flex;
      gap: 8px;
      align-items: flex-end;
      z-index: 10;
    `;

    this.inputEl = document.createElement('textarea');
    this.inputEl.placeholder = '输入消息... (Enter 发送, Shift+Enter 换行)';
    this.inputEl.rows = 1;
    this.inputEl.style.cssText = `
      flex: 1;
      padding: 8px 12px;
      font-family: "Zpix", monospace;
      font-size: 12px;
      color: #3C2814;
      background: #FFF8DC;
      border: 3px solid #8B5E3C;
      border-radius: 0;
      outline: none;
      resize: none;
      box-shadow: inset 2px 2px 0 rgba(0,0,0,0.1);
      max-height: 80px;
      line-height: 1.4;
    `;

    const sendBtn = document.createElement('button');
    sendBtn.textContent = '发送';
    sendBtn.style.cssText = `
      padding: 8px 16px;
      font-family: "Zpix", monospace;
      font-size: 12px;
      color: #3C2814;
      background: #D2A86E;
      border: 3px solid #8B5E3C;
      border-radius: 0;
      cursor: pointer;
      box-shadow: 2px 2px 0 #5C3D2E;
    `;
    sendBtn.onmousedown = () => {
      sendBtn.style.transform = 'translate(1px, 1px)';
      sendBtn.style.boxShadow = '1px 1px 0 #5C3D2E';
    };
    sendBtn.onmouseup = () => {
      sendBtn.style.transform = '';
      sendBtn.style.boxShadow = '2px 2px 0 #5C3D2E';
    };
    sendBtn.onclick = () => this._handleSend();

    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this._handleSend();
      }
    });

    this.inputEl.addEventListener('input', () => {
      this.inputEl.style.height = 'auto';
      this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 80) + 'px';
    });

    wrapper.appendChild(this.inputEl);
    wrapper.appendChild(sendBtn);
    container.style.position = 'relative';
    container.appendChild(wrapper);
  }

  // ─── 滚轮支持 ───────────────────────────────────────────────

  private _setupScroll(): void {
    this.input.on('wheel', (_pointer: Phaser.Input.Pointer, _dx: number, _dy: number, dz: number) => {
      this.scrollOffset += dz * 0.5;
      this.scrollOffset = Phaser.Math.Clamp(this.scrollOffset, 0, this.maxScroll);
      this._renderMessages();
    });
  }

  // ─── WebSocket ──────────────────────────────────────────────

  private _connectWs(): void {
    this.ws = new WsClient(WS_URL);

    this.ws.on('connected', () => {
      this.statusDot.setFillStyle(COLORS.accentGreen);
      this.statusText.setText('在线');
    });

    this.ws.on('disconnected', () => {
      this.statusDot.setFillStyle(COLORS.accentRed);
      this.statusText.setText('离线');
    });

    // 流式文本
    this.ws.on('text_delta', (msg: WsIncoming) => {
      if (!this.isStreaming) {
        this.isStreaming = true;
        this.streamBuffer = '';
        this.xiSprite.setState('talking');
      }
      this.streamBuffer += msg.text ?? '';
      this._updateStreamDisplay();
    });

    // 完成
    this.ws.on('done', () => {
      if (this.isStreaming && this.streamBuffer) {
        this._addMessage('assistant', this.streamBuffer);
      }
      this.isStreaming = false;
      this.streamBuffer = '';
      this._clearStreamDisplay();
      this.typingIndicator.setAlpha(0);
      this.xiSprite.setState('idle');
    });

    // 工具事件
    this.ws.on('tool_use_start', (msg: WsIncoming) => {
      this._addMessage('tool', `🔧 调用: ${msg.tool_name}`);
    });

    this.ws.on('tool_executing', (msg: WsIncoming) => {
      this._addMessage('tool', `⚙ 执行中: ${msg.tool_name}...`);
    });

    this.ws.on('tool_result', (msg: WsIncoming) => {
      const preview = msg.preview ?? '';
      const short = preview.length > 120 ? preview.slice(0, 120) + '...' : preview;
      this._addMessage('tool', `📋 ${msg.tool_name} → ${short}`);
    });

    this.ws.on('tool_denied', (msg: WsIncoming) => {
      this._addMessage('tool', `🚫 已拒绝: ${msg.tool_name}`);
    });

    // 工具确认请求
    this.ws.on('tool_confirm_request', (msg: WsIncoming) => {
      this._showConfirmDialog(msg.tool_name ?? '工具', msg.args ?? {});
    });

    // 系统消息
    this.ws.on('system', (msg: WsIncoming) => {
      this._addMessage('system', msg.message ?? '');
    });

    // 错误
    this.ws.on('error', (msg: WsIncoming) => {
      this._addMessage('system', `❌ ${msg.message ?? '未知错误'}`);
    });

    this.ws.connect();
  }

  // ─── 消息处理 ───────────────────────────────────────────────

  private _handleSend(): void {
    const text = this.inputEl.value.trim();
    if (!text) return;

    // 斜杠命令
    if (text.startsWith('/')) {
      this.ws.sendCommand(text);
      this._addMessage('system', `> ${text}`);
    } else {
      if (this.isStreaming) return; // 等待回复中
      this.ws.sendChat(text);
      this._addMessage('user', text);
      // 显示打字指示 + 角色思考
      this.typingIndicator.setAlpha(1);
      this.xiSprite.setState('thinking');
    }

    this.inputEl.value = '';
    this.inputEl.style.height = 'auto';
  }

  private _addMessage(role: ChatMessage['role'], text: string): void {
    this.messages.push({ role, text });
    // 限制历史消息数量（防止内存溢出）
    if (this.messages.length > 100) {
      this.messages = this.messages.slice(-80);
    }
    this._renderMessages();
    // 自动滚到底部
    this.scrollOffset = this.maxScroll;
    this._renderMessages();
  }

  // ─── 消息渲染 ───────────────────────────────────────────────

  private _renderMessages(): void {
    // 清除容器内所有子对象
    this.msgContainer.removeAll(true);

    const startX = MSG_AREA.x + 12;
    const maxWidth = MSG_AREA.w - 24;
    let curY = MSG_AREA.y + 10 - this.scrollOffset;

    const allMsgs = [...this.messages];

    // 计算总高度（用于滚动限制）
    let totalH = 0;
    const tempTexts: { text: string; h: number }[] = [];
    for (const msg of allMsgs) {
      const t = this.add.text(0, 0, this._formatMsg(msg), {
        fontSize: '12px', fontFamily: '"Zpix", monospace',
        wordWrap: { width: maxWidth }, lineSpacing: 3,
      });
      tempTexts.push({ text: this._formatMsg(msg), h: t.height });
      totalH += t.height + 10;
      t.destroy();
    }
    // 加上流式缓冲
    if (this.isStreaming && this.streamBuffer) {
      const t = this.add.text(0, 0, '[Xi] ' + this.streamBuffer + '▌', {
        fontSize: '12px', fontFamily: '"Zpix", monospace',
        wordWrap: { width: maxWidth }, lineSpacing: 3,
      });
      totalH += t.height + 10;
      t.destroy();
    }

    this.contentHeight = totalH;
    this.maxScroll = Math.max(0, totalH - MSG_AREA.h + 20);
    this.scrollOffset = Phaser.Math.Clamp(this.scrollOffset, 0, this.maxScroll);

    // 重新计算 curY（应用滚动）
    curY = MSG_AREA.y + 10 - this.scrollOffset;

    for (let i = 0; i < allMsgs.length; i++) {
      const msg = allMsgs[i];
      const formatted = this._formatMsg(msg);
      const color = this._msgColor(msg.role);

      const textObj = this.add.text(startX, curY, formatted, {
        fontSize: '12px',
        color,
        fontFamily: '"Zpix", monospace',
        wordWrap: { width: maxWidth },
        lineSpacing: 3,
      });

      this.msgContainer.add(textObj);
      curY += textObj.height + 10;
    }

    // 流式消息
    if (this.isStreaming && this.streamBuffer) {
      const streamObj = this.add.text(startX, curY, '[Xi] ' + this.streamBuffer + '▌', {
        fontSize: '12px',
        color: '#3C2814',
        fontFamily: '"Zpix", monospace',
        wordWrap: { width: maxWidth },
        lineSpacing: 3,
      });
      this.msgContainer.add(streamObj);
    }
  }

  private _formatMsg(msg: ChatMessage): string {
    switch (msg.role) {
      case 'user': return `[你] ${msg.text}`;
      case 'assistant': return `[Xi] ${msg.text}`;
      case 'tool': return msg.text;
      case 'system': return `  ${msg.text}`;
    }
  }

  private _msgColor(role: ChatMessage['role']): string {
    switch (role) {
      case 'user': return '#1A3A5C';
      case 'assistant': return '#3C2814';
      case 'tool': return '#5C3D2E';
      case 'system': return '#6B4C2E';
    }
  }

  private _updateStreamDisplay(): void {
    this._renderMessages();
    // 自动跟随
    this.scrollOffset = this.maxScroll;
    this._renderMessages();
  }

  private _clearStreamDisplay(): void {
    // 流式结束后由 _addMessage 重新渲染
  }

  // ─── 工具确认弹窗 ───────────────────────────────────────────

  private _showConfirmDialog(toolName: string, args: Record<string, unknown>): void {
    if (this.confirmOverlay) {
      this.confirmOverlay.destroy(true);
    }

    const overlay = this.add.container(0, 0);

    // 半透明背景
    const bg = this.add.rectangle(GAME_WIDTH / 2, GAME_HEIGHT / 2, GAME_WIDTH, GAME_HEIGHT, 0x000000, 0.5);
    overlay.add(bg);

    // 弹窗面板
    const panelW = 360;
    const panelH = 180;
    const px = (GAME_WIDTH - panelW) / 2;
    const py = (GAME_HEIGHT - panelH) / 2;

    const gfx = this.add.graphics();
    this._drawPixelPanel(gfx, px, py, panelW, panelH);
    overlay.add(gfx);

    // 标题
    const title = this.add.text(GAME_WIDTH / 2, py + 20, '⚠ 工具确认', {
      fontSize: '13px', color: '#3C2814', fontFamily: 'monospace',
    }).setOrigin(0.5);
    overlay.add(title);

    // 工具名
    const nameText = this.add.text(GAME_WIDTH / 2, py + 48, `工具: ${toolName}`, {
      fontSize: '11px', color: '#5C3D2E', fontFamily: 'monospace',
    }).setOrigin(0.5);
    overlay.add(nameText);

    // 参数预览
    const argsStr = JSON.stringify(args, null, 1);
    const shortArgs = argsStr.length > 100 ? argsStr.slice(0, 100) + '...' : argsStr;
    const argsText = this.add.text(GAME_WIDTH / 2, py + 72, shortArgs, {
      fontSize: '9px', color: '#6B4C2E', fontFamily: 'monospace',
      wordWrap: { width: panelW - 40 },
    }).setOrigin(0.5);
    overlay.add(argsText);

    // 允许按钮
    const allowBtn = this._createPixelButton(GAME_WIDTH / 2 - 60, py + panelH - 40, '允许', COLORS.accentGreen);
    allowBtn.on('pointerdown', () => {
      this.ws.sendConfirm(true);
      overlay.destroy(true);
      this.confirmOverlay = null;
      this._addMessage('tool', `✓ 已允许: ${toolName}`);
    });
    overlay.add(allowBtn);

    // 拒绝按钮
    const denyBtn = this._createPixelButton(GAME_WIDTH / 2 + 60, py + panelH - 40, '拒绝', COLORS.accentRed);
    denyBtn.on('pointerdown', () => {
      this.ws.sendConfirm(false);
      overlay.destroy(true);
      this.confirmOverlay = null;
      this._addMessage('tool', `✗ 已拒绝: ${toolName}`);
    });
    overlay.add(denyBtn);

    this.confirmOverlay = overlay;
  }

  private _createPixelButton(
    cx: number, cy: number, label: string, color: number
  ): Phaser.GameObjects.Container {
    const btn = this.add.container(cx, cy);

    const bg = this.add.rectangle(0, 0, 80, 28, color);
    bg.setStrokeStyle(2, COLORS.panelBorder);

    const text = this.add.text(0, 0, label, {
      fontSize: '11px', color: '#FFFFFF', fontFamily: 'monospace',
    }).setOrigin(0.5);

    btn.add([bg, text]);
    btn.setSize(80, 28);
    btn.setInteractive({ useHandCursor: true });

    btn.on('pointerover', () => { bg.setFillStyle(color, 0.8); });
    btn.on('pointerout', () => { bg.setFillStyle(color, 1); });

    return btn;
  }
}
