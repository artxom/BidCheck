export type CategoryType =
  | 'qualification'
  | 'commercial_scoring'
  | 'technical_scoring'
  | 'procurement_req'
  | 'format_redline';

export const CATEGORY_LABELS: Record<CategoryType, string> = {
  qualification: '资格审查',
  commercial_scoring: '商务资信',
  technical_scoring: '技术方案',
  procurement_req: '采购需求',
  format_redline: '形式红线',
};

export interface ProviderConfig {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  currency: string;
  enabled: boolean;
}

export interface RoleRouteConfig {
  role: 'master' | 'text_worker' | 'vision_worker' | 'report_assembler';
  provider_id: string;
  model: string;
  concurrency: number;
  input_price_per_m: number;
  output_price_per_m: number;
  enabled: boolean;
}

export interface AppSettings {
  providers: ProviderConfig[];
  routes: Record<string, RoleRouteConfig>;
}

export interface SuggestedModel {
  id: string;
  label: string;
  vision: boolean;
  input_price: number;
  output_price: number;
}

export interface RemoteModelInfo {
  id: string;
  vision: boolean;
  input_price: number | null;
  output_price: number | null;
  price_source: 'api' | 'catalog' | 'manual';
}

export interface ProviderPreset {
  id: string;
  name: string;
  base_url: string;
  suggested_models: SuggestedModel[];
  currency: string;
}

export interface RoleDefinition {
  role: string;
  label: string;
  desc: string;
  default_concurrency: number;
}

export interface MatchedSectionRef {
  section_id: string;
  breadcrumb: string;
  page_label: string;
}

export interface ChecklistItem {
  item_id: string;
  order_index: number;
  category: CategoryType;
  title: string;
  requirement_text: string;
  tender_source: string;
  risk_level: 'fatal' | 'score_loss' | 'minor';
  requires_vision: boolean;
  search_keywords: string[];
  enabled: boolean;
  run_status: 'pending' | 'running' | 'completed' | 'skipped' | 'failed';
  compliance_status: 'unchecked' | 'passed' | 'partial' | 'missing';
  matched_sections: MatchedSectionRef[];
  evidence_excerpt: string;
  media_ids: string[];
  vision_verified: boolean;
  vision_note: string;
  conclusion: string;
  remediation: string;
  checked_by_model: string;
  duration_ms: number;
}

export interface ActiveModelStat {
  role: string;
  role_label: string;
  model: string;
  active_calls: number;
  total_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: number;
}

export interface TelemetrySnapshot {
  project_id: string;
  stage:
    | 'idle'
    | 'parsing'
    | 'planning'
    | 'awaiting_confirm'
    | 'inspecting'
    | 'assembling_report'
    | 'completed'
    | 'error';
  stage_label: string;
  completed_items: number;
  total_items: number;
  progress_pct: number;
  eta_seconds: number | null;
  elapsed_seconds: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  currency: string;
  estimated_plan_tokens: number;
  estimated_plan_cost: number;
  estimated_plan_seconds: number;
  active_models: ActiveModelStat[];
}

export interface DeterministicFinding {
  finding_id: string;
  rule_type: string;
  severity: 'fatal' | 'warning' | 'info';
  title: string;
  detail: string;
  section_id: string;
  breadcrumb: string;
  page_hint: string;
  snippet: string;
}

export interface CategoryStat {
  category: string;
  label: string;
  total: number;
  passed: number;
  partial: number;
  missing: number;
}

export interface InspectionReport {
  generated_at: string;
  project_name: string;
  target_lot: string;
  overall_verdict: 'ready' | 'needs_fix' | 'high_risk';
  verdict_label: string;
  readiness_score: number;
  executive_summary: string;
  key_risks: string[];
  priority_actions: string[];
  total_items: number;
  passed_count: number;
  partial_count: number;
  missing_count: number;
  fatal_issue_count: number;
  score_issue_count: number;
  minor_issue_count: number;
  category_stats: CategoryStat[];
  deterministic_findings: DeterministicFinding[];
}

export interface DocumentSummary {
  doc_id: string;
  filename: string;
  file_type: string;
  doc_role: 'tender' | 'response';
  file_size_bytes: number;
  total_pages: number;
  total_chars: number;
  total_tables: number;
  total_images: number;
  detected_lots: string[];
  metadata: Record<string, unknown>;
  deterministic_count: number;
}

export interface ChatMessage {
  id: string;
  project_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  msg_type: 'text' | 'precheck_card' | 'plan_card' | 'report_ready' | 'error';
  meta: Record<string, unknown>;
  created_at: string;
}

export interface ProjectDetail {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  stage: string;
  target_lot: string;
  tender_doc: DocumentSummary | null;
  response_doc: DocumentSummary | null;
  telemetry: TelemetrySnapshot;
  checklist: ChecklistItem[];
  report: InspectionReport | null;
  messages: ChatMessage[];
}

export interface ProjectListItem {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  stage: string;
  target_lot: string;
  has_tender: boolean;
  has_response: boolean;
  progress_pct: number;
  total_tokens: number;
}

export interface WorkspaceSample {
  filename: string;
  size_mb: number;
  guessed_role: 'tender' | 'response';
}

export interface SectionDetail {
  section_id: string;
  level: number;
  title: string;
  breadcrumb: string;
  page_label: string;
  paragraphs: string[];
  tables: {
    table_id: string;
    row_count: number;
    col_count: number;
    headers: string[];
    rows: string[][];
    media_ids: string[];
  }[];
  media_ids: string[];
  deterministic_findings: DeterministicFinding[];
}

export interface OutlineSectionLite {
  section_id: string;
  level: number;
  title: string;
  breadcrumb: string;
  page_label: string;
  char_count: number;
  table_count: number;
  image_count: number;
}

export interface OfflineReportSnapshot {
  format: 'bidguard-static-report-v1';
  exported_at: string;
  app_version: string;
  project: ProjectDetail;
  outline: OutlineSectionLite[];
  deterministic_findings: DeterministicFinding[];
  sections: Record<string, SectionDetail>;
  media_map: Record<string, string>;
  media_blobs: Record<string, string>;
}
