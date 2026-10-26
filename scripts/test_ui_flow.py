import json
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.connection import SessionLocal
from backend.models.ticket import Ticket
from backend.models.order import Order
from backend.models.customer import Customer
from backend.models.audit import PendingAction
from backend.services.approval_service import create_pending_action, list_pending_actions

def main():
    print("=" * 60)
    print("SUPPORTFLOW AI — COMPREHENSIVE END-TO-END UI & API TEST")
    print("=" * 60)

    db = SessionLocal()
    try:
        # Step 1: Ensure an active Pending Action exists for Approvals View
        pending = list_pending_actions(db, status="PENDING_APPROVAL")
        if not pending:
            print("\n[SETUP] Creating a fresh pending action for Approvals testing...")
            t = db.query(Ticket).filter(Ticket.ticket_number == "TKT1023").first()
            o = db.query(Order).filter(Order.order_number == "ORD1001").first()
            c = db.query(Customer).filter(Customer.customer_code == "CUST001").first()
            act = create_pending_action(
                db,
                action_type="REFUND",
                agent_reason="Order ORD1001 delayed by 9 days beyond policy threshold (5 days). Customer eligible for full refund.",
                ticket_id=t.id if t else None,
                customer_id=c.id if c else None,
                order_id=o.id if o else None,
                refund_id="RFD2034",
                policy_evidence=json.dumps({
                    "eligible": True,
                    "delay_days": 9,
                    "threshold_days": 5,
                    "auto_refund_limit": 5000.0,
                    "reasons": ["Order is delayed by 9 day(s); policy threshold is 5 day(s)."]
                }),
                parameters={"order_number": "ORD1001", "amount": 2499.0},
                amount=2499.0,
            )
            print(f"  -> Created pending action: {act.action_id} for {o.order_number} ({c.name})")

        # Step 2: Test All Backend Endpoints powering the UI Views
        print("\n[TEST 1] Verifying all UI View Endpoints...")
        checks = [
            ("Dashboard & Analytics", "http://127.0.0.1:8000/api/analytics"),
            ("Tickets View", "http://127.0.0.1:8000/api/tickets"),
            ("Ticket Detail (TKT1023)", "http://127.0.0.1:8000/api/tickets/TKT1023"),
            ("Customers View", "http://127.0.0.1:8000/api/customers"),
            ("Customer Detail (CUST001)", "http://127.0.0.1:8000/api/customers/CUST001"),
            ("Orders View", "http://127.0.0.1:8000/api/orders"),
            ("Order Detail (ORD1144)", "http://127.0.0.1:8000/api/orders/ORD1144"),
            ("Order Detail (ORD1001)", "http://127.0.0.1:8000/api/orders/ORD1001"),
            ("Approvals Queue", "http://127.0.0.1:8000/api/approvals"),
            ("Knowledge Base", "http://127.0.0.1:8000/api/knowledge/documents"),
            ("Audit Logs", "http://127.0.0.1:8000/api/audit"),
        ]

        for name, url in checks:
            resp = urllib.request.urlopen(url)
            assert resp.status == 200, f"Expected 200 for {name}, got {resp.status}"
            payload = json.loads(resp.read().decode())
            print(f"  [OK] {name}: HTTP {resp.status} OK")

        # Step 3: Validate Specific Order ORD1144 Data (verifying fix for None fields)
        print("\n[TEST 2] Verifying Order ORD1144 Detail Integrity...")
        ord_resp = urllib.request.urlopen("http://127.0.0.1:8000/api/orders/ORD1144")
        ord_data = json.loads(ord_resp.read().decode())
        o_item = ord_data.get("order") or ord_data
        c_item = ord_data.get("customer") or {}

        assert o_item.get("order_number") == "ORD1144", f"Unexpected order_number: {o_item.get('order_number')}"
        assert o_item.get("product_name") == "Nimbus Smartwatch", f"Unexpected product_name: {o_item.get('product_name')}"
        assert o_item.get("status") == "OUT_FOR_DELIVERY", f"Unexpected status: {o_item.get('status')}"
        assert o_item.get("amount") is not None and o_item.get("amount") > 0, "Amount should be positive"
        assert c_item.get("customer_code") == "CUST025", f"Unexpected customer: {c_item.get('customer_code')}"
        assert c_item.get("name") == "Sana Reddy", f"Unexpected customer name: {c_item.get('name')}"
        assert o_item.get("shipping_address") is not None, "Shipping address must not be None"
        print(f"  [OK] Order Number: {o_item['order_number']}")
        print(f"  [OK] Product: {o_item['product_name']}")
        print(f"  [OK] Status: {o_item['status']}")
        print(f"  [OK] Amount: Rs {o_item['amount']}")
        print(f"  [OK] Customer: {c_item['name']} ({c_item['customer_code']})")
        print(f"  [OK] Address: {o_item['shipping_address']}")

        # Step 4: Validate Approvals Queue Data (verifying Ticket, Customer, Order enrichment)
        print("\n[TEST 3] Verifying Approvals Item Entity Enrichment...")
        app_resp = urllib.request.urlopen("http://127.0.0.1:8000/api/approvals")
        app_data = json.loads(app_resp.read().decode())
        assert len(app_data) > 0, "Expected at least 1 pending action in approvals queue"
        first_app = app_data[0]
        print(f"  [OK] Action ID: {first_app.get('action_id')}")
        print(f"  [OK] Ticket: {first_app.get('ticket_number')} - {first_app.get('ticket_subject')}")
        print(f"  [OK] Customer: {first_app.get('customer_name')} ({first_app.get('customer_code')})")
        print(f"  [OK] Order: {first_app.get('order_number')} ({first_app.get('order_product')})")
        print(f"  [OK] Disbursement Amount: Rs {first_app.get('amount')}")
        assert first_app.get("ticket_number") is not None, "ticket_number must be populated"
        assert first_app.get("customer_name") is not None, "customer_name must be populated"
        assert first_app.get("order_number") is not None, "order_number must be populated"

        # Step 5: Test AI Copilot Investigation Endpoint
        print("\n[TEST 4] Testing AI Copilot Investigation API...")
        copilot_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/agent/investigate",
            data=json.dumps({
                "message": "Where is order ORD1001?",
                "session_id": "test-ui-session",
                "requested_by": "exec@supportflow.local"
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        cop_resp = urllib.request.urlopen(copilot_req, timeout=60)
        assert cop_resp.status == 200, f"Copilot failed with status {cop_resp.status}"
        cop_data = json.loads(cop_resp.read().decode())
        print(f"  [OK] Copilot Intent: {cop_data.get('intent')}")
        print(f"  [OK] Copilot Latency: {cop_data.get('latency_ms')} ms")
        print(f"  [OK] Tools Used: {[t.get('tool_name') for t in cop_data.get('tools_used', [])]}")
        print(f"  [OK] Requires Approval: {cop_data.get('requires_approval')}")
        assert cop_data.get("intent") is not None, "Intent should be identified"

        # Step 6: Test Streamlit Web Server Status
        print("\n[TEST 5] Testing Streamlit Frontend Server...")
        st_resp = urllib.request.urlopen("http://127.0.0.1:8501")
        assert st_resp.status == 200, f"Streamlit returned {st_resp.status}"
        print(f"  [OK] Streamlit Server: HTTP {st_resp.status} OK (Port 8501)")

        print("\n" + "=" * 60)
        print("ALL UI TEST PHASES PASSED WITH ZERO ERRORS!")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    main()
