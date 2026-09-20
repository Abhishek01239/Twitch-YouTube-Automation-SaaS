create extension if not exists pgcrypto;

create table if not exists public.profiles(id uuid primary key references auth.users(id) on delete cascade,email text,created_at timestamptz not null default now());
create table if not exists public.channels(id uuid primary key default gen_random_uuid(),user_id uuid not null references public.profiles(id) on delete cascade,name text not null,twitch_user_id text,twitch_login text,youtube_channel_id text,youtube_access_token text,youtube_refresh_token text,youtube_token_expires_at timestamptz,status text not null default 'inactive' check(status in ('inactive','active','paused')),created_at timestamptz not null default now());
create table if not exists public.subscriptions(id uuid primary key default gen_random_uuid(),channel_id uuid not null unique references public.channels(id) on delete cascade,razorpay_subscription_id text unique,status text not null default 'inactive' check(status in ('inactive','active','paused','cancelled','expired')),amount_paise integer not null default 9900,current_period_end timestamptz,created_at timestamptz not null default now());
create table if not exists public.source_shorts(id uuid primary key default gen_random_uuid(),source_url text,storage_path text,title text,description text,tags text[] not null default '{}',hashtags text[] not null default '{}',created_at timestamptz not null default now());
create table if not exists public.upload_jobs(id uuid primary key default gen_random_uuid(),source_short_id uuid not null references public.source_shorts(id) on delete cascade,channel_id uuid not null references public.channels(id) on delete cascade,scheduled_at timestamptz not null,status text not null default 'pending' check(status in ('pending','processing','uploaded','failed','skipped')),youtube_video_id text,attempts integer not null default 0,last_error text,created_at timestamptz not null default now(),unique(source_short_id,channel_id));
create index if not exists upload_jobs_due_idx on public.upload_jobs(status,scheduled_at);
create index if not exists channels_user_idx on public.channels(user_id);

alter table public.profiles enable row level security;
alter table public.channels enable row level security;
alter table public.subscriptions enable row level security;
alter table public.source_shorts enable row level security;
alter table public.upload_jobs enable row level security;

create policy "users read own profile" on public.profiles for select using(auth.uid()=id);
create policy "users read own channels" on public.channels for select using(auth.uid()=user_id);
create policy "users manage own channels" on public.channels for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
create policy "users read own subscriptions" on public.subscriptions for select using(exists(select 1 from public.channels c where c.id=channel_id and c.user_id=auth.uid()));
create policy "users read own jobs" on public.upload_jobs for select using(exists(select 1 from public.channels c where c.id=channel_id and c.user_id=auth.uid()));

create or replace function public.handle_new_user() returns trigger language plpgsql security definer set search_path=public as $$
begin
  insert into public.profiles(id,email) values(new.id,new.email)
  on conflict(id) do update set email=excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute procedure public.handle_new_user();

-- Scheduling rule: a channel's pending upload must be at least 2 hours after its previous uploaded/processing distribution.
create or replace function public.can_schedule_channel_upload(p_channel_id uuid, p_scheduled_at timestamptz)
returns boolean language sql stable as $$
  select not exists (
    select 1 from public.upload_jobs
    where channel_id=p_channel_id
      and status in ('uploaded','processing')
      and abs(extract(epoch from (p_scheduled_at-scheduled_at))) < 7200
  );
$$;
