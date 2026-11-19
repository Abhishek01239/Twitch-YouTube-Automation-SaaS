-- Streamers who have explicitly allowed this user to clip their channel.
-- Clips are only fetched when the streamer has also added the user's Twitch account
-- as a channel editor (Twitch enforces this on the clip download endpoint).
create table if not exists public.approved_streamers(
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  twitch_user_id text not null,
  twitch_login text not null,
  twitch_display_name text not null,
  permission_note text not null check(length(trim(permission_note))>0),
  game_id text,
  game_name text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique(user_id,twitch_user_id)
);
alter table public.approved_streamers enable row level security;
create policy "users manage own approved streamers" on public.approved_streamers
  for all using(auth.uid()=user_id) with check(auth.uid()=user_id);

-- The user's own gameplay recordings, cut into highlight Shorts by the worker.
create table if not exists public.gameplay_uploads(
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  storage_path text not null unique,
  title text,
  game_name text not null default 'Grand Theft Auto VI',
  clip_count integer not null default 3 check(clip_count between 1 and 10),
  clip_seconds integer not null default 30 check(clip_seconds between 10 and 60),
  status text not null default 'pending' check(status in ('pending','processing','done','failed')),
  clips_created integer not null default 0,
  last_error text,
  created_at timestamptz not null default now()
);
alter table public.gameplay_uploads enable row level security;
create policy "users read own gameplay uploads" on public.gameplay_uploads
  for select using(auth.uid()=user_id);
create policy "users add own gameplay uploads" on public.gameplay_uploads
  for insert with check(auth.uid()=user_id and status='pending' and storage_path like auth.uid()::text||'/%');

insert into storage.buckets(id,name,public) values('gameplay-uploads','gameplay-uploads',false)
on conflict(id) do update set public=false;
create policy "users upload own gameplay" on storage.objects for insert to authenticated
  with check(bucket_id='gameplay-uploads' and (storage.foldername(name))[1]=auth.uid()::text);
create policy "users read own gameplay" on storage.objects for select to authenticated
  using(bucket_id='gameplay-uploads' and (storage.foldername(name))[1]=auth.uid()::text);

-- Track where each source Short came from and who may distribute it.
alter table public.source_shorts
  add column if not exists owner_user_id uuid references public.profiles(id) on delete cascade,
  add column if not exists source_kind text not null default 'own_twitch' check(source_kind in ('own_twitch','approved_streamer','own_gameplay')),
  add column if not exists credit_text text,
  add column if not exists dedupe_key text;
create unique index if not exists source_shorts_dedupe_key_unique on public.source_shorts(dedupe_key) where dedupe_key is not null;
create index if not exists source_shorts_owner_idx on public.source_shorts(owner_user_id);
