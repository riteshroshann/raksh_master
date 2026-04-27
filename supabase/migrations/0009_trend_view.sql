-- trend query with age-contextual reference ranges
-- for a given member and parameter, returns all confirmed values
-- with the correct indian reference range for the patient's age
-- at the time of each test (not their current age).

create or replace view v_parameter_trend as
select
  rp.id as parameter_id,
  rp.member_id,
  rp.parameter_name,
  rp.value_numeric,
  rp.unit,
  rp.flag,
  rp.value_text,
  rp.fasting_status,
  rp.test_date,
  d.confirmed_at,

  -- age at the time of the test, not current age
  extract(year from age(rp.test_date, m.dob))::int as age_at_test,

  -- contextual reference range: uses the patient's age at each test date
  rr.range_low,
  rr.range_high,
  rr.critical_low,
  rr.critical_high,
  rr.source,
  rr.source_citation,
  rr.fasting_required,

  -- re-derive flag from contextual range (may differ from stored flag
  -- if ranges were updated since original confirmation)
  case
    when rp.value_numeric is null then null
    when rr.critical_low is not null and rp.value_numeric < rr.critical_low then 'critical_low'
    when rr.critical_high is not null and rp.value_numeric > rr.critical_high then 'critical_high'
    when rr.range_low is not null and rp.value_numeric < rr.range_low then 'below_range'
    when rr.range_high is not null and rp.value_numeric > rr.range_high then 'above_range'
    when rr.range_low is not null and rr.range_high is not null then 'normal'
    else null
  end as contextual_flag,

  -- fasting warning: true if this parameter requires fasting and
  -- fasting status was not confirmed as fasting
  case
    when rr.fasting_required = true
      and (rp.fasting_status is null or rp.fasting_status != 'fasting')
    then true
    else false
  end as fasting_warning

from report_parameters rp
join documents d on rp.document_id = d.id
join family_members m on rp.member_id = m.id
left join lateral (
  select
    r.range_low,
    r.range_high,
    r.critical_low,
    r.critical_high,
    r.source,
    r.source_citation,
    r.fasting_required
  from reference_ranges r
  where lower(r.parameter_name) = lower(rp.parameter_name)
    and (r.sex = m.sex or r.sex = 'any')
    and (
      r.age_min is null
      or extract(year from age(rp.test_date, m.dob))::int >= r.age_min
    )
    and (
      r.age_max is null
      or extract(year from age(rp.test_date, m.dob))::int <= r.age_max
    )
    and r.effective_from <= rp.test_date
    and (r.effective_to is null or r.effective_to > rp.test_date)
  order by
    -- prefer indian ranges (source = 'indian')
    case when r.source = 'indian' then 0 else 1 end,
    -- prefer more specific age ranges
    (coalesce(r.age_max, 999) - coalesce(r.age_min, 0)) asc,
    -- prefer more specific sex match
    case when r.sex = m.sex then 0 else 1 end,
    r.version desc
  limit 1
) rr on true
where d.confirmed_at is not null
order by rp.member_id, rp.parameter_name, rp.test_date;

comment on view v_parameter_trend is
  'Trend view: returns all confirmed parameter values for a member with '
  'age-contextual Indian reference ranges and re-derived flags. '
  'Each data point uses the reference range correct for the patient''s age '
  'at the time of that specific test, not their current age.';
