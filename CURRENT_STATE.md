# Current state

| Surface | Current evidence |
|---|---:|
| Release | v0.2.0-rc1 preview |
| Workspace packages | 50 |
| Package admission | 50/50 passed; 0 failed |
| Blind AI silver semantic evaluation | 8/50 tasks |
| Scenario families | 25 |
| Task contexts | 14 code / 12 writing / 12 internal review / 12 external peer review |
| Full model matrix | not run |
| Static auxiliary responses | 544 (separate `static-response-v0.1`) |
| Post-bootstrap living cases admitted and scored | 1 |
| Public CI suite | 47/47 passing |
| Local extended regression suite | 254/254 passing |

All 50 packages pass environment, baseline, reference, scope, oracle-leakage, and known-wrong-solution admission checks. This does **not** mean all 50 have complete semantic model evaluation: the public scored calibration is 8/50. Those trajectories use a Codex read-only proposal plus allowed-path host executor. AI references are silver, and the ROI includes explicitly documented diagnostic imputations rather than observed human labor.

Git versions, track manifests, packet-set IDs, and run cards are authoritative. No redundant per-file SHA-256 inventory is maintained.
