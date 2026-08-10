# Leaf Online Store

Leaf is a FastAPI storefront and administration application for managing products,
categories, inventory, customers, carts and orders. The production storefront is
available at `https://leaf.ads-ai.in` and the administration area is under
`/admin`.

## Current payment status

Leaf implements Cash on Delivery (COD) and a manual UPI flow. UPI generates an
amount-specific `upi://pay` deep link and QR code, while the order remains
`Payment Pending` until an administrator verifies the transaction outside Leaf
and records the result. Product administrators can disable COD per product; COD
is unavailable when any product in the cart disallows it.

This manual UPI flow does not receive a bank/provider callback and must never
claim automatic payment success. The order model records:

- `payment_method`
- `payment_status` (`pending`, `paid`, `failed`, `refunded`, or
  `partially_refunded`)
- `payment_reference`

Razorpay and the other providers described below remain future automated-payment
integration instructions. Adding gateway credentials alone will not enable them.

### Manual UPI configuration

Configure the merchant VPA directly in the environment:

```env
UPI_ENABLED=true
UPI_VPA=merchant@bank
UPI_PAYEE_NAME=Leaf Online Store
```

Restart the service after changing these values. Never mark a UPI order paid
until the amount, Leaf order reference and UTR have been verified independently.

## Local development

### Requirements

- Python 3.12+
- PostgreSQL for a production-like environment
- A virtual environment

### Setup

```bash
python -m venv .venv
```

Activate the environment and install dependencies:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, provide local values, then run migrations:

```bash
alembic upgrade head
```

