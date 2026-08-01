-- ============================================================================
-- Проактивный анализ привычек — расширяем agent_memory структурированными
-- полями. Раньше эта таблица только объявлялась, но реально не наполнялась;
-- теперь Edge Function 'analyze-habits' будет писать сюда результат анализа
-- последних meal_logs, а Home.jsx — читать и показывать карточку с советом
-- без запроса от пользователя.
-- ============================================================================

alter table public.agent_memory
  add column if not exists frequent_foods text[] default '{}',
  add column if not exists macro_gap text, -- какого макронутриента чаще всего не хватает/избыток
  add column if not exists suggestion text, -- готовый текст подсказки для карточки на главной
  add column if not exists suggestion_generated_at timestamptz;
