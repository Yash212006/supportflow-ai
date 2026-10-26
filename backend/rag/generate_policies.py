"""Create fictional Northwind Commerce policy PDFs (not copied from real companies)."""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.config.settings import ROOT_DIR

COMPANY = "Northwind Commerce (fictional)"

POLICIES: dict[str, list[tuple[str, str]]] = {
    "refund_policy.pdf": [
        ("Refund Policy", f"This document describes refund rules for {COMPANY}."),
        (
            "Delayed delivery refunds",
            "If an order is delayed by more than 5 calendar days beyond the expected delivery date "
            "and the customer still has not received the item, the customer may request a full refund "
            "of the order amount. A delay of 5 days or fewer does not automatically qualify.",
        ),
        (
            "Eligibility checks",
            "Refunds are available only for paid orders that are not cancelled. An order may have only "
            "one active refund request at a time. Duplicate refunds for the same order are not permitted.",
        ),
        (
            "Approval",
            "All refunds require human approval in the support console. Automated systems may create a "
            "pending refund request but must not process payment until a support executive approves.",
        ),
        (
            "High-value orders",
            "Orders of ₹50,000 or more are high-value transactions. They cannot be auto-resolved. "
            "They must be escalated to a human support specialist even if delay-based eligibility is met.",
        ),
        (
            "Auto refund limit",
            "Even when eligible, refunds above ₹5,000 still require human approval and additional review. "
            "The automated copilot must never silently process these amounts.",
        ),
        (
            "Ineligible cases",
            "Refunds are not granted solely because a customer changed their mind after the cancellation "
            "window, or because tracking shows the parcel is still within the promised window.",
        ),
    ],
    "shipping_policy.pdf": [
        ("Shipping Policy", f"Shipping commitments for {COMPANY}."),
        (
            "Standard delivery window",
            "Standard orders are expected to arrive within 5 days of the order date unless a different "
            "expected delivery date is shown on the order record.",
        ),
        (
            "Status meanings",
            "PLACED means the order is accepted. PROCESSING means warehouse work is underway. SHIPPED "
            "means the carrier has the parcel. OUT_FOR_DELIVERY means last-mile is in progress. "
            "DELAYED means the expected date has passed without delivery. DELIVERED means the customer "
            "received the parcel. CANCELLED means the order will not ship.",
        ),
        (
            "Investigating delays",
            "Support executives should inspect expected delivery, actual delivery, and current status "
            "before promising compensation. Do not invent a carrier location if it is not in the order record.",
        ),
        (
            "Missing address data",
            "If shipping address information is missing from the order, the case should be flagged as "
            "missing information and may require escalation.",
        ),
    ],
    "cancellation_policy.pdf": [
        ("Cancellation Policy", f"Order cancellation rules for {COMPANY}."),
        (
            "Cancellation window",
            "Customers may cancel an unpaid or unshipped order within 24 hours of placement. After the "
            "order is SHIPPED or OUT_FOR_DELIVERY, cancellation is not available; a return or refund "
            "request should be evaluated instead.",
        ),
        (
            "Already delivered",
            "Delivered orders cannot be cancelled. Customers may request a replacement or refund under "
            "those separate policies.",
        ),
    ],
    "replacement_policy.pdf": [
        ("Replacement Policy", f"Product replacement rules for {COMPANY}."),
        (
            "Defective items",
            "If an item is delivered damaged or defective, a replacement may be offered within 7 days of "
            "actual delivery, provided the customer has not already received a refund for the same order.",
        ),
        (
            "Wrong item",
            "If the wrong product was delivered, support should open a replacement request and keep the "
            "original ticket open until the replacement ships.",
        ),
    ],
    "customer_support_policy.pdf": [
        ("Customer Support Policy", f"How {COMPANY} support teams should work."),
        (
            "Verified information only",
            "Agents must look up customers, orders, and tickets in business systems. They must not guess "
            "account details, invent policy text, or claim a refund was processed unless the refund record "
            "shows PROCESSED.",
        ),
        (
            "Tone",
            "Responses should be professional, concise, and empathetic. Do not share internal tool names "
            "with customers. Distinguish internal recommendations from customer-facing wording.",
        ),
        (
            "Sensitive actions",
            "Refunds, ticket closures, and account changes require human approval. The copilot proposes; "
            "a support executive decides.",
        ),
    ],
    "escalation_policy.pdf": [
        ("Escalation Policy", f"When {COMPANY} cases must go to a human specialist."),
        (
            "Mandatory escalation",
            "Escalate when: the issue is marked CRITICAL; fraud is suspected; required information is "
            "missing; policy is ambiguous; the customer asks for a human representative; automated "
            "resolution has failed twice; or the order amount is ₹50,000 or higher.",
        ),
        (
            "High-value example",
            "A refund request of ₹80,000 exceeds automated handling and must be escalated. No automatic "
            "refund should occur.",
        ),
        (
            "After escalation",
            "Set ticket status to ESCALATED, record the reason, and stop retrying the same sensitive action.",
        ),
    ],
    "warranty_policy.pdf": [
        ("Warranty Policy", f"Limited warranty for {COMPANY} products."),
        (
            "Coverage period",
            "Most products include a 365-day limited warranty covering manufacturing defects. Accidental "
            "damage, liquid damage, and consumable wear are not covered.",
        ),
        (
            "Claims",
            "Warranty claims require an order number and proof that the item was delivered. Support should "
            "not promise extended coverage that is not in this document.",
        ),
    ],
}


def generate_knowledge_pdfs(output_dir: Path | None = None) -> list[Path]:
    output_dir = output_dir or (ROOT_DIR / "knowledge_base")
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    styles = getSampleStyleSheet()
    for filename, sections in POLICIES.items():
        path = output_dir / filename
        doc = SimpleDocTemplate(str(path), pagesize=A4)
        story = []
        for title, body in sections:
            story.append(Paragraph(title, styles["Heading2"]))
            story.append(Spacer(1, 8))
            story.append(Paragraph(body, styles["BodyText"]))
            story.append(Spacer(1, 16))
        doc.build(story)
        written.append(path)
    return written
