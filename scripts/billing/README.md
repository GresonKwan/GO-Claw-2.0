# GO CLAW Billing Service

This service implements the server side of the compute-recharge contracts in
`docs/contracts/compute-recharge`. It is intentionally disabled by default.

## Safety status

- Development and test mode use a fake payment provider and in-memory stores.
- Non-development startup currently fails closed until the durable PostgreSQL
  repositories and their fault-injection suite are enabled.
- No WeChat merchant secret, NewAPI admin token, database DSN, billing bearer
  token, or decrypted payer identity may enter Git, a ZIP, logs, or CI artifacts.
- Disabling new orders must not disable processing of already-paid orders,
  callbacks, quota recovery, refunds, or reconciliation.

## Local contract tests

```powershell
$env:PYTHONPATH = "scripts/billing"
python -m pytest scripts/billing/tests -q
```

Do not deploy by copying `.env.example`. Production values must be injected by
the deployment secret manager. Merchant onboarding and the production feature
flag require the product, finance, legal, security, and operations approvals
listed in the implementation plan.
