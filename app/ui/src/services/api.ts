import axios from 'axios'

// In dev, Vite proxies /api -> VITE_API_URL. In production, the nginx container
// proxies /api -> BACKEND_URL. The app always calls the relative /api/v1 base.
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 90_000,
})

// Auth token helper — in production, read from secure storage
export const getAuthToken = (): string | null => {
  // Dev: read from localStorage or return a dev token
  const token = localStorage.getItem('rpg_auth_token')
  return token || null
}

export const setAuthToken = (token: string) => {
  localStorage.setItem('rpg_auth_token', token)
}

export const getApiErrorMessage = (error: unknown, fallback: string): string => {
  if (!axios.isAxiosError(error)) return fallback

  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item: { msg?: string }) => item.msg)
      .filter((message: unknown): message is string => typeof message === 'string')
      .join('; ') || fallback
  }
  return error.message || fallback
}

// Request interceptor — attach auth token
api.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export interface SessionResponse {
  session_id: string
  current_step: string
  step_status: string
  messages: { role: string; agent?: string; content: string }[]
  collected: Record<string, unknown>
}

export interface TenderEvent {
  id: string
  event_id: string
  tender_id: string
  project_name: string
  stage: string
  prior_stage: string | null
  source_type: string
  data_provenance: string
  existing_win_probability_percent: number | null
  probability_updated_at?: string | null
  material_categories: string[]
  region?: string | null
  tender_value?: number | null
  currency?: string | null
  opening_at?: string | null
  closing_at?: string | null
  source_updated_at: string | null
  ingested_at: string | null
  sender_entity_id: string
  tenant_id: string
  source_revision: string
}

export interface Subsidiary {
  id: string
  name: string
}

export interface ConnectorInfo {
  connector_id: string
  name: string
  source_type: string
  source_name: string
  description: string | null
  is_active: boolean
  is_enabled: boolean
  last_sync_at: string | null
  last_success_at: string | null
  last_error: string | null
  last_run: {
    status: string | null
    records_fetched: number
    records_created: number
    started_at: string | null
    errors: string[]
  } | null
}

export interface RoutingRule {
  id: number
  rule_id: string
  tenant_id: string
  name: string
  description: string | null
  enabled: boolean
  trigger_stages: string[]
  min_win_probability_percent: number | null
  purpose: string
  channel: string
  selected_recipient_email: string | null
  selected_recipient_emails: string[]
  regions: string[]
  tender_currency: string | null
  minimum_tender_value: number | null
  maximum_tender_value: number | null
  minimum_days_to_close: number | null
  maximum_days_to_close: number | null
  previewed_at: string | null
  max_event_age_seconds: number
  max_probability_age_seconds: number
  version: number
  created_at: string | null
  routes: Array<{
    id: number
    rule_id: string
    subsidiary_entity_id: string
    material_categories: string[]
  }>
}

export interface RecipientAddress {
  id: number
  email: string
  display_name: string | null
  created_at: string | null
}

export interface RecipientDecision {
  id: number
  event_id: string
  tenant_id: string
  subsidiary_entity_id: string
  recipient_user_id: string
  disposition: string
  reason: string
  payload: Record<string, any>
  decided_at: string | null
}

export interface NotificationDelivery {
  id: number
  event_id: string
  recipient_user_id: string
  channel: string
  status: string
  message_id: string | null
  payload: Record<string, any>
  sent_at: string | null
  delivered_at: string | null
  error_message: string | null
  retry_count: number
  created_at: string | null
}

export interface DeliveryStats {
  total: number
  pending: number
  sent: number
  delivered: number
  failed: number
  suppressed: number
}

export interface SyncResult {
  status: string
  steps: number
  connectors_run: number
  connector_ids: string[]
  total_fetched: number
  total_normalized: number
  total_created: number
  errors: string[]
  connector_results: Record<string, any>
  routing?: {
    status: string
    events_evaluated?: number
    deliveries_sent?: number
    deliveries_failed?: number
    deliveries_retried?: number
    error?: string
  }
}

export const checkHealth = () => api.get<{ status: string }>('/health')

export const startSession = (message: string, context?: Record<string, unknown>) =>
  api.post<SessionResponse>('/example/start', { message, context })

export const resumeSession = (session_id: string, message: string) =>
  api.post<SessionResponse>('/example/resume', { session_id, message })

export const getSession = (session_id: string) =>
  api.get<SessionResponse>(`/example/${session_id}`)

// Data ingestion endpoints
export const listTenders = () => api.get<TenderEvent[]>('/data-ingestion/tenders')
export const listSubsidiaries = () => api.get<Subsidiary[]>('/data-ingestion/subsidiaries')
export const listSubsidiaryTenders = (subsidiaryId: string) =>
  api.get<TenderEvent[]>(`/data-ingestion/subsidiaries/${encodeURIComponent(subsidiaryId)}/tenders`)
