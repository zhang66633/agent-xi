/**
 * BootScene — 资源加载 + 像素 UI 纹理生成
 *
 * 在加载外部素材之前，先用代码生成基础像素纹理：
 * - 面板边框（9-slice 用）
 * - 按钮状态
 * - 输入框背景
 * 这样即使没有外部美术资源也能跑起来。
 */
import Phaser from 'phaser';
import { COLORS, GAME_WIDTH, GAME_HEIGHT } from '../config';

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload(): void {
    // 显示加载进度条（像素风）
    const barWidth = 200;
    const barHeight = 12;
    const x = (GAME_WIDTH - barWidth) / 2;
    const y = (GAME_HEIGHT - barHeight) / 2;

    const barBg = this.add.rectangle(
      x + barWidth / 2, y + barHeight / 2,
      barWidth, barHeight, COLORS.panelDark
    );
    const barFill = this.add.rectangle(
      x + 2, y + barHeight / 2,
      0, barHeight - 4, COLORS.accentGreen
    ).setOrigin(0, 0.5);

    const loadText = this.add.text(
      GAME_WIDTH / 2, y - 20, 'Loading...',
      { fontSize: '10px', color: '#F5DEB3', fontFamily: 'monospace' }
    ).setOrigin(0.5);

    this.load.on('progress', (value: number) => {
      barFill.width = (barWidth - 4) * value;
    });

    this.load.on('complete', () => {
      barBg.destroy();
      barFill.destroy();
      loadText.destroy();
    });

    // 加载银狼 sprite
    this.load.image('xi_idle', 'assets/xi/idle.png');
    // this.load.bitmapFont('zpix', 'fonts/zpix.png', 'fonts/zpix.xml');
  }

  create(): void {
    // 生成程序化像素纹理
    this._generatePanelTexture();
    this._generateButtonTexture();
    this._generateInputTexture();

    // 进入主场景
    this.scene.start('ChatScene');
  }

  /** 生成 9-slice 面板纹理（24x24，边框 8px） */
  private _generatePanelTexture(): void {
    const size = 24;
    const border = 8;
    const rt = this.textures.createCanvas('panel', size, size);
    if (!rt) return;
    const ctx = rt.getContext();

    // 背景
    ctx.fillStyle = '#F5DEB3';
    ctx.fillRect(0, 0, size, size);

    // 边框（木棕色）
    ctx.fillStyle = '#8B5E3C';
    ctx.fillRect(0, 0, size, border);           // top
    ctx.fillRect(0, size - border, size, border); // bottom
    ctx.fillRect(0, 0, border, size);           // left
    ctx.fillRect(size - border, 0, border, size); // right

    // 内阴影（深木色，1px）
    ctx.fillStyle = '#5C3D2E';
    ctx.fillRect(border, border, size - border * 2, 1);
    ctx.fillRect(border, border, 1, size - border * 2);

    // 外高光（亮色，1px）
    ctx.fillStyle = '#D2A86E';
    ctx.fillRect(border, size - border - 1, size - border * 2, 1);
    ctx.fillRect(size - border - 1, border, 1, size - border * 2);

    rt.refresh();
  }

  /** 生成按钮纹理（normal / hover / pressed） */
  private _generateButtonTexture(): void {
    const w = 48;
    const h = 16;
    const states: [string, string, string][] = [
      ['btn_normal', '#D2A86E', '#8B5E3C'],
      ['btn_hover', '#F4D03F', '#8B5E3C'],
      ['btn_pressed', '#8B5E3C', '#5C3D2E'],
    ];

    for (const [key, fill, border] of states) {
      const rt = this.textures.createCanvas(key, w, h);
      if (!rt) continue;
      const ctx = rt.getContext();

      ctx.fillStyle = border;
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = fill;
      ctx.fillRect(2, 2, w - 4, h - 4);

      // 凸起高光
      ctx.fillStyle = 'rgba(255,255,255,0.3)';
      ctx.fillRect(2, 2, w - 4, 1);

      rt.refresh();
    }
  }

  /** 生成输入框纹理（内凹效果） */
  private _generateInputTexture(): void {
    const w = 64;
    const h = 16;
    const rt = this.textures.createCanvas('input_bg', w, h);
    if (!rt) return;
    const ctx = rt.getContext();

    // 边框
    ctx.fillStyle = '#8B5E3C';
    ctx.fillRect(0, 0, w, h);
    // 内凹背景
    ctx.fillStyle = '#FFF8DC';
    ctx.fillRect(2, 2, w - 4, h - 4);
    // 内凹阴影（左上深色）
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.fillRect(2, 2, w - 4, 1);
    ctx.fillRect(2, 2, 1, h - 4);

    rt.refresh();
  }
}
