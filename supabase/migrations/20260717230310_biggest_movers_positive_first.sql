-- Reorders biggest_movers() so the biggest gains appear first, instead of
-- the biggest swing in either direction. Previously the function ordered
-- by abs(change) desc, which meant a category with a huge drop (e.g. -349)
-- would rank above a category with a smaller gain (e.g. +85) -- both are
-- "big movers" in magnitude, but the newsletter reads better with growth
-- at the top rather than decline.

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
      and category_label not in ('Part time Jobs')
    group by category_label
  ),
  last_week_counts as (
    select category_label, count(*) as cnt
    from jobs
    where first_seen_at >= now() - interval '14 days'
      and first_seen_at < now() - interval '7 days'
      and category_label is not null
      and category_label not in ('Part time Jobs')
    group by category_label
  )
  select
    coalesce(t.category_label, l.category_label) as category_label,
    coalesce(t.cnt, 0) as this_week,
    coalesce(l.cnt, 0) as last_week,
    coalesce(t.cnt, 0) - coalesce(l.cnt, 0) as change
  from this_week_counts t
  full outer join last_week_counts l using (category_label)
  order by coalesce(t.cnt, 0) - coalesce(l.cnt, 0) desc
  limit 10;
$$;
