-- Updates the stale-job deletion window from 7 days to 21 days for business reasons
select cron.unschedule('delete-stale-jobs');

select cron.schedule(
  'delete-stale-jobs',
  '0 3 * * *',  -- daily at 3am UTC
  $$
  delete from jobs
  where last_seen_at < now() - interval '21 days'
  $$
);
