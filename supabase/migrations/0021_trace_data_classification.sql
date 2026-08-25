-- Explicit classifications make privacy policy inspectable and enforceable.

alter table public.agent_runs
  add column input_data_classification text not null default 'sensitive'
    check (input_data_classification in ('public', 'internal', 'personal', 'sensitive', 'restricted')),
  add column output_data_classification text
    check (output_data_classification in ('public', 'internal', 'personal', 'sensitive', 'restricted'));

alter table public.agent_tool_calls
  add column arg_data_classification text not null default 'sensitive'
    check (arg_data_classification in ('public', 'internal', 'personal', 'sensitive', 'restricted')),
  add column result_data_classification text
    check (result_data_classification in ('public', 'internal', 'personal', 'sensitive', 'restricted'));

comment on column public.agent_runs.input_data_classification is
  'Classification applied before the conversation input reaches trace storage.';
comment on column public.agent_runs.output_data_classification is
  'Classification applied before the conversation output reaches trace storage.';
comment on column public.agent_tool_calls.arg_data_classification is
  'Classification applied before tool arguments reach trace storage.';
comment on column public.agent_tool_calls.result_data_classification is
  'Classification applied before tool results reach trace storage.';
