from decimal import Decimal
from datetime import timedelta

from sqlalchemy import select

from tests.conftest import register_and_login
from tests.conftest import TestSession
from app.models import Role, User
from app.models import AuditLog
from app.core.security import create_token
from app.models import Deposit, LedgerEntry, Notification, OperationStatus, Refund, RefundStatus, TransactionLimit, Transfer, Wallet, WalletStatus, utcnow
from app.jobs.pending_transaction_cleanup import cleanup_pending_transactions
from app.jobs.suspicious_transaction_scan import scan_suspicious_transactions
from app.models import SuspiciousTransaction
from app.jobs.failed_transaction_retry import retry_failed_transactions
from app.jobs.daily_limit_reset import reset_daily_limits
from app.services.refund_service import complete_approved_refunds
from app.models import DailyLimitReset


def authorized(token):
    return {"Authorization": f"Bearer {token}"}


def test_deposit_is_atomic_and_idempotent(client):
    token = register_and_login(client, "depositor@example.com")
    wallet_response = client.post("/api/wallets", headers=authorized(token), json={"currency": "INR"})
    assert wallet_response.status_code == 201
    wallet_id = wallet_response.json()["id"]
    headers = {**authorized(token), "Idempotency-Key": "deposit-123"}
    payload = {"amount": "1000.00"}
    first = client.post(f"/api/wallets/{wallet_id}/deposits", headers=headers, json=payload)
    second = client.post(f"/api/wallets/{wallet_id}/deposits", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/api/wallets/{wallet_id}", headers=authorized(token)).json()["available_balance"] == "1000.00"
    assert len(client.get("/api/ledger", headers=authorized(token)).json()) == 1


def test_transaction_history_search_amount_sort_and_pagination(client):
    token = register_and_login(client, "history-search@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    for key, amount in (("history-20", "20.00"), ("history-40", "40.00")):
        response = client.post(
            f"/api/wallets/{wallet_id}/deposits",
            headers={**authorized(token), "Idempotency-Key": key},
            json={"amount": amount},
        )
        assert response.status_code == 201

    filtered = client.get(
        "/api/transactions?type=deposit&min_amount=30&max_amount=50&search=Wallet%20deposit&sort_by=amount&sort_order=asc&page=1&page_size=1",
        headers=authorized(token),
    )
    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 1
    assert filtered.json()["items"][0]["amount"] == "40.00"
    assert filtered.json()["total"] == 1
    completed_detail = client.get(
        f"/api/transactions/{filtered.json()['items'][0]['id']}",
        headers=authorized(token),
    )
    assert completed_detail.status_code == 200
    assert completed_detail.json()["status"] == "COMPLETED"

    openapi = client.get("/openapi.json").json()
    assert (
        openapi["paths"]["/api/transactions"]["get"]["responses"]["200"]["content"]
        ["application/json"]["schema"]["$ref"]
        == "#/components/schemas/TransactionHistoryOut"
    )

    invalid_range = client.get(
        "/api/transactions?min_amount=50&max_amount=10",
        headers=authorized(token),
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["error"]["code"] == "INVALID_TRANSACTION_FILTER"

    invalid_type = client.get(
        "/api/transactions?type=NOT_A_TRANSACTION_TYPE",
        headers=authorized(token),
    )
    assert invalid_type.status_code == 422
    assert invalid_type.json()["error"]["code"] == "INVALID_TRANSACTION_TYPE"


def test_transaction_history_includes_non_ledger_operation_statuses(client):
    sender_token = register_and_login(client, "history-sender@example.com")
    receiver_token = register_and_login(client, "history-receiver@example.com")
    sender_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    receiver_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(receiver_token),
        json={"currency": "INR"},
    ).json()["id"]

    with TestSession() as session:
        sender = session.scalar(
            select(User).where(User.email == "history-sender@example.com")
        )
        receiver = session.scalar(
            select(User).where(User.email == "history-receiver@example.com")
        )
        session.add(
            Deposit(
                wallet_id=sender_wallet_id,
                user_id=sender.id,
                amount=Decimal("25.00"),
                currency="INR",
                status=OperationStatus.FAILED,
            )
        )
        session.add(
            Transfer(
                sender_wallet_id=sender_wallet_id,
                receiver_wallet_id=receiver_wallet_id,
                user_id=sender.id,
                amount=Decimal("15.00"),
                currency="INR",
                status=OperationStatus.FAILED,
            )
        )
        session.commit()

    failed_deposits = client.get(
        "/api/transactions?type=deposit&status=failed",
        headers=authorized(sender_token),
    )
    assert failed_deposits.status_code == 200
    assert failed_deposits.json()["total"] == 1
    assert failed_deposits.json()["items"][0]["status"] == "FAILED"
    assert failed_deposits.json()["items"][0]["balance_before"] is None
    failed_deposit_id = failed_deposits.json()["items"][0]["id"]
    failed_deposit_detail = client.get(
        f"/api/transactions/{failed_deposit_id}",
        headers=authorized(sender_token),
    )
    assert failed_deposit_detail.status_code == 200
    assert failed_deposit_detail.json()["status"] == "FAILED"

    failed_incoming_transfers = client.get(
        "/api/transactions?type=transfer&status=failed",
        headers=authorized(receiver_token),
    )
    assert failed_incoming_transfers.status_code == 200
    assert failed_incoming_transfers.json()["total"] == 1
    assert failed_incoming_transfers.json()["items"][0]["transaction_type"] == "TRANSFER_CREDIT"
    assert failed_incoming_transfers.json()["items"][0]["wallet_id"] == receiver_wallet_id
    failed_transfer_id = failed_incoming_transfers.json()["items"][0]["id"]
    failed_transfer_detail = client.get(
        f"/api/transactions/{failed_transfer_id}",
        headers=authorized(receiver_token),
    )
    assert failed_transfer_detail.status_code == 200
    assert failed_transfer_detail.json()["transaction_type"] == "TRANSFER_CREDIT"
    assert failed_transfer_detail.json()["wallet_id"] == receiver_wallet_id


def test_insufficient_transfer_does_not_debit_sender(client):
    sender_token = register_and_login(client, "sender@example.com")
    receiver_token = register_and_login(client, "receiver@example.com")
    sender_id = client.post("/api/wallets", headers=authorized(sender_token), json={"currency": "INR"}).json()["id"]
    receiver_id = client.post("/api/wallets", headers=authorized(receiver_token), json={"currency": "INR"}).json()["id"]
    client.post(f"/api/wallets/{sender_id}/deposits", headers={**authorized(sender_token), "Idempotency-Key": "fund-sender"}, json={"amount": "1000.00"})
    response = client.post("/api/transfers", headers={**authorized(sender_token), "Idempotency-Key": "overspend"}, json={
        "sender_wallet_id": sender_id, "receiver_wallet_id": receiver_id, "amount": "1000.01",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert client.get(f"/api/wallets/{sender_id}", headers=authorized(sender_token)).json()["available_balance"] == "1000.00"
    assert client.get(f"/api/wallets/{receiver_id}", headers=authorized(receiver_token)).json()["available_balance"] == "0.00"
    sender_notifications = client.get(
        "/api/notifications",
        headers=authorized(sender_token),
    ).json()
    assert any(item["event"] == "TRANSFER_FAILED" for item in sender_notifications)
    with TestSession() as db:
        sender_user = db.scalar(select(User).where(User.email == "sender@example.com"))
        blocked_event = db.scalar(
            select(AuditLog).where(
                AuditLog.user_id == sender_user.id,
                AuditLog.action == "TRANSACTION_BLOCKED",
                AuditLog.entity == "TRANSFER",
            )
        )
        assert blocked_event is not None
        assert blocked_event.ip_address == "testclient"
        assert blocked_event.metadata_json["error_code"] == "INSUFFICIENT_BALANCE"


def test_transfer_rejects_frozen_receiver_and_currency_mismatch(client):
    sender_token = register_and_login(client, "transfer-rules-sender@example.com")
    frozen_token = register_and_login(client, "transfer-rules-frozen@example.com")
    other_currency_token = register_and_login(client, "transfer-rules-currency@example.com")
    sender_wallet = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    frozen_wallet = client.post(
        "/api/wallets",
        headers=authorized(frozen_token),
        json={"currency": "INR"},
    ).json()["id"]
    usd_wallet = client.post(
        "/api/wallets",
        headers=authorized(other_currency_token),
        json={"currency": "USD"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{sender_wallet}/deposits",
        headers={**authorized(sender_token), "Idempotency-Key": "transfer-rules-fund"},
        json={"amount": "50.00"},
    )
    client.post(f"/api/wallets/{frozen_wallet}/freeze", headers=authorized(frozen_token))

    frozen_transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "transfer-rules-frozen"},
        json={
            "sender_wallet_id": sender_wallet,
            "receiver_wallet_id": frozen_wallet,
            "amount": "10.00",
        },
    )
    assert frozen_transfer.status_code == 409
    assert frozen_transfer.json()["error"]["code"] == "WALLET_FROZEN"

    currency_transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "transfer-rules-currency"},
        json={
            "sender_wallet_id": sender_wallet,
            "receiver_wallet_id": usd_wallet,
            "amount": "10.00",
        },
    )
    assert currency_transfer.status_code == 400
    assert currency_transfer.json()["error"]["code"] == "INVALID_TRANSFER"
    assert client.get(
        f"/api/wallets/{sender_wallet}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "50.00"


def test_blocking_reviewed_suspicious_transfer_reverses_funds(client):
    sender_token = register_and_login(client, "risk-reverse-sender@example.com")
    receiver_token = register_and_login(client, "risk-reverse-receiver@example.com")
    sender_id = client.get("/api/auth/me", headers=authorized(sender_token)).json()["id"]
    sender_wallet = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    receiver_wallet = client.post(
        "/api/wallets",
        headers=authorized(receiver_token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{sender_wallet}/deposits",
        headers={**authorized(sender_token), "Idempotency-Key": "risk-reverse-fund"},
        json={"amount": "100.00"},
    )
    with TestSession() as db:
        limits = db.get(TransactionLimit, 1)
        limits.suspicious_amount_threshold = Decimal("50.00")
        admin = db.get(User, sender_id)
        admin.role = Role.ADMIN
        db.commit()
    transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "risk-reverse-transfer"},
        json={
            "sender_wallet_id": sender_wallet,
            "receiver_wallet_id": receiver_wallet,
            "amount": "60.00",
        },
    )
    assert transfer.status_code == 201
    admin_token = client.post(
        "/api/auth/login",
        json={"email": "risk-reverse-sender@example.com", "password": "SecureTest123!"},
    ).json()["access_token"]
    flagged = client.get(
        "/api/admin/suspicious-transactions",
        headers=authorized(admin_token),
    ).json()
    record = next(item for item in flagged if item["transfer_id"] == transfer.json()["id"])
    reviewed = client.post(
        f"/api/admin/suspicious-transactions/{record['id']}/review",
        headers=authorized(admin_token),
        json={"status": "BLOCKED"},
    )

    assert reviewed.status_code == 200
    blocked_transfer = client.get(
        f"/api/transfers/{transfer.json()['id']}",
        headers=authorized(sender_token),
    ).json()
    assert blocked_transfer["status"] == "COMPLETED"
    assert blocked_transfer["reversed_at"] is not None
    assert client.get(
        f"/api/wallets/{sender_wallet}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "100.00"
    assert client.get(
        f"/api/wallets/{receiver_wallet}",
        headers=authorized(receiver_token),
    ).json()["available_balance"] == "0.00"
    reversal_entries = client.get(
        "/api/transactions?type=REVERSAL",
        headers=authorized(sender_token),
    ).json()["items"]
    assert len(reversal_entries) == 2
    assert {entry["reference_id"] for entry in reversal_entries} == {transfer.json()["id"]}


def test_customer_dashboard_reports_balances_by_currency(client):
    token = register_and_login(client, "dashboard-customer@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{wallet_id}/deposits",
        headers={**authorized(token), "Idempotency-Key": "dashboard-fund"},
        json={"amount": "125.00"},
    )

    response = client.get("/api/dashboards/customer", headers=authorized(token))

    assert response.status_code == 200
    assert {
        "wallets",
        "wallet_balance",
        "recent_transactions",
        "total_deposits",
        "total_transfers",
        "total_withdrawals",
        "pending_transactions",
    } <= response.json().keys()
    assert response.json()["wallet_balance"]["INR"] == {
        "available_balance": 125.0,
        "pending_balance": 0.0,
    }


def test_dashboard_role_contracts_and_error_response_shapes(client):
    customer_token = register_and_login(client, "dashboard-contract@example.com")
    customer_id = client.get(
        "/api/auth/me",
        headers=authorized(customer_token),
    ).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == customer_id)).role = Role.ADMIN
        db.commit()
    admin_token = client.post(
        "/api/auth/login",
        json={"email": "dashboard-contract@example.com", "password": "SecureTest123!"},
    ).json()["access_token"]

    admin = client.get("/api/dashboards/admin", headers=authorized(admin_token))
    assert admin.status_code == 200
    assert {
        "total_users",
        "active_wallets",
        "total_wallet_balance",
        "wallet_balances_by_currency",
        "today_transactions",
        "today_transaction_volume",
        "failed_transactions",
        "suspicious_transactions",
    } <= admin.json().keys()

    support_token = register_and_login(client, "dashboard-support@example.com")
    support_id = client.get(
        "/api/auth/me",
        headers=authorized(support_token),
    ).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == support_id)).role = Role.SUPPORT_AGENT
        db.commit()
    support_token = client.post(
        "/api/auth/login",
        json={"email": "dashboard-support@example.com", "password": "SecureTest123!"},
    ).json()["access_token"]
    support = client.get("/api/dashboards/support", headers=authorized(support_token))
    assert support.status_code == 200
    assert {
        "pending_reviews",
        "suspicious_transactions",
        "failed_transactions",
        "refund_requests",
        "frozen_wallets",
    } <= support.json().keys()

    response = client.post("/api/wallets", headers=authorized(admin_token), json={"currency": "??"})
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "FORBIDDEN"

    invalid_registration = client.post(
        "/api/auth/register",
        json={
            "email": "not-an-email",
            "full_name": "Test Customer",
            "password": "valid-password-123",
        },
    )
    assert invalid_registration.status_code == 422
    assert "valid-password-123" not in invalid_registration.text

    unknown_route = client.get("/api/not-a-real-route")
    assert unknown_route.status_code == 404
    assert unknown_route.json()["success"] is False
    assert unknown_route.json()["error"]["code"] == "NOT_FOUND"


