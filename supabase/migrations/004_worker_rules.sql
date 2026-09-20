-- Remove the old token columns after migration 003 moved them to protected token tables.
-- Kept as a separate migration so fresh and existing databases can be upgraded safely.
alter table public.channels
  drop column if exists youtube_access_token,
  drop column if exists youtube_refresh_token,
  drop column if exists youtube_token_expires_at;

alter table public.twitch_connections
  drop column if exists twitch_access_token,
  drop column if exists twitch_refresh_token,
  drop column if exists twitch_token_expires_at;
