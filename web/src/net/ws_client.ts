/**
 * WebSocket 客户端 — 与 Agent Xi 内核通信
 *
 * 协议（对齐 ws_chat.py）：
 * 客户端 → 服务端:
 *   { type: "chat", content: "你好" }
 *   { type: "confirm_tool", allowed: true }
 *   { type: "command", content: "/clear" }
 *
 * 服务端 → 客户端:
 *   { type: "session_init", session_id: "...", restored: true, turns: 3 }
 *   { type: "text_delta", text: "你" }
 *   { type: "tool_use_start", tool_name: "get_time" }
 *   { type: "tool_executing", tool_name: "get_time" }
 *   { type: "tool_result", tool_name: "get_time", preview: "..." }
 *   { type: "tool_confirm_request", tool_name: "...", args: {...} }
 *   { type: "tool_denied", tool_name: "..." }
 *   { type: "done" }
 *   { type: "error", message: "..." }
 *   { type: "system", message: "..." }
 *
 * 会话持久化：
 *   连接时附带 ?session_id=<localStorage 中的值>，
 *   收到 session_init 后把服务端确认的 id 写回 localStorage。
 */
import { SESSION_STORAGE_KEY } from '../config';
import type { AttachmentMeta } from '../types';

export interface WsIncoming {
  type: string;
  text?: string;
  tool_name?: string;
  preview?: string;
  args?: Record<string, unknown>;
  message?: string;
  session_id?: string;
  restored?: boolean;
  turns?: number;
}

type EventHandler = (msg: WsIncoming) => void;

export class WsClient {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempts = 0;
  private _connected = false;

  constructor(private url: string) {}

  get connected(): boolean {
    return this._connected;
  }

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    // 附带本地保存的 session_id，让后端恢复历史
    let url = this.url;
    const savedId = this._loadSessionId();
    if (savedId) {
      url += `${this.url.includes('?') ? '&' : '?'}session_id=${encodeURIComponent(savedId)}`;
    }
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this._connected = true;
      this.reconnectAttempts = 0;
      this._emit('connected', { type: 'connected' });
      this._startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: WsIncoming = JSON.parse(event.data as string);
        // 服务端确认会话 id → 持久化到 localStorage
        if (msg.type === 'session_init' && msg.session_id) {
          this._saveSessionId(msg.session_id);
        }
        this._emit(msg.type, msg);
        this._emit('*', msg);
      } catch {
        console.warn('[WS] 无法解析消息:', event.data);
      }
    };

    this.ws.onclose = () => {
      this._connected = false;
      this._stopHeartbeat();
      this._emit('disconnected', { type: 'disconnected' });
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      console.warn('[WS] 连接错误');
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this._stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this._connected = false;
    this.reconnectAttempts = 0;
  }

  /** 发送聊天消息（可携带已上传附件的元信息） */
  sendChat(content: string, attachments?: AttachmentMeta[]): void {
    const payload: Record<string, unknown> = { type: 'chat', content };
    if (attachments && attachments.length > 0) {
      // 只发协议字段，本地预览用的 url 不出网
      payload.attachments = attachments.map(({ file_id, name, size, mime }) => ({
        file_id, name, size, mime,
      }));
    }
    this._send(payload);
    this._emit('chat_sent', { type: 'chat_sent', text: content });
  }

  /** 当前会话 id（session_init 后写入 localStorage；上传 API 需要） */
  get sessionId(): string | null {
    return this._loadSessionId();
  }

  /** 发送工具确认 */
  sendConfirm(allowed: boolean): void {
    this._send({ type: 'confirm_tool', allowed });
  }

  /** 发送命令 */
  sendCommand(content: string): void {
    this._send({ type: 'command', content });
  }

  /** 注册事件监听，返回取消函数 */
  on(type: string, handler: EventHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);
    return () => this.off(type, handler);
  }

  off(type: string, handler: EventHandler): void {
    this.handlers.get(type)?.delete(handler);
  }

  private _send(msg: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] 未连接，消息未发送:', msg.type);
      return;
    }
    this.ws.send(JSON.stringify(msg));
  }

  private _emit(type: string, msg: WsIncoming): void {
    this.handlers.get(type)?.forEach((h) => h(msg));
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this._connected) {
        this._send({ type: 'ping' });
      }
    }, 30_000);
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /** 清除本地会话 id（下次连接将开启全新会话） */
  resetSession(): void {
    try {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      /* localStorage 不可用时静默 */
    }
  }

  private _loadSessionId(): string | null {
    try {
      return localStorage.getItem(SESSION_STORAGE_KEY);
    } catch {
      return null;
    }
  }

  private _saveSessionId(id: string): void {
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, id);
    } catch {
      /* localStorage 不可用时静默 */
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    // 指数退避：3s → 6s → 12s …… 上限 60s
    const delay = Math.min(3000 * 2 ** this.reconnectAttempts, 60_000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }
}
