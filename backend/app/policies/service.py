"""Policy selection, versioning and decision recording."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import NotFound, ValidationFailed
from app.models import BusinessPolicy, PolicyDecision, PolicyVersion
from app.models.enums import ActionType, DecisionOutcome, RiskLevel
from app.policies.engine import Evaluation, evaluate, validate_rules
from app.services.audit import audit, jsonable


def active_version(db: Session, business_id: uuid.UUID, action_type: ActionType, at: datetime | None = None) -> tuple[BusinessPolicy, PolicyVersion] | None:
    at = at or utcnow()
    policy = db.scalars(
        select(BusinessPolicy).where(BusinessPolicy.business_id == business_id, BusinessPolicy.action_type == action_type, BusinessPolicy.is_active.is_(True))
    ).first()
    if policy is None:
        return None
    version = db.scalars(
        select(PolicyVersion)
        .where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.effective_from <= at,
            or_(PolicyVersion.effective_to.is_(None), PolicyVersion.effective_to > at),
        )
        .order_by(PolicyVersion.version.desc())
    ).first()
    if version is None:
        return None
    return policy, version


def evaluate_and_record(
    db: Session,
    *,
    business_id: uuid.UUID,
    action_type: ActionType,
    facts: dict[str, Any],
    customer_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    agent_execution_id: uuid.UUID | None = None,
    risk_level: RiskLevel | None = None,
    record: bool = True,
) -> tuple[Evaluation, PolicyDecision | None, PolicyVersion | None]:
    found = active_version(db, business_id, action_type)
    if found is None:
        ev = Evaluation(
            outcome=DecisionOutcome.ESCALATED,
            matched_rule_id=None,
            matched_rule_name=None,
            explanation=f"No active policy configured for {action_type.value}; escalating to a human.",
            rules=[],
        )
        policy = version = None
    else:
        policy, version = found
        ev = evaluate(action_type, version.rules, version.default_outcome, facts)
    decision = None
    if record:
        decision = PolicyDecision(
            business_id=business_id,
            policy_id=policy.id if policy else None,
            policy_version_id=version.id if version else None,
            policy_version=version.version if version else None,
            action_type=action_type,
            outcome=ev.outcome,
            matched_rule_id=ev.matched_rule_id,
            inputs=jsonable(facts),
            evaluated_conditions=ev.evaluated_conditions(),
            explanation=ev.explanation,
            customer_id=customer_id,
            order_id=order_id,
            payment_id=payment_id,
            agent_execution_id=agent_execution_id,
            risk_level=risk_level,
        )
        db.add(decision)
        db.flush()
    return ev, decision, version


def create_version(
    db: Session,
    *,
    policy: BusinessPolicy,
    rules: list[dict[str, Any]],
    default_outcome: DecisionOutcome,
    effective_from: datetime | None,
    change_note: str | None,
    user_id: uuid.UUID | None,
) -> PolicyVersion:
    problems = validate_rules(rules)
    if problems:
        raise ValidationFailed("Policy rules are invalid", details=problems)
    eff = effective_from or utcnow()
    latest = db.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == policy.id).order_by(PolicyVersion.version.desc())).first()
    next_no = (latest.version + 1) if latest else 1
    # Close the currently-open version(s) at the new effective date. Versions are otherwise immutable.
    for v in db.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == policy.id, PolicyVersion.effective_to.is_(None))):
        if v.effective_from < eff:
            v.effective_to = eff
    version = PolicyVersion(
        policy_id=policy.id,
        version=next_no,
        rules=rules,
        default_outcome=default_outcome,
        effective_from=eff,
        change_note=change_note,
        created_by_user_id=user_id,
    )
    db.add(version)
    policy.current_version = next_no
    db.flush()
    audit(
        db,
        business_id=policy.business_id,
        actor=f"user:{user_id}" if user_id else "system",
        action="policy.version_created",
        entity_type="policy",
        entity_id=policy.id,
        summary=f"Policy '{policy.name}' v{next_no} created (effective {eff.isoformat()})",
        data={"rules": rules, "default_outcome": default_outcome.value, "note": change_note},
    )
    return version


def get_policy(db: Session, business_id: uuid.UUID, policy_id: uuid.UUID) -> BusinessPolicy:
    p = db.get(BusinessPolicy, policy_id)
    if p is None or p.business_id != business_id:
        raise NotFound("Policy not found")
    return p
