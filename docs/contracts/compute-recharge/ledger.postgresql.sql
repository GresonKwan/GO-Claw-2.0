-- GO CLAW Compute Recharge ledger contract template
-- Target: PostgreSQL 16+
-- Amounts are integers. CNY uses fen; customer display uses DISPLAY_COMPUTE_UNIT;
-- NewAPI execution uses NEWAPI_QUOTA_UNIT. These unit types must never be mixed.
-- This schema is a contract and must be installed through versioned migrations.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE billing_account (
    account_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id             uuid NOT NULL UNIQUE,
    newapi_user_id          bigint NOT NULL UNIQUE CHECK (newapi_user_id > 0),
    status                  text NOT NULL DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE billing_access_token (
    token_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id              uuid NOT NULL REFERENCES billing_account(account_id),
    token_hash              text NOT NULL,
    token_version           integer NOT NULL CHECK (token_version > 0),
    status                  text NOT NULL DEFAULT 'ISSUED'
                            CHECK (status IN ('ISSUED', 'ACTIVE', 'REVOKED')),
    issued_expires_at       timestamptz NOT NULL,
    first_authenticated_at  timestamptz,
    last_authenticated_at   timestamptz,
    revoked_at              timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, token_version),
    CHECK (issued_expires_at > created_at),
    CHECK (status <> 'ACTIVE' OR first_authenticated_at IS NOT NULL),
    CHECK (status <> 'REVOKED' OR revoked_at IS NOT NULL)
);

CREATE INDEX billing_access_token_account_status_idx
    ON billing_access_token (account_id, status, token_version DESC);

COMMENT ON COLUMN billing_access_token.token_hash IS
    'Argon2id hash only. Bearer token plaintext must never enter the database.';

CREATE TABLE pricing_policy (
    policy_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version                   text NOT NULL UNIQUE,
    currency                  text NOT NULL CHECK (currency = 'CNY'),
    display_compute_units_per_fen bigint NOT NULL
                                  CHECK (display_compute_units_per_fen = 50000),
    newapi_quota_units_per_fen bigint NOT NULL
                                  CHECK (newapi_quota_units_per_fen = 750),
    min_amount_fen            bigint NOT NULL CHECK (min_amount_fen = 100),
    max_amount_fen            bigint NOT NULL CHECK (max_amount_fen = 10000000),
    preset_amounts_fen        bigint[] NOT NULL
                                  CHECK (preset_amounts_fen = ARRAY[1000, 5000, 10000, 20000]::bigint[]),
    amount_step_fen           bigint NOT NULL CHECK (amount_step_fen = 1),
    daily_limit_fen           bigint CHECK (
                                  daily_limit_fen IS NULL OR
                                  daily_limit_fen >= max_amount_fen
                              ),
    terms_version             text NOT NULL,
    effective_from            timestamptz NOT NULL,
    effective_until           timestamptz,
    created_by                text NOT NULL,
    created_at                timestamptz NOT NULL DEFAULT now(),
    CHECK (effective_until IS NULL OR effective_until > effective_from)
);

COMMENT ON TABLE pricing_policy IS
    'Immutable price versions. Create a new row; never rewrite a referenced policy.';

CREATE TABLE request_idempotency (
    account_id              uuid NOT NULL REFERENCES billing_account(account_id),
    idempotency_key         text NOT NULL,
    operation               text NOT NULL,
    request_sha256          bytea NOT NULL CHECK (octet_length(request_sha256) = 32),
    response_status         integer,
    response_body           jsonb,
    resource_id             uuid,
    created_at              timestamptz NOT NULL DEFAULT now(),
    expires_at              timestamptz NOT NULL,
    PRIMARY KEY (account_id, operation, idempotency_key),
    CHECK (char_length(idempotency_key) BETWEEN 16 AND 64),
    CHECK (expires_at > created_at)
);

