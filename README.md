# Digital Wallet & Transaction Processing Platform

FastAPI REST service for ledger-backed wallets, transfers, simulated deposits and withdrawals, refunds, authentication, notifications, and administration. PostgreSQL is the production database; SQLite is supported for isolated tests. 


### 1. Create and configure PostgreSQL

Create a database and an application login using an administrative PostgreSQL account. For example, from `psql`:

```sql
CREATE ROLE wallet LOGIN PASSWORD 'replace-with-a-strong-local-password';
CREATE DATABASE wallet_db OWNER wallet;
```

For production, grant only the database privileges required by the application and migrations. Do not reuse the PostgreSQL superuser as the application account.

### 2. Create the Python environment

From the repository root, create and activate a virtual environment.

**Windows PowerShell:**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents environment activation, either allow activation for the current process with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again, or call the environment's Python directly as `.\.venv\Scripts\python.exe`.

**macOS/Linux:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Configure environment variables

Create a local `.env` from the example file.

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**macOS/Linux:**

```bash
cp .env.example .env
```

Generate a suitable secret locally, for example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The provided `.env.example` contains the remaining required settings for token lifetimes, transaction limits, and optional Celery Redis URLs. Change defaults to suit your development environment. If the PostgreSQL password contains URL-reserved characters, percent-encode it in `DATABASE_URL`. Keep `.env` and real credentials private; never commit them or use the example JWT secret in a deployed environment.

### 4. Apply database migrations

From the activated environment:

```powershell
alembic upgrade head
```

Or, without activating the Windows virtual environment:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

### 5. Create the initial Super Admin

Run this once, after migrations, while the users table is empty:

```powershell
python -m scripts.seed_admin
```

The script prompts for the email, name, and password; it currently supports interactive setup only. **Password input is visible in the terminal.** Bootstrap is refused once any user exists, and the script requires a valid email, a non-empty name, and a password of at least eight characters. Do not put bootstrap credentials in source control.

Public registration creates customers only. Use the Super Admin account to assign roles through the role-management endpoint. Do not use the initial Super Admin for routine customer workflows.

### 6. Start the API

```powershell
uvicorn app.main:app --reload
```

The local server listens at `http://127.0.0.1:8000` by default. To bind another address or port, use Uvicorn options such as `--host 0.0.0.0 --port 8000`; only expose the service to trusted networks.

### 7. Open API documentation and authenticate

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Call `POST /api/auth/login` with the Super Admin or customer credentials to receive an access token and a refresh token. In Swagger, click **Authorize**, paste the **access token** into the bearer authentication field, and authorize. Protected calls use the standard `Authorization: Bearer <access_token>` header; do not use the refresh token as a bearer access token. Refresh tokens are sent to `POST /api/auth/refresh`.

For endpoint details, request/response examples, and error formats, see [API Documentation](docs/API_DOCUMENTATION.md). The database schema and foreign-key relationships are shown in the [ER diagram](docs/ER_DIAGRAM.md). Import [`postman_collection.json`](postman_collection.json) into Postman to try the documented API operations.

### 8. Run automated tests

With the virtual environment active:

```powershell
python -m pytest
```

On Windows without activation:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The tests create their own in-memory SQLite schema and do not use the configured PostgreSQL database. PostgreSQL-specific concurrency behavior should additionally be tested against a dedicated PostgreSQL test database. Never point destructive tests or migrations at production data.

## Architecture

The [architecture diagrams](docs/ARCHITECTURE.md) describe the application layers, request authorization and financial transaction flow, PostgreSQL persistence, and optional scheduled/background jobs. They reflect the current implementation; payment-provider integrations and external notification delivery are not configured.

## Financial integrity and concurrency

Each balance-changing operation executes in one database transaction. The acting user's row is locked before idempotency and daily-limit checks, serializing that user's financial requests across different wallets and preventing concurrent requests from exceeding daily amount/count limits or creating the same idempotent operation twice. Wallet rows are then selected `FOR UPDATE`; for two-wallet transfers, rows are locked in sorted wallet-ID order to reduce deadlocks. The transaction checks status, currency, balance, and limits while holding the locks, then changes balances and appends ledger entries before commit. A rollback leaves neither a partial debit nor a credit. Unrelated users do not contend on a global limits-row lock; administrators lock the limits row when changing configuration. The database also enforces nonnegative balances, positive ledger amounts, foreign keys, unique wallet-per-owner/currency, unique operation references, and unique per-user idempotency keys.

Every request creating a deposit, transfer, withdrawal, or refund must include `Idempotency-Key`. The key is scoped to the authenticated user and stored with a canonical request hash and resulting entity. Repeating the same request returns its original entity; reusing the key for a different payload/type returns `409 DUPLICATE_IDEMPOTENCY_KEY`. A uniqueness constraint closes the race between simultaneous retries.

