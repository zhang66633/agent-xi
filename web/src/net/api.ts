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

class ApiClient {
  private async _get<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    return res.json() as Promise<T>;
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
    reward: '💎×1',
    progress,
  };
}
