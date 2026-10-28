# Digital Wallet Platform API

This guide documents the REST API implemented by the Digital Wallet & Transaction Processing Platform. The OpenAPI schema is the canonical source for operation parameters and request/response models; this guide adds workflow notes and practical examples.

## Documentation and base URL

| Resource | URL |
|---|---|
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| API base | `http://127.0.0.1:8000/api` |
| Postman collection | [`../postman_collection.json`](../postman_collection.json) |

Import the Postman collection into Postman and set its `baseUrl` collection variable if the service is not running at the default URL. The collection covers all operations exposed in Swagger. Sign in to obtain a token; the collection saves the access and refresh tokens from successful login and refresh responses.

## Authentication and authorization

Protected operations require an access token in the standard HTTP bearer header:

```http
Authorization: Bearer <access_token>
```

In Swagger UI, click **Authorize** and paste the access token (do not include the `Bearer ` prefix if the dialog expects just the token). In Postman, the collection uses `{{accessToken}}`.

Registration creates a `CUSTOMER` account. The initial `SUPER_ADMIN` is bootstrapped using the project setup script. Admin endpoints do not create or promote a super admin. Inactive users cannot log in.

| Role | Scope |
|---|---|
| `CUSTOMER` | Own wallets and financial resources; transfers and refund requests; customer dashboard and notifications |
| `SUPPORT_AGENT` | Staff review of suspicious transactions and refunds; support dashboard; staff resource visibility where supported |
| `ADMIN` | Admin user and wallet management, limits, audit logs, admin dashboard/reports, plus staff review |
| `SUPER_ADMIN` | Admin capabilities plus user role assignment |

Resource ownership is enforced in addition to the role rules. A staff role does not automatically grant every operation; the endpoint table below notes the specific role requirement where restricted.

## Request conventions

- Send and receive JSON for JSON request bodies. Amounts are decimal currency values with up to two fractional digits; use strings (for example `"25.00"`) to avoid client-side floating-point rounding.
- Resource IDs are integers.
- List endpoints with `page` and `page_size` default to page 1 and 20 items. The maximum page size is 100. `/api/transactions` returns an envelope containing `items`, `page`, `page_size`, and `total`.
- Financial create operations require a unique `Idempotency-Key` header: deposit, transfer, withdrawal, and refund. Use a new key for a new logical request. Repeating the same key and payload replays the original operation; reusing the key with a different payload or operation returns a conflict.
- Transfers, deposits, and withdrawals are simulated and normally complete synchronously. Do not treat this simulation as an external payment-provider integration.

Example headers for a new financial operation:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Idempotency-Key: 6fa23274-8fe1-4f4a-9bb4-7410c932fefe
```

## Endpoint reference

All paths below are relative to `/api`. Unless marked **Public**, endpoints require bearer authentication. Role labels refer to the roles in the preceding table. All path IDs shown as `{..._id}` are integers.

### Authentication

| Method | Path | Access | Description |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Register a customer |
| `POST` | `/auth/login` | Public | Authenticate and issue access/refresh tokens |
| `POST` | `/auth/refresh` | Public (refresh token required) | Rotate the refresh token and issue a new token pair |
| `POST` | `/auth/logout` | Authenticated | Revoke the current user's refresh token |
| `GET` | `/auth/me` | Authenticated | Get the current user |
| `POST` | `/auth/change-password` | Authenticated | Change the current user's password |

### Users

All user-management endpoints require `ADMIN` or `SUPER_ADMIN`, except role assignment, which requires `SUPER_ADMIN`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/users?page=1&page_size=20` | List users |
| `POST` | `/users` | Create a customer user |
| `GET` | `/users/{user_id}` | Get a user |
| `PATCH` | `/users/{user_id}` | Update `email` and/or `full_name` |
| `PATCH` | `/users/{user_id}/activate` | Activate a user |
| `PATCH` | `/users/{user_id}/deactivate` | Deactivate a user |
| `PATCH` | `/users/{user_id}/role` | Set a role (**SUPER_ADMIN** only) |

### Wallets

