export interface Page<T> { items: T[]; total: number }

export interface Order {
  id: string; order_number: number; customer_id: string; customer_name: string; customer_email?: string;
  status: string; currency: string; total_amount: string; is_sample: boolean; placed_at: string; delivered_at: string | null;
  item_count: number; items_summary: string; payment_status: string | null; payment_id: string | null; shipment_status: string | null;
  items?: { id: string; product_id: string; product_name: string; sku: string; quantity: number; unit_price: string; category?: string }[];
  customer?: Customer; executions?: Execution[]; decisions?: Decision[]; notes?: string | null;
  payments?: Payment[]; shipments?: Shipment[]; refunds?: Refund[]; tickets?: Ticket[];
}
export interface Shipment { id: string; carrier: string; tracking_number: string; status: string; estimated_delivery: string | null; delivered_at: string | null; last_event: string | null }
export interface Payment {
  id: string; order_id: string; order_number: number; customer_id: string; customer_name: string; attempt: number; source: string; is_sample: boolean;
  method: string; status: string; amount: string; refunded_amount: string; refundable_amount: string; currency: string;
  paypal_order_id: string | null; paypal_capture_id: string | null; approve_url: string | null; payer_email: string | null; failure_reason: string | null;
  captured_at: string | null; created_at: string; paypal_transactions?: PayPalTx[]; refunds?: Refund[];
}
export interface PayPalTx { id: string; operation: string; request_id: string | null; http_status: number | null; paypal_debug_id: string | null; resource_id: string | null; resource_status: string | null; outcome: string; error_message: string | null; duration_ms: number | null; created_at: string }
export interface Refund {
  id: string; payment_id: string; order_id: string; order_number: number; customer_id: string; customer_name: string; ticket_id: string | null;
  capture_id: string | null; amount: string; currency: string; reason: string; status: string; is_sample: boolean; paypal_refund_id: string | null;
  paypal_status: string | null; paypal_status_reason: string | null; failure_reason: string | null; policy_decision_id: string | null;
  execution_action_id: string | null; executed_at: string | null; completed_at: string | null; created_at: string;
  policy_outcome?: string; approval_status?: string; approval_id?: string;
  decision?: Decision; action?: NonNullable<Approval['action']> & { error_code?: string | null; attempts?: number }; approval?: Approval; paypal_transactions?: PayPalTx[];
}
export interface Ticket {
  id: string; ticket_number: number; customer_id: string; customer_name: string; order_id: string | null; subject: string; description: string;
  status: string; priority: string; category: string; ai_classification_confidence: number | null; assigned_to: string | null; assigned_to_user_id: string | null;
  resolved_by: string | null; resolution_summary: string | null; satisfaction_score: number | null; is_sample: boolean; created_at: string; updated_at: string;
  resolved_at: string | null; reopened_count: number; events?: TicketEvent[]; messages?: ChatMessage[];
  customer?: Customer; order?: Order; executions?: Execution[]; refunds?: Refund[];
}
export interface TicketEvent { id: string; actor: string; event: string; detail: string | null; created_at: string }
export interface Customer { id: string; email: string; full_name: string; phone: string | null; city: string | null; segment: string | null; created_at: string; orders?: number; spent?: string; open_tickets?: number; refunds?: number }
export interface Citation { title: string; version: number; category: string; document_id: string; score: number; excerpt: string }
export interface ActionCard {
  kind: string; action_id?: string; action_state?: string; decision?: string | null; explanation?: string | null; refund_id?: string | null;
  refund_status?: string | null; paypal_refund_id?: string | null; paypal_status?: string | null; approval_id?: string | null; error?: string | null; duplicate?: boolean;
  [k: string]: unknown;
}
export interface ChatMessage {
  id: string; role: 'CUSTOMER' | 'USER' | 'ASSISTANT' | 'AGENT' | 'STAFF' | 'SYSTEM'; content: string; created_at: string; agent_execution_id?: string | null;
  meta?: { author?: string; citations?: Citation[]; actions?: ActionCard[]; intent?: string; ticket?: { ticket_id: string; ticket_number: number; status: string } | null; execution_id?: string; llm_mode?: string; resolution?: string };
}
export interface Approval {
  id: string; status: string; title: string; reason: string; proposed_by: string; risk_level: string;
  risk_summary: { level: string; score: number; signals: { code: string; detail: string; weight?: number }[] | string[]; recommended_next_step: string; requires_review: boolean };
  decided_by: string | null; decided_at: string | null; manager_note: string | null; final_result: Record<string, unknown>; is_sample: boolean; created_at: string;
  action?: { id: string; action_type: string; state: string; idempotency_key: string; payload: Record<string, string>; result?: Record<string, unknown>; history?: { from: string | null; to: string; at: string; actor: string; note?: string }[]; error_message?: string | null };
  decision?: Decision; current_check?: { refundable_amount: string; payment_status: string; risk: Approval['risk_summary']; paypal_capture: string | null; is_sample: boolean };
  current_policy_version?: number | null; agent_execution?: Execution | null; order?: Order; customer?: Customer; refund?: Refund; payment?: Payment; customer_refund_history?: Refund[];
}
export interface Decision {
  id: string; policy_id: string | null; policy_version: number | null; action_type: string; outcome: string; matched_rule_id: string | null;
  inputs: Record<string, unknown>; evaluated_conditions: { rule_id: string; rule_name: string; rule_outcome: string; matched: boolean; conditions: { field: string; op: string; expected: unknown; actual: unknown; passed: boolean }[] }[];
  explanation: string; risk_level?: string | null; created_at: string;
}
export interface Execution {
  id: string; workflow: string; status: string; intent: string | null; llm_mode: string; input_summary: string | null; outcome_summary: string | null;
  decision_outcome: string | null; resolved_autonomously: boolean; required_human: boolean; error: string | null; duration_ms: number | null;
  ticket_id: string | null; order_id: string | null; conversation_id: string | null; is_sample: boolean; created_at: string; finished_at: string | null;
  agents?: string[]; tool_count?: number;
  steps?: { agent: string; step: string; summary: string; at: string; data?: Record<string, unknown> }[];
  decisions?: Decision[]; actions?: NonNullable<Approval["action"]>[];
  tool_calls?: { id: string; agent: string; tool: string; arguments: Record<string, unknown>; result_summary: string | null; success: boolean; authorized: boolean; duration_ms: number | null; created_at: string }[];
}
export interface Notification { id: string; type: string; title: string; body: string; link: string | null; read_at: string | null; created_at: string }
export interface Product { id: string; sku: string; name: string; category: string; price: string; refundable_days: number; description: string | null }
export interface Policy {
  id: string; key: string; name: string; action_type: string; description: string | null; is_active: boolean; current_version: number; active_version: number | null;
  versions: PolicyVersion[];
}
export interface PolicyRule { id: string; name?: string; priority: number; match?: 'all' | 'any'; conditions: { field: string; op: string; value?: unknown }[]; outcome: string; explanation?: string }
export interface PolicyVersion { id: string; version: number; rules: PolicyRule[]; default_outcome: string; effective_from: string; effective_to: string | null; change_note: string | null; created_by?: string | null; created_at: string }
export interface KnowledgeDoc { id: string; doc_key: string; version: number; is_current: boolean; title: string; category: string; filename: string; size_bytes: number; status: string; embedding_model: string; chunk_count: number; error: string | null; created_at: string }
export interface AuditRow { id: string; actor_type: string; actor_id: string | null; action: string; entity_type: string | null; entity_id: string | null; summary: string; data: Record<string, unknown>; created_at: string }
export interface Overview {
  currency: string; revenue: number; net_revenue: number; total_payments: number; failed_payments: number; payment_success_rate: number; avg_transaction_value: number;
  refund_volume: number; refund_count: number; refund_rate: number; pending_approvals: number; open_tickets: number; resolved_tickets: number; avg_resolution_hours: number;
  escalation_rate: number; csat: number; ai_executions: number; ai_autonomous_rate: number; ai_human_rate: number;
  series: { date: string; captured: number; refunded: number; tickets?: number; executions?: number }[];
  alerts?: { level: string; title: string; detail: string; link?: string }[];
  [k: string]: unknown;
}
export interface IntegrationStatus {
  paypal: { configured: boolean; webhook_configured: boolean; base_url: string; mode: string; sdk: string };
  llm: { configured: boolean; provider: string; mode: string };
  embeddings: { model: string; semantic: boolean };
  ag_studio: { license_configured: boolean; ai_enabled: boolean };
  redis: { connected: boolean };
}
