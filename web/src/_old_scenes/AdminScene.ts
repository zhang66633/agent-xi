/**
 * AdminScene — 管理面板（记忆 / 技能 / 历史）
 *
 * 三个标签页：
 * - 记忆：情景记忆 + 语义记忆统计和最近条目
 * - 技能：已安装技能列表 + 使用次数
 * - 历史：对话轮次统计
 */
import Phaser from 'phaser';
import { COLORS, GAME_WIDTH, GAME_HEIGHT } from '../config';
import { API_BASE } from '../config';

type AdminTab = 'memory' | 'skills' | 'history';

export class AdminScene extends Phaser.Scene {
  private currentTab: AdminTab = 'memory';
  private contentContainer!: Phaser.GameObjects.Container;
  private tabBgs: Phaser.GameObjects.Rectangle[] = [];

  constructor() {
    super({ key: 'AdminScene' });
  }

  create(): void {
    this.cameras.main.fadeIn(200);
    // 隐藏聊天输入框
    const overlay = document.getElementById('input-overlay');
    if (overlay) overlay.style.display = 'none';

    this._drawBackground();
    this._drawHeader();
    this._drawTabs();
    this.contentContainer = this.add.container(0, 0);
    this._loadContent();
  }

  private _drawBackground(): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(COLORS.bg, 1);
    gfx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);
    gfx.fillStyle(0x000000, 0.06);
    for (let y = 0; y < GAME_HEIGHT; y += 4) {
      gfx.fillRect(0, y, GAME_WIDTH, 1);
    }
  }

  private _drawHeader(): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(COLORS.panelBorder, 1);
    gfx.fillRect(0, 0, GAME_WIDTH, 44);
    gfx.fillStyle(COLORS.panelDark, 1);
    gfx.fillRect(2, 2, GAME_WIDTH - 4, 40);

    this.add.text(16, 22, '⚙ 管理面板', {
      fontSize: '14px', color: '#F5DEB3', fontFamily: 'monospace',
    }).setOrigin(0, 0.5);

    const backBtn = this.add.text(GAME_WIDTH - 16, 22, '← 返回对话', {
      fontSize: '11px', color: '#F4D03F', fontFamily: 'monospace',
    }).setOrigin(1, 0.5).setInteractive({ useHandCursor: true });

    backBtn.on('pointerdown', () => this.scene.start('ChatScene'));
    backBtn.on('pointerover', () => backBtn.setColor('#FFFFFF'));
    backBtn.on('pointerout', () => backBtn.setColor('#F4D03F'));
  }

  private _drawTabs(): void {
    const tabs: { key: AdminTab; label: string }[] = [
      { key: 'memory', label: '记忆' },
      { key: 'skills', label: '技能' },
      { key: 'history', label: '历史' },
    ];

    let tx = 70;
    for (const tab of tabs) {
      const bg = this.add.rectangle(tx, 60, 100, 28, COLORS.panelBg);
      bg.setStrokeStyle(2, COLORS.panelBorder);
      bg.setInteractive({ useHandCursor: true });

      this.add.text(tx, 60, tab.label, {
        fontSize: '11px', color: '#3C2814', fontFamily: 'monospace',
      }).setOrigin(0.5);

      bg.on('pointerdown', () => {
        this.currentTab = tab.key;
        this._loadContent();
        this._updateTabStyles();
      });

      this.tabBgs.push(bg);
      tx += 120;
    }

    this._updateTabStyles();
  }

  private _updateTabStyles(): void {
    const tabs: AdminTab[] = ['memory', 'skills', 'history'];
    this.tabBgs.forEach((bg, i) => {
      bg.setFillStyle(tabs[i] === this.currentTab ? COLORS.accent : COLORS.panelBg);
    });
  }

  private async _loadContent(): Promise<void> {
    this.contentContainer.removeAll(true);

    switch (this.currentTab) {
      case 'memory': await this._loadMemory(); break;
      case 'skills': await this._loadSkills(); break;
      case 'history': await this._loadHistory(); break;
    }
  }

  // ─── 记忆标签页 ─────────────────────────────────────────────

  private async _loadMemory(): Promise<void> {
    let stats = { episodic_count: 0, semantic_count: 0 };
    try {
      const res = await fetch(`${API_BASE}/api/memory/stats`);
      stats = await res.json();
    } catch { /* 忽略 */ }

    const panelX = 40;
    const panelY = 90;
    const panelW = GAME_WIDTH - 80;
    const panelH = GAME_HEIGHT - 140;

    this._drawPanel(panelX, panelY, panelW, panelH);

    // 标题
    this._addContentText(panelX + 20, panelY + 20, '📦 记忆存储', '13px', '#3C2814');

    // 统计卡片
    const cardY = panelY + 55;
    this._drawStatCard(panelX + 20, cardY, '情景记忆', `${stats.episodic_count}`, COLORS.accentGreen);
    this._drawStatCard(panelX + 220, cardY, '语义记忆', `${stats.semantic_count}`, COLORS.wolfBlue);

    // 说明
    this._addContentText(panelX + 20, cardY + 80, '情景记忆：对话中的关键事件和上下文', '10px', '#6B4C2E');
    this._addContentText(panelX + 20, cardY + 100, '语义记忆：提炼的长期知识和用户偏好', '10px', '#6B4C2E');

    // 操作提示
    this._addContentText(panelX + 20, cardY + 140, '💡 对话中说"记住..."可主动存储记忆', '10px', '#5C3D2E');
    this._addContentText(panelX + 20, cardY + 160, '💡 说"你还记得..."可触发记忆检索', '10px', '#5C3D2E');
  }

  // ─── 技能标签页 ─────────────────────────────────────────────

  private async _loadSkills(): Promise<void> {
    let skills: { id: string; name: string; description: string; use_count: number }[] = [];
    try {
      const res = await fetch(`${API_BASE}/api/skills`);
      const data = await res.json();
      skills = data.skills ?? [];
    } catch { /* 忽略 */ }

    const panelX = 40;
    const panelY = 90;
    const panelW = GAME_WIDTH - 80;
    const panelH = GAME_HEIGHT - 140;

    this._drawPanel(panelX, panelY, panelW, panelH);
    this._addContentText(panelX + 20, panelY + 20, '🎯 已安装技能', '13px', '#3C2814');

    if (skills.length === 0) {
      this._addContentText(panelX + 20, panelY + 60, '暂无技能。在对话中使用 /save-skill 保存，或去市场安装。', '11px', '#6B4C2E');
      return;
    }

    let sy = panelY + 55;
    for (const skill of skills.slice(0, 8)) {
      this._addContentText(panelX + 20, sy, `• ${skill.name}`, '11px', '#3C2814');
      this._addContentText(panelX + 200, sy, skill.description, '10px', '#6B4C2E');
      this._addContentText(panelX + panelW - 80, sy, `使用 ${skill.use_count} 次`, '9px', '#5C3D2E');
      sy += 30;
    }
  }

  // ─── 历史标签页 ─────────────────────────────────────────────

  private async _loadHistory(): Promise<void> {
    const panelX = 40;
    const panelY = 90;
    const panelW = GAME_WIDTH - 80;
    const panelH = GAME_HEIGHT - 140;

    this._drawPanel(panelX, panelY, panelW, panelH);
    this._addContentText(panelX + 20, panelY + 20, '📜 对话历史', '13px', '#3C2814');

    // 通过 WS 命令获取（简化：显示提示）
    this._addContentText(panelX + 20, panelY + 60, '当前会话的对话轮次可通过 /history 命令查看。', '11px', '#6B4C2E');
    this._addContentText(panelX + 20, panelY + 90, '历史记录存储在本地 SQLite 数据库中。', '10px', '#6B4C2E');

    // 显示工具列表
    let tools: { name: string; security_level: string }[] = [];
    try {
      const res = await fetch(`${API_BASE}/api/tools`);
      const data = await res.json();
      tools = data.tools ?? [];
    } catch { /* 忽略 */ }

    if (tools.length > 0) {
      this._addContentText(panelX + 20, panelY + 130, `🔧 已注册工具 (${tools.length}):`, '11px', '#3C2814');
      let ty = panelY + 155;
      for (const tool of tools.slice(0, 10)) {
        const level = tool.security_level === 'safe' ? '🟢' : '🟡';
        this._addContentText(panelX + 30, ty, `${level} ${tool.name}`, '10px', '#5C3D2E');
        ty += 22;
      }
    }
  }

  // ─── 辅助绘制 ───────────────────────────────────────────────

  private _drawPanel(x: number, y: number, w: number, h: number): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(COLORS.panelBorder, 1);
    gfx.fillRect(x, y, w, h);
    gfx.fillStyle(COLORS.panelBg, 1);
    gfx.fillRect(x + 3, y + 3, w - 6, h - 6);
    this.contentContainer.add(gfx);
  }

  private _drawStatCard(x: number, y: number, label: string, value: string, color: number): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(color, 0.2);
    gfx.fillRect(x, y, 160, 60);
    gfx.lineStyle(2, color);
    gfx.strokeRect(x, y, 160, 60);
    this.contentContainer.add(gfx);

    this._addContentText(x + 80, y + 18, value, '18px', '#3C2814', 0.5);
    this._addContentText(x + 80, y + 42, label, '10px', '#6B4C2E', 0.5);
  }

  private _addContentText(
    x: number, y: number, text: string,
    fontSize: string, color: string, originX = 0
  ): void {
    const t = this.add.text(x, y, text, {
      fontSize, color, fontFamily: 'monospace',
    }).setOrigin(originX, 0);
    this.contentContainer.add(t);
  }
}
