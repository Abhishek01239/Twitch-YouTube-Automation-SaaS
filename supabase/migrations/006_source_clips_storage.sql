insert into storage.buckets (id, name, public)
values ('source-clips', 'source-clips', false)
on conflict (id) do update set public = false;
