-- ==================================================
-- Refresh Token Performance Optimization Migration
-- ==================================================
-- 1. Add deterministic hash column for fast lookup
-- 2. Add supporting index
-- ==================================================

ALTER TABLE public.refresh_tokens
ADD COLUMN IF NOT EXISTS token_sha256 VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_sha256
ON public.refresh_tokens(token_sha256);

-- Optional: backfill token_sha256 for existing rows is not possible
-- because original refresh token plaintext is not stored.
-- Existing tokens will continue to use the legacy lookup path
-- until they naturally expire (7 days by default).