CREATE TABLE payment_order (
    order_id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id                uuid NOT NULL REFERENCES billing_account(account_id),
    pricing_policy_id         uuid NOT NULL REFERENCES pricing_policy(policy_id),
    pricing_version           text NOT NULL,
    terms_version             text NOT NULL,
    out_trade_no              varchar(32) NOT NULL UNIQUE,
    amount_fen                bigint NOT NULL CHECK (
                                  amount_fen BETWEEN 100 AND 10000000
                              ),
    currency                  text NOT NULL CHECK (currency = 'CNY'),
    display_compute_units     bigint NOT NULL CHECK (display_compute_units > 0),
    display_compute_units_per_fen bigint NOT NULL
                                  CHECK (display_compute_units_per_fen = 50000),
    newapi_quota_units        bigint NOT NULL CHECK (newapi_quota_units > 0),
    newapi_quota_units_per_fen bigint NOT NULL
                                  CHECK (newapi_quota_units_per_fen = 750),
    payment_state             text NOT NULL
                              CHECK (payment_state IN (
                                  'CREATED', 'QR_READY', 'PAID', 'EXPIRED',
                                  'CLOSED', 'PAYMENT_REVIEW_REQUIRED'
                              )),
    grant_state               text NOT NULL DEFAULT 'NOT_REQUESTED'
                              CHECK (grant_state IN (
                                  'NOT_REQUESTED', 'QUEUED', 'APPLYING',
                                  'APPLIED', 'REVERSING', 'REVERSED',
                                  'REVIEW_REQUIRED'
                              )),
    code_url_ciphertext       bytea,
    code_url_key_version      integer,
    wechat_transaction_id     varchar(32) UNIQUE,
    paid_at                   timestamptz,
    credited_at               timestamptz,
    expires_at                timestamptz NOT NULL,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    row_version               bigint NOT NULL DEFAULT 1 CHECK (row_version > 0),
    CHECK (display_compute_units = amount_fen * display_compute_units_per_fen),
    CHECK (newapi_quota_units = amount_fen * newapi_quota_units_per_fen),
    CHECK (expires_at > created_at),
    CHECK (payment_state <> 'PAID' OR (wechat_transaction_id IS NOT NULL AND paid_at IS NOT NULL)),
    CHECK (grant_state <> 'APPLIED' OR credited_at IS NOT NULL)
);

CREATE INDEX payment_order_account_created_idx
    ON payment_order (account_id, created_at DESC, order_id DESC);
CREATE INDEX payment_order_recovery_idx
    ON payment_order (payment_state, grant_state, updated_at);

CREATE TABLE webhook_inbox (
    provider                  text NOT NULL CHECK (provider = 'WECHATPAY'),
    event_id                  varchar(64) NOT NULL,
    event_type                varchar(64) NOT NULL,
    serial_id                 varchar(128) NOT NULL,
    raw_body_sha256           bytea NOT NULL CHECK (octet_length(raw_body_sha256) = 32),
    encrypted_body            bytea,
    encryption_key_version    integer,
    signature_verified_at     timestamptz NOT NULL,
    received_at               timestamptz NOT NULL DEFAULT now(),
    processed_at              timestamptz,
    processing_error_code     text,
    PRIMARY KEY (provider, event_id)
);

COMMENT ON TABLE webhook_inbox IS
    'Stores dedupe and evidence. Decrypted payer identifiers are not retained unless legally required.';

CREATE TABLE quota_adjustment (
    adjustment_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id                  uuid NOT NULL REFERENCES payment_order(order_id),
    account_id                uuid NOT NULL REFERENCES billing_account(account_id),
    newapi_user_id            bigint NOT NULL CHECK (newapi_user_id > 0),
    direction                 text NOT NULL CHECK (direction IN ('CREDIT', 'DEBIT')),
    newapi_quota_units        bigint NOT NULL CHECK (newapi_quota_units > 0),
    state                     text NOT NULL
                              CHECK (state IN (
                                  'QUEUED', 'APPLYING', 'APPLIED',
                                  'FAILED_RETRYABLE', 'REVIEW_REQUIRED'
                              )),
    reversal_of_adjustment_id uuid REFERENCES quota_adjustment(adjustment_id),
    attempt_id                uuid,
    attempt_started_at        timestamptz,
    applied_at                timestamptz,
    last_error_code           text,
    evidence_sha256           bytea CHECK (
                                  evidence_sha256 IS NULL OR
                                  octet_length(evidence_sha256) = 32
                              ),
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_id, direction),
    CHECK (state <> 'APPLIED' OR applied_at IS NOT NULL),
    CHECK (direction <> 'DEBIT' OR reversal_of_adjustment_id IS NOT NULL)
);

CREATE UNIQUE INDEX quota_adjustment_one_applying_per_user_idx
    ON quota_adjustment (newapi_user_id)
    WHERE state = 'APPLYING';
CREATE INDEX quota_adjustment_worker_idx
    ON quota_adjustment (state, updated_at);

