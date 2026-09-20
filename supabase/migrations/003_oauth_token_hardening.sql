-- Keep OAuth secrets out of tables that authenticated users can read.
create table if not exists public.twitch_tokens(
  connection_id uuid primary key references public.twitch_connections(id) on delete cascade,
  access_token text not null,
  refresh_token text not null,
  token_expires_at timestamptz,
  scopes text[] not null default '{}',
  updated_at timestamptz not null default now()
);

insert into public.twitch_tokens(connection_id,access_token,refresh_token,token_expires_at)
select id,twitch_access_token,twitch_refresh_token,twitch_token_expires_at
from public.twitch_connections
on conflict(connection_id) do update set
  access_token=excluded.access_token,
  refresh_token=excluded.refresh_token,
  token_expires_at=excluded.token_expires_at;

alter table public.twitch_tokens enable row level security;
revoke all on public.twitch_tokens from anon,authenticated;

alter table public.twitch_connections
  drop column if exists twitch_access_token,
  drop column if exists twitch_refresh_token,
  drop column if exists twitch_token_expires_at;

create table if not exists public.youtube_tokens(
  channel_id uuid primary key references public.channels(id) on delete cascade,
  access_token text not null,
  refresh_token text not null,
  token_expires_at timestamptz,
  scopes text[] not null default '{}',
  updated_at timestamptz not null default now()
);

alter table public.youtube_tokens enable row level security;
revoke all on public.youtube_tokens from anon,authenticated;

alter table public.channels
  drop column if exists youtube_access_token,
  drop column if exists youtube_refresh_token,
  drop column if exists youtube_token_expires_at;
