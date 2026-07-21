/**
 * Agent Xi 控制台 — REST API 客户端
 * 封装后端 /api/* 调用，提供类型化接口
 */
import { API_BASE } from '../config';
import type { Agent, Quest } from '../types';

export interface ToolInfo {
  name: string;
  description: string;
  security_level: string;  // "safe" | "caution" | "dangerous"
}

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  use_count: number;
}

export interface MemoryStats {
  episodic_count: number;
  semantic_count: number;
}

export interface HealthInfo {
  status: string;
  sessions: number;
}

export interface HistoryMessage {
  role: string;   // "user" | "assistant"
  text: string;
}

export interface MarketItem {
  id: string;
  name: string;
  description: string;
  icon: string;
  installed: boolean;
  env?: Record<string, string>;   // 仅 MCP：需要填写的环境变量键
  needs_restart?: boolean;        // 仅 MCP：变更需重启后端生效
}

export interface MarketResult {
  ok: boolean;
  message?: string;
  error?: string;
}

export interface KeyInfo {
  var: string;
  name: string;
  desc: string;
  configured: boolean;
  masked: string;
}

export interface MemoryFact {
  content: string;
  category: string;
  updated_at: number;
}

class ApiClient {
  private async _get<T>(path: string): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8_000);
    try {
      const res = await fetch(`${API_BASE}${path}`, { signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
      return res.json() as Promise<T>;
    } finally {
      clearTimeout(timer);
    }
  }

  private async _post<T>(path: string, body: unknown): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8_000);
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
      return res.json() as Promise<T>;
    } finally {
      clearTimeout(timer);
    }
  }

  async health(): Promise<HealthInfo> {
    return this._get<HealthInfo>('/api/health');
  }

  async memoryStats(): Promise<MemoryStats> {
    return this._get<MemoryStats>('/api/memory/stats');
  }

  async listTools(): Promise<ToolInfo[]> {
    const data = await this._get<{ tools: ToolInfo[] }>('/api/tools');
    return data.tools ?? [];
  }

  async listSkills(): Promise<SkillInfo[]> {
    const data = await this._get<{ skills: SkillInfo[] }>('/api/skills');
    return data.skills ?? [];
  }

  /** 拉取会话持久化历史（刷新后重建日志用） */
  async history(sessionId: string): Promise<HistoryMessage[]> {
    try {
      const data = await this._get<{ ok: boolean; messages: HistoryMessage[] }>(
        `/api/history?session_id=${encodeURIComponent(sessionId)}`,
      );
      return data.ok ? (data.messages ?? []) : [];
    } catch {
      return [];
    }
  }

  // ─── 市场 ─────────────────────────────────────────────

  /** MCP 服务器列表（installed 以 mcp.yaml 为准） */
  async marketMcp(): Promise<MarketItem[]> {
    const data = await this._get<{ items: MarketItem[] }>('/api/market/mcp');
    return data.items ?? [];
  }

  /** 技能包列表（installed 以 SkillStore 为准） */
  async marketSkills(): Promise<MarketItem[]> {
    const data = await this._get<{ items: MarketItem[] }>('/api/market/skills');
    return data.items ?? [];
  }

  /** 安装 MCP（可带 env 值）或技能 */
  async marketInstall(
    type: 'mcp' | 'skill',
    id: string,
    env?: Record<string, string>,
  ): Promise<MarketResult> {
    return this._post<MarketResult>('/api/market/install', {
      type, id, ...(env ? { env } : {}),
    });
  }

  /** 卸载 MCP 或技能 */
  async marketUninstall(type: 'mcp' | 'skill', id: string): Promise<MarketResult> {
    return this._post<MarketResult>('/api/market/uninstall', { type, id });
  }

  // ─── 设置 ─────────────────────────────────────────────

  /** API Key 列表（masked） */
  async settingsKeys(): Promise<KeyInfo[]> {
    const data = await this._get<{ keys: KeyInfo[] }>('/api/settings/keys');
    return data.keys ?? [];
  }

  /** 保存 API Key 到 .env（重启后端生效） */
  async saveKey(varName: string, key: string): Promise<MarketResult> {
    return this._post<MarketResult>('/api/settings/keys', { var: varName, key });
  }

  /** 最近 N 条语义记忆 */
  async memoryRecent(limit = 5): Promise<MemoryFact[]> {
    const data = await this._get<{ facts: MemoryFact[] }>(
      `/api/memory/recent?limit=${limit}`,
    );
    return data.facts ?? [];
  }
}

export const api = new ApiClient();

// ─── 数据映射 ─────────────────────────────────────────────

/** 把后端 memory stats + tools + skills 映射成 Xi 智能体卡片 */
export function mapXiAgent(stats: MemoryStats, tools: ToolInfo[], skills: SkillInfo[]): Agent {
  const episodicCap = 500;
  const semanticCap = 200;
  const en = Math.min(100, Math.round((stats.episodic_count / episodicCap) * 100));
  // 友好度：基于语义记忆丰富度
  const hearts = Math.min(10, Math.max(1, Math.ceil(stats.semantic_count / 20)));

  return {
    id: 'xi',
    name: 'Xi',
    role: '智能体',
    level: Math.max(1, Math.floor((stats.episodic_count + stats.semantic_count) / 50) + 1),
    state: 'active',
    en,
    hearts,
    emoji: '✦',
    currentTask: tools.length > 0 ? `${tools.length} 工具就绪` : '待命',
    totalTasks: stats.episodic_count,
  };
}

/** 把工具调用映射成任务公告板条目 */
let questCounter = 0;
export function toolCallToQuest(
  toolName: string,
  state: 'running' | 'done' | 'failed' = 'running',
  progress = 0,
  preview?: string,
): Quest {
  questCounter++;
  return {
    id: `q-tool-${Date.now()}-${questCounter}`,
    name: toolName,
    stars: 2,
    state,
    assignee: 'Xi',
    reward: '◆×1',
    progress,
  };
}
