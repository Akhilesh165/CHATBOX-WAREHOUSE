export type ChartType = 'bar' | 'line' | 'pie' | 'none';
export type OutputType = 'kpi' | 'table' | 'line_chart' | 'bar_chart' | 'pie_chart' | 'list' | 'text' | 'kpi_summary_table';

export interface ChartMetadata {
  type: ChartType;
  title?: string;
  xAxis?: string;
  yAxis?: string;
  x_key?: string;
  y_key?: string;
  data: Array<Record<string, any>>;
}

export interface ResponseMeta {
  requestId?: string;
  rowCount: number;
  executionMs: number;
  llmMs?: number;
  sqlMs?: number;
}

export interface FollowUpAction {
  message: string;
  action: string;
  action_prompt: string;
  label?: string;
}

export interface RelevantKpi {
  label: string;
  value: string | number;
  subtext?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sql?: string | null;
  data?: Array<Record<string, any>>;
  rows?: Array<Record<string, any>>;
  chart?: ChartMetadata;
  meta?: ResponseMeta;
  rowCount?: number;
  executionMs?: number;
  llmMs?: number;
  sqlMs?: number;
  warnings?: string[];
  intent?: string;
  output_type?: OutputType;
  metric?: string;
  filters?: Record<string, any>;
  time_range?: string;
  follow_up_action?: FollowUpAction;
  relevant_kpis?: RelevantKpi[];
  timestamp: Date;
}

export interface ChatRequestPayload {
  message: string;
  conversation_id?: string;
  is_admin?: boolean;
}

export interface ChatResponsePayload {
  answer: string;
  data?: Array<Record<string, any>>;
  rows?: Array<Record<string, any>>;
  chart: ChartMetadata;
  meta?: ResponseMeta;
  sql?: string | null;
  warnings?: string[];
  intent?: string;
  output_type?: OutputType;
  metric?: string;
  filters?: Record<string, any>;
  time_range?: string;
  row_count?: number;
  execution_ms?: number;
  llm_ms?: number;
  sql_ms?: number;
  follow_up_action?: FollowUpAction;
  relevant_kpis?: RelevantKpi[];
}

