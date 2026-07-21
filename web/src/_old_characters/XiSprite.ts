/**
 * XiSprite — 银狼像素角色 + 动画状态机
 *
 * 角色设计（32x40 像素矩阵）：
 * - 银灰色短发（略带凌乱）
 * - 深蓝连帽外套
 * - 黑色短裤 + 长袜
 * - 泡泡糖（idle 时偶尔出现）
 *
 * 动画状态：
 * - idle: 呼吸起伏 + 偶尔眨眼
 * - talking: 嘴巴开合
 * - thinking: 手托下巴 + 省略号气泡
 * - happy: 眼睛弯月 + 跳跃
 */
import Phaser from 'phaser';
import { COLORS } from '../config';

// ─── 调色板索引 ─────────────────────────────────────────────
const PAL = {
  _: 0x00000000, // 透明
  H: 0xffc0c0c0, // 银发（亮）
  h: 0xffa0a0a8, // 银发（暗）
  S: 0xffffe0c8, // 皮肤
  s: 0xfff0c8a8, // 皮肤（暗）
  E: 0xff4a90d9, // 眼睛（蓝）
  B: 0xff1a3a5c, // 外套（深蓝）
  b: 0xff0f2840, // 外套（暗）
  W: 0xffffffff, // 白色高光
  K: 0xff1a1a2e, // 黑色（裤子/鞋）
  P: 0xffff8fab, // 泡泡糖粉
  G: 0xff3c3c50, // 深灰（细节）
} as const;

type PalKey = keyof typeof PAL;

// 32 列 x 40 行的像素矩阵（银狼正面半身像）
// 简化为 24x32 以适配侧边栏
const FRAME_IDLE: string[] = [
  '........................',
  '........................',
  '........HHHHHH..........',
  '......HHHHHHHHHH........',
  '.....HHHHHHHHHHHH.......',
  '.....HHHHHHHHHHHH.......',
  '....HHHSSSSSSSHHH.......',
  '....HHSSSSSSSSSHH.......',
  '....HHSSESSSSESSH.......',
  '....HSSSSSSSSSSSSH......',
  '....HSSSSSSSSSSSSH......',
  '....HSSSSsSSsSSSSH......',
  '.....SSSSSSSSSSSS.......',
  '.....SSSSSSSSSSSS.......',
  '......SSSSSSSSSS........',
  '.......SSSSSSSS.........',
  '........BBBBBB..........',
  '......BBBBBBBBBB........',
  '.....BBBBBBBBBBBB.......',
  '....BBBBBBBBBBBBBB......',
  '....BBBBBBBBBBBBBB......',
  '....BBbBBBBBBBBbBB......',
  '....BBbBBBBBBBBbBB......',
  '....BBBBBBBBBBBBBB......',
  '.....BBBBBBBBBBBB.......',
  '.....BBBBBBBBBBBB.......',
  '......BBBBBBBBBB........',
  '......BBB....BBB........',
  '......KKK....KKK........',
  '......KKK....KKK........',
  '......KKK....KKK........',
  '......GGG....GGG........',
];

// talking 帧：嘴巴张开
const FRAME_TALK: string[] = [
  '........................',
  '........................',
  '........HHHHHH..........',
  '......HHHHHHHHHH........',
  '.....HHHHHHHHHHHH.......',
  '.....HHHHHHHHHHHH.......',
  '....HHHSSSSSSSHHH.......',
  '....HHSSSSSSSSSHH.......',
  '....HHSSESSSSESSH.......',
  '....HSSSSSSSSSSSSH......',
  '....HSSSSSSSSSSSSH......',
  '....HSSSSsSSsSSSSH......',
  '.....SSSSSSSSSSSS.......',
  '.....SSSsSSSSsSSS.......',
  '......SSSsSSsSSS........',
  '.......SSSSSSSS.........',
  '........BBBBBB..........',
  '......BBBBBBBBBB........',
  '.....BBBBBBBBBBBB.......',
  '....BBBBBBBBBBBBBB......',
  '....BBBBBBBBBBBBBB......',
  '....BBbBBBBBBBBbBB......',
  '....BBbBBBBBBBBbBB......',
  '....BBBBBBBBBBBBBB......',
  '.....BBBBBBBBBBBB.......',
  '.....BBBBBBBBBBBB.......',
  '......BBBBBBBBBB........',
  '......BBB....BBB........',
  '......KKK....KKK........',
  '......KKK....KKK........',
  '......KKK....KKK........',
  '......GGG....GGG........',
];

// thinking 帧：手托下巴
const FRAME_THINK: string[] = [
  '........................',
  '........................',
  '........HHHHHH..........',
  '......HHHHHHHHHH........',
  '.....HHHHHHHHHHHH.......',
  '.....HHHHHHHHHHHH.......',
  '....HHHSSSSSSSHHH.......',
  '....HHSSSSSSSSSHH.......',
  '....HHSSESSSSESSH.......',
  '....HSSSSSSSSSSSSH......',
  '....HSSSSSSSSSSSSH......',
  '....HSSSSsSSsSSSSH......',
  '.....SSSSSSSSSSSS.......',
  '.....SSSSSSSSSSSS.......',
  '......SSSSSSSSSS........',
  '.......SSSSSSSS.........',
  '........BBBBBB..........',
  '......BBBBBBBBBB........',
  '.....BBBBBBBBBBBB.......',
  '....BBBBBBBBBBBBBB......',
  '....BBBBBBBBBBBBBB......',
  '....BBbBBBBBBBBbBB......',
  '....SSbBBBBBBBBbBB......',
  '....SSBBBBBBBBBBBB......',
  '.....SSBBBBBBBBBB.......',
  '.....BBBBBBBBBBBB.......',
  '......BBBBBBBBBB........',
  '......BBB....BBB........',
  '......KKK....KKK........',
  '......KKK....KKK........',
  '......KKK....KKK........',
  '......GGG....GGG........',
];

