# Defect List — Thrombectomy M1 — Iteration 005

## Loop stop condition

The requested loop limit was reached: 5 total blind-review iterations.

Final score: 72/100 — FAIL by strict 75 threshold.

Score trajectory:

- Iteration 001: 13/100
- Iteration 002: 52/100
- Iteration 003: 63/100
- Iteration 004: 69/100
- Iteration 005: 72/100

Total improvement: +59 points.

## Resolved or materially improved by iteration 005

1. Generic open-surgery scaffold removed from thrombectomy output.
2. Thrombectomy-specific anatomy/workflow/risk/postop scaffold added.
3. Imaging review and EVT eligibility framework added.
4. Landmark evidence families are named with honest citation verification caveats.
5. Actionable right M1 workflow, BP/antithrombotic framework, and morning-of-case page added.
6. Parsed known facts propagate better into summary/README/YAML.
7. “Right right M1” polish issue fixed.

## Remaining P0 defects preventing pass

1. Evidence retrieval/ranking still fails to retrieve and cite landmark EVT trials/guidelines.
2. Low-relevance sources still appear repeatedly in clinical files.
3. Eligibility thresholds need more operational guideline/trial-aligned detail.
4. Rescue algorithms for perforation, ICAD/re-occlusion, tandem lesion, distal embolus, sICH, and malignant edema need stepwise detail.

## Recommended next product slice

The bottleneck is now evidence retrieval and evidence hierarchy, not generic templating.

Implement a thrombectomy-specific evidence pack/retriever that:
- forces landmark EVT trials/guidelines for anterior circulation LVO/M1 cases;
- provides verified PMIDs/DOIs and applicability summaries;
- separates practice-changing evidence, guidelines, technique reviews, and edge-case/case reports;
- prevents M2-only, AI workflow, rare anomaly, and historical vignette sources from appearing as primary evidence for routine M1 EVT;
- moves low-relevance provenance to a true appendix instead of repeating it in clinical sections.