Start the application:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8070 --reload
```

Run the automated test suite:

```bash
pytest -q
```

Never commit `.env`, API secrets, webhook secrets, customer information or
production database backups.

## Recommended payment architecture

Use a provider-independent service layer rather than placing provider calls in
the checkout router. A suggested interface is:

```text
PaymentGateway
├── create_order(internal_order, amount, currency)
├── verify_checkout_response(payload)
├── verify_webhook(raw_body, signature)
├── fetch_payment(provider_payment_id)
└── create_refund(provider_payment_id, amount)
```

Create a `payment_attempts` table so retries and webhook processing are auditable.
Recommended fields:

| Field | Purpose |
| --- | --- |
| `id` | Internal attempt identifier |
| `order_id` | Leaf order relationship |
| `provider` | `razorpay`, `cashfree`, `stripe`, etc. |
| `provider_order_id` | Order/session identifier returned by the provider |
| `provider_payment_id` | Successful payment identifier |
| `amount` and `currency` | Immutable server-calculated payment amount |
| `status` | `created`, `authorized`, `captured`, `failed`, `refunded` |
| `failure_code/message` | Support and reconciliation information |
| `idempotency_key` | Prevents duplicate attempts or webhook effects |
| timestamps | Creation and last update times |

Important rules:

1. Calculate totals on the Leaf server. Never trust an amount received from the
   browser.
2. Recheck product availability and lock inventory during order creation.
3. Create the provider order from the backend.
4. Verify the provider signature on the backend before marking an order paid.
5. Treat webhooks as the reconciliation authority and process them idempotently.
6. Confirm/fulfil online orders only after the payment is captured.
7. Do not log secrets, signatures, complete webhook bodies containing customer
   data, or card/payment instrument details.
8. Restore reserved inventory when an unpaid order expires or is definitively
   failed/cancelled.

## Razorpay integration (recommended for India)

Razorpay Standard Checkout can expose UPI, cards, net banking and supported
wallets through one hosted payment interface.

Official references:

- [Standard Checkout prerequisites](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/)
- [Standard Checkout integration](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/)
- [Webhooks](https://razorpay.com/docs/webhooks/)
- [Validate and test webhooks](https://razorpay.com/docs/webhooks/validate-test/)

### 1. Create and prepare the Razorpay account

1. Create a Razorpay account and complete the required business/KYC activation.
2. Keep the account in **Test Mode** while developing.
3. Open **Account & Settings → API Keys** and generate test keys.
4. Configure automatic capture in the Razorpay Dashboard. Leaf should only
   fulfil a captured payment.
5. Enable the payment methods required by the store. Availability can depend on
   Razorpay approval and the activated account.

### 2. Configure Leaf secrets

Add placeholders to `.env.example`, but put real values only in the VPS `.env`:

```env
PAYMENT_DEFAULT_METHOD=cash_on_delivery
RAZORPAY_ENABLED=false
RAZORPAY_KEY_ID=rzp_test_REPLACE_ME
RAZORPAY_KEY_SECRET=REPLACE_ME
RAZORPAY_WEBHOOK_SECRET=REPLACE_WITH_A_LONG_RANDOM_SECRET
RAZORPAY_CURRENCY=INR
```

Security notes:

- The Key ID may be sent to Razorpay Checkout in the browser.
- The Key Secret and webhook secret must never be included in HTML, JavaScript,
  screenshots, logs, commits or chat messages.
- Use separate test and live credentials.
- Restart `leaf-store.service` after changing production environment variables.

Example production restart:

```bash
sudo systemctl restart leaf-store.service
sudo systemctl is-active leaf-store.service
```

### 3. Add server configuration

Read the Razorpay values in `app/core/config.py`. Startup should fail clearly if
`RAZORPAY_ENABLED=true` while a required secret is missing. Do not provide an
insecure default for a payment secret.

The implementation can call the Razorpay REST API with a maintained HTTP client
or use Razorpay's supported Python SDK. Pin any added dependency in
`requirements.txt`.

### 4. Create the Leaf order and Razorpay order

Add a backend endpoint such as:

```text
POST /payments/razorpay/order
```

The endpoint should:

1. Load the current cart from the server session.
2. Validate the address and customer details.
3. Lock/recheck inventory and calculate totals on the server.
4. Create a Leaf order in a pending-payment state.
5. Convert INR to paise exactly: `Decimal("499.00")` becomes integer `49900`.
6. Call Razorpay's Orders API with the amount, `INR`, a unique Leaf receipt and
   safe notes such as the Leaf order number.
7. Store the returned Razorpay `order_id` in a payment attempt.
8. Return only the public checkout configuration to the browser.

Every Razorpay payment must be associated with a server-created Razorpay order.
Do not create an order directly from browser-provided totals.

### 5. Open Standard Checkout

Add **Pay Online** next to COD in `store/checkout.html`. Load Razorpay's official
Checkout script from:

```text
https://checkout.razorpay.com/v1/checkout.js
```

Pass the Key ID, Razorpay order ID, amount, currency, Leaf name/theme and
prefilled customer contact data. Do not pass the Key Secret. On success, the
handler returns:

```text
razorpay_payment_id
razorpay_order_id
razorpay_signature
```

Send these values immediately to Leaf's backend for verification. Showing the
client success handler is not sufficient proof of payment.

### 6. Verify the checkout response

Add an endpoint such as:

```text
POST /payments/razorpay/verify
```

The server must:

1. Load its stored provider order ID using the Leaf order/payment attempt.
2. Compute HMAC-SHA256 over
   `stored_razorpay_order_id + "|" + razorpay_payment_id` using the Key Secret.
3. Compare it with `razorpay_signature` using a constant-time comparison.
4. Optionally fetch the payment from Razorpay for immediate status confirmation.
5. Mark the order paid only when the response is authentic and payment is
   captured.
6. Store provider IDs and clear/convert the cart exactly once.

Never use only the browser-returned order ID as the trusted value during
signature verification.

### 7. Configure webhooks

Create this public HTTPS endpoint:

```text
POST https://leaf.ads-ai.in/payments/razorpay/webhook
```

In the Razorpay Dashboard, configure the same URL and a separate webhook secret.
Recommended initial events:

- `order.paid`
- `payment.captured`
- `payment.failed`
- relevant refund events when refunds are implemented

Webhook handling requirements:

1. Read and retain the **raw request body** before JSON parsing.
2. Verify `X-Razorpay-Signature` using HMAC-SHA256 and the webhook secret.
3. Reject invalid signatures without updating an order.
4. Deduplicate events or make every state change idempotent.
5. Locate the payment attempt by provider order/payment ID.
6. Verify amount, currency and Leaf order association.
7. Apply only valid forward state transitions.
8. Return a `2xx` response quickly; move slow follow-up work to a worker when one
   is introduced.

Do not confuse the Checkout callback/handler with a webhook. The handler supports
the customer's immediate experience; the signed server-to-server webhook
reconciles payment state when a browser is closed or connectivity is interrupted.

### 8. Payment and order states

Recommended mapping:

| Provider condition | Leaf payment status | Leaf order status |
| --- | --- | --- |
| Provider order created | `pending` | `pending` |
| Authorized but not captured | `pending` | `pending` |
| Captured / order paid | `paid` | `confirmed` |
| Definitive payment failure | `failed` | `pending` or `cancelled` |
| Full refund completed | `refunded` | business-dependent |
| Partial refund completed | `partially_refunded` | business-dependent |

Avoid sending an online-payment order into fulfilment while payment is merely
authorized or pending.

### 9. Refund workflow

Refunds must be initiated by an authenticated administrator and recorded before
calling the provider. Store the provider refund ID, requested amount, reason,
actor and timestamps. Confirm the final status through a signed webhook or fetch
API response. A return is not automatically a refund; inventory, fulfilment and
payment states must remain separate.

### 10. Test Mode checklist

Test all of these before using live keys:

- successful UPI/card test payment
- user closes the checkout without paying
- simulated payment failure
- invalid checkout signature
- invalid webhook signature
- duplicate webhook delivery
- webhook delivered before/after the browser verification request
- refresh or double-click during checkout
- price changes or stock exhaustion before payment creation
- captured payment with a lost browser response
- failed/expired payment releases inventory
- COD remains operational
- admin and customer order pages show the correct payment state

Automated tests must mock provider HTTP calls. The normal test suite must never
contact Razorpay or use live credentials.

### 11. Go live safely

1. Complete end-to-end Test Mode acceptance.
2. Finish Razorpay live-account activation/KYC.
3. Generate **Live Mode** keys; never reuse test keys.
4. Add a live webhook using a new live webhook secret.
5. Confirm automatic capture and desired payment methods.
6. Back up the application and database.
7. Add live secrets directly to `/opt/leaf-store/.env` with restrictive file
   permissions.
8. Restart Leaf and check `/health`.
9. Make a small real payment and confirm capture, settlement visibility, webhook
   processing, order confirmation and admin display.
10. Monitor errors and reconcile the first live transactions in both Leaf and
    Razorpay dashboards.

Use a feature flag so online payment can be disabled without disabling COD:

```env
RAZORPAY_ENABLED=false
```

## Other payment providers

The same gateway interface can support Cashfree Payments, PayU, Stripe or another
provider. Provider-specific order/session creation and signature rules differ,
but the Leaf invariants remain the same:

- totals originate on the server;
- secrets stay on the server;
- every attempt is stored and traceable;
- callbacks and webhooks are cryptographically verified;
- webhook processing is idempotent;
- captured payment is required before fulfilment;
- refunds are recorded and reconciled.

For an India-focused clothing store, start with one provider rather than
implementing several simultaneously. Razorpay or Cashfree are typical candidates;
evaluate current pricing, activation requirements, settlement timing, support and
the payment methods enabled for the actual merchant account before choosing.

## Production deployment notes

The production application is expected at `/opt/leaf-store` and the included
systemd unit reads `/opt/leaf-store/.env`.

Typical safe deployment verification:

```bash
cd /opt/leaf-store
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest -q
sudo systemctl restart leaf-store.service
sudo systemctl is-active leaf-store.service
curl -fsS https://leaf.ads-ai.in/health
```

Create a database/application backup before running payment-related migrations.
Do not deploy payment code and live credentials for the first time in the same
untested step.

## Payment incident checklist

When a customer reports a payment issue:

1. Search by Leaf order number and provider payment/order ID.
2. Compare amount, currency and status in Leaf and the provider dashboard.
3. Check signed webhook delivery and response history.
4. Fetch current provider status when necessary.
5. Never mark an order paid based only on a screenshot, SMS or customer claim.
6. Do not retry a charge automatically.
7. Record any manual reconciliation action and administrator identity.

Common symptoms:

| Symptom | Likely check |
| --- | --- |
| Customer paid but Leaf says pending | Webhook delivery, signature verification, provider fetch |
| Authorized but no settlement | Capture settings/status |
| Duplicate orders | Idempotency key and repeated checkout submission |
| Signature mismatch | Correct test/live secret, stored order ID, raw webhook body |
| Test payment appears successful but no money settles | Test keys are still active |
| Provider paid but stock unavailable | Inventory reservation timing and expiry policy |

## Security baseline

- Require HTTPS for checkout, verification and webhook endpoints.
- Keep framework and payment dependencies patched and pinned.
- Apply rate limits to payment-order creation and verification endpoints.
- Protect admin refund actions with authentication, CSRF controls and audit logs.
- Use constant-time signature comparison.
- Validate all provider IDs, amounts, currencies and order ownership.
- Do not handle or store raw card data; use the provider-hosted checkout.
- Rotate compromised keys immediately and reconcile affected transactions.
- Keep backups encrypted and restrict access to production `.env` and logs.