def test_failed_login_audit_records_action_and_ip(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "not-registered@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    with TestSession() as db:
        record = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "LOGIN_FAILED",
                AuditLog.entity_id.is_(None),
            )
        )
        assert record is not None
        assert record.ip_address == "testclient"


def test_swagger_uses_bearer_token_for_current_user(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert schema["paths"]["/api/auth/me"]["get"]["security"] == [{"HTTPBearer": []}]

    token = register_and_login(client, "swagger-bearer@example.com")
    response = client.get("/api/auth/me", headers=authorized(token))
    assert response.status_code == 200
    assert response.json()["email"] == "swagger-bearer@example.com"


def test_invalid_credentials_and_expired_access_tokens_are_rejected(client):
    invalid_login = client.post(
        "/api/auth/login",
        json={"email": "missing-user@example.com", "password": "wrong"},
    )
    assert invalid_login.status_code == 401
    assert invalid_login.json()["error"]["code"] == "INVALID_CREDENTIALS"

    expired_token, _, _ = create_token(
        "nonexistent-user",
        "access",
        timedelta(seconds=-1),
    )
    expired_response = client.get(
        "/api/auth/me",
        headers=authorized(expired_token),
    )
    assert expired_response.status_code == 401
    assert expired_response.json()["error"]["code"] == "UNAUTHORIZED"


def test_notification_reads_are_owned_and_mutated_through_service(client):
    token = register_and_login(client, "notifications@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{wallet_id}/deposits",
        headers={**authorized(token), "Idempotency-Key": "notification-deposit-1"},
        json={"amount": "10.00"},
    )
    client.post(
        f"/api/wallets/{wallet_id}/deposits",
        headers={**authorized(token), "Idempotency-Key": "notification-deposit-2"},
        json={"amount": "20.00"},
    )

    notifications = client.get("/api/notifications", headers=authorized(token))
    assert notifications.status_code == 200
    assert len(notifications.json()) == 2
    first_id = notifications.json()[0]["id"]
    marked = client.patch(
        f"/api/notifications/{first_id}/read",
        headers=authorized(token),
    )
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    all_read = client.patch(
        "/api/notifications/read-all",
        headers=authorized(token),
    )
    assert all_read.status_code == 200
    assert all(item["is_read"] for item in client.get(
        "/api/notifications",
        headers=authorized(token),
    ).json())


def test_expired_pending_deposit_uses_specific_failure_audit_and_notification(client):
    token = register_and_login(client, "pending-cleanup@example.com")
    user_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    with TestSession() as db:
        deposit = Deposit(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=Decimal("12.00"),
            currency="INR",
            status=OperationStatus.PROCESSING,
            created_at=utcnow() - timedelta(days=2),
        )
        db.add(deposit)
        db.commit()
        deposit_id = deposit.id
        assert cleanup_pending_transactions(db) == 1

    with TestSession() as db:
        assert db.get(Deposit, deposit_id).status == OperationStatus.FAILED
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "DEPOSIT_FAILED",
                AuditLog.entity_id == deposit_id,
            )
        )
        notification = db.scalar(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.event == "DEPOSIT_FAILED",
            )
        )
        assert notification is not None


