/**
 * MarketScene — 插件市场（像素风）
 *
 * 功能：
 * - MCP 服务器 / 技能包 分类浏览
 * - 卡片式列表 + 安装按钮
 * - 返回主对话场景
 */
import Phaser from 'phaser';
import { COLORS, GAME_WIDTH, GAME_HEIGHT } from '../config';
import { API_BASE } from '../config';

interface MarketItem {
  id: string;
  name: string;
  description: string;
  icon: string;
  installed: boolean;
}

type Tab = 'mcp' | 'skills';

export class MarketScene extends Phaser.Scene {
  private currentTab: Tab = 'mcp';
  private items: MarketItem[] = [];
  private cardContainer!: Phaser.GameObjects.Container;

  constructor() {
    super({ key: 'MarketScene' });
  }

  create(): void {
    this.cameras.main.fadeIn(200);
    // 隐藏聊天输入框
    const overlay = document.getElementById('input-overlay');
    if (overlay) overlay.style.display = 'none';

    this._drawBackground();
    this._drawHeader();
    this._drawTabs();
    this.cardContainer = this.add.container(0, 0);
    this._loadItems();
  }

  private _drawBackground(): void {
    const gfx = this.add.graphics();
    gfx.fillStyle(COLORS.bg, 1);
    gfx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);
    // 网格纹理
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

    this.add.text(16, 22, '🏪 插件市场', {
      fontSize: '14px', color: '#F5DEB3', fontFamily: 'monospace',
    }).setOrigin(0, 0.5);

    // 返回按钮
    const backBtn = this.add.text(GAME_WIDTH - 16, 22, '← 返回对话', {
      fontSize: '11px', color: '#F4D03F', fontFamily: 'monospace',
    }).setOrigin(1, 0.5).setInteractive({ useHandCursor: true });

    backBtn.on('pointerdown', () => {
      this.scene.start('ChatScene');
    });
    backBtn.on('pointerover', () => backBtn.setColor('#FFFFFF'));
    backBtn.on('pointerout', () => backBtn.setColor('#F4D03F'));
  }

  private tabBgs: Phaser.GameObjects.Rectangle[] = [];

  private _drawTabs(): void {
    const tabs: { key: Tab; label: string }[] = [
      { key: 'mcp', label: 'MCP 服务器' },
      { key: 'skills', label: '技能包' },
    ];

    let tx = 80;
    for (const tab of tabs) {
      const bg = this.add.rectangle(tx, 60, 120, 28, COLORS.panelBg);
      bg.setStrokeStyle(2, COLORS.panelBorder);
      bg.setInteractive({ useHandCursor: true });

      const label = this.add.text(tx, 60, tab.label, {
        fontSize: '11px', color: '#3C2814', fontFamily: 'monospace',
      }).setOrigin(0.5);

      bg.on('pointerdown', () => {
        this.currentTab = tab.key;
        this._loadItems();
        this._updateTabStyles();
      });

      this.tabBgs.push(bg);
      tx += 140;
    }

    this._updateTabStyles();
  }

  private _updateTabStyles(): void {
    const tabs: Tab[] = ['mcp', 'skills'];
    this.tabBgs.forEach((bg, i) => {
      if (tabs[i] === this.currentTab) {
        bg.setFillStyle(COLORS.accent);
      } else {
        bg.setFillStyle(COLORS.panelBg);
      }
    });
  }

  private async _loadItems(): Promise<void> {
    const endpoint = this.currentTab === 'mcp'
      ? `${API_BASE}/api/market/mcp`
      : `${API_BASE}/api/market/skills`;

    try {
      const res = await fetch(endpoint);
      const data = await res.json();
      this.items = data.items ?? [];
    } catch {
      this.items = [];
    }

    this._renderCards();
  }

  private _renderCards(): void {
    this.cardContainer.removeAll(true);

    const cols = 2;
    const cardW = 420;
    const cardH = 80;
    const gapX = 20;
    const gapY = 16;
    const startX = (GAME_WIDTH - (cols * cardW + (cols - 1) * gapX)) / 2;
    const startY = 90;

    this.items.forEach((item, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = startX + col * (cardW + gapX);
      const y = startY + row * (cardH + gapY);

      const card = this._createCard(x, y, cardW, cardH, item);
      this.cardContainer.add(card);
    });
  }

  private _createCard(
    x: number, y: number, w: number, h: number, item: MarketItem
  ): Phaser.GameObjects.Container {
    const card = this.add.container(x, y);

    // 卡片背景
    const gfx = this.add.graphics();
    gfx.fillStyle(COLORS.panelBorder, 1);
    gfx.fillRect(0, 0, w, h);
    gfx.fillStyle(COLORS.panelBg, 1);
    gfx.fillRect(2, 2, w - 4, h - 4);
    card.add(gfx);

    // 图标
    const icon = this.add.text(20, h / 2, item.icon, {
      fontSize: '22px',
    }).setOrigin(0, 0.5);
    card.add(icon);

    // 名称
    const name = this.add.text(52, 18, item.name, {
      fontSize: '12px', color: '#3C2814', fontFamily: 'monospace',
      fontStyle: 'bold',
    });
    card.add(name);

    // 描述
    const desc = this.add.text(52, 38, item.description, {
      fontSize: '10px', color: '#6B4C2E', fontFamily: 'monospace',
      wordWrap: { width: w - 140 },
    });
    card.add(desc);

    // 安装/已安装按钮
    if (item.installed) {
      const installed = this.add.text(w - 20, h / 2, '✓ 已安装', {
        fontSize: '10px', color: '#7DCE82', fontFamily: 'monospace',
      }).setOrigin(1, 0.5);
      card.add(installed);
    } else {
      const btnBg = this.add.rectangle(w - 50, h / 2, 64, 24, COLORS.accentGreen);
      btnBg.setStrokeStyle(2, COLORS.panelBorder);
      const btnText = this.add.text(w - 50, h / 2, '安装', {
        fontSize: '10px', color: '#FFFFFF', fontFamily: 'monospace',
      }).setOrigin(0.5);

      btnBg.setInteractive({ useHandCursor: true });
      btnBg.on('pointerdown', () => this._installItem(item, btnBg, btnText));
      btnBg.on('pointerover', () => btnBg.setFillStyle(0x5dae63));
      btnBg.on('pointerout', () => btnBg.setFillStyle(COLORS.accentGreen));

      card.add([btnBg, btnText]);
    }

    return card;
  }

  private async _installItem(
    item: MarketItem,
    btnBg: Phaser.GameObjects.Rectangle,
    btnText: Phaser.GameObjects.Text
  ): Promise<void> {
    btnText.setText('...');

    try {
      const res = await fetch(`${API_BASE}/api/market/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: this.currentTab === 'mcp' ? 'mcp' : 'skill', id: item.id }),
      });
      const data = await res.json();

      if (data.ok) {
        item.installed = true;
        btnBg.setFillStyle(COLORS.panelBg);
        btnText.setText('✓ 已装').setColor('#7DCE82');
      } else {
        btnText.setText('失败').setColor('#E74C3C');
        this.time.delayedCall(1500, () => btnText.setText('安装').setColor('#FFFFFF'));
      }
    } catch {
      btnText.setText('错误').setColor('#E74C3C');
      this.time.delayedCall(1500, () => btnText.setText('安装').setColor('#FFFFFF'));
    }
  }
}