Transfers complete synchronously in the simulated workflow. The sender's cancel endpoint accepts only `PENDING` or `PROCESSING` transfers and marks them `CANCELLED` without posting balances. A `COMPLETED` transfer cannot be cancelled by its sender; the endpoint returns `409 INVALID_TRANSACTION_STATE` and leaves the balances and original ledger entries unchanged. Separately, an administrator's suspicious-transaction review may reverse a blocked completed transfer through compensating `REVERSAL` ledger entries; the original transfer remains `COMPLETED` and its `reversed_at` timestamp records that review action.

The ledger is append-only through the API and PostgreSQL: migration `0004_immutable_ledger` installs triggers that reject `UPDATE`, `DELETE`, and `TRUNCATE` on `transaction_ledger`. Normal financial service paths only append entries; cancellations use compensating `REVERSAL` entries. The deployment role should still have only the database privileges it needs.

Audit logs are append-only through PostgreSQL as well: migration `0005_immutable_audit_logs` rejects `UPDATE`, `DELETE`, and `TRUNCATE` on `audit_logs`. Audit records capture the request IP where available, important successful operations, and rejected financial operations with their domain error codes. Migration `0006_restrict_audit_actor_deletion` prevents deleting a user whose identity is preserved by an audit record.

Migration `0007_generic_risk_events` lets suspicious records represent rejected attempts as well as posted transfers. Configured-limit rejections are stored as `REVIEW_REQUIRED` events with the user, wallet, amount, operation type, and reason; reviewers can resolve them to `NORMAL` or `BLOCKED` through the same staff review API.

Completed withdrawals are simulated as immediately settled. Their cancellation endpoint performs an atomic compensating reversal that credits the wallet and appends a `REVERSAL` ledger entry; pending/processing withdrawals can be cancelled without a balance movement. Cancellation is single-use and audited.


Amounts are `NUMERIC(18,2)` and use Python `Decimal`. Entity IDs and their foreign keys are integers. Financial operations and ledger entries draw IDs from a shared integer identifier table so transaction-history IDs remain unambiguous across operation types. Roles are stored in the `roles` catalog and referenced by each user's role; the built-in role values are seeded by migration `0011_integer_entity_ids`. Reference IDs are intentionally polymorphic in the ledger so a single immutable history can represent each operation while operation tables retain their domain-specific state. Refund requests refer to the sender's outgoing `TRANSFER_DEBIT` ledger entry and validate cumulative requests against the original transfer amount.

The sender of a completed transfer can request a refund using their outgoing debit ledger entry. A Support Agent, Admin, or Super Admin reviews the request and can reject it or approve it. Approval first commits the durable `APPROVED` state, then a separate atomic settlement debits the recipient's available balance, credits the sender's wallet, writes both immutable ledger entries, and marks the refund `COMPLETED` with `completed_at`. Approval cannot settle if the recipient has insufficient available balance or either wallet is closed. When settlement completes, any linked suspicious-transfer review is resolved to `NORMAL`; rejecting a refund leaves the risk review open. Risk blocking and refund settlement serialize on the transfer and wallet rows, and a transfer with a requested, under-review, approved, or completed refund cannot be blocked, preventing a second reversal of refunded funds. Scheduled recovery settles refunds left `APPROVED` after an interruption. Unreviewed requests that exceed the pending-cleanup age are moved to `FAILED` and the requester is notified.

Rejected deposit, transfer, and withdrawal attempts generate the corresponding `*_FAILED` in-app notification as well as the audit event. Scheduled expiry also generates failure notifications. Notifications are stored in the database and delivered through the authenticated notifications API; external email, SMS, and push-provider delivery is not configured.

The customer dashboard returns each wallet plus a currency-keyed `wallet_balance` object, so balances in different currencies are not combined. The admin dashboard includes `wallet_balances_by_currency` for the same reason; the scalar `total_wallet_balance` remains available for the requested aggregate.

## API summary

All routes are under `/api`; auth is bearer JWT. Domain, HTTP, request-validation, and unexpected server errors use a consistent JSON envelope: `{"success":false,"error":{"code":"...","message":"..."}}`. Validation errors use `422 VALIDATION_ERROR`; unexpected errors are logged server-side and return a generic `500 INTERNAL_SERVER_ERROR` message.

