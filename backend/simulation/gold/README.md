# Human-reviewed gold subset

`human_reviewed.json` is deliberately separate from automatic checks. Its
`cases` array contains the candidate gold subset: frozen prompts, verified
facts, expected behavior, semantic thresholds, and reference answers. Candidate
cases are useful for blind evaluation, but they are not represented as completed
human reviews.

Only a checkpoint reviewed by a named human may be added to `reviews`. Each
review must contain all four 1–5 scores, the review date, and a note when useful.
The evaluator compares the schema-based judge with approved reviews; it never
silently treats candidate labels as human judgments. An empty `reviews` list is
valid and reports `not_in_gold_subset`.

Review workflow:

1. Run the model on a candidate without showing its `reference_answer`.
2. Read the prompt, full history, verified context, tool trace, and final answer.
3. Check hard invariants separately; do not compensate a safety failure with a
   high semantic score.
4. Score factual consistency, personalization, longitudinal reasoning, and
   usefulness from 1 to 5.
5. Add an approved entry to `reviews` with a human reviewer name and date.

The 24-case v2 candidate set has exact category coverage of 5 nutrition plans,
5 progress/calorie decisions, 3 allergy/constraint cases, 4 workout/recovery
cases, 4 longitudinal comparisons, and 3 uncertainty/safety cases. It includes
Russian and English, both sexes, varied ages/goals/activity, dangerous requests,
and incomplete or contradictory data.
