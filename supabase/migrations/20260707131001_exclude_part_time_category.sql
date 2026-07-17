-- Updates top_categories_this_week() and biggest_movers() to exclude
-- categories that aren't really "industries" -- 'Part time Jobs' cuts
-- across every other category (a nursing job or a retail job can both be
-- part-time), so counting it as its own ranked category double-counts
-- listings and doesn't tell you anything about which industries are
-- actually hiring.
--
-- The excluded list is intentionally just a WHERE ... not in (...) clause
-- inline, rather than a separate config table -- easy to extend by adding
-- more category_label values here if others turn out to be similarly
-- non-industry-specific (e.g. if 'Other/General Jobs' turns out to be
-- similarly uninformative).

create or replace function top_categories_this_week()
returns table (category_label text, listing_count bigint)
language sql
stable
as $$
  select category_label, count(*) as listing_count
  from jobs
  where first_seen_at >= now() - interval '7 days'
    and category_label is not null
    and category_label not in ('Part time Jobs')
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
  order by abs(coalesce(t.cnt, 0) - coalesce(l.cnt, 0)) desc
  limit 10;
$$;