| Method | Path | Access | Description |
|---|---|---|---|
| `POST` | `/wallets` | `CUSTOMER` | Create a wallet owned by the current customer |
| `GET` | `/wallets` | Authenticated; ownership/staff rules apply | List visible wallets |
| `GET` | `/wallets/{wallet_id}` | Authenticated; ownership/staff rules apply | Get a wallet |
| `PATCH` | `/wallets/{wallet_id}` | `ADMIN` or `SUPER_ADMIN` | Set the wallet status |
| `POST` | `/wallets/{wallet_id}/freeze` | Authenticated; ownership/staff rules apply | Freeze a wallet |
| `POST` | `/wallets/{wallet_id}/unfreeze` | Authenticated; ownership/staff rules apply | Unfreeze a wallet |
| `POST` | `/wallets/{wallet_id}/close` | `ADMIN` or `SUPER_ADMIN` | Close a wallet |
| `GET` | `/wallets/{wallet_id}/ledger` | Authenticated; ownership/staff rules apply | List a wallet's ledger entries |

Wallet status values are `ACTIVE`, `FROZEN`, `SUSPENDED`, and `CLOSED`. Invalid status transitions are rejected.

### Deposits

| Method | Path | Description |
|---|---|---|
| `POST` | `/wallets/{wallet_id}/deposits` | Simulate a deposit (requires `Idempotency-Key`) |
| `GET` | `/deposits?page=1&page_size=20` | List visible deposits |
| `GET` | `/deposits/{deposit_id}` | Get a deposit |
| `POST` | `/deposits/{deposit_id}/cancel` | Cancel a cancellable deposit |

### Transfers

| Method | Path | Description |
|---|---|---|
| `POST` | `/transfers` | Transfer between wallets (requires `Idempotency-Key`) |
| `GET` | `/transfers?page=1&page_size=20` | List visible transfers |
| `GET` | `/transfers/{transfer_id}` | Get a transfer |
| `POST` | `/transfers/{transfer_id}/cancel` | Cancel a cancellable transfer |

Completed transfers cannot be cancelled by the sender. A staff risk review can block and reverse an eligible completed transfer by posting compensating ledger entries. A transfer with a related requested, under-review, approved, or completed refund cannot be blocked, preventing a second movement of the same funds.

### Withdrawals

| Method | Path | Description |
|---|---|---|
| `POST` | `/wallets/{wallet_id}/withdrawals` | Withdraw from a wallet (requires `Idempotency-Key`) |
| `GET` | `/withdrawals?page=1&page_size=20` | List visible withdrawals |
| `GET` | `/withdrawals/{withdrawal_id}` | Get a withdrawal |
| `POST` | `/withdrawals/{withdrawal_id}/cancel` | Cancel a cancellable withdrawal |

Withdrawals require an active wallet, sufficient balance, a positive amount, and compliance with configured maximum and daily limits.

### Refunds

| Method | Path | Access | Description |
|---|---|---|---|
| `POST` | `/refunds` | Authenticated sender; requires `Idempotency-Key` | Request refund for an outgoing transfer |
| `GET` | `/refunds?page=1&page_size=20` | Authenticated; ownership/staff rules apply | List visible refunds |
| `GET` | `/refunds/{refund_id}` | Authenticated; ownership/staff rules apply | Get a refund |
| `POST` | `/refunds/{refund_id}/review` | `SUPPORT_AGENT`, `ADMIN`, or `SUPER_ADMIN` | Move a requested refund into review |
| `POST` | `/refunds/{refund_id}/approve` | `SUPPORT_AGENT`, `ADMIN`, or `SUPER_ADMIN` | Approve and settle the refund |
| `POST` | `/refunds/{refund_id}/reject` | `SUPPORT_AGENT`, `ADMIN`, or `SUPER_ADMIN` | Reject the refund |

The sender supplies the ID of their original `TRANSFER_DEBIT` ledger entry. A completed refund debits the recipient's available balance and credits the sender's wallet. Refund approval cannot settle if the recipient lacks available funds or either wallet is closed. When a refund completes, a linked suspicious transfer review is resolved to `NORMAL`; rejection leaves that risk case open.

