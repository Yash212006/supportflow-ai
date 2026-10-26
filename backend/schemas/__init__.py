from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    customer_code: str
    name: str
    email: EmailStr
    phone: str
    status: str = "active"


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_number: str
    customer_id: int
    order_date: date
    expected_delivery: date | None
    actual_delivery: date | None
    status: str
    amount: float
    payment_status: str
    shipping_address: str
    product_name: str
    created_at: datetime | None = None


class TicketCreate(BaseModel):
    customer_id: int | None = None
    customer_code: str | None = None
    order_id: int | None = None
    order_number: str | None = None
    subject: str
    description: str
    priority: str = "MEDIUM"
    category: str = "GENERAL"
    assigned_to: str | None = None


class TicketUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    resolution: str | None = None
    assigned_to: str | None = None
    investigation_notes: str | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticket_number: str
    customer_id: int
    order_id: int | None
    subject: str
    description: str
    priority: str
    status: str
    category: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    assigned_to: str | None = None
    resolution: str | None = None
    investigation_notes: str | None = None


class RefundCreate(BaseModel):
    order_number: str
    amount: float | None = None
    reason: str
    ticket_number: str | None = None
    requested_by: str = "support_agent"


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    refund_id: str
    order_id: int
    customer_id: int
    ticket_id: int | None
    amount: float
    reason: str
    status: str
    requested_at: datetime | None = None
    approved_at: datetime | None = None
    processed_at: datetime | None = None
    rejected_reason: str | None = None


class PendingActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action_id: str
    ticket_id: int | None
    customer_id: int | None
    order_id: int | None
    refund_id: str | None
    ticket_number: str | None = None
    ticket_subject: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    order_number: str | None = None
    order_product: str | None = None
    action_type: str
    requested_by: str
    agent_reason: str
    policy_evidence: str | None
    parameters: str | None
    amount: float | None
    status: str
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_note: str | None = None


class ApprovalDecision(BaseModel):
    reviewed_by: str = "support_executive"
    note: str | None = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action_id: str
    ticket_id: int | None
    action_type: str
    requested_by: str
    agent_reason: str | None
    tool_name: str | None
    parameters: str | None
    approval_status: str
    executed_at: datetime | None = None
    result: str | None
    latency_ms: int | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    requested_by: str = "support_executive"


class ToolTraceItem(BaseModel):
    tool_name: str
    status: str
    latency_ms: int = 0
    facts: dict | list | str | None = None


class SourceItem(BaseModel):
    document: str
    page: int | None = None
    policy_type: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    intent: str | None = None
    answer: str
    facts: list[str] = Field(default_factory=list)
    policy: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    proposed_action: dict | None = None
    requires_approval: bool = False
    customer_response: str | None = None
    tools_used: list[ToolTraceItem] = Field(default_factory=list)
    sources: list[SourceItem] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    display_name: str | None = None
    email: str | None = None
    message: str | None = None