CREATE TABLE refund (
    refund_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id                  uuid NOT NULL REFERENCES payment_order(order_id),
    account_id                uuid NOT NULL REFERENCES billing_account(account_id),
    out_refund_no             varchar(64) NOT NULL UNIQUE,
    wechat_refund_id          varchar(32) UNIQUE,
    amount_fen                bigint NOT NULL CHECK (amount_fen > 0),
    display_compute_units     bigint NOT NULL CHECK (display_compute_units > 0),
    newapi_quota_units        bigint NOT NULL CHECK (newapi_quota_units > 0),
    state                     text NOT NULL
                              CHECK (state IN (
                                  'REQUESTED', 'QUOTA_REVERSING', 'QUOTA_REVERSED',
                                  'WECHAT_PROCESSING', 'REFUNDED', 'REVIEW_REQUIRED'
                              )),
    reason                    text NOT NULL CHECK (char_length(reason) BETWEEN 3 AND 500),
    requested_by              text NOT NULL,
    approved_by               text,
    completed_at              timestamptz,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    CHECK (state <> 'REFUNDED' OR (wechat_refund_id IS NOT NULL AND completed_at IS NOT NULL))
);

CREATE INDEX refund_recovery_idx ON refund (state, updated_at);

CREATE TABLE ledger_account (
    ledger_account_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_code              text NOT NULL,
    asset_code                text NOT NULL CHECK (
                                  asset_code IN ('CNY_FEN', 'NEWAPI_QUOTA_UNIT')
                              ),
    owner_account_id          uuid REFERENCES billing_account(account_id),
    created_at                timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_code, owner_account_id, asset_code),
    UNIQUE (ledger_account_id, asset_code)
);

CREATE TABLE journal_entry (
    journal_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_type              text NOT NULL CHECK (journal_type IN (
                                  'PAYMENT', 'QUOTA_CREDIT', 'QUOTA_REVERSAL', 'REFUND'
                              )),
    order_id                  uuid NOT NULL REFERENCES payment_order(order_id),
    refund_id                 uuid REFERENCES refund(refund_id),
    reversal_of_journal_id    uuid REFERENCES journal_entry(journal_id),
    correlation_id            uuid NOT NULL,
    description               text NOT NULL,
    occurred_at               timestamptz NOT NULL,
    posted_at                 timestamptz NOT NULL DEFAULT now(),
    previous_hash             bytea CHECK (
                                  previous_hash IS NULL OR octet_length(previous_hash) = 32
                              ),
    entry_hash                bytea NOT NULL UNIQUE CHECK (octet_length(entry_hash) = 32),
    key_version               integer NOT NULL CHECK (key_version > 0),
    created_by                text NOT NULL
);

CREATE UNIQUE INDEX journal_one_reversal_idx
    ON journal_entry (reversal_of_journal_id)
    WHERE reversal_of_journal_id IS NOT NULL;
CREATE INDEX journal_order_idx ON journal_entry (order_id, occurred_at);

CREATE TABLE journal_line (
    line_id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_id                uuid NOT NULL REFERENCES journal_entry(journal_id),
    ledger_account_id         uuid NOT NULL,
    asset_code                text NOT NULL CHECK (
                                  asset_code IN ('CNY_FEN', 'NEWAPI_QUOTA_UNIT')
                              ),
    debit_amount              bigint NOT NULL DEFAULT 0 CHECK (debit_amount >= 0),
    credit_amount             bigint NOT NULL DEFAULT 0 CHECK (credit_amount >= 0),
    memo                      text,
    FOREIGN KEY (ledger_account_id, asset_code)
        REFERENCES ledger_account(ledger_account_id, asset_code),
    CHECK (
        (debit_amount > 0 AND credit_amount = 0) OR
        (credit_amount > 0 AND debit_amount = 0)
    )
);

CREATE INDEX journal_line_journal_idx ON journal_line (journal_id, asset_code);