export type XiAnimState = 'idle' | 'talking' | 'thinking' | 'happy';

export class XiSprite {
  private scene: Phaser.Scene;
  private container: Phaser.GameObjects.Container;
  private spriteImg: Phaser.GameObjects.Image;
  private bubbleText: Phaser.GameObjects.Text | null = null;
  private state: XiAnimState = 'idle';
  private animTimer: Phaser.Time.TimerEvent | null = null;
  private breathTween: Phaser.Tweens.Tween | null = null;

  // 显示尺寸（原图 1024x1024）
  private static readonly DISPLAY_H = 96;
  private static readonly IMG_SIZE = 1024;

  constructor(scene: Phaser.Scene, x: number, y: number) {
    this.scene = scene;
    this.container = scene.add.container(x, y);

    // 使用 BootScene 预加载的 PNG
    const texKey = scene.textures.exists('xi_idle') ? 'xi_idle' : undefined;
    if (texKey) {
      this.spriteImg = scene.add.image(0, 0, texKey);
    } else {
      // fallback: 纯色占位
      this.spriteImg = scene.add.image(0, 0, '__DEFAULT');
    }
    this.spriteImg.setOrigin(0.5, 0.5);
    const s = XiSprite.DISPLAY_H / XiSprite.IMG_SIZE;
    this.spriteImg.setScale(s);
    this.container.add(this.spriteImg);

    // 呼吸动画
    this._startBreathing();
  }

  get x(): number { return this.container.x; }
  get y(): number { return this.container.y; }

  /** 切换动画状态 */
  setState(newState: XiAnimState): void {
    if (this.state === newState) return;
    this.state = newState;
    this._applyState();
  }

  /** 显示对话气泡 */
  showBubble(text: string, duration = 3000): void {
    this._clearBubble();
    const short = text.length > 20 ? text.slice(0, 20) + '...' : text;
    this.bubbleText = this.scene.add.text(0, -55, short, {
      fontSize: '8px',
      color: '#3C2814',
      fontFamily: 'monospace',
      backgroundColor: '#F5DEB3',
      padding: { x: 4, y: 2 },
    }).setOrigin(0.5);
    this.container.add(this.bubbleText);

    if (duration > 0) {
      this.scene.time.delayedCall(duration, () => this._clearBubble());
    }
  }

  destroy(): void {
    this.animTimer?.destroy();
    this.breathTween?.destroy();
    this.container.destroy(true);
  }

  // ─── 内部方法 ─────────────────────────────────────────────

  private _applyState(): void {
    // 清除旧动画
    this.animTimer?.destroy();
    this.animTimer = null;
    this._stopBreathing();
    this._clearBubble();
    this.spriteImg.angle = 0;

    switch (this.state) {
      case 'idle':
        this._startBreathing();
        this._startBlinkLoop();
        break;
      case 'talking':
        this._startTalkAnim();
        break;
      case 'thinking':
        this.spriteImg.angle = -3; // 微微歪头
        this.showBubble('...', 0);
        break;
      case 'happy':
        this._doHappyBounce();
        break;
    }
  }

  private _startBreathing(): void {
    this._stopBreathing();
    this.breathTween = this.scene.tweens.add({
      targets: this.spriteImg,
      y: 1.5,
      duration: 1200,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
  }

  private _stopBreathing(): void {
    this.breathTween?.destroy();
    this.breathTween = null;
    this.spriteImg.y = 0;
  }

  private _startTalkAnim(): void {
    // 说话时轻微上下弹跳 + 缩放
    this.breathTween = this.scene.tweens.add({
      targets: this.spriteImg,
      y: -2,
      scaleX: this.spriteImg.scaleX * 1.02,
      duration: 180,
      yoyo: true,
      repeat: -1,
      ease: 'Quad.easeInOut',
    });
  }

  private _startBlinkLoop(): void {
    // 随机眨眼（简化：短暂缩放 y）
    this.animTimer?.destroy();
    const blink = () => {
      if (this.state !== 'idle') return;
      this.scene.tweens.add({
        targets: this.spriteImg,
        scaleY: this.spriteImg.scaleY * 0.95,
        duration: 80,
        yoyo: true,
        onComplete: () => {
          // 下次眨眼
          const next = Phaser.Math.Between(2000, 5000);
          this.animTimer = this.scene.time.delayedCall(next, blink);
        },
      });
    };
    this.animTimer = this.scene.time.delayedCall(2000, blink);
  }

  private _doHappyBounce(): void {
    this.scene.tweens.add({
      targets: this.container,
      y: this.container.y - 6,
      duration: 200,
      yoyo: true,
      repeat: 2,
      ease: 'Quad.easeOut',
      onComplete: () => {
        this.setState('idle');
      },
    });
  }

  private _clearBubble(): void {
    this.bubbleText?.destroy();
    this.bubbleText = null;
  }
}
