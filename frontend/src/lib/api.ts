import {
  BudgetGuardStatus,
  ChapterSummary,
  ChatSession,
  Citation,
  DocumentItem,
  IngestionStatusDetail,
  MarginDashboardData,
  Message,
  ModelStatus,
  PlanItem,
  QuotaRemaining,
  StudentProfile,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

function getHeaders(profile?: StudentProfile | null): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (profile) {
    headers["X-User-Id"] = profile.id;
    headers["X-Semester"] = profile.semester.toString();
    headers["X-Department"] = profile.department;
  }
  return headers;
}

// ─────────────────────────────────────────────────────────────
// Stream /ask with SSE
// ─────────────────────────────────────────────────────────────

export interface StreamCallbacks {
  onFilter?: (data: {
    subject: string | null;
    chapter_no: number | null;
    unit_no: number | null;
    clean_query: string;
  }) => void;
  onRoute?: (route: string) => void;
  onToken?: (token: string) => void;
  onQueue?: (position: number, estimatedSeconds?: number) => void;
  onCitations?: (citations: Citation[]) => void;
  onDone?: (data: {
    quota?: QuotaRemaining;
    units_charged?: number;
    detected_detailed?: boolean;
    thinking_mode?: boolean;
    thinking_reason?: string;
    thinking_left_today?: number;
    hint?: "try_thinking" | "upgrade_for_thinking";
  }) => void;
  onError?: (error: string) => void;
}

export async function askQuestionStream(
  question: string,
  profile: StudentProfile,
  options: {
    sessionId?: string;
    detailed?: boolean;
    thinking?: boolean;
  },
  callbacks: StreamCallbacks,
  abortSignal?: AbortSignal
): Promise<void> {
  const headers = getHeaders(profile);

  const response = await fetch(`${BASE_URL}/ask`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      question,
      session_id: options.sessionId,
      detailed: options.detailed ?? false,
      thinking: options.thinking ?? false,
    }),
    signal: abortSignal,
  });

  if (!response.ok) {
    let errorDetail = `Request failed (${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorDetail = err.detail;
    } catch {}
    callbacks.onError?.(errorDetail);
    return;
  }

  if (!response.body) {
    callbacks.onError?.("No response body received from server");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    let currentEvent = "message";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.replace(/^event:\s*/, "").trim();
      } else if (line.startsWith("data:")) {
        const rawData = line.replace(/^data:\s*/, "").trim();
        if (!rawData) continue;

        try {
          const parsed = JSON.parse(rawData);

          switch (currentEvent) {
            case "filter":
              callbacks.onFilter?.(parsed);
              break;
            case "route":
              callbacks.onRoute?.(parsed.route);
              break;
            case "token":
              if (parsed.text) callbacks.onToken?.(parsed.text);
              break;
            case "queue":
              callbacks.onQueue?.(parsed.position, parsed.estimated_seconds);
              break;
            case "citations":
              if (parsed.citations) callbacks.onCitations?.(parsed.citations);
              break;
            case "quota":
              callbacks.onDone?.({ quota: parsed });
              break;
            case "done":
              callbacks.onDone?.(parsed);
              break;
            case "error":
              callbacks.onError?.(parsed.error || "An error occurred");
              break;
          }
        } catch (e) {
          console.warn("Failed to parse SSE JSON:", rawData, e);
        }
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────
// Quota & Usage
// ─────────────────────────────────────────────────────────────

export async function fetchQuotaRemaining(
  profile: StudentProfile
): Promise<QuotaRemaining> {
  const res = await fetch(`${BASE_URL}/quota/remaining`, {
    headers: getHeaders(profile),
  });
  if (!res.ok) throw new Error("Failed to fetch quota");
  return res.json();
}

export async function fetchUsageHistory(
  profile: StudentProfile,
  days = 7
): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/quota/usage?days=${days}`, {
    headers: getHeaders(profile),
  });
  if (!res.ok) throw new Error("Failed to fetch usage history");
  return res.json();
}

// ─────────────────────────────────────────────────────────────
// Chat Sessions
// ─────────────────────────────────────────────────────────────

export async function createChatSession(
  profile: StudentProfile,
  title?: string,
  subject?: string
): Promise<ChatSession> {
  const res = await fetch(`${BASE_URL}/chat/sessions`, {
    method: "POST",
    headers: getHeaders(profile),
    body: JSON.stringify({ title, subject }),
  });
  if (!res.ok) throw new Error("Failed to create chat session");
  return res.json();
}

export async function listChatSessions(
  profile: StudentProfile
): Promise<{ total: number; sessions: ChatSession[] }> {
  const res = await fetch(`${BASE_URL}/chat/sessions`, {
    headers: getHeaders(profile),
  });
  if (!res.ok) throw new Error("Failed to list chat sessions");
  return res.json();
}

