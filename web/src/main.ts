/**
 * Agent Xi 控制台 v2.7 — 入口
 * 像素 RPG 风格智能体控制台
 * 三栏布局：冒险者名册 · 系统日志 · 冒险者详情+任务板
 */
import { App } from './app';

declare global {
  interface Window {
    __xiApp?: App;
  }
}

// HMR / 重复初始化时先释放旧实例，避免轮询与 WS 连接叠加
window.__xiApp?.destroy();

const app = new App();
window.__xiApp = app;

try {
  app.init();
} catch (err) {
  console.error('[Agent Xi] 控制台初始化失败:', err);
  document.body.insertAdjacentHTML(
    'beforeend',
    '<div style="position:fixed;inset:auto 0 0 0;padding:10px 16px;background:#5A2328;color:#FFE9C9;font-family:monospace;font-size:13px;z-index:9999;">'
    + '控制台初始化失败，请检查页面 DOM 结构（F12 控制台查看详情）</div>',
  );
}
