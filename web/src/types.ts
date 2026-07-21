/**
 * Agent Xi 控制台 — 数据模型
 */

/** 智能体状态 */
export type AgentState = 'active' | 'running' | 'idle' | 'error';

/** 智能体（冒险者） */
export interface Agent {
  id: string;
  name: string;            // 显示名（如 "艾芙"）
  role: string;            // 职业（如 "协调者"）
  level: number;           // 等级
  state: AgentState;
  en: number;              // 能量值 0~100
  hearts: number;          // 友好度 0~10
  avatar?: string;         // 头像 URL（可选）
  emoji?: string;          // 头像 emoji 占位
  currentTask?: string;    // 当前任务
  totalTasks?: number;     // 累计任务数
}

/** 附件元信息（上传完成后随 WS chat 消息上报） */
export interface AttachmentMeta {
  file_id: string;
  name: string;
  size: number;
  mime: string;
  url?: string;            // 本地 object URL，仅日志预览用，不发送后端
}

/** 日志类型 */
export type LogType = 'system' | 'info' | 'warn' | 'error' | 'tool' | 'chat';

/** 日志条目 */
export interface LogEntry {
  id: string;
  time: string;            // HH:MM 格式
  type: LogType;
  source?: string;         // 来源智能体名（如 "艾芙"）
  text: string;
  attachments?: AttachmentMeta[];  // 用户消息附带的附件
}

/** 任务状态 */
export type QuestState = 'running' | 'pending' | 'done' | 'failed';

/** 任务（公告板） */
export interface Quest {
  id: string;
  name: string;
  stars: number;           // 1~5
  state: QuestState;
  assignee: string;        // 负责人名
  reward: string;          // 奖励 emoji+数量
  progress: number;        // 0~100
}

/** 状态徽章计数 */
export interface StatusCounts {
  online: number;
  idle: number;
  error: number;
}