export async function getSessionMessages(
  sessionId: string,
  profile: StudentProfile
): Promise<{ messages: Message[] }> {
  const res = await fetch(`${BASE_URL}/chat/sessions/${sessionId}/messages`, {
    headers: getHeaders(profile),
  });
  if (!res.ok) throw new Error("Failed to fetch session messages");
  return res.json();
}

export async function addSessionMessage(
  sessionId: string,
  message: {
    role: "user" | "assistant";
    content: string;
    citations?: Citation[];
    model_used?: string | null;
    tokens_used?: number | null;
  },
  profile: StudentProfile
): Promise<void> {
  await fetch(`${BASE_URL}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: getHeaders(profile),
    body: JSON.stringify(message),
  });
}

export async function deleteChatSession(
  sessionId: string,
  profile: StudentProfile
): Promise<void> {
  await fetch(`${BASE_URL}/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: getHeaders(profile),
  });
}

// ─────────────────────────────────────────────────────────────
// Admin: Documents & Ingestion
// ─────────────────────────────────────────────────────────────

export async function uploadDocument(
  file: File,
  metadata: {
    department: string;
    semester: number;
    subject: string;
    academic_year: string;
    doc_type: string;
    is_active?: boolean;
  },
  profile?: StudentProfile
): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("department", metadata.department);
  formData.append("semester", metadata.semester.toString());
  formData.append("subject", metadata.subject);
  formData.append("academic_year", metadata.academic_year);
  formData.append("doc_type", metadata.doc_type);
  formData.append("is_active", (metadata.is_active ?? true).toString());

  const headers: Record<string, string> = {};
  if (profile) headers["X-User-Id"] = profile.id;

  const res = await fetch(`${BASE_URL}/admin/documents/upload`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload document");
  }
  return res.json();
}

export async function listDocuments(filters?: {
  department?: string;
  semester?: number;
  subject?: string;
}): Promise<DocumentItem[]> {
  const params = new URLSearchParams();
  if (filters?.department) params.append("department", filters.department);
  if (filters?.semester) params.append("semester", filters.semester.toString());
  if (filters?.subject) params.append("subject", filters.subject);

  const res = await fetch(`${BASE_URL}/admin/documents?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to list documents");
  return res.json();
}

export async function getDocumentStatus(
  docId: string
): Promise<IngestionStatusDetail> {
  const res = await fetch(`${BASE_URL}/admin/documents/${docId}/status`);
  if (!res.ok) throw new Error("Failed to get ingestion status");
  return res.json();
}

export async function getDocumentSummaries(
  docId: string
): Promise<ChapterSummary[]> {
  const res = await fetch(`${BASE_URL}/admin/documents/${docId}/summaries`);
  if (!res.ok) throw new Error("Failed to get chapter summaries");
  return res.json();
}

export async function toggleDocumentActive(
  docId: string,
  isActive: boolean
): Promise<void> {
  const res = await fetch(
    `${BASE_URL}/admin/documents/${docId}/active?is_active=${isActive}`,
    {
      method: "PATCH",
    }
  );
  if (!res.ok) throw new Error("Failed to toggle document active status");
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/admin/documents/${docId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete document");
}

export async function reingestDocument(docId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/admin/documents/${docId}/reingest`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger re-ingestion");
}

// ─────────────────────────────────────────────────────────────
// Admin: Models & Runtime Status
// ─────────────────────────────────────────────────────────────

export async function fetchAllModelStatus(): Promise<ModelStatus[]> {
  const res = await fetch(`${BASE_URL}/admin/models/status`);
  if (!res.ok) throw new Error("Failed to fetch model status");
  return res.json();
}

export async function toggleModel(
  modelId: string,
  enabled?: boolean
): Promise<{ model_id: string; is_enabled: boolean }> {
  const res = await fetch(
    `${BASE_URL}/admin/models/${encodeURIComponent(modelId)}/toggle`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(enabled !== undefined ? { enabled } : {}),
    }
  );
  if (!res.ok) throw new Error("Failed to toggle model");
  return res.json();
}

export async function clearModelCooldown(
  modelId: string
): Promise<{ model_id: string; cooldown_cleared: boolean }> {
  const res = await fetch(
    `${BASE_URL}/admin/models/${encodeURIComponent(modelId)}/clear-cooldown`,
    {
      method: "POST",
    }
  );
  if (!res.ok) throw new Error("Failed to clear cooldown");
  return res.json();
}

