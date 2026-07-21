/**
 * Agent Xi 控制台 — 前端配置
 */

// ─── WebSocket & API ──────────────────────────────────────
export const WS_URL = `ws://${window.location.hostname}:9731/ws/chat`;
export const API_BASE = `http://${window.location.hostname}:9731`;

// 会话持久化：localStorage 中保存后端下发的 session_id，刷新后上报以恢复历史
export const SESSION_STORAGE_KEY = 'agent_xi_session_id';

// ─── 版本 ─────────────────────────────────────────────────
export const CONSOLE_VERSION = 'v2.7';
export const CONSOLE_CONTEXT = `Agent Xi 内核 · ${window.location.hostname}:9731`;

// ─── 应用配置 ─────────────────────────────────────────────
export const LOG_MAX_ENTRIES = 500;
export const HEART_MAX = 10;
export const EN_MAX = 100;
