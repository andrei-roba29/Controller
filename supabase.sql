-- PadLink: Realtime authorization.
--
-- Already applied to project ljvafmdhcpxbtstaljqb ("padlink"). Keep this file in
-- sync if you point PadLink at a different Supabase project.
--
-- Supabase Realtime checks broadcast/presence traffic against RLS policies on
-- `realtime.messages`. These two policies let the anonymous key send and receive
-- on nothing but a `padlink:<ROOMCODE>` topic, so the anon key that ships inside
-- the public website cannot read or write any other channel in this project.

alter table realtime.messages enable row level security;

create policy padlink_receive on realtime.messages
  for select to anon, authenticated
  using (realtime.topic() ~ '^padlink:[0-9A-HJKMNP-TV-Z]{8}$');

create policy padlink_send on realtime.messages
  for insert to anon, authenticated
  with check (realtime.topic() ~ '^padlink:[0-9A-HJKMNP-TV-Z]{8}$');