def test_scheduled_risk_scan_flags_large_deposit_once(client):
    token = register_and_login(client, "risk-scan-deposit@example.com")
    user_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    with TestSession() as db:
        db.add(TransactionLimit(id=1, suspicious_amount_threshold=Decimal("10.00")))
        db.commit()
    deposit = client.post(
        f"/api/wallets/{wallet_id}/deposits",
        headers={**authorized(token), "Idempotency-Key": "risk-scan-deposit"},
        json={"amount": "25.00"},
    )
    assert deposit.status_code == 201
    with TestSession() as db:
        assert scan_suspicious_transactions(db) == 1
        assert scan_suspicious_transactions(db) == 0
        event = db.scalar(
            select(SuspiciousTransaction).where(
                SuspiciousTransaction.operation_type == "DEPOSIT",
                SuspiciousTransaction.operation_id == deposit.json()["id"],
            )
        )
        assert event is not None
        assert event.user_id == user_id
        assert event.wallet_id == wallet_id
        assert event.amount == Decimal("25.00")
        assert event.status.value == "REVIEW_REQUIRED"


def test_cleanup_marks_stale_refund_failed_and_notifies_requester(client):
    token = register_and_login(client, "stale-refund@example.com")
    user_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{wallet_id}/deposits",
        headers={**authorized(token), "Idempotency-Key": "stale-refund-deposit"},
        json={"amount": "20.00"},
    )
    with TestSession() as db:
        ledger_entry = db.scalar(
            select(LedgerEntry).where(LedgerEntry.wallet_id == wallet_id)
        )
        refund = Refund(
            ledger_entry_id=ledger_entry.id,
            wallet_id=wallet_id,
            user_id=user_id,
            amount=Decimal("10.00"),
            status=RefundStatus.UNDER_REVIEW,
            created_at=utcnow() - timedelta(days=2),
        )
        db.add(refund)
        db.commit()
        refund_id = refund.id
        assert cleanup_pending_transactions(db) == 1
        assert db.get(Refund, refund_id).status == RefundStatus.FAILED
        assert db.scalar(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.event == "REFUND_FAILED",
            )
        )


def test_daily_limit_reset_is_persisted_and_idempotent(client):
    with TestSession() as db:
        first = reset_daily_limits(db)
        second = reset_daily_limits(db)
        assert first["already_reset"] is False
        assert second["already_reset"] is True
        assert first["reset_date"] == second["reset_date"]
        assert first["reset_at"] == second["reset_at"]
        assert first["strategy"] == "UTC_CALENDAR_DAY"
        assert db.query(DailyLimitReset).count() == 1


