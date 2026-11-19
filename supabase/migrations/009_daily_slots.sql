-- Daily schedule: 4 Shorts + 1 long-form video at 6am, 9am, 12pm, 3pm, 6pm America/New_York.
alter table public.source_shorts
  add column if not exists kind text not null default 'short',
  add column if not exists compilation_date date;

alter table public.source_shorts drop constraint if exists source_shorts_kind_check;
alter table public.source_shorts
  add constraint source_shorts_kind_check check (kind in ('short','video'));

-- One compiled long-form video per New York calendar day.
create unique index if not exists source_shorts_video_day_unique
  on public.source_shorts(compilation_date)
  where kind = 'video';

create index if not exists source_shorts_kind_created_idx
  on public.source_shorts(kind, created_at desc);
