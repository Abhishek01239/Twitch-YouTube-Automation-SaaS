alter table public.source_shorts
  add column if not exists edited_storage_path text;

create index if not exists source_shorts_edited_path_idx
  on public.source_shorts(edited_storage_path)
  where edited_storage_path is not null;
