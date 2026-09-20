create table if not exists public.twitch_connections(
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references public.profiles(id) on delete cascade,
  twitch_user_id text not null unique,
  twitch_login text not null,
  twitch_display_name text not null,
  twitch_access_token text not null,
  twitch_refresh_token text not null,
  twitch_token_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.twitch_connections enable row level security;

create policy "users read own twitch connection"
  on public.twitch_connections for select
  using(auth.uid()=user_id);

create or replace function public.update_twitch_connection_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at=now();
  return new;
end;
$$;

drop trigger if exists twitch_connections_updated_at on public.twitch_connections;
create trigger twitch_connections_updated_at
before update on public.twitch_connections
for each row execute procedure public.update_twitch_connection_updated_at();
