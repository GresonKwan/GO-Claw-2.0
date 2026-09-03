# GO CLAW Billing Service

This service implements the server side of the compute-recharge contracts in
`docs/contracts/compute-recharge`. It is intentionally disabled by default.

## Safety status

- Development and test mode use a fake payment provider and in-memory stores.
- Non-development uses versioned PostgreSQL migrations and refuses readiness
  below schema version 4. Migrations never run in application startup.
- Signed WeChat callbacks and signed query recovery are both idempotent. Order
  close always queries WeChat first. An ambiguous external result never becomes
  a local success.
- Refunds are internal/customer-service only and require two distinct operator
  identities. Customer service chooses any positive amount up to the order's
  remaining refundable amount. The service reverses the exact proportional
  quota first, then requests WeChat refund, and shows `REFUNDED` only after
  signed completion.
- No WeChat merchant secret, NewAPI admin token, database DSN, billing bearer
  token, or decrypted payer identity may enter Git, a ZIP, logs, or CI artifacts.
- Disabling new orders must not disable processing of already-paid orders,
  callbacks, payment recovery, quota recovery, refunds, or outbox draining.

## Production activation gate

Keep `GO_CLAW_BILLING_ENABLED=false` through deployment and callback probing.
Before enabling new orders, all of the following must pass:

1. apply migrations `0001` through `0004` with `ON_ERROR_STOP=1`;
2. readiness reports HTTP 200 and the exact transaction/refund callback paths
   are reachable without redirect;
3. inject every credential through systemd `LoadCredential`, including a
   separate `admin_token`; never place values in `non-secret.env`;
4. verify the bound NewAPI build exposes signed/admin-authenticated
   `GET /api/user/{id}` and returns an integer non-negative `data.quota`;
5. complete one staging ￥1 Native payment, confirm exactly one PAYMENT and one
   QUOTA_CREDIT journal, then complete the reviewed refund drill;
6. only after reconciliation and rollback evidence is archived may the feature
   flag be enabled for customers.

Run migrations explicitly (never from application startup):

```bash
/opt/go-claw-billing/.venv/bin/python /opt/go-claw-billing/migrate.py \
  --dsn-file /etc/go-claw-billing/credentials/database_dsn
```

## Operator payment recovery

If a callback or quota commit fails after the customer has paid, do not reset
the order state and do not ask the customer to pay again. Query the exact order
from WeChat first; the command is read-only unless `--commit` is present and
prints only non-sensitive verification fields:

```bash
/opt/go-claw-billing/.venv/bin/python \
  /opt/go-claw-billing/operator_recover_payment.py \
  00000000-0000-0000-0000-000000000000
```

Only after the result reports `signedResponseVerified=true`,
`tradeState=SUCCESS`, and the expected amount may an operator append
`--commit`. The database transition accepts `PAYMENT_REVIEW_REQUIRED` only
through the same signed confirmation path. Replaying the command must report
one credit adjustment and one PAYMENT journal; it must never create a second
credit.

## Customer-service refund entry

There is intentionally no customer refund button or desktop route. A customer
contacts support through WeChat or the commerce platform; support records the
case and a second operator reviews the amount. An authorized operator then runs
`refund_cli.py` on the billing host. The public Nginx route for `/internal/`
returns 404, so this entry is unavailable from customer devices.

Example (identifiers only; never paste credentials on the command line):

```bash
/opt/go-claw-billing/.venv/bin/python /opt/go-claw-billing/refund_cli.py \
  --order-id 00000000-0000-0000-0000-000000000000 \
  --amount-cny 1.00 --reason '客服工单 CS-20260903-001' \
  --evidence-ref 'CS-20260903-001' \
  --operator-id support-a --approver-id finance-b
```

## Local contract tests

```powershell
$env:PYTHONPATH = "scripts/billing"
python -m pytest scripts/billing/tests -q
```

Do not deploy by copying `.env.example`. Production values must be injected by
the deployment secret manager. Merchant onboarding and the production feature
flag require the product, finance, legal, security, and operations approvals
listed in the implementation plan.