### Transactions and ledger

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions` | Search and page through the current user's transaction history |
| `GET` | `/transactions/{transaction_id}` | Get a ledger-backed transaction |
| `GET` | `/ledger?page=1&page_size=20` | List visible immutable ledger entries |
| `GET` | `/ledger/{ledger_id}` | Get a ledger entry |

`GET /transactions` supports `page`, `page_size`, `type`, `status`, `min_amount`, `max_amount`, `from_date`, `to_date`, `search`, `sort_by` (`created_at` or `amount`), and `sort_order` (`asc` or `desc`). Ledger entries are append-only; corrections are represented by compensating entries rather than edits.

### Administration, risk, reporting, and dashboards

| Method | Path | Access | Description |
|---|---|---|---|
| `GET` | `/admin/transaction-limits` | `ADMIN` or `SUPER_ADMIN` | Read configured limits |
| `PATCH` | `/admin/transaction-limits` | `ADMIN` or `SUPER_ADMIN` | Update one or more limits |
| `GET` | `/admin/suspicious-transactions?page=1&page_size=20` | Staff (`SUPPORT_AGENT`, `ADMIN`, `SUPER_ADMIN`) | List suspicious events |
| `GET` | `/admin/suspicious-transactions/{suspicious_id}` | Staff | Get a suspicious event |
| `POST` | `/admin/suspicious-transactions/{suspicious_id}/review` | Staff | Resolve a case to `NORMAL` or `BLOCKED` |
| `GET` | `/admin/reports/daily-transactions` | `ADMIN` or `SUPER_ADMIN` | Get the daily transaction report |
| `GET` | `/dashboards/admin` | `ADMIN` or `SUPER_ADMIN` | Get admin dashboard metrics |
| `GET` | `/dashboards/support` | Staff | Get support dashboard metrics |
| `GET` | `/dashboards/customer` | Authenticated | Get the current customer's dashboard |
| `GET` | `/admin/audit-logs?page=1&page_size=50` | `ADMIN` or `SUPER_ADMIN` | List audit events |
| `GET` | `/admin/audit-logs/{log_id}` | `ADMIN` or `SUPER_ADMIN` | Get an audit event |

Limit fields are `max_transaction_amount`, `daily_transfer_limit`, `daily_withdrawal_limit`, `max_transactions_per_day`, and `suspicious_amount_threshold`. Each may be updated independently.

Risk review outcomes are `NORMAL` or `BLOCKED`; `REVIEW_REQUIRED` is not a valid reviewer decision. A reviewed case cannot be reviewed again through the same endpoint. Blocking a completed transfer attempts a compensating reversal; if the funds cannot safely be recovered, the request fails and the case remains unresolved.

### Notifications

| Method | Path | Description |
|---|---|---|
| `GET` | `/notifications?page=1&page_size=20` | List the current user's notifications |
| `PATCH` | `/notifications/{notification_id}/read` | Mark one notification as read |
| `PATCH` | `/notifications/read-all` | Mark all current user's notifications as read |

## Request examples

### Register and log in

`POST /api/auth/register`

```json
{
  "email": "alex@example.com",
  "full_name": "Alex Customer",
  "password": "ReplaceThis123!"
}
```

Successful registration returns `201 Created` and a user object:

```json
{
  "id": 101,
  "email": "alex@example.com",
  "full_name": "Alex Customer",
  "role": "CUSTOMER",
  "is_active": true
}
```

`POST /api/auth/login`

```json
{
  "email": "alex@example.com",
  "password": "ReplaceThis123!"
}
```

Successful login returns `200 OK`:

```json
{
  "access_token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_type": "bearer"
}
```

Use the access token for protected calls. Refresh using `POST /api/auth/refresh` with `{"refresh_token":"<refresh-token>"}`; the response contains the rotated token pair. `POST /api/auth/logout` accepts no request body and revokes the current user's refresh token.

### Create a wallet and deposit

`POST /api/wallets`

```json
{
  "currency": "INR"
}
```

`POST /api/wallets/101/deposits`

```json
{
  "amount": "1000.00"
}
```

Include `Idempotency-Key` on the deposit request. A successful wallet response has this shape:

```json
{
  "id": 101,
  "owner_id": 101,
  "currency": "INR",
  "available_balance": "0.00",
  "pending_balance": "0.00",
  "status": "ACTIVE",
  "created_at": "2026-10-28T10:00:00Z",
  "updated_at": "2026-10-28T10:00:00Z"
}
```

A completed deposit response includes its ID, wallet, amount, currency, `COMPLETED` status, reference, creation time, and completion time. The deposit credits the balance and appends a ledger entry atomically.

### Transfer funds

`POST /api/transfers`

```json
{
  "sender_wallet_id": 101,
  "receiver_wallet_id": 202,
  "amount": "25.00"
}
```

Include an `Idempotency-Key`. A successful transfer response (`201 Created`) looks like:

```json
{
  "id": 501,
  "sender_wallet_id": 101,
  "receiver_wallet_id": 202,
  "amount": "25.00",
  "currency": "INR",
  "status": "COMPLETED",
  "reference": "TRF-EXAMPLE-501",
  "created_at": "2026-10-28T10:05:00Z",
  "completed_at": "2026-10-28T10:05:00Z",
  "reversed_at": null
}
```

The API rejects transfers to the same user's wallet, mismatched currencies, inactive wallets, insufficient balance, and non-positive amounts. A successful transfer debits and credits wallets and appends both ledger entries in one database transaction.

### Request and review a refund

`POST /api/refunds`

```json
{
  "ledger_entry_id": 9001,
  "amount": "10.00",
  "reason": "Sent money to the wrong recipient"
}
```

`ledger_entry_id` must be the sender's `TRANSFER_DEBIT` entry for the completed outgoing transfer. Include an `Idempotency-Key`. The initial response has status `REQUESTED`; a support agent or administrator can mark it under review, approve it, or reject it.

### Search transaction history

```http
GET /api/transactions?page=1&page_size=20&type=TRANSFER_DEBIT&status=COMPLETED&min_amount=1.00&max_amount=5000.00&sort_by=created_at&sort_order=desc
```

Example response:

```json
{
  "items": [
    {
      "id": 9001,
      "wallet_id": 101,
      "transaction_type": "TRANSFER_DEBIT",
      "amount": "25.00",
      "balance_before": "100.00",
      "balance_after": "75.00",
      "status": "COMPLETED",
      "reference_entity": "TRANSFER",
      "reference_id": 501,
      "description": "Wallet transfer sent",
      "created_by": 101,
      "metadata_json": {},
      "created_at": "2026-10-28T10:05:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

## Response conventions

Successful operations return the endpoint's documented resource, list, or summary shape. Common success status codes:

| Status | Meaning |
|---|---|
| `200 OK` | Read or successful action |
| `201 Created` | Resource/financial operation created |

List operations may return a JSON array; transaction history specifically returns the pagination envelope shown above. Decimal values are serialized as strings.

## Error responses

Domain and HTTP errors use this common envelope:

```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_BALANCE",
    "message": "Insufficient wallet balance."
  }
}
```

Validation errors return `422 Unprocessable Entity` and include field details:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [
      {
        "type": "greater_than",
        "loc": ["body", "amount"],
        "msg": "Input should be greater than 0"
      }
    ]
  }
}
```

Common status codes and examples:

| HTTP status | Example codes | Meaning |
|---|---|---|
| `400 Bad Request` | `INVALID_TRANSFER`, `IDEMPOTENCY_KEY_REQUIRED`, `BAD_REQUEST` | Invalid business request or missing required key |
| `401 Unauthorized` | `UNAUTHORIZED` | Missing, invalid, expired, or revoked access token |
| `403 Forbidden` | `FORBIDDEN` | Role or resource ownership does not permit the operation |
| `404 Not Found` | `NOT_FOUND`, `WALLET_NOT_FOUND` | Resource does not exist or is not visible |
| `409 Conflict` | `INSUFFICIENT_BALANCE`, `TRANSACTION_LIMIT_EXCEEDED`, `DUPLICATE_IDEMPOTENCY_KEY`, `INVALID_TRANSACTION_STATE`, `REFUND_IN_PROGRESS` | Current balance, state, limits, or idempotency conflict prevents the operation |
| `422 Unprocessable Entity` | `VALIDATION_ERROR`, `INVALID_REVIEW_STATUS` | Request fields or requested review state are invalid |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Unexpected server failure; details are logged server-side |

Example: insufficient balance (`409 Conflict`):

```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_BALANCE",
    "message": "Insufficient wallet balance."
  }
}
```

Example: idempotency key reused for a different request (`409 Conflict`):

```json
{
  "success": false,
  "error": {
    "code": "DUPLICATE_IDEMPOTENCY_KEY",
    "message": "This Idempotency-Key was already used with a different request."
  }
}
```

The precise domain error code/message depends on the failed rule. Use the returned error code for client-side handling rather than parsing the human-readable message.

## Interactive examples and schemas

For the authoritative current schemas, enum values, query constraints, and generated examples, use Swagger UI at `/docs` or retrieve `/openapi.json`. The Postman collection is maintained alongside this guide at [`../postman_collection.json`](../postman_collection.json).