export const addSubsidiaryTender = (
  subsidiaryId: string,
  data: Omit<TenderInput, 'event_id'>,
) => api.post<TenderEvent>(
  `/data-ingestion/subsidiaries/${encodeURIComponent(subsidiaryId)}/tenders`,
  data,
)

export interface TenderInput {
  event_id?: string
  tender_id: string
  project_name: string
  stage: string
  material_categories: string[]
  region?: string | null
  tender_value?: number | null
  currency?: string | null
  opening_at?: string | null
  closing_at?: string | null
}

export interface TenderFollowUp {
  event_id: string
  tender_id: string
  project_name: string
  closing_at: string | null
  assigned_to: string | null
  status: string
  notes: string
  follow_up_at: string | null
  is_due: boolean
}

export interface PursuitAssessment {
  assessment_id: string
  event_id: string
  tenant_id: string
  recommendation: 'bid' | 'no_bid' | 'review'
  status: 'pending_review' | 'bid_approved' | 'no_bid_approved'
  report: {
    tender: TenderEvent
    recommendation: {
      recommendation: 'bid' | 'no_bid' | 'review'
      rationale: string
      next_steps: {
        task: string
        description?: string
        evidence?: Record<string, unknown>
        references?: { document: string; location: string }[]
      }[]
      requires_human_approval: boolean
      external_actions_taken: string[]
      agent_analysis?: string
    }
    qualification: {
      fit_score: number
      active_rule_matches: string[]
      missing_fields: string[]
      findings: string[]
      agent_analysis?: string
      method: string
    }
    documents: {
      documents_analyzed: number
      text_locations_reviewed: number
      findings: Record<string, { document: string; location: string; excerpt: string }[]>
      extracted_financial_amounts: { value: string; cost_type?: string; document: string; location: string; excerpt: string }[]
      extracted_tender_values?: { value: string; document: string; location: string; excerpt: string }[]
      extracted_deadlines: { value: string; document: string; location: string; excerpt: string }[]
      extracted_timeline?: { event: string; event_type?: string; value: string; document: string; location: string; excerpt: string }[]
      extracted_tender_periods?: { value: string; document: string; location: string; excerpt: string }[]
      prequalification_criteria?: {
        criterion_id: string
        excerpt: string
        summary: string
        summary_source?: 'model' | 'document_excerpt'
        references: { document: string; location: string; excerpt: string }[]
      }[]
      economics_summaries?: { summary: string; references?: { document: string; location: string }[] }[]
      processing_guidelines?: { category: string; summary: string; references?: { document: string; location: string }[] }[]
      explicit_disqualifier_evidence: { document: string; location: string; excerpt: string }[]
      limitations: string[]
      agent_analysis?: string
    }
    risk_review: {
      risks: {
        level: string
        risk: string
        document?: string
        location?: string
        excerpt?: string
        references?: { document: string; location: string; excerpt: string }[]
      }[]
      hard_stop: boolean
      limitations: string
      agent_analysis?: string
    }
    win_probability: {
      probability_percent: number
      model_version: string
      method: string
      training_snapshot_count: number
      training_tender_count: number
      training_wins: number
      training_losses: number
      dataset_label: string
      confidence: string
      features_used: { feature: string; value: string; direction: string }[]
      limitations: string
    } | null
    agent_trace: { agent: string; summary: string }[]
    tool_trace: { parent_agent: string; tool: string; summary: string }[]
    model?: { provider: string; model: string }
    trace_id?: string | null
    method: string
    human_approval_required: boolean
  }
  document_names: string[]
  decision: 'bid' | 'no_bid' | null
  decision_note: string | null
  decision_by: string | null
  decided_at: string | null
  created_by: string
  created_at: string | null
}

export const analyzePursuit = (eventId: string, files: File[]) => {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return api.post<PursuitAssessment>(
    `/pursuit/${encodeURIComponent(eventId)}/analyze`,
    form,
    { timeout: 300_000 },
  )
}
export const askTenderQuestion = (
  assessmentId: string,
  question: string,
  history: { role: 'user' | 'assistant'; content: string }[],
) => api.post<{
  answer: string
  sources: { document: string; location: string; excerpt: string }[]
}>(`/pursuit/assessment/${encodeURIComponent(assessmentId)}/chat`, { question, history })
export const listPursuitAssessments = (eventId: string) =>
  api.get<PursuitAssessment[]>(`/pursuit/${encodeURIComponent(eventId)}/assessments`)
export const recordPursuitDecision = (assessmentId: string, decision: 'bid' | 'no_bid', note: string) =>
  api.post<PursuitAssessment>(`/pursuit/assessment/${encodeURIComponent(assessmentId)}/decision`, { decision, note })

