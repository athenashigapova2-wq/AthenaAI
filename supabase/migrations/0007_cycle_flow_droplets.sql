-- ============================================================================
-- Меняем flow с текстового enum ('none'..'heavy') на число 0-4 — под UI
-- с 4 капельками, где количество закрашенных капелек = интенсивность.
-- ============================================================================

alter table public.cycle_logs drop column if exists flow;
alter table public.cycle_logs add column flow smallint not null default 0 check (flow between 0 and 4);
