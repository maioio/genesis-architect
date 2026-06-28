# The Genesis Thinking Loop

Every meaningful task runs through the same 15-step loop. It is the operating
system of the partnership.

```
Understand → Ask → Research → Verify → Compare → Consult Committee →
Decide → Plan → Request Approval → Implement → Test → Validate →
Document → Learn → Remember
```

| Step | What happens | Engine |
|------|--------------|--------|
| Understand | Classify the request + technical domain | Intent classifier |
| Ask | Only the missing questions needed to align | Governance |
| Research | Plan + run research by source priority | [Research Intelligence](10_research_intelligence.md) |
| Verify | Cross-check claims against stronger sources | [Field Intelligence](11_field_intelligence.md) |
| Compare | Lay out alternatives + trade-offs | [Decision Engine](22_decision_engine.md) |
| Consult Committee | Multiple perspectives on close calls | Decision Engine |
| Decide | Recommend one, with confidence + "what would change it" | Decision Engine |
| Plan | Order the work into safe phases | Governance / planner |
| Request Approval | Gate consequential + dangerous actions | [Governance](26_governance.md) |
| Implement | Run the registered engines for the phase | [Engine adapters](22_decision_engine.md) |
| Test | Add + run tests for the change | Validation |
| Validate | Architecture gate, regressions | [`genesis gate`](27_rules_engine.md) |
| Document | Record what was done + why | [Memory](24_memory_learning.md) |
| Learn | Record which strategy worked | [Learning](24_memory_learning.md) |
| Remember | Persist for the next session | Cross-session Memory |

The loop maps onto the runtime lifecycle stages the Decision Engine executes
(`INTAKE → PLAN → EXECUTE → GATE → REPORT → APPROVE → COMMIT`), with gates at the
consequential transitions.
