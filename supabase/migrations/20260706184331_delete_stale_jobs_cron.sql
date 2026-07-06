-- Schedules a daily pg_cron job that permanently deletes any job row not seen (last_seen_at) in 7 days regardless of status. This keeps jobs fresh for the users
select cron.schedule(
  'delete-stale-jobs',
  '0 3 * * *',  -- daily at 3am UTC
  $$
  delete from jobs
  where last_seen_at < now() - interval '7 days'
  $$
);
