BEGIN;

ALTER TABLE payment_order
    ADD COLUMN next_recovery_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN recovery_attempts integer NOT NULL DEFAULT 0
        CHECK (recovery_attempts >= 0),
    ADD COLUMN recovery_error_code varchar(128);

CREATE INDEX payment_order_payment_recovery_due_idx
    ON payment_order (next_recovery_at, created_at)
    WHERE payment_state IN ('CREATED', 'QR_READY');

INSERT INTO billing_schema_version (version, migration_sha256)
VALUES (3, 'ed3818958e0caa472f69fa17ac5aea6e5cdce331fcc20a5f87f216e04e1f26a1');

COMMIT;
