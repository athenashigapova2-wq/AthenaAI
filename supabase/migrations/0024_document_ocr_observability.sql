-- Receipt/invoice extraction is a first-class, SLO-visible AI route.

alter table public.agent_runs
  drop constraint if exists agent_runs_route_check;

alter table public.agent_runs
  add constraint agent_runs_route_check
  check (route in ('nutrition', 'workout', 'recovery', 'general', 'document_ocr'));

comment on constraint agent_runs_route_check on public.agent_runs is
  'Allowlisted canonical AI execution routes, including receipt/invoice OCR.';
