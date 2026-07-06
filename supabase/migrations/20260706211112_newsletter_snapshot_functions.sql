-- Two functions backing the Monday newsletter snapshot:
--   top_categories_this_week()  -- Top 10 categories by new-listing volume, trailing 7 days
--   biggest_movers()            -- Categories with the largest week-over-week change in volume
--
-- Both are exposed automatically by PostgREST as RPC endpoints:
--   POST /rest/v1/rpc/top_categories_this_week
--   POST /rest/v1/rpc/biggest_movers
--
-- "This week" is defined as a trailing 7-day window ending now

create or replace function top_categories_this_week()
returns table (category_label text, listing_count bigint)
language sql
stable
as $$
  select category_label, count(*) as listing_count
  from jobs
  where first_seen_at >= now() - interval '7 days'
    and category_label is not null
  group by category_label
  order by listing_count desc
  limit 10;
$$;

create or replace function biggest_movers()
returns table (
  category_label text,
  this_week bigint,
  last_week bigint,
  change bigint
)
language sql
stable
as $$
  with this_week_counts as (
    select category_label, count(*) as cnt
    from jobs
    where first_seen_at >= now() - interval '7 days'
      and category_label is not null
    group by category_label
  ),
  last_week_counts as (
    select category_label, count(*) as cnt
    from jobs
    where first_seen_at >= now() - interval '14 days'
      and first_seen_at < now() - interval '7 days'
      and category_label is not null
    group by category_label
  )
  select
    coalesce(t.category_label, l.category_label) as category_label,
    coalesce(t.cnt, 0) as this_week,
    coalesce(l.cnt, 0) as last_week,
    coalesce(t.cnt, 0) - coalesce(l.cnt, 0) as change
  from this_week_counts t
  full outer join last_week_counts l using (category_label)
  order by abs(coalesce(t.cnt, 0) - coalesce(l.cnt, 0)) desc
  limit 10;
$$;

-- Both functions need to be reachable by the same public/anon role the rest of the read-only API uses
grant execute on function top_categories_this_week() to anon, authenticated;
grant execute on function biggest_movers() to anon, authenticated;
