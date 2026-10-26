from dataclasses import asdict, dataclass
from functools import lru_cache


@dataclass(frozen=True)
class BusinessRules:
    auto_refund_limit: float = 5000.0
    high_value_threshold: float = 50000.0
    max_auto_resolution_attempts: int = 2
    delivery_delay_refund_days: int = 5
    cancellation_window_hours: int = 24
    replacement_window_days: int = 7
    warranty_period_days: int = 365
    duplicate_refund_block: bool = True
    escalate_on_fraud_keywords: tuple[str, ...] = (
        "fraud",
        "stolen card",
        "unauthorized payment",
        "identity theft",
    )
    escalate_on_human_request_keywords: tuple[str, ...] = (
        "human",
        "representative",
        "manager",
        "speak to someone",
    )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["escalate_on_fraud_keywords"] = list(self.escalate_on_fraud_keywords)
        data["escalate_on_human_request_keywords"] = list(
            self.escalate_on_human_request_keywords
        )
        return data


@lru_cache
def get_business_rules() -> BusinessRules:
    return BusinessRules()
