# Frozen taxonomy

Frozen: 2026-07-01T09:00:00Z, before annotation began.

- route_omission: the exact benchmark gold route is required but no route is emitted.
- label_ambiguity: the exact benchmark scorer marks the prediction wrong, while a documented competing interpretation exists; these remain benchmark errors but are analyzed separately.
- entity_extraction: a required entity is missed and changes the selected route.
- unsupported_format: the documented frozen parser contract cannot consume the input format.
- other: residual exact-match routing errors not covered above.

Annotators label independently from the item context, exact gold route, prediction, and scoring result. Disagreements are adjudicated without changing definitions.
