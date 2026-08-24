-- Explicit dietary constraints consumed by the deterministic nutrition engine.

alter table public.user_profiles
  add column dietary_pattern text not null default 'omnivore'
    check (dietary_pattern in ('omnivore', 'vegetarian', 'vegan', 'pescatarian')),
  add column dietary_restrictions text[] not null default '{}'
    check (
      dietary_restrictions <@ array[
        'halal', 'kosher', 'lactose_free', 'gluten_free'
      ]::text[]
      and array_position(dietary_restrictions, null) is null
      and cardinality(dietary_restrictions) <= 4
    );

comment on column public.user_profiles.dietary_pattern is
  'Server-validated dietary pattern used by nutrition constraints.';
comment on column public.user_profiles.dietary_restrictions is
  'Canonical hard restrictions enforced independently of the LLM.';
