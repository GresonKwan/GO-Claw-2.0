BEGIN;

-- The approved v1 policy is immutable.  A future price/terms change inserts a
-- new version and closes the previous effective range in a reviewed migration.
INSERT INTO pricing_policy (
    version, currency, display_compute_units_per_fen,
    newapi_quota_units_per_fen, min_amount_fen, max_amount_fen,
    preset_amounts_fen, amount_step_fen, daily_limit_fen, terms_version,
    effective_from, created_by
) VALUES (
    'cny-v1', 'CNY', 50000,
    750, 100, 10000000,
    ARRAY[1000, 5000, 10000, 20000]::bigint[], 1, 10000000, '2026-09-v1',
    '2026-09-03T00:00:00Z', 'migration-0002'
) ON CONFLICT (version) DO NOTHING;

CREATE TRIGGER pricing_policy_immutable
BEFORE UPDATE OR DELETE ON pricing_policy
FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();

-- PostgreSQL's ordinary UNIQUE permits multiple NULL owners.  Platform ledger
-- accounts use a NULL owner, so make NULL compare equal for this identity.
CREATE UNIQUE INDEX ledger_account_identity_v2_idx
    ON ledger_account (account_code, owner_account_id, asset_code)
    NULLS NOT DISTINCT;

CREATE TABLE billing_schema_version (
    version integer PRIMARY KEY CHECK (version > 0),
    installed_at timestamptz NOT NULL DEFAULT now(),
    migration_sha256 text NOT NULL CHECK (char_length(migration_sha256) = 64)
);

INSERT INTO billing_schema_version (version, migration_sha256)
VALUES (2, '5acf098e5fbf680d03c100b2b842f5c81b0d5adafa399a1872024352fe645883');

COMMIT;