def test_scheduled_risk_scan_detects_frequency_across_operation_types(client):
    token = register_and_login(client, "risk-scan-frequency@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    with TestSession() as db:
        db.add(TransactionLimit(id=1, suspicious_amount_threshold=Decimal("1000.00")))
        db.commit()

    for index in range(2):
        response = client.post(
            f"/api/wallets/{wallet_id}/deposits",
            headers={**authorized(token), "Idempotency-Key": f"risk-frequency-deposit-{index}"},
            json={"amount": "10.00"},
        )
        assert response.status_code == 201
    for index in range(3):
        response = client.post(
            f"/api/wallets/{wallet_id}/withdrawals",
            headers={**authorized(token), "Idempotency-Key": f"risk-frequency-withdrawal-{index}"},
            json={"amount": "1.00"},
        )
        assert response.status_code == 201

    with TestSession() as db:
        assert scan_suspicious_transactions(db) == 1
        events = db.scalars(
            select(SuspiciousTransaction).where(
                SuspiciousTransaction.user_id
                == client.get("/api/auth/me", headers=authorized(token)).json()["id"],
                SuspiciousTransaction.reason.like("%five financial operations%"),
            )
        ).all()
        assert len(events) == 1
        assert events[0].operation_type == "WITHDRAWAL"


def test_failed_transaction_retry_respects_wallet_state_and_posts_ledger(client):
    token = register_and_login(client, "retry-failed-deposit@example.com")
    user_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    with TestSession() as db:
        deposit = Deposit(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=Decimal("15.00"),
            currency="INR",
            status=OperationStatus.FAILED,
        )
        db.add(deposit)
        db.commit()
        deposit_id = deposit.id
        wallet = db.get(Wallet, wallet_id)
        wallet.status = WalletStatus.FROZEN
        db.commit()
        assert retry_failed_transactions(db) == 0
        assert db.get(Deposit, deposit_id).status == OperationStatus.FAILED
        wallet.status = WalletStatus.ACTIVE
        db.commit()
        assert retry_failed_transactions(db) == 1

    with TestSession() as db:
        assert db.get(Deposit, deposit_id).status == OperationStatus.COMPLETED
        assert db.get(Wallet, wallet_id).available_balance == Decimal("15.00")
        entries = db.scalars(
            select(LedgerEntry).where(LedgerEntry.reference_id == deposit_id)
        ).all()
        assert len(entries) == 1


def test_withdrawal_debits_wallet_and_writes_ledger(client):
    token = register_and_login(client, "withdrawal@example.com")
    wallet_id = client.post("/api/wallets", headers=authorized(token), json={"currency": "INR"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", headers={**authorized(token), "Idempotency-Key": "withdraw-fund"}, json={"amount": "100.00"})
    response = client.post(f"/api/wallets/{wallet_id}/withdrawals", headers={**authorized(token), "Idempotency-Key": "withdraw-30"}, json={"amount": "30.00"})
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"
    assert client.get(f"/api/wallets/{wallet_id}", headers=authorized(token)).json()["available_balance"] == "70.00"
    ledger = client.get(f"/api/wallets/{wallet_id}/ledger", headers=authorized(token)).json()
    assert len(ledger) == 2
    assert any(entry["transaction_type"] == "WITHDRAWAL" for entry in ledger)


def test_withdrawal_idempotency_does_not_debit_twice(client):
    token = register_and_login(client, "withdrawal-retry@example.com")
    wallet_id = client.post("/api/wallets", headers=authorized(token), json={"currency": "INR"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", headers={**authorized(token), "Idempotency-Key": "withdraw-retry-fund"}, json={"amount": "100.00"})
    headers = {**authorized(token), "Idempotency-Key": "withdraw-retry"}
    payload = {"amount": "40.00"}
    first = client.post(f"/api/wallets/{wallet_id}/withdrawals", headers=headers, json=payload)
    second = client.post(f"/api/wallets/{wallet_id}/withdrawals", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/api/wallets/{wallet_id}", headers=authorized(token)).json()["available_balance"] == "60.00"


def test_completed_withdrawal_cancellation_reverses_balance_and_is_single_use(client):
    token = register_and_login(client, "withdrawal-cancel@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{wallet_id}/deposits",
        headers={**authorized(token), "Idempotency-Key": "withdrawal-cancel-fund"},
        json={"amount": "100.00"},
    )
    withdrawal = client.post(
        f"/api/wallets/{wallet_id}/withdrawals",
        headers={**authorized(token), "Idempotency-Key": "withdrawal-cancel-create"},
        json={"amount": "30.00"},
    )
    assert withdrawal.status_code == 201
    assert client.get(
        f"/api/wallets/{wallet_id}",
        headers=authorized(token),
    ).json()["available_balance"] == "70.00"

    cancelled = client.post(
        f"/api/withdrawals/{withdrawal.json()['id']}/cancel",
        headers=authorized(token),
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert client.get(
        f"/api/wallets/{wallet_id}",
        headers=authorized(token),
    ).json()["available_balance"] == "100.00"
    ledger = client.get(
        "/api/transactions?type=REVERSAL",
        headers=authorized(token),
    ).json()["items"]
    assert len(ledger) == 1
    assert ledger[0]["reference_entity"] == "WITHDRAWAL"
    assert ledger[0]["reference_id"] == withdrawal.json()["id"]
    repeated = client.post(
        f"/api/withdrawals/{withdrawal.json()['id']}/cancel",
        headers=authorized(token),
    )
    assert repeated.status_code == 409


def test_freeze_blocks_withdrawal_and_idempotency_mismatch_conflicts(client):
    token = register_and_login(client, "walletowner@example.com")
    wallet_id = client.post("/api/wallets", headers=authorized(token), json={"currency": "INR"}).json()["id"]
    headers = {**authorized(token), "Idempotency-Key": "same-key"}
    client.post(f"/api/wallets/{wallet_id}/deposits", headers=headers, json={"amount": "100.00"})
    changed = client.post(f"/api/wallets/{wallet_id}/deposits", headers=headers, json={"amount": "200.00"})
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "DUPLICATE_IDEMPOTENCY_KEY"
    assert client.post(f"/api/wallets/{wallet_id}/freeze", headers=authorized(token)).status_code == 200
    withdrawal = client.post(f"/api/wallets/{wallet_id}/withdrawals", headers={**authorized(token), "Idempotency-Key": "withdraw-frozen"}, json={"amount": "10.00"})
    assert withdrawal.status_code == 409
    assert withdrawal.json()["error"]["code"] == "WALLET_FROZEN"


def test_wallet_status_patch_is_admin_only_but_freeze_routes_remain_available(client):
    customer_token = register_and_login(client, "wallet-status-customer@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(customer_token),
        json={"currency": "INR"},
    ).json()["id"]

    customer_patch = client.patch(
        f"/api/wallets/{wallet_id}",
        headers=authorized(customer_token),
        json={"status": "FROZEN"},
    )
    assert customer_patch.status_code == 403
    assert client.post(
        f"/api/wallets/{wallet_id}/freeze",
        headers=authorized(customer_token),
    ).status_code == 200
    assert client.post(
        f"/api/wallets/{wallet_id}/unfreeze",
        headers=authorized(customer_token),
    ).status_code == 200

    support_token = register_and_login(client, "wallet-status-support@example.com")
    support_id = client.get(
        "/api/auth/me",
        headers=authorized(support_token),
    ).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == support_id)).role = Role.SUPPORT_AGENT
        db.commit()
    support_token = client.post(
        "/api/auth/login",
        json={
            "email": "wallet-status-support@example.com",
            "password": "SecureTest123!",
        },
    ).json()["access_token"]

    support_patch = client.patch(
        f"/api/wallets/{wallet_id}",
        headers=authorized(support_token),
        json={"status": "SUSPENDED"},
    )
    assert support_patch.status_code == 403
    assert client.post(
        f"/api/wallets/{wallet_id}/freeze",
        headers=authorized(support_token),
    ).status_code == 200


def test_wallet_ownership_is_enforced(client):
    owner = register_and_login(client, "owner@example.com")
    other = register_and_login(client, "other@example.com")
    wallet_id = client.post("/api/wallets", headers=authorized(owner), json={"currency": "INR"}).json()["id"]
    response = client.get(f"/api/wallets/{wallet_id}", headers=authorized(other))
    assert response.status_code == 403


def test_transfer_is_replayed_once_and_credits_both_wallets(client):
    sender_token = register_and_login(client, "sender2@example.com")
    receiver_token = register_and_login(client, "receiver2@example.com")
    sender_id = client.post("/api/wallets", headers=authorized(sender_token), json={"currency": "INR"}).json()["id"]
    receiver_id = client.post("/api/wallets", headers=authorized(receiver_token), json={"currency": "INR"}).json()["id"]
    client.post(f"/api/wallets/{sender_id}/deposits", headers={**authorized(sender_token), "Idempotency-Key": "fund-2"}, json={"amount": "100.00"})
    headers = {**authorized(sender_token), "Idempotency-Key": "transfer-2"}
    payload = {"sender_wallet_id": sender_id, "receiver_wallet_id": receiver_id, "amount": "30.00"}
    first = client.post("/api/transfers", headers=headers, json=payload)
    second = client.post("/api/transfers", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/api/wallets/{sender_id}", headers=authorized(sender_token)).json()["available_balance"] == "70.00"
    assert client.get(f"/api/wallets/{receiver_id}", headers=authorized(receiver_token)).json()["available_balance"] == "30.00"


def test_completed_transfer_cannot_be_cancelled(client):
    sender_token = register_and_login(client, "cancel-sender@example.com")
    receiver_token = register_and_login(client, "cancel-receiver@example.com")
    sender_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    receiver_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(receiver_token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{sender_wallet_id}/deposits",
        headers={**authorized(sender_token), "Idempotency-Key": "cancel-fund"},
        json={"amount": "100.00"},
    )
    transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "cancel-transfer"},
        json={
            "sender_wallet_id": sender_wallet_id,
            "receiver_wallet_id": receiver_wallet_id,
            "amount": "40.00",
        },
    )
    assert transfer.status_code == 201
    assert transfer.json()["status"] == "COMPLETED"
    assert transfer.json()["reversed_at"] is None

    cancellation = client.post(
        f"/api/transfers/{transfer.json()['id']}/cancel",
        headers=authorized(sender_token),
    )

    assert cancellation.status_code == 409
    assert cancellation.json()["error"]["code"] == "INVALID_TRANSACTION_STATE"
    transfer_detail = client.get(
        f"/api/transfers/{transfer.json()['id']}",
        headers=authorized(sender_token),
    ).json()
    assert transfer_detail["status"] == "COMPLETED"
    assert transfer_detail["reversed_at"] is None
    assert client.get(
        f"/api/wallets/{sender_wallet_id}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "60.00"
    assert client.get(
        f"/api/wallets/{receiver_wallet_id}",
        headers=authorized(receiver_token),
    ).json()["available_balance"] == "40.00"
    ledger = client.get(
        "/api/transactions?type=REVERSAL",
        headers=authorized(sender_token),
    ).json()["items"]
    assert ledger == []


def test_pending_and_processing_transfers_can_be_cancelled(client):
    sender_token = register_and_login(client, "cancel-state-sender@example.com")
    receiver_token = register_and_login(client, "cancel-state-receiver@example.com")
    sender = client.get("/api/auth/me", headers=authorized(sender_token)).json()
    sender_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    receiver_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(receiver_token),
        json={"currency": "INR"},
    ).json()["id"]
    transfers = []
    with TestSession() as db:
        for status in (OperationStatus.PENDING, OperationStatus.PROCESSING):
            transfer = Transfer(
                sender_wallet_id=sender_wallet_id,
                receiver_wallet_id=receiver_wallet_id,
                user_id=sender["id"],
                amount=Decimal("10.00"),
                currency="INR",
                status=status,
            )
            db.add(transfer)
            db.flush()
            transfers.append((transfer.id, status.value))
        db.commit()

    assert [status for _, status in transfers] == ["PENDING", "PROCESSING"]
    for transfer_id, _ in transfers:
        response = client.post(
            f"/api/transfers/{transfer_id}/cancel",
            headers=authorized(sender_token),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"


def test_completed_transfer_cannot_be_cancelled_after_receiver_spends_funds(client):
    sender_token = register_and_login(client, "spent-sender@example.com")
    receiver_token = register_and_login(client, "spent-receiver@example.com")
    third_party_token = register_and_login(client, "spent-third-party@example.com")
    sender_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    receiver_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(receiver_token),
        json={"currency": "INR"},
    ).json()["id"]
    third_party_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(third_party_token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{sender_wallet_id}/deposits",
        headers={**authorized(sender_token), "Idempotency-Key": "spent-fund"},
        json={"amount": "100.00"},
    )
    transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "spent-transfer"},
        json={
            "sender_wallet_id": sender_wallet_id,
            "receiver_wallet_id": receiver_wallet_id,
            "amount": "40.00",
        },
    )
    spend = client.post(
        "/api/transfers",
        headers={**authorized(receiver_token), "Idempotency-Key": "spent-receiver-transfer"},
        json={
            "sender_wallet_id": receiver_wallet_id,
            "receiver_wallet_id": third_party_wallet_id,
            "amount": "40.00",
        },
    )
    assert spend.status_code == 201

    cancellation = client.post(
        f"/api/transfers/{transfer.json()['id']}/cancel",
        headers=authorized(sender_token),
    )

    assert cancellation.status_code == 409
    assert cancellation.json()["error"]["code"] == "INVALID_TRANSACTION_STATE"
    assert client.get(
        f"/api/wallets/{sender_wallet_id}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "60.00"
    assert client.get(
        f"/api/wallets/{receiver_wallet_id}",
        headers=authorized(receiver_token),
    ).json()["available_balance"] == "0.00"
    assert client.get(
        f"/api/transfers/{transfer.json()['id']}",
        headers=authorized(sender_token),
    ).json()["status"] == "COMPLETED"


def test_refresh_token_rotation_and_logout_revocation(client):
    client.post("/api/auth/register", json={
        "email": "refresh@example.com", "full_name": "Refresh Test", "password": "SecureTest123!",
    })
    login = client.post("/api/auth/login", json={"email": "refresh@example.com", "password": "SecureTest123!"}).json()
    rotated = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != login["refresh_token"]
    assert client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    logout = client.post(
        "/api/auth/logout",
        headers=authorized(rotated.json()["access_token"]),
    )
    assert logout.status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 401


def test_logout_without_refresh_token_revokes_access_and_refresh_tokens(client):
    client.post("/api/auth/register", json={
        "email": "logout-all@example.com",
        "full_name": "Logout All",
        "password": "SecureTest123!",
    })
    tokens = client.post("/api/auth/login", json={
        "email": "logout-all@example.com",
        "password": "SecureTest123!",
    }).json()

    response = client.post(
        "/api/auth/logout",
        headers=authorized(tokens["access_token"]),
    )

    assert response.status_code == 200
    logout_operation = client.get("/openapi.json").json()["paths"]["/api/auth/logout"]["post"]
    assert "requestBody" not in logout_operation
    assert client.get(
        "/api/auth/me",
        headers=authorized(tokens["access_token"]),
    ).status_code == 401
    assert client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    ).status_code == 401


def test_password_change_revokes_existing_access_and_refresh_tokens(client):
    client.post("/api/auth/register", json={
        "email": "password-revoke@example.com",
        "full_name": "Password Revoke",
        "password": "SecureTest123!",
    })
    tokens = client.post("/api/auth/login", json={
        "email": "password-revoke@example.com",
        "password": "SecureTest123!",
    }).json()

    response = client.post(
        "/api/auth/change-password",
        headers=authorized(tokens["access_token"]),
        json={
            "current_password": "SecureTest123!",
            "new_password": "AnotherSecure123!",
        },
    )

    assert response.status_code == 200
    assert client.get(
        "/api/auth/me",
        headers=authorized(tokens["access_token"]),
    ).status_code == 401
    assert client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    ).status_code == 401
    assert client.post("/api/auth/login", json={
        "email": "password-revoke@example.com",
        "password": "AnotherSecure123!",
    }).status_code == 200


def test_wallet_close_is_admin_only_through_all_routes(client):
    support_token = register_and_login(client, "support-wallet@example.com")
    support_user_id = client.get(
        "/api/auth/me",
        headers=authorized(support_token),
    ).json()["id"]
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(support_token),
        json={"currency": "INR"},
    ).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == support_user_id)).role = Role.SUPPORT_AGENT
        db.commit()
    support_token = client.post("/api/auth/login", json={
        "email": "support-wallet@example.com",
        "password": "SecureTest123!",
    }).json()["access_token"]

    patch_response = client.patch(
        f"/api/wallets/{wallet_id}",
        headers=authorized(support_token),
        json={"status": "CLOSED"},
    )
    close_response = client.post(
        f"/api/wallets/{wallet_id}/close",
        headers=authorized(support_token),
    )

    assert patch_response.status_code == 403
    assert close_response.status_code == 403

    with TestSession() as db:
        db.scalar(select(User).where(User.id == support_user_id)).role = Role.ADMIN
        db.commit()
    admin_token = client.post("/api/auth/login", json={
        "email": "support-wallet@example.com",
        "password": "SecureTest123!",
    }).json()["access_token"]
    assert client.post(
        f"/api/wallets/{wallet_id}/close",
        headers=authorized(admin_token),
    ).status_code == 200