| Area | Routes |
|---|---|
| Authentication | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/change-password`; `GET /auth/me` |
| Users (admin) | `POST/GET /users`, `GET/PATCH /users/{user_id}`, `PATCH /users/{user_id}/activate`, `/deactivate`, `/role` |
| Wallets | `POST/GET /wallets`, `GET/PATCH /wallets/{wallet_id}`, `POST /wallets/{wallet_id}/freeze`, `/unfreeze`, `/close` |
| Deposits | `POST /wallets/{wallet_id}/deposits`, `GET /deposits`, `GET /deposits/{deposit_id}`, `POST /deposits/{deposit_id}/cancel` |
| Transfers | `POST/GET /transfers`, `GET /transfers/{transfer_id}`, `POST /transfers/{transfer_id}/cancel` |
| Withdrawals | `POST /wallets/{wallet_id}/withdrawals`, `GET /withdrawals`, `GET /withdrawals/{withdrawal_id}`, `POST /withdrawals/{withdrawal_id}/cancel` |
| Refunds | `POST/GET /refunds`, `GET /refunds/{refund_id}`, `POST /refunds/{refund_id}/review`, `/approve`, `/reject` |
| History/ledger | `GET /transactions`, `/transactions/{transaction_id}`, `/ledger`, `/ledger/{ledger_id}`, `/wallets/{wallet_id}/ledger` |
| Administration | `GET/PATCH /admin/transaction-limits`; `GET /admin/suspicious-transactions[/{suspicious_id}]`; `POST /admin/suspicious-transactions/{suspicious_id}/review`; `GET /admin/audit-logs[/{log_id}]`; `GET /admin/reports/daily-transactions` |
| Notifications | `GET /notifications`, `PATCH /notifications/{notification_id}/read`, `/notifications/read-all` |
| Dashboards | `GET /dashboards/admin`, `/dashboards/support`, `/dashboards/customer` |

Transaction history combines immutable ledger entries with operation records that have not posted to the ledger yet. This keeps pending, failed, rejected, and pre-posting cancelled operations visible, including incoming transfers for their recipient. For unposted operations, `balance_before` and `balance_after` are `null`; posted entries retain their recorded ledger balances. Customer history remains limited to wallets they own.

Wallet status changes through `PATCH /wallets/{wallet_id}` and closure through `POST /wallets/{wallet_id}/close` are restricted to Admin and Super Admin. Customers can freeze and unfreeze their own wallets using the dedicated endpoints; Support Agents can use the dedicated freeze/unfreeze endpoints to assist with wallet issues. Only Admin and Super Admin can suspend or close wallets.

For all deposit/withdrawal/transfer/refund creation calls, send `Idempotency-Key: <unique-client-key>`. Amounts must be positive decimal values. Example transfer:

```http
POST /api/transfers
Authorization: Bearer <access-token>
Idempotency-Key: payment-2026-0001
Content-Type: application/json

{"sender_wallet_id":101,"receiver_wallet_id":202,"amount":"125.00"}
```

Example domain error:

```json
{"success":false,"error":{"code":"INSUFFICIENT_BALANCE","message":"Insufficient wallet balance."}}
```

Successful deposit response example:

```json
{
  "id": 501,
  "wallet_id": 101,
  "amount": "100.00",
  "currency": "INR",
  "status": "COMPLETED",
  "reference": "transaction-reference",
  "created_at": "2026-10-21T07:30:00Z",
  "completed_at": "2026-10-21T07:30:00Z"
}
```

API docs include operation schemas and bearer security. Read [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md) for the endpoint catalog, authorization requirements, workflows, request and response examples, and error formats. The database structure is documented in [`docs/ER_DIAGRAM.md`](docs/ER_DIAGRAM.md); the runtime and component design is shown in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Import `postman_collection.json` from the repository root into Postman for all documented API operations. The collection follows the FastAPI OpenAPI schema and includes parameters, authentication, and JSON request examples.

## Scheduled work

Tasks can be invoked by a system scheduler (Windows Task Scheduler, cron, or a managed job runner) as `python -m app.jobs <task>`. Available tasks are `reset-daily-limits`, `cleanup-pending`, `scan-suspicious`, `daily-wallet-summary`, `retry-failed`, `process-approved-refunds`, and `daily-report`. Daily usage is calculated from the current UTC calendar-day start, so limits roll over at UTC midnight without mutating financial history. The scheduled reset records one idempotent `daily_limit_resets` checkpoint per UTC date; a primary key prevents duplicate reset runs. Deposits/transfers/withdrawals are simulated and normally complete synchronously; failed-operation retry only retries records with no ledger posting. Approved refunds are durably recorded before settlement; the settlement task completes approved requests that were interrupted between those steps. The optional Celery worker/Beat integration uses `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (Redis by default).

To run the optional Celery integration, start a worker with `celery -A app.workers.celery_app:celery worker --loglevel=INFO` and Beat with `celery -A app.workers.celery_app:celery beat --loglevel=INFO`.

## Scope and operational notes

The deposit/withdrawal rails are simulations, not payment-provider integrations. For a real-money launch, integrate a regulated payment provider, persist provider/webhook idempotency, use an outbox for external notifications, add secret management and key rotation, configure database least privilege, and run PostgreSQL concurrency/load and security testing. The provided test suite uses SQLite for portability; row-lock concurrency guarantees specifically require PostgreSQL and should be verified against a PostgreSQL test service before production.