export async function reverifyModels(): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/admin/models/reverify`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to re-verify models");
  return res.json();
}

// ─────────────────────────────────────────────────────────────
// Admin: Settings, Balance, Margin
// ─────────────────────────────────────────────────────────────

export async function fetchMarginDashboard(): Promise<MarginDashboardData> {
  const res = await fetch(`${BASE_URL}/admin/margin`);
  if (!res.ok) throw new Error("Failed to fetch margin dashboard");
  return res.json();
}

export async function fetchAccountBalance(): Promise<{
  account_balance_usd: number;
}> {
  const res = await fetch(`${BASE_URL}/admin/settings/balance`);
  if (!res.ok) throw new Error("Failed to fetch balance");
  return res.json();
}

export async function updateAccountBalance(
  amount: number,
  adminId?: string
): Promise<{ account_balance_usd: number }> {
  const res = await fetch(`${BASE_URL}/admin/settings/balance?amount=${amount}`, {
    method: "POST",
    headers: { "X-User-Id": adminId || "admin" },
  });
  if (!res.ok) throw new Error("Failed to update balance");
  return res.json();
}

export async function togglePremiumSetting(
  enabled: boolean,
  adminId?: string
): Promise<{ premium_enabled: boolean }> {
  const res = await fetch(
    `${BASE_URL}/admin/settings/premium-toggle?enabled=${enabled}`,
    {
      method: "POST",
      headers: { "X-User-Id": adminId || "admin" },
    }
  );
  if (!res.ok) throw new Error("Failed to toggle premium setting");
  return res.json();
}

export async function fetchModelPrices(): Promise<{ prices: Record<string, any> }> {
  const res = await fetch(`${BASE_URL}/admin/settings/model-prices`);
  if (!res.ok) throw new Error("Failed to fetch model prices");
  return res.json();
}

export async function updateModelPrices(
  prices: Record<string, { input: number; output: number }>,
  adminId?: string
): Promise<any> {
  const res = await fetch(`${BASE_URL}/admin/settings/model-prices`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": adminId || "admin",
    },
    body: JSON.stringify(prices),
  });
  if (!res.ok) throw new Error("Failed to update model prices");
  return res.json();
}

export async function fetchBudgetGuardStatus(): Promise<BudgetGuardStatus> {
  const res = await fetch(`${BASE_URL}/admin/budget-guard`);
  if (!res.ok) throw new Error("Failed to fetch budget guard");
  return res.json();
}

export async function updateBudgetGuard(
  settings: Partial<BudgetGuardStatus>,
  adminId?: string
): Promise<any> {
  const params = new URLSearchParams();
  if (settings.is_active !== undefined)
    params.append("is_enabled", settings.is_active.toString());
  if (settings.manual_retrieval_only !== undefined)
    params.append("manual_retrieval_only", settings.manual_retrieval_only.toString());
  if (settings.threshold_pct !== undefined)
    params.append("threshold_pct", settings.threshold_pct.toString());
  if (settings.monthly_spend_cap_usd !== undefined)
    params.append("monthly_spend_cap_usd", settings.monthly_spend_cap_usd.toString());

  const res = await fetch(`${BASE_URL}/admin/budget-guard?${params.toString()}`, {
    method: "POST",
    headers: { "X-User-Id": adminId || "admin" },
  });
  if (!res.ok) throw new Error("Failed to update budget guard");
  return res.json();
}

// ─────────────────────────────────────────────────────────────
// Plans & Payments
// ─────────────────────────────────────────────────────────────

export async function fetchPlans(): Promise<PlanItem[]> {
  const res = await fetch(`${BASE_URL}/plans`);
  if (!res.ok) throw new Error("Failed to fetch plans");
  return res.json();
}

export async function grantPlanManual(
  userIds: string[],
  planName: string,
  durationDays = 30
): Promise<any> {
  const res = await fetch(`${BASE_URL}/admin/plans/grant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_ids: userIds,
      plan_name: planName,
      duration_days: durationDays,
    }),
  });
  if (!res.ok) throw new Error("Failed to grant plan");
  return res.json();
}

export async function createPaymentOrder(
  planName: string,
  profile: StudentProfile
): Promise<{
  order_id: string;
  amount_paise: number;
  currency: string;
  key_id: string;
  plan_name: string;
  plan_display_name: string;
}> {
  const res = await fetch(`${BASE_URL}/payments/create-order`, {
    method: "POST",
    headers: getHeaders(profile),
    body: JSON.stringify({ plan_name: planName }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create payment order");
  }
  return res.json();
}

export async function verifyPayment(payload: {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}): Promise<any> {
  const res = await fetch(`${BASE_URL}/payments/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to verify payment");
  return res.json();
}
