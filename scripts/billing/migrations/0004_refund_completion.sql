BEGIN;

ALTER TABLE payment_order
    ADD COLUMN refunded_at timestamptz,
    ADD COLUMN refund_state text NOT NULL DEFAULT 'NONE'
        CHECK (refund_state IN ('NONE','PROCESSING','REFUNDED','REVIEW_REQUIRED'));

ALTER TABLE quota_adjustment
    ADD COLUMN refund_id uuid REFERENCES refund(refund_id),
    DROP CONSTRAINT quota_adjustment_order_id_direction_key,
    ADD CONSTRAINT quota_adjustment_refund_binding_check CHECK (
        (direction='CREDIT' AND refund_id IS NULL) OR
        (direction='DEBIT' AND refund_id IS NOT NULL)
    );

CREATE UNIQUE INDEX quota_adjustment_one_credit_per_order_idx
    ON quota_adjustment (order_id) WHERE direction='CREDIT';
CREATE UNIQUE INDEX quota_adjustment_one_debit_per_refund_idx
    ON quota_adjustment (refund_id) WHERE direction='DEBIT';

DROP INDEX journal_one_reversal_idx;

ALTER TABLE refund
    ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    ADD COLUMN last_error_code varchar(128);

CREATE INDEX refund_attempt_due_idx
    ON refund (next_attempt_at, updated_at)
    WHERE state IN ('QUOTA_REVERSED', 'WECHAT_PROCESSING');

CREATE INDEX payment_order_refunded_idx
    ON payment_order (refunded_at)
    WHERE refunded_at IS NOT NULL;

INSERT INTO billing_schema_version (version, migration_sha256)
VALUES (4, 'aaf9ede21eb263b4dc7f8e5120d1706152d628d22bf6dba9c847a1f16c906e6b');

COMMIT;