export const listManagedTenders = (params?: Record<string, string | number>) =>
  api.get<TenderEvent[]>('/tenders', { params })
export const createTender = (data: TenderInput) => api.post<TenderEvent>('/tenders', data)
export const updateTender = (eventId: string, data: TenderInput) => api.patch<TenderEvent>(`/tenders/${encodeURIComponent(eventId)}`, data)
export const previewTenderImport = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<{ headers: string[]; preview: Record<string, unknown>[]; row_count: number }>('/tenders/import/preview', form)
}
export const importTenders = (file: File, mapping: Record<string, string>) => {
  const form = new FormData()
  form.append('file', file)
  form.append('mapping_json', JSON.stringify(mapping))
  return api.post<{ imported: number; rejected_count: number; rejected_rows: { row: number; reason: string }[] }>('/tenders/import', form)
}
export const getTenderFeedback = (eventId: string) => api.get<{ feedback: string | null; reason: string | null }>(`/tenders/${encodeURIComponent(eventId)}/feedback`)
export const saveTenderFeedback = (eventId: string, feedback: string, reason: string) =>
  api.put(`/tenders/${encodeURIComponent(eventId)}/feedback`, { feedback, reason })
export const listFollowUps = (dueOnly = false) => api.get<TenderFollowUp[]>('/tenders/follow-ups', { params: { due_only: dueOnly } })
export const saveFollowUp = (eventId: string, payload: Omit<TenderFollowUp, 'event_id' | 'tender_id' | 'project_name' | 'closing_at' | 'is_due' | 'updated_at'>) =>
  api.put(`/tenders/${encodeURIComponent(eventId)}/follow-up`, payload)
export const feedbackSuggestions = () => api.get<{ counts: Record<string, number>; recommendations: string[]; automatic_rule_changes: boolean }>('/tenders/feedback/suggestions')
export const reportSummary = (params?: Record<string, string | number>) => api.get<Record<string, unknown>>('/tenders/reports/summary', { params })
export const exportTenderReport = (params?: Record<string, string | number>) =>
  api.get<Blob>('/tenders/reports/export.csv', { params, responseType: 'blob' })
export const previewRule = (ruleId: string) => api.post<{
  rule_id: string
  evaluated: number
  matches: number
  excluded: number
  exclusion_reasons: Record<string, number>
  samples: { event_id: string; tender_id: string; project_name: string; match: boolean; reason: string }[]
}>(`/tenders/rules/${encodeURIComponent(ruleId)}/preview`)
export const setRuleEnabled = (ruleId: string, enabled: boolean) =>
  api.patch<RoutingRule>(`/rules/${encodeURIComponent(ruleId)}/enabled`, { enabled })

export const syncData = () => api.post<SyncResult>('/data-ingestion/sync')

export const listConnectors = () => api.get<ConnectorInfo[]>('/data-ingestion/connectors')

export const syncConnector = (connectorId: string) =>
  api.post<{
    connector_id: string
    source_name: string
    records_fetched: number
    status: string
    errors: string[]
    routing?: SyncResult['routing']
  }>(
    `/data-ingestion/connectors/${connectorId}/sync`
  )

// Rules & policies
export const listRules = () => api.get<RoutingRule[]>('/rules')
export const deleteRule = (ruleId: string) =>
  api.delete<void>(`/rules/${encodeURIComponent(ruleId)}`)
export const listRecipients = () => api.get<RecipientAddress[]>('/recipients')
export const listDecisions = () => api.get<RecipientDecision[]>('/recipients/decisions')
export const createRecipient = (data: { email: string; display_name?: string }) =>
  api.post<RecipientAddress>('/recipients', data)
export const updateRecipient = (recipientId: number, data: { email: string; display_name?: string }) =>
  api.patch<RecipientAddress>(`/recipients/${recipientId}`, data)
export const deleteRecipient = (recipientId: number) =>
  api.delete<void>(`/recipients/${recipientId}`)

// Signal history & audit
export const listSignalHistory = () => api.get<TenderEvent[]>('/signal-history')
export const listAuditEvents = () => api.get<any[]>('/signal-history/audit')

// Delivery status
export const deliveryStats = () => api.get<DeliveryStats>('/delivery-status/stats')
export const listDeliveries = () => api.get<NotificationDelivery[]>('/delivery-status')
export const getEmailConfiguration = () => api.get<{ provider: string; configured: boolean; sender: string | null; secret_exposed: boolean }>('/delivery-status/configuration')
export const sendTestEmail = (recipient_email: string) => api.post('/delivery-status/test-email', { recipient_email })
export const retryDelivery = (deliveryId: number) => api.post(`/delivery-status/${deliveryId}/retry`)
export const deliveryAttempts = (deliveryId: number) => api.get(`/delivery-status/${deliveryId}/attempts`)

export default api

export const createRule = (data:any) => api.post('/rules', data)
