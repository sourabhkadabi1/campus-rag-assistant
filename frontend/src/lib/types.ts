export type UserRole = "student" | "admin";

export interface StudentProfile {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string;
  semester: number;
  roll_no: string;
  plan_name: "free" | "paid";
  is_paid: boolean;
  plan_expires_at?: string | null;
}

export interface QuotaRemaining {
  requests_remaining: number;
  tokens_remaining: number;
  requests_limit: number;
  tokens_limit: number;
  requests_used: number;
  tokens_used: number;
  cache_hits: number;
  plan_name: string;
  is_paid: boolean;
  thinking_credits_remaining: number;
  thinking_credits_limit: number;
  thinking_credits_used: number;
  units_used?: number;
  thinking_left_today?: number;
}

export interface Citation {
  subject: string;
  doc_type: string;
  chapter_no: number | null;
  chapter_title: string | null;
  unit_no?: number | null;
  page_start: number | null;
  page_end: number | null;
  document_id: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  model_used?: string | null;
  tokens_used?: number | null;
  created_at?: string;
  isStreaming?: boolean;
  detected_detailed?: boolean;
  thinking_mode?: boolean;
  thinking_reason?: string;
  hint?: "try_thinking" | "upgrade_for_thinking";
  route?: "cache" | "summary" | "syllabus" | "llm" | "retrieval_only";
}

export interface ChatSession {
  id: string;
  title: string | null;
  subject: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  original_filename: string;
  department: string;
  semester: number;
  subject: string;
  academic_year: string;
  doc_type: "syllabus" | "book" | "notes" | "previous_paper" | "slides_pdf";
  unit_no?: number | null;
  is_active: boolean;
  file_size_bytes: number;
  total_pages: number | null;
  ingestion_status: "queued" | "processing" | "done" | "failed";
  ingestion_error: string | null;
  created_at: string;
}

export interface IngestionStatusDetail {
  document_id: string;
  status: string;
  total_pages: number | null;
  chunks_created: number;
  chapters_found: number;
  summaries_generated: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ChapterSummary {
  chapter_no: number;
  chapter_title: string | null;
  summary: string;
  key_concepts: string[] | null;
  model_used: string;
}

export interface ModelStatus {
  model_id: string;
  provider: string;
  is_verified: boolean;
  closest_match?: string | null;
  error_message?: string | null;
  verified_at?: string | null;
  is_enabled: boolean;
  is_available: boolean;
  status_reason: string;
  cooldown_remaining_seconds: number;
  rpm_used: number;
  rpm_limit: number;
  tpm_used: number;
  tpm_limit: number;
  rpd_used: number;
  rpd_limit: number;
  tokens_today: number;
  is_summary_model: boolean;
  reserve_rpd: number;
  reset_timezone: string;
}

export interface MarginDashboardData {
  today_spend_usd: number;
  seven_day_spend_usd: number;
  remaining_balance_usd: number;
  estimated_days_left: number;
  premium_spend_today_usd: number;
  premium_daily_cap_usd: number;
  thinking_requests_today: number;
  cache_hit_rate: number;
  detailed_share: number;
  avg_cost_per_profile: Record<string, number>;
  avg_cost_per_paid_user_month: number;
  plan_price_monthly_usd: number;
  margin_alert: boolean;
  margin_alert_message: string | null;
}

export interface PlanItem {
  id: string;
  name: string;
  display_name: string;
  requests_per_day: number;
  tokens_per_day: number;
  features: Record<string, any>;
  is_default: boolean;
  price_paise_monthly?: number;
  price_paise_semester?: number;
  thinking_credits_per_day?: number;
}

export interface BudgetGuardStatus {
  is_active: boolean;
  capacity_used_pct: number;
  threshold_pct: number;
  free_users_affected: boolean;
  manual_retrieval_only: boolean;
  monthly_spend_cap_usd: number;
}

// ── Stage 7: Practice & Quiz ─────────────────────────────────────

export interface PracticeCitation {
  document_id?: string | null;
  doc_type?: string | null;
  chapter_no?: number | null;
  chapter_title?: string | null;
  unit_no?: number | null;
  page_start?: number | null;
  page_end?: number | null;
}

export interface PracticeQuestion {
  id: string;
  type: "mcq" | "descriptive";
  question: string;
  options?: string[] | null;
  correct_option_index?: number | null;
  model_answer: string;
  key_points?: string[] | null;
  citation?: PracticeCitation | null;
}

export interface PracticeSet {
  id: string;
  subject: string;
  semester: number;
  department: string;
  academic_year: string;
  topic?: string | null;
  unit_no?: number | null;
  chapter_no?: number | null;
  question_type: "mcq" | "descriptive" | "mixed";
  difficulty: "easy" | "medium" | "hard";
  questions: PracticeQuestion[];
  units_charged: number;
  created_at: string;
}

export interface PracticeSubmitFeedback {
  question_id: string;
  type: "mcq" | "descriptive";
  question: string;
  selected_option_index?: number | null;
  correct_option_index?: number | null;
  is_correct?: boolean;
  model_answer?: string;
  key_points?: string[];
  citation?: PracticeCitation | null;
}

export interface PracticeSubmitResponse {
  submission_id: string;
  practice_set_id: string;
  score: number;
  total: number;
  percentage: number;
  feedback: PracticeSubmitFeedback[];
}

export interface PracticeGenerateParams {
  subject: string;
  topic?: string;
  chapter_no?: number;
  unit_no?: number;
  question_type?: "mcq" | "descriptive" | "mixed";
  difficulty?: "easy" | "medium" | "hard";
  count?: number;
}