CREATE TABLE outbox_event (
    event_id                  uuid PRIMARY KEY,
    aggregate_type            text NOT NULL,
    aggregate_id              uuid NOT NULL,
    event_type                text NOT NULL,
    event_version             integer NOT NULL CHECK (event_version = 1),
    correlation_id            uuid NOT NULL,
    causation_id              uuid,
    payload                   jsonb NOT NULL,
    state                     text NOT NULL DEFAULT 'PENDING'
                              CHECK (state IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED')),
    attempts                  integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at              timestamptz NOT NULL DEFAULT now(),
    created_at                timestamptz NOT NULL DEFAULT now(),
    published_at              timestamptz,
    last_error_code           text
);

CREATE INDEX outbox_worker_idx ON outbox_event (state, available_at, created_at);

CREATE TABLE audit_event (
    audit_id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type                text NOT NULL CHECK (actor_type IN ('SYSTEM', 'ACCOUNT', 'OPERATOR')),
    actor_id                  text NOT NULL,
    action                    text NOT NULL,
    resource_type             text NOT NULL,
    resource_id               text NOT NULL,
    reason                    text,
    evidence_sha256           bytea CHECK (
                                  evidence_sha256 IS NULL OR octet_length(evidence_sha256) = 32
                              ),
    metadata                  jsonb NOT NULL DEFAULT '{}'::jsonb,
    previous_hash             bytea CHECK (
                                  previous_hash IS NULL OR octet_length(previous_hash) = 32
                              ),
    event_hash                bytea NOT NULL UNIQUE CHECK (octet_length(event_hash) = 32),
    key_version               integer NOT NULL CHECK (key_version > 0),
    occurred_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_resource_idx
    ON audit_event (resource_type, resource_id, occurred_at);

CREATE TABLE reconciliation_run (
    run_id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    business_date            date NOT NULL UNIQUE,
    state                     text NOT NULL
                              CHECK (state IN ('RUNNING', 'MATCHED', 'DIFFERENCES', 'FAILED')),
    wechat_bill_sha256        bytea CHECK (
                                  wechat_bill_sha256 IS NULL OR octet_length(wechat_bill_sha256) = 32
                              ),
    ledger_root_hash          bytea CHECK (
                                  ledger_root_hash IS NULL OR octet_length(ledger_root_hash) = 32
                              ),
    ledger_root_signature     bytea,
    signature_key_version     integer,
    immutable_archive_uri     text,
    started_at                timestamptz NOT NULL DEFAULT now(),
    completed_at              timestamptz
);

CREATE TABLE reconciliation_item (
    item_id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                    uuid NOT NULL REFERENCES reconciliation_run(run_id),
    severity                  text NOT NULL CHECK (severity IN ('P0', 'P1', 'P2')),
    difference_type           text NOT NULL,
    order_id                  uuid REFERENCES payment_order(order_id),
    refund_id                 uuid REFERENCES refund(refund_id),
    details                   jsonb NOT NULL,
    resolved_at               timestamptz,
    resolved_by               text,
    resolution_reason         text,
    created_at                timestamptz NOT NULL DEFAULT now()
);

-- Immutable journal and audit rows. Corrections must be new reversal rows.
CREATE OR REPLACE FUNCTION reject_immutable_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; insert a reversal/correction instead', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER journal_entry_immutable
BEFORE UPDATE OR DELETE ON journal_entry
FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();

CREATE TRIGGER journal_line_immutable
BEFORE UPDATE OR DELETE ON journal_line
FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();

CREATE TRIGGER audit_event_immutable
BEFORE UPDATE OR DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();

-- Every posted journal must contain at least two lines and balance per asset.
CREATE OR REPLACE FUNCTION assert_journal_balanced()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    target_journal uuid;
    line_count bigint;
    unbalanced_assets bigint;
BEGIN
    target_journal := CASE
        WHEN TG_TABLE_NAME = 'journal_entry' THEN NEW.journal_id
        ELSE NEW.journal_id
    END;

    SELECT count(*)
      INTO line_count
      FROM journal_line
     WHERE journal_id = target_journal;

    SELECT count(*)
      INTO unbalanced_assets
      FROM (
          SELECT asset_code
            FROM journal_line
           WHERE journal_id = target_journal
           GROUP BY asset_code
          HAVING sum(debit_amount) <> sum(credit_amount)
      ) AS differences;

    IF line_count < 2 OR unbalanced_assets <> 0 THEN
        RAISE EXCEPTION 'journal % is not balanced', target_journal;
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER journal_entry_balance_guard
AFTER INSERT ON journal_entry
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_journal_balanced();

CREATE CONSTRAINT TRIGGER journal_line_balance_guard
AFTER INSERT ON journal_line
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_journal_balanced();

-- PUBLIC must never be able to mutate evidence tables.
REVOKE UPDATE, DELETE, TRUNCATE ON journal_entry, journal_line, audit_event FROM PUBLIC;

-- Example seed policy. Replace operator identity and effective timestamp in a migration.
-- INSERT INTO pricing_policy (
--     version, currency, display_compute_units_per_fen,
--     newapi_quota_units_per_fen, min_amount_fen, max_amount_fen,
--     preset_amounts_fen, amount_step_fen, daily_limit_fen, terms_version,
--     effective_from, created_by
-- ) VALUES (
--     '2026-09-v1', 'CNY', 50000,
--     750, 100, 10000000,
--     ARRAY[1000, 5000, 10000, 20000]::bigint[], 1, NULL, '2026-09-v1',
--     '2026-09-10T00:00:00Z', 'migration'
-- );