def test_admin_routes_reject_customer_and_support_roles(client):
    customer_token = register_and_login(client, "rbac-customer@example.com")
    assert client.get(
        "/api/admin/transaction-limits",
        headers=authorized(customer_token),
    ).status_code == 403

    customer_id = client.get(
        "/api/auth/me",
        headers=authorized(customer_token),
    ).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == customer_id)).role = Role.SUPPORT_AGENT
        db.commit()
    support_token = client.post("/api/auth/login", json={
        "email": "rbac-customer@example.com",
        "password": "SecureTest123!",
    }).json()["access_token"]
    assert client.get(
        "/api/admin/transaction-limits",
        headers=authorized(support_token),
    ).status_code == 403

    with TestSession() as db:
        db.scalar(select(User).where(User.id == customer_id)).role = Role.ADMIN
        db.commit()
    admin_token = client.post("/api/auth/login", json={
        "email": "rbac-customer@example.com",
        "password": "SecureTest123!",
    }).json()["access_token"]
    assert client.get(
        "/api/admin/transaction-limits",
        headers=authorized(admin_token),
    ).status_code == 200


def test_role_assignment_rejects_invalid_role_with_domain_error(client):
    token = register_and_login(client, "role-validation-admin@example.com")
    admin_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == admin_id)).role = Role.SUPER_ADMIN
        db.commit()
    admin_token = client.post(
        "/api/auth/login",
        json={
            "email": "role-validation-admin@example.com",
            "password": "SecureTest123!",
        },
    ).json()["access_token"]
    target = register_and_login(client, "role-validation-target@example.com")
    target_id = client.get("/api/auth/me", headers=authorized(target)).json()["id"]

    openapi = client.get("/openapi.json").json()
    request_schema = openapi["paths"]["/api/users/{user_id}/role"]["patch"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    role_schema = openapi["components"]["schemas"][request_schema["$ref"].split("/")[-1]]
    assert role_schema["properties"].keys() == {"role"}
    assert role_schema["example"] == {"role": "admin"}

    assigned = client.patch(
        f"/api/users/{target_id}/role",
        headers=authorized(admin_token),
        json={"role": "admin"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["role"] == "ADMIN"

    response = client.patch(
        f"/api/users/{target_id}/role",
        headers=authorized(admin_token),
        json={"role": "NOT_A_ROLE"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ROLE"


def test_user_patch_only_updates_email_and_full_name(client):
    admin_token = register_and_login(client, "user-patch-admin@example.com")
    admin_id = client.get("/api/auth/me", headers=authorized(admin_token)).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == admin_id)).role = Role.ADMIN
        db.commit()
    admin_token = client.post(
        "/api/auth/login",
        json={
            "email": "user-patch-admin@example.com",
            "password": "SecureTest123!",
        },
    ).json()["access_token"]

    customer_token = register_and_login(client, "user-patch-customer@example.com")
    customer = client.get(
        "/api/auth/me",
        headers=authorized(customer_token),
    ).json()
    schema = client.get("/openapi.json").json()["components"]["schemas"]["UserPatch"]
    assert set(schema["properties"]) == {"email", "full_name"}

    updated = client.patch(
        f"/api/users/{customer['id']}",
        headers=authorized(admin_token),
        json={"email": "updated-customer@example.com", "full_name": "Updated Customer"},
    )
    assert updated.status_code == 200
    assert updated.json()["email"] == "updated-customer@example.com"
    assert updated.json()["full_name"] == "Updated Customer"
    assert updated.json()["role"] == "CUSTOMER"

    rejected = client.patch(
        f"/api/users/{customer['id']}",
        headers=authorized(admin_token),
        json={"is_active": False},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_wallet_returns_domain_conflict(client):
    token = register_and_login(client, "duplicate-wallet@example.com")
    first = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    )
    duplicate = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_WALLET"


def test_only_customers_can_create_wallets_for_themselves(client):
    customer_token = register_and_login(client, "wallet-create-customer@example.com")
    customer_id = client.get(
        "/api/auth/me",
        headers=authorized(customer_token),
    ).json()["id"]

    inr_wallet = client.post(
        "/api/wallets",
        headers=authorized(customer_token),
        json={"currency": "INR"},
    )
    usd_wallet = client.post(
        "/api/wallets",
        headers=authorized(customer_token),
        json={"currency": "USD"},
    )
    assert inr_wallet.status_code == 201
    assert usd_wallet.status_code == 201
    assert inr_wallet.json()["owner_id"] == customer_id
    assert usd_wallet.json()["owner_id"] == customer_id

    for role, suffix in (
        (Role.SUPER_ADMIN, "super-admin"),
        (Role.ADMIN, "admin"),
        (Role.SUPPORT_AGENT, "support"),
    ):
        email = f"wallet-create-{suffix}@example.com"
        token = register_and_login(client, email)
        with TestSession() as db:
            db.scalar(select(User).where(User.email == email)).role = role
            db.commit()
        response = client.post(
            "/api/wallets",
            headers=authorized(token),
            json={"currency": "INR"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_empty_wallet_patch_returns_domain_error(client):
    token = register_and_login(client, "empty-wallet-patch@example.com")
    wallet_id = client.post(
        "/api/wallets",
        headers=authorized(token),
        json={"currency": "INR"},
    ).json()["id"]
    user_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == user_id)).role = Role.ADMIN
        db.commit()
    token = client.post(
        "/api/auth/login",
        json={
            "email": "empty-wallet-patch@example.com",
            "password": "SecureTest123!",
        },
    ).json()["access_token"]

    response = client.patch(
        f"/api/wallets/{wallet_id}",
        headers=authorized(token),
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_WALLET_STATE"


def test_refund_requires_admin_approval_and_credits_ledger(client, monkeypatch):
    sender_token = register_and_login(client, "refund-sender@example.com")
    recipient_token = register_and_login(client, "refund-recipient@example.com")
    sender_id = client.get("/api/auth/me", headers=authorized(sender_token)).json()["id"]
    sender_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    recipient_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(recipient_token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{sender_wallet_id}/deposits",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-sender-fund"},
        json={"amount": "100.00"},
    )
    with TestSession() as db:
        db.get(TransactionLimit, 1).suspicious_amount_threshold = Decimal("50.00")
        db.commit()
    transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-original-transfer"},
        json={
            "sender_wallet_id": sender_wallet_id,
            "receiver_wallet_id": recipient_wallet_id,
            "amount": "80.00",
        },
    )
    assert transfer.status_code == 201
    with TestSession() as db:
        suspicious = db.scalar(
            select(SuspiciousTransaction).where(
                SuspiciousTransaction.transfer_id == transfer.json()["id"]
            )
        )
        assert suspicious is not None
        suspicious_id = suspicious.id
        assert suspicious.status == "REVIEW_REQUIRED"
    sender_ledger = client.get(
        f"/api/wallets/{sender_wallet_id}/ledger",
        headers=authorized(sender_token),
    ).json()
    outgoing_entry = next(
        entry for entry in sender_ledger
        if entry["transaction_type"] == "TRANSFER_DEBIT"
    )
    recipient_ledger = client.get(
        f"/api/wallets/{recipient_wallet_id}/ledger",
        headers=authorized(recipient_token),
    ).json()
    incoming_entry = next(
        entry for entry in recipient_ledger
        if entry["transaction_type"] == "TRANSFER_CREDIT"
    )

    wrong_direction = client.post(
        "/api/refunds",
        headers={**authorized(recipient_token), "Idempotency-Key": "refund-wrong-direction"},
        json={
            "ledger_entry_id": incoming_entry["id"],
            "amount": "20.00",
            "reason": "Recipient cannot initiate a sender refund",
        },
    )
    assert wrong_direction.status_code == 400
    assert wrong_direction.json()["error"]["code"] == "INVALID_REFUND"

    oversized = client.post(
        "/api/refunds",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-too-large"},
        json={
            "ledger_entry_id": outgoing_entry["id"],
            "amount": "80.01",
            "reason": "Over original amount",
        },
    )
    assert oversized.status_code == 409
    assert oversized.json()["error"]["code"] == "INVALID_REFUND"
    with TestSession() as db:
        limits = db.get(TransactionLimit, 1)
        limits.max_transaction_amount = Decimal("50.00")
        db.commit()
    exceeds_configured_limit = client.post(
        "/api/refunds",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-over-limit"},
        json={
            "ledger_entry_id": outgoing_entry["id"],
            "amount": "60.00",
            "reason": "Over configured limit",
        },
    )
    assert exceeds_configured_limit.status_code == 409
    assert exceeds_configured_limit.json()["error"]["code"] == "TRANSACTION_LIMIT_EXCEEDED"
    assert exceeds_configured_limit.json()["error"]["message"] == (
        "Maximum transaction amount is INR 50.00."
    )
    with TestSession() as db:
        limits = db.get(TransactionLimit, 1)
        limits.max_transaction_amount = Decimal("100000.00")
        db.commit()
    request_payload = {
        "ledger_entry_id": outgoing_entry["id"],
        "amount": "20.00",
        "reason": "Wrong transfer",
    }
    request_headers = {
        **authorized(sender_token),
        "Idempotency-Key": "refund-request",
    }
    request = client.post(
        "/api/refunds",
        headers=request_headers,
        json=request_payload,
    )
    replay = client.post(
        "/api/refunds",
        headers=request_headers,
        json=request_payload,
    )
    assert request.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == request.json()["id"]
    assert request.json()["wallet_id"] == sender_wallet_id

    over_remaining = client.post(
        "/api/refunds",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-over-remaining"},
        json={
            "ledger_entry_id": outgoing_entry["id"],
            "amount": "61.00",
            "reason": "Exceeds remaining refundable amount",
        },
    )
    assert over_remaining.status_code == 409
    assert over_remaining.json()["error"]["code"] == "INVALID_REFUND"

    with TestSession() as db:
        admin = db.scalar(select(User).where(User.id == sender_id))
        admin.role = Role.ADMIN
        db.commit()
    admin_token = client.post(
        "/api/auth/login",
        json={
            "email": "refund-sender@example.com",
            "password": "SecureTest123!",
        },
    ).json()["access_token"]
    under_review = client.post(
        f"/api/refunds/{request.json()['id']}/review",
        headers=authorized(admin_token),
    )
    assert under_review.status_code == 200
    assert under_review.json()["status"] == "UNDER_REVIEW"

    import app.services.refund_service as refund_service

    monkeypatch.setattr(
        refund_service,
        "_complete_approved_refund",
        lambda db, refund_id, reviewer=None: db.get(Refund, refund_id),
    )
    result = client.post(f"/api/refunds/{request.json()['id']}/approve", headers=authorized(admin_token))
    assert result.status_code == 200
    assert result.json()["status"] == "APPROVED"
    assert result.json()["reviewed_at"] is not None
    assert result.json()["completed_at"] is None
    assert client.get(
        f"/api/wallets/{sender_wallet_id}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "20.00"
    assert client.get(
        f"/api/wallets/{recipient_wallet_id}",
        headers=authorized(recipient_token),
    ).json()["available_balance"] == "80.00"
    with TestSession() as db:
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == request.json()["id"],
                AuditLog.action == "REFUND_APPROVED",
            )
        )

    monkeypatch.undo()
    with TestSession() as db:
        assert complete_approved_refunds(db) == 1
        assert complete_approved_refunds(db) == 0
        refund = db.get(Refund, request.json()["id"])
        assert refund.status == RefundStatus.COMPLETED
        assert refund.completed_at is not None
        refund_entries = db.scalars(
            select(LedgerEntry).where(
                LedgerEntry.reference_entity == "REFUND",
                LedgerEntry.reference_id == refund.id,
            )
        ).all()
        assert len(refund_entries) == 2
        debited = next(
            entry for entry in refund_entries
            if entry.wallet_id == recipient_wallet_id
        )
        credited = next(
            entry for entry in refund_entries
            if entry.wallet_id == sender_wallet_id
        )
        assert (debited.balance_before, debited.balance_after) == (
            Decimal("80.00"),
            Decimal("60.00"),
        )
        assert (credited.balance_before, credited.balance_after) == (
            Decimal("20.00"),
            Decimal("40.00"),
        )
    assert client.get(
        f"/api/wallets/{sender_wallet_id}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "40.00"
    assert client.get(
        f"/api/wallets/{recipient_wallet_id}",
        headers=authorized(recipient_token),
    ).json()["available_balance"] == "60.00"
    with TestSession() as db:
        suspicious = db.get(SuspiciousTransaction, suspicious_id)
        assert suspicious.status == "NORMAL"
        assert db.get(Transfer, transfer.json()["id"]).risk_status == "NORMAL"
    blocked_after_refund = client.post(
        f"/api/admin/suspicious-transactions/{suspicious_id}/review",
        headers=authorized(admin_token),
        json={"status": "BLOCKED"},
    )
    assert blocked_after_refund.status_code == 409
    assert blocked_after_refund.json()["error"]["code"] == "INVALID_REVIEW_STATUS"
    assert client.get(
        f"/api/wallets/{sender_wallet_id}",
        headers=authorized(sender_token),
    ).json()["available_balance"] == "40.00"
    assert client.get(
        f"/api/wallets/{recipient_wallet_id}",
        headers=authorized(recipient_token),
    ).json()["available_balance"] == "60.00"


def test_rejected_refund_leaves_suspicious_transfer_open(client):
    sender_token = register_and_login(client, "refund-rejected-sender@example.com")
    recipient_token = register_and_login(client, "refund-rejected-recipient@example.com")
    sender_id = client.get("/api/auth/me", headers=authorized(sender_token)).json()["id"]
    sender_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(sender_token),
        json={"currency": "INR"},
    ).json()["id"]
    recipient_wallet_id = client.post(
        "/api/wallets",
        headers=authorized(recipient_token),
        json={"currency": "INR"},
    ).json()["id"]
    client.post(
        f"/api/wallets/{sender_wallet_id}/deposits",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-rejected-fund"},
        json={"amount": "100.00"},
    )
    with TestSession() as db:
        db.get(TransactionLimit, 1).suspicious_amount_threshold = Decimal("50.00")
        db.commit()
    transfer = client.post(
        "/api/transfers",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-rejected-transfer"},
        json={
            "sender_wallet_id": sender_wallet_id,
            "receiver_wallet_id": recipient_wallet_id,
            "amount": "80.00",
        },
    )
    assert transfer.status_code == 201
    outgoing_entry = next(
        entry
        for entry in client.get(
            f"/api/wallets/{sender_wallet_id}/ledger",
            headers=authorized(sender_token),
        ).json()
        if entry["transaction_type"] == "TRANSFER_DEBIT"
    )
    refund = client.post(
        "/api/refunds",
        headers={**authorized(sender_token), "Idempotency-Key": "refund-rejected-request"},
        json={
            "ledger_entry_id": outgoing_entry["id"],
            "amount": "20.00",
            "reason": "Request to return incorrect payment",
        },
    )
    assert refund.status_code == 201
    with TestSession() as db:
        suspicious = db.scalar(
            select(SuspiciousTransaction).where(
                SuspiciousTransaction.transfer_id == transfer.json()["id"]
            )
        )
        assert suspicious is not None
        suspicious_id = suspicious.id
        admin = db.get(User, sender_id)
        admin.role = Role.ADMIN
        db.commit()
    admin_token = client.post(
        "/api/auth/login",
        json={
            "email": "refund-rejected-sender@example.com",
            "password": "SecureTest123!",
        },
    ).json()["access_token"]
    rejected = client.post(
        f"/api/refunds/{refund.json()['id']}/reject",
        headers=authorized(admin_token),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    with TestSession() as db:
        assert db.get(SuspiciousTransaction, suspicious_id).status == "REVIEW_REQUIRED"
        assert db.get(Transfer, transfer.json()["id"]).risk_status == "REVIEW_REQUIRED"


def test_inactive_users_cannot_login(client):
    token = register_and_login(client, "inactive@example.com")
    user_id = client.get("/api/auth/me", headers=authorized(token)).json()["id"]
    with TestSession() as db:
        record = db.scalar(select(User).where(User.id == user_id))
        record.is_active = False
        db.commit()
    response = client.post("/api/auth/login", json={"email": "inactive@example.com", "password": "SecureTest123!"})
    assert response.status_code == 401


def test_admin_limits_history_filters_and_risk_review(client):
    admin_token = register_and_login(client, "limits-admin@example.com")
    admin_id = client.get("/api/auth/me", headers=authorized(admin_token)).json()["id"]
    with TestSession() as db:
        db.scalar(select(User).where(User.id == admin_id)).role = Role.SUPER_ADMIN
        db.commit()
    sender_token = register_and_login(client, "limits-sender@example.com")
    receiver_token = register_and_login(client, "limits-receiver@example.com")
    sender_id = client.post("/api/wallets", headers=authorized(sender_token), json={"currency": "INR"}).json()["id"]
    receiver_id = client.post("/api/wallets", headers=authorized(receiver_token), json={"currency": "INR"}).json()["id"]
    limit_update = client.patch("/api/admin/transaction-limits", headers=authorized(admin_token), json={
        "max_transaction_amount": "1000.00",
        "daily_transfer_limit": "20.00",
        "daily_withdrawal_limit": "50.00",
        "max_transactions_per_day": 100,
        "suspicious_amount_threshold": "20.00",
    })
    assert limit_update.status_code == 200
    client.post(f"/api/wallets/{sender_id}/deposits", headers={**authorized(sender_token), "Idempotency-Key": "limits-fund"}, json={"amount": "100.00"})
    over_limit = client.post("/api/transfers", headers={**authorized(sender_token), "Idempotency-Key": "limits-over"}, json={
        "sender_wallet_id": sender_id, "receiver_wallet_id": receiver_id, "amount": "20.01",
    })
    assert over_limit.status_code == 409
    assert over_limit.json()["error"]["code"] == "TRANSACTION_LIMIT_EXCEEDED"
    transfer = client.post("/api/transfers", headers={**authorized(sender_token), "Idempotency-Key": "limits-valid"}, json={
        "sender_wallet_id": sender_id, "receiver_wallet_id": receiver_id, "amount": "20.00",
    })
    assert transfer.status_code == 201
    next_transfer = client.post("/api/transfers", headers={**authorized(sender_token), "Idempotency-Key": "limits-daily"}, json={
        "sender_wallet_id": sender_id, "receiver_wallet_id": receiver_id, "amount": "1.00",
    })
    assert next_transfer.status_code == 409
    over_daily_withdrawal = client.post(
        f"/api/wallets/{sender_id}/withdrawals",
        headers={**authorized(sender_token), "Idempotency-Key": "limits-withdraw-over"},
        json={"amount": "50.01"},
    )
    assert over_daily_withdrawal.status_code == 409
    assert over_daily_withdrawal.json()["error"]["code"] == "TRANSACTION_LIMIT_EXCEEDED"
    history = client.get("/api/transactions?type=transfer&status=completed&sort_order=asc", headers=authorized(sender_token))
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    dashboard = client.get("/api/dashboards/admin", headers=authorized(admin_token))
    assert dashboard.status_code == 200
    assert dashboard.json()["today_transactions"] == 2
    assert Decimal(str(dashboard.json()["today_transaction_volume"])) == Decimal("120.00")
    report = client.get(
        "/api/admin/reports/daily-transactions",
        headers=authorized(admin_token),
    )
    assert report.status_code == 200
    assert report.json()["transactions"] == 2
    assert Decimal(str(report.json()["volume"])) == Decimal("120.00")
    flagged = client.get("/api/admin/suspicious-transactions", headers=authorized(admin_token))
    assert flagged.status_code == 200
    assert len(flagged.json()) >= 3
    blocked_attempt = next(
        item
        for item in flagged.json()
        if item["transfer_id"] is None
        and item["operation_type"] == "TRANSFER"
        and Decimal(str(item["amount"])) == Decimal("20.01")
    )
    reviewed = client.post(f"/api/admin/suspicious-transactions/{blocked_attempt['id']}/review", headers=authorized(admin_token), json={"status": "BLOCKED"})
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "BLOCKED"
