"""Controlled Action Execution Engine.

The only code path that can move money. Agents and the copilot *request* actions here; they can never
call PayPal directly. Every action:

  REQUESTED → VALIDATING → (REQUIRES_APPROVAL → APPROVED | REJECTED | ESCALATED | APPROVED)
            → EXECUTING → SUCCEEDED | PENDING_CONFIRMATION | FAILED

- Claim first: the ExecutionAction row (UNIQUE idempotency_key) is committed before PayPal is called.
- The payment row is locked (SELECT … FOR UPDATE) while refundable amount is recomputed.
- Financial actions are revalidated immediately before execution (permissions, payment state,
  refundable amount, policy version, idempotency).
- Success is only recorded from PayPal's actual response status (or a verified webhook later).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.integrations.paypal.errors import PayPalError
from app.integrations.paypal.gateway import PayPalGateway
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ExecutionAction,
    Order,
    Payment,
    PolicyDecision,
    Refund,
    SupportTicket,
    User,
)
from app.models.enums import (
    MANAGER_ROLES,
    ActionState,
    ActionType,
    ApprovalStatus,
    DecisionOutcome,
    NotificationType,
    OrderStatus,
    PaymentSource,
    PaymentStatus,
    RefundStatus,
    TicketStatus,
)
from app.policies.facts import assess_refund_risk, latest_payment, refund_facts
from app.policies.service import active_version, evaluate_and_record
from app.services.audit import audit, jsonable
from app.services.notifications import notify_customer, notify_managers
from app.services.paypal_records import recorder_for
from app.services.tickets import set_status

TRANSITIONS: dict[ActionState, set[ActionState]] = {
    ActionState.REQUESTED: {ActionState.VALIDATING, ActionState.CANCELLED},
    ActionState.VALIDATING: {ActionState.APPROVED, ActionState.REQUIRES_APPROVAL, ActionState.REJECTED, ActionState.ESCALATED, ActionState.CANCELLED},
    ActionState.REQUIRES_APPROVAL: {ActionState.APPROVED, ActionState.REJECTED, ActionState.CANCELLED},
    ActionState.ESCALATED: {ActionState.APPROVED, ActionState.REJECTED, ActionState.CANCELLED},
    ActionState.APPROVED: {ActionState.EXECUTING, ActionState.REJECTED, ActionState.FAILED},
    ActionState.EXECUTING: {ActionState.SUCCEEDED, ActionState.PENDING_CONFIRMATION, ActionState.FAILED},
    ActionState.PENDING_CONFIRMATION: {ActionState.SUCCEEDED, ActionState.FAILED},
    ActionState.FAILED: {ActionState.APPROVED},  # manual retry, only when PayPal never received the request
    ActionState.SUCCEEDED: set(),
    ActionState.REJECTED: set(),
    ActionState.CANCELLED: set(),
}


class InvalidTransition(Conflict):
    code = "invalid_state_transition"


def transition(action: ExecutionAction, new: ActionState, *, actor: str, note: str = "") -> None:
    if new not in TRANSITIONS[action.state]:
        raise InvalidTransition(f"Cannot move action from {action.state.value} to {new.value}")
    history = list(action.history or [])
    history.append({"from": action.state.value, "to": new.value, "at": utcnow().isoformat(), "actor": actor, "note": note})
    action.history = history
    action.state = new


@dataclass
class RefundOutcome:
    action: ExecutionAction
    refund: Refund | None
    decision: PolicyDecision | None
    approval: ApprovalRequest | None
    duplicate: bool = False

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "action_id": str(self.action.id),
            "action_state": self.action.state.value,
            "decision": self.decision.outcome.value if self.decision else None,
            "explanation": self.decision.explanation if self.decision else None,
            "refund_id": str(self.refund.id) if self.refund else None,
            "refund_status": self.refund.status.value if self.refund else None,
            "paypal_refund_id": self.refund.paypal_refund_id if self.refund else None,
            "paypal_status": self.refund.paypal_status if self.refund else None,
            "approval_id": str(self.approval.id) if self.approval else None,
            "error": self.action.error_message,
            "duplicate": self.duplicate,
        }


def _lock_payment(db: Session, payment_id: uuid.UUID) -> Payment:
    p = db.scalars(select(Payment).where(Payment.id == payment_id).with_for_update(key_share=True)).one()
    return p


def _refundable(db: Session, payment: Payment) -> Decimal:
    return payment.refundable_amount


class ExecutionEngine:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ request
    def request_refund(
        self,
        *,
        business_id: uuid.UUID,
        order: Order,
        amount: Decimal | None,
        reason: str,
        requested_by: str,
        idempotency_key: str,
        ticket: SupportTicket | None = None,
        agent_execution_id: uuid.UUID | None = None,
        requested_by_user_id: uuid.UUID | None = None,
    ) -> RefundOutcome:
        db = self.db
        if order.business_id != business_id:
            raise Forbidden("Order does not belong to this business")
        # Duplicate prevention: same idempotency key → same action, no second refund.
        existing = db.scalars(select(ExecutionAction).where(ExecutionAction.idempotency_key == idempotency_key)).first()
        if existing is not None:
            return self._outcome_for(existing, duplicate=True)

        payment = latest_payment(db, order.id)
        if amount is None and payment is not None:
            amount = payment.refundable_amount
        if amount is not None:
            amount = Decimal(amount).quantize(Decimal("0.01"))
            if amount <= 0:
                raise ValidationFailed("Refund amount must be positive")

        action = ExecutionAction(
            business_id=business_id,
            action_type=ActionType.INITIATE_REFUND,
            state=ActionState.REQUESTED,
            idempotency_key=idempotency_key,
            payload=jsonable({"order_id": order.id, "payment_id": payment.id if payment else None, "amount": amount, "currency": order.currency, "reason": reason}),
            requested_by=requested_by,
            agent_execution_id=agent_execution_id,
            order_id=order.id,
            payment_id=payment.id if payment else None,
            ticket_id=ticket.id if ticket else None,
            history=[{"from": None, "to": "REQUESTED", "at": utcnow().isoformat(), "actor": requested_by, "note": reason}],
        )
        try:
            with db.begin_nested():
                db.add(action)
                db.flush()
        except IntegrityError:
            existing = db.scalars(select(ExecutionAction).where(ExecutionAction.idempotency_key == idempotency_key)).one()
            return self._outcome_for(existing, duplicate=True)

        transition(action, ActionState.VALIDATING, actor="system:execution-engine")
        if payment is not None:
            payment = _lock_payment(db, payment.id)
        risk = assess_refund_risk(db, order=order, payment=payment, amount=amount)
        facts = refund_facts(db, order=order, payment=payment, amount=amount, risk=risk)
        ev, decision, version = evaluate_and_record(
            db,
            business_id=business_id,
            action_type=ActionType.INITIATE_REFUND,
            facts=facts,
            customer_id=order.customer_id,
            order_id=order.id,
            payment_id=payment.id if payment else None,
            agent_execution_id=agent_execution_id,
            risk_level=risk.level,
        )
        action.policy_decision_id = decision.id if decision else None
        action.result = {"risk": risk.to_dict(), "policy_version": version.version if version else None}
        audit(
            db,
            business_id=business_id,
            actor=requested_by,
            action="refund.requested",
            entity_type="execution_action",
            entity_id=action.id,
            summary=f"Refund of {order.currency} {amount} requested for order #{order.order_number}; policy → {ev.outcome.value}",
            data={"facts": facts, "decision": ev.outcome.value, "explanation": ev.explanation, "risk": risk.to_dict()},
        )

        if ev.outcome == DecisionOutcome.NEEDS_MORE_INFORMATION or payment is None or amount is None:
            transition(action, ActionState.CANCELLED, actor="system:policy-engine", note=ev.explanation)
            action.error_code = "NEEDS_MORE_INFORMATION"
            action.error_message = ev.explanation if payment is not None else "No payment found for this order."
            return RefundOutcome(action, None, decision, None)

        refund = Refund(
            business_id=business_id,
            payment_id=payment.id,
            order_id=order.id,
            customer_id=order.customer_id,
            ticket_id=ticket.id if ticket else None,
            amount=amount,
            currency=payment.currency,
            reason=reason[:500],
            status=RefundStatus.REQUESTED,
            policy_decision_id=decision.id if decision else None,
            execution_action_id=action.id,
            requested_by_user_id=requested_by_user_id,
        )
        db.add(refund)
        db.flush()

        approval = None
        if ev.outcome == DecisionOutcome.AUTO_EXECUTE:
            transition(action, ActionState.APPROVED, actor="system:policy-engine", note=f"Policy auto-approved ({ev.matched_rule_name})")
            db.commit()  # claim is durable before any PayPal call
            self.execute_refund(action, actor="system:execution-engine")
        elif ev.outcome in (DecisionOutcome.REQUIRES_APPROVAL, DecisionOutcome.ESCALATED):
            target = ActionState.REQUIRES_APPROVAL if ev.outcome == DecisionOutcome.REQUIRES_APPROVAL else ActionState.ESCALATED
            transition(action, target, actor="system:policy-engine", note=ev.explanation)
            refund.status = RefundStatus.AWAITING_APPROVAL
            approval = ApprovalRequest(
                business_id=business_id,
                execution_action_id=action.id,
                policy_decision_id=decision.id if decision else None,
                status=ApprovalStatus.PENDING,
                title=f"{'Manual review' if target == ActionState.ESCALATED else 'Approve'} refund of {payment.currency} {amount} — order #{order.order_number}",
                reason=ev.explanation,
                proposed_by=requested_by,
                risk_level=risk.level,
                risk_summary=risk.to_dict(),
            )
            db.add(approval)
            db.flush()
            notify_managers(
                db,
                business_id=business_id,
                type_=NotificationType.APPROVAL_REQUIRED if target == ActionState.REQUIRES_APPROVAL else NotificationType.RISK_ALERT,
                title=approval.title,
                body=ev.explanation[:400],
                link=f"/manager/approvals/{approval.id}",
            )
            if ticket is not None:
                set_status(db, ticket, TicketStatus.AWAITING_APPROVAL if target == ActionState.REQUIRES_APPROVAL else TicketStatus.ESCALATED, actor=requested_by, detail=ev.explanation[:300])
            notify_customer(
                db,
                customer_id=order.customer_id,
                type_=NotificationType.TICKET_UPDATED,
                title=f"Refund request for order #{order.order_number} is under review",
                body="A manager will review your refund request. We'll notify you of the decision.",
                link="/customer/refunds",
            )
        else:  # REJECTED
            transition(action, ActionState.REJECTED, actor="system:policy-engine", note=ev.explanation)
            refund.status = RefundStatus.REJECTED
            refund.failure_reason = ev.explanation[:500]
        db.commit()
        return RefundOutcome(action, refund, decision, approval)

    # ------------------------------------------------------------------ execute
    def execute_refund(self, action: ExecutionAction, *, actor: str, approver: User | None = None) -> RefundOutcome:
        db = self.db
        refund = db.scalars(select(Refund).where(Refund.execution_action_id == action.id)).one()
        decision = db.get(PolicyDecision, action.policy_decision_id) if action.policy_decision_id else None
        payment = _lock_payment(db, refund.payment_id)
        order = db.get(Order, refund.order_id)
        assert order is not None
        revalidation: dict[str, Any] = {"at": utcnow().isoformat()}

        def fail(code: str, msg: str, *, refund_status: RefundStatus = RefundStatus.FAILED) -> RefundOutcome:
            transition(action, ActionState.FAILED, actor=actor, note=msg)
            action.error_code, action.error_message = code, msg
            refund.status, refund.failure_reason = refund_status, msg[:500]
            action.result = {**(action.result or {}), "revalidation": revalidation}
            notify_customer(db, customer_id=refund.customer_id, type_=NotificationType.REFUND_FAILED, title=f"Refund for order #{order.order_number} could not be processed", body=msg[:300], link="/customer/refunds")
            notify_managers(db, business_id=refund.business_id, type_=NotificationType.REFUND_FAILED, title=f"Refund failed — order #{order.order_number}", body=msg[:300], link=f"/manager/refunds/{refund.id}")
            audit(db, business_id=refund.business_id, actor=actor, action="refund.failed", entity_type="refund", entity_id=refund.id, summary=f"Refund failed: {msg}", data={"code": code, "revalidation": revalidation})
            self._sync_ticket(refund, success=False, message=msg, actor=actor)
            db.commit()
            return RefundOutcome(action, refund, decision, None)

        # --- revalidation immediately before execution ---
        if approver is not None and approver.role not in MANAGER_ROLES:
            raise Forbidden("Only managers can execute approved refunds")
        revalidation["refundable_amount"] = str(_refundable(db, payment))
        revalidation["payment_status"] = payment.status.value
        if payment.order_id != order.id or payment.customer_id != order.customer_id:
            return fail("OWNERSHIP_MISMATCH", "Payment does not belong to the order/customer")
        if payment.status not in (PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED):
            return fail("PAYMENT_NOT_REFUNDABLE", f"Payment is {payment.status.value}; only captured payments can be refunded")
        if refund.amount > _refundable(db, payment):
            return fail("EXCEEDS_REFUNDABLE", f"Refund {refund.amount} exceeds refundable amount {_refundable(db, payment)}")
        if decision is not None and decision.policy_id is not None:
            current = active_version(db, refund.business_id, ActionType.INITIATE_REFUND)
            revalidation["decision_policy_version"] = decision.policy_version
            revalidation["current_policy_version"] = current[1].version if current else None
            if current is not None and current[1].version != decision.policy_version and approver is None:
                return fail("POLICY_CHANGED", "Policy changed since the decision; re-evaluation required")
        revalidation["idempotency_key"] = action.idempotency_key
        if payment.source != PaymentSource.PAYPAL_SANDBOX or not payment.paypal_capture_id:
            return fail(
                "NOT_A_PAYPAL_CAPTURE",
                "This payment is labelled sample data (not a real PayPal Sandbox capture), so no PayPal refund can be issued. Use an order paid through PayPal Sandbox checkout.",
            )
        if not get_settings().paypal_configured:
            return fail("PAYPAL_NOT_CONFIGURED", "PayPal Sandbox is not configured; refund not sent.")
        revalidation["passed"] = True

        transition(action, ActionState.EXECUTING, actor=actor, note="Revalidated; calling PayPal Refund API")
        action.attempts += 1
        action.executed_at = refund.executed_at = utcnow()
        action.result = {**(action.result or {}), "revalidation": revalidation}
        db.commit()

        gateway = PayPalGateway(recorder_for(db, business_id=refund.business_id, payment_id=payment.id, refund_id=refund.id))
        try:
            res = gateway.refund_capture(
                payment.paypal_capture_id,
                amount=refund.amount,
                currency=refund.currency,
                request_id=action.idempotency_key,
                invoice_id=f"RF-{str(refund.id)[:8]}",
                note=f"Refund for order #{order.order_number}: {refund.reason}"[:255],
            )
        except PayPalError as err:
            payment = _lock_payment(db, payment.id)
            if err.outcome == "unknown":
                # Request may have reached PayPal: reserve the amount, never mark success, reconcile later.
                transition(action, ActionState.PENDING_CONFIRMATION, actor=actor, note=str(err))
                action.error_code, action.error_message = "OUTCOME_UNKNOWN", str(err)
                refund.status = RefundStatus.OUTCOME_UNKNOWN
                payment.refunded_amount = payment.refunded_amount + refund.amount
                audit(db, business_id=refund.business_id, actor="paypal", action="refund.outcome_unknown", entity_type="refund", entity_id=refund.id, summary=f"PayPal outcome unknown; will reconcile using PayPal-Request-Id {action.idempotency_key}", data=err.to_dict())
                db.commit()
                return RefundOutcome(action, refund, decision, None)
            action.result = {**(action.result or {}), "paypal_error": err.to_dict()}
            return fail(f"PAYPAL_{err.kind.upper()}", f"PayPal {('rejected' if err.outcome == 'rejected' else 'was not reached for')} the refund: {err.user_message()}")

        payment = _lock_payment(db, payment.id)
        refund.paypal_refund_id = res.id
        refund.paypal_status = res.status
        refund.paypal_status_reason = res.status_reason
        action.result = {**(action.result or {}), "paypal": {"refund_id": res.id, "status": res.status, "amount": str(res.amount) if res.amount else None}}
        if res.status in ("COMPLETED", "PENDING"):
            payment.refunded_amount = payment.refunded_amount + refund.amount
            self._apply_payment_refund_state(payment, order)
            if res.status == "COMPLETED":
                refund.status, refund.completed_at = RefundStatus.COMPLETED, utcnow()
                transition(action, ActionState.SUCCEEDED, actor="paypal", note=f"PayPal refund {res.id} COMPLETED")
                self._notify_refund(refund, order, completed=True)
                self._sync_ticket(refund, success=True, message=f"Refund of {refund.currency} {refund.amount} completed by PayPal (refund {res.id}).", actor=actor)
            else:
                refund.status = RefundStatus.PENDING
                transition(action, ActionState.PENDING_CONFIRMATION, actor="paypal", note=f"PayPal refund {res.id} PENDING ({res.status_reason or 'no reason'})")
                self._notify_refund(refund, order, completed=False)
                self._sync_ticket(refund, success=True, message=f"Refund of {refund.currency} {refund.amount} submitted to PayPal (refund {res.id}); PayPal reports PENDING.", actor=actor, final=False)
            audit(db, business_id=refund.business_id, actor="paypal", action="refund.paypal_response", entity_type="refund", entity_id=refund.id, summary=f"PayPal refund {res.id} status {res.status}", data={"paypal_refund_id": res.id, "status": res.status})
            db.commit()
            return RefundOutcome(action, refund, decision, None)
        return fail("PAYPAL_REFUND_" + res.status, f"PayPal returned refund status {res.status} ({res.status_reason or 'no reason given'})")

    # ------------------------------------------------------------------ approvals
    def approve(self, approval: ApprovalRequest, *, manager: User, note: str | None) -> RefundOutcome:
        db = self.db
        if manager.role not in MANAGER_ROLES or manager.business_id != approval.business_id:
            raise Forbidden("Only managers of this business can approve")
        if approval.status != ApprovalStatus.PENDING:
            raise Conflict(f"Approval is already {approval.status.value}")
        action = db.get(ExecutionAction, approval.execution_action_id)
        assert action is not None
        approval.status = ApprovalStatus.APPROVED
        approval.decided_by_user_id, approval.decided_at, approval.manager_note = manager.id, utcnow(), note
        transition(action, ActionState.APPROVED, actor=f"user:{manager.id}", note=note or "Approved by manager")
        db.add(ApprovalAction(approval_id=approval.id, user_id=manager.id, action="APPROVE", note=note))
        audit(db, business_id=approval.business_id, actor=f"user:{manager.id}", action="approval.approved", entity_type="approval", entity_id=approval.id, summary=f"{manager.full_name} approved: {approval.title}", data={"note": note})
        db.commit()
        outcome = self.execute_refund(action, actor=f"user:{manager.id}", approver=manager)
        db.refresh(action)
        refund = outcome.refund
        aa = db.scalars(select(ApprovalAction).where(ApprovalAction.approval_id == approval.id).order_by(ApprovalAction.created_at.desc())).first()
        if aa is not None:
            aa.revalidation = (action.result or {}).get("revalidation", {})
        approval.final_result = {
            "action_state": action.state.value,
            "refund_status": refund.status.value if refund else None,
            "paypal_refund_id": refund.paypal_refund_id if refund else None,
            "paypal_status": refund.paypal_status if refund else None,
            "error": action.error_message,
        }
        if action.state == ActionState.FAILED:
            approval.status = ApprovalStatus.EXECUTION_FAILED
        if refund is not None and action.state != ActionState.FAILED:
            notify_customer(
                db,
                customer_id=refund.customer_id,
                type_=NotificationType.APPROVAL_GRANTED,
                title="Your refund request was approved",
                body=f"Refund status: {refund.status.value}",
                link="/customer/refunds",
            )
        db.commit()
        return RefundOutcome(action, refund, outcome.decision, approval)

    def reject(self, approval: ApprovalRequest, *, manager: User, note: str | None) -> RefundOutcome:
        db = self.db
        if manager.role not in MANAGER_ROLES or manager.business_id != approval.business_id:
            raise Forbidden("Only managers of this business can reject")
        if approval.status != ApprovalStatus.PENDING:
            raise Conflict(f"Approval is already {approval.status.value}")
        action = db.get(ExecutionAction, approval.execution_action_id)
        assert action is not None
        approval.status = ApprovalStatus.REJECTED
        approval.decided_by_user_id, approval.decided_at, approval.manager_note = manager.id, utcnow(), note
        transition(action, ActionState.REJECTED, actor=f"user:{manager.id}", note=note or "Rejected by manager")
        db.add(ApprovalAction(approval_id=approval.id, user_id=manager.id, action="REJECT", note=note))
        refund = db.scalars(select(Refund).where(Refund.execution_action_id == action.id)).first()
        if refund is not None:
            refund.status = RefundStatus.REJECTED
            refund.failure_reason = f"Rejected by manager: {note or 'no note'}"[:500]
            notify_customer(db, customer_id=refund.customer_id, type_=NotificationType.APPROVAL_REJECTED, title="Your refund request was declined", body=note or "A manager reviewed and declined this refund.", link="/customer/refunds")
            self._sync_ticket(refund, success=False, message=f"Refund declined by manager. {note or ''}".strip(), actor=f"user:{manager.id}")
        approval.final_result = {"action_state": action.state.value, "refund_status": refund.status.value if refund else None}
        audit(db, business_id=approval.business_id, actor=f"user:{manager.id}", action="approval.rejected", entity_type="approval", entity_id=approval.id, summary=f"{manager.full_name} rejected: {approval.title}", data={"note": note})
        db.commit()
        return RefundOutcome(action, refund, None, approval)

    def reconcile(self, action: ExecutionAction, *, actor: str) -> RefundOutcome:
        """Re-send the identical refund with the same PayPal-Request-Id: PayPal returns the original
        refund instead of creating a new one. Used for OUTCOME_UNKNOWN actions."""
        db = self.db
        if action.state != ActionState.PENDING_CONFIRMATION:
            raise Conflict("Only actions awaiting confirmation can be reconciled")
        refund = db.scalars(select(Refund).where(Refund.execution_action_id == action.id)).one()
        payment = _lock_payment(db, refund.payment_id)
        gateway = PayPalGateway(recorder_for(db, business_id=refund.business_id, payment_id=payment.id, refund_id=refund.id))
        if refund.paypal_refund_id:
            res = gateway.get_refund(refund.paypal_refund_id)
        else:
            assert payment.paypal_capture_id
            res = gateway.refund_capture(payment.paypal_capture_id, amount=refund.amount, currency=refund.currency, request_id=action.idempotency_key, invoice_id=f"RF-{str(refund.id)[:8]}", note=refund.reason)
        self.apply_refund_status(refund, res.id, res.status, actor=actor, reason=res.status_reason)
        db.commit()
        return self._outcome_for(action)

    # ------------------------------------------------------------------ helpers
    def apply_refund_status(self, refund: Refund, paypal_refund_id: str, status: str, *, actor: str, reason: str | None = None) -> None:
        """Synchronise a refund with a PayPal-reported status (API read or verified webhook)."""
        db = self.db
        payment = _lock_payment(db, refund.payment_id)
        order = db.get(Order, refund.order_id)
        assert order is not None
        action = db.get(ExecutionAction, refund.execution_action_id) if refund.execution_action_id else None
        refund.paypal_refund_id = refund.paypal_refund_id or paypal_refund_id
        refund.paypal_status = status
        refund.paypal_status_reason = reason
        reserved = refund.status in (RefundStatus.PENDING, RefundStatus.OUTCOME_UNKNOWN, RefundStatus.COMPLETED)
        if status == "COMPLETED" and refund.status != RefundStatus.COMPLETED:
            if not reserved:
                payment.refunded_amount = payment.refunded_amount + refund.amount
            refund.status, refund.completed_at = RefundStatus.COMPLETED, utcnow()
            self._apply_payment_refund_state(payment, order)
            if action is not None and action.state in (ActionState.PENDING_CONFIRMATION, ActionState.EXECUTING):
                transition(action, ActionState.SUCCEEDED, actor=actor, note=f"PayPal refund {paypal_refund_id} COMPLETED")
            self._notify_refund(refund, order, completed=True)
            self._sync_ticket(refund, success=True, message=f"Refund of {refund.currency} {refund.amount} completed by PayPal.", actor=actor)
        elif status in ("FAILED", "CANCELLED") and refund.status not in (RefundStatus.FAILED, RefundStatus.CANCELLED):
            if reserved:
                payment.refunded_amount = max(Decimal("0"), payment.refunded_amount - refund.amount)
            refund.status = RefundStatus.FAILED if status == "FAILED" else RefundStatus.CANCELLED
            refund.failure_reason = f"PayPal reported {status}" + (f": {reason}" if reason else "")
            self._apply_payment_refund_state(payment, order)
            if action is not None and action.state in (ActionState.PENDING_CONFIRMATION, ActionState.EXECUTING):
                transition(action, ActionState.FAILED, actor=actor, note=refund.failure_reason)
            notify_customer(db, customer_id=refund.customer_id, type_=NotificationType.REFUND_FAILED, title=f"Refund for order #{order.order_number} failed", body=refund.failure_reason, link="/customer/refunds")
            self._sync_ticket(refund, success=False, message=refund.failure_reason, actor=actor)
        elif status == "PENDING" and refund.status == RefundStatus.OUTCOME_UNKNOWN:
            refund.status = RefundStatus.PENDING
        audit(db, business_id=refund.business_id, actor=actor, action="refund.status_synced", entity_type="refund", entity_id=refund.id, summary=f"Refund {paypal_refund_id} → {status}")

    @staticmethod
    def _apply_payment_refund_state(payment: Payment, order: Order) -> None:
        if payment.refunded_amount <= 0:
            payment.status = PaymentStatus.CAPTURED
        elif payment.refunded_amount >= payment.amount:
            payment.status = PaymentStatus.REFUNDED
            order.status = OrderStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED
            order.status = OrderStatus.PARTIALLY_REFUNDED

    def _notify_refund(self, refund: Refund, order: Order, *, completed: bool) -> None:
        notify_customer(
            self.db,
            customer_id=refund.customer_id,
            type_=NotificationType.REFUND_COMPLETED if completed else NotificationType.REFUND_INITIATED,
            title=f"Refund {'completed' if completed else 'initiated'} for order #{order.order_number}",
            body=f"{refund.currency} {refund.amount} — PayPal refund {refund.paypal_refund_id} ({refund.paypal_status}).",
            link="/customer/refunds",
        )

    def _sync_ticket(self, refund: Refund, *, success: bool, message: str, actor: str, final: bool = True) -> None:
        if refund.ticket_id is None:
            return
        ticket = self.db.get(SupportTicket, refund.ticket_id)
        if ticket is None:
            return
        if success and final:
            set_status(self.db, ticket, TicketStatus.RESOLVED, actor=actor, detail=message, resolved_by="AI" if actor.startswith(("system", "agent", "paypal")) else "HUMAN")
        elif success:
            set_status(self.db, ticket, TicketStatus.IN_PROGRESS, actor=actor, detail=message)
        else:
            set_status(self.db, ticket, TicketStatus.ESCALATED if ticket.status != TicketStatus.RESOLVED else ticket.status, actor=actor, detail=message)

    def _outcome_for(self, action: ExecutionAction, duplicate: bool = False) -> RefundOutcome:
        db = self.db
        refund = db.scalars(select(Refund).where(Refund.execution_action_id == action.id)).first()
        decision = db.get(PolicyDecision, action.policy_decision_id) if action.policy_decision_id else None
        approval = db.scalars(select(ApprovalRequest).where(ApprovalRequest.execution_action_id == action.id)).first()
        return RefundOutcome(action, refund, decision, approval, duplicate=duplicate)


def get_action(db: Session, business_id: uuid.UUID, action_id: uuid.UUID) -> ExecutionAction:
    a = db.get(ExecutionAction, action_id)
    if a is None or a.business_id != business_id:
        raise NotFound("Action not found")
    return a

