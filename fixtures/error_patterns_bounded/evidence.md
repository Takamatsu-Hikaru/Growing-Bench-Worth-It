# Evidence record

- Frozen system: RouteModel 2.3.1, artifact RM-2.3.1, route configuration v7, deterministic greedy routing at temperature zero.
- Scoring: exact route match on the fixed ErrorBench-English v1.0 English test split; 506/600 correct and 94 errors.
- `data/taxonomy.md` is the taxonomy frozen at 2026-07-01T09:00:00Z before labeling.
- `data/annotations.csv` contains all 94 item IDs, item context, exact gold route, prediction, scoring result, independent labels, adjudicated label, and rationale.
- `data/analysis.json` contains category counts, agreement, Cohen's kappa, and disagreements.
- No multilingual, cross-domain, cross-system, or alternate-scoring analysis was conducted or claimed.
- `data/ambiguity_notes.csv` supplies all 29 pre-annotation benchmark notes referenced by label-ambiguity records.
- The analysis is a census of the 94 errors in the fixed test set; it makes no customer-, template-, or future-population sampling claim.
