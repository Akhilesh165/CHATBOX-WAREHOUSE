# MULTI-PLANT SCOPE & THRESHOLD LIST RULES

## 1. Multi-plant scope rule (applies to EVERY intent, not just ranking/comparison)
- If the question names more than one plant ("Plant 7228 and 1268", "plants 1258, 1266 and 7228",
  "Plant 1258 or Plant 7228", "both 7228 and 1268"), ALL named plants are in scope.
- Use WHERE b.Plant IN ('7228','1268'). NEVER keep only the first or last plant.
- Never drop a plant silently. If a named plant does not exist, say so explicitly and still
  answer for the others.
- A list/filter/count for several plants is COMBINED across them unless the user says
  "each", "per plant", "by plant", "separately", or "compare". For those, GROUP BY Plant.
- When more than one plant is in scope, the result table MUST include a Plant column.
- Year-like numbers (2024, 2025, 2026) are never plant IDs.

## 2. Threshold operator fidelity (must match the wording exactly)
- "above / over / more than / greater than / exceeding X%"  -> Utilization >  X
- "at least / X% or more / minimum X%"                      -> Utilization >= X
- "below / under / less than X%"                            -> Utilization <  X
- "at most / X% or below / X% or less"                      -> Utilization <= X
- "between X% and Y%"                                       -> X <= Utilization <= Y (inclusive)
- Do not convert "above" into ">=" or "below" into "<=".

## 3. "Show / list / find bins ..." completeness rule
- The result is at BIN level: Bin | Plant | Bin Capacity | Occupied Volume | Utilization %.
- The answer must state the TRUE total of matching bins (a separate COUNT), never the
  number of rows displayed. If rows are capped, say:
  "Showing the top N of TOTAL matching bins (sorted by utilization, highest first)."
  Never write "Found 50 bins" when 50 is only the display limit.
- When several plants are in scope, also give the per-plant breakdown of the total
  (e.g. "Plant 7228: A bins, Plant 1268: B bins").
- "How many ..." -> return the count only (plus per-plant split if multiple plants).
  "Show/list ..." -> return the bin rows AND the total count. Never only one of them.

## 4. Scope echo
- The first line of every answer must restate the scope that was actually applied:
  metric, operator + threshold, and ALL plants.
  Example: "Bins with utilization > 80% in Plants 7228 and 1268."
- If the SQL scope differs from what the user asked (a plant missing, a threshold changed),
  the answer is wrong. Re-generate; do not present it.

## 5. Over-capacity bins (utilization above 100%)
- Utilization = Occupied Volume / Bin Capacity * 100, where
  Occupied Volume = SUM(UnrestrictedQty * Material Volume) for that bin.
- A value above 100% means stock volume exceeds the bin's defined capacity (overfilled bin
  or a data-quality issue in bin/material volume). It is a valid computed value: do NOT cap it
  at 100% and do NOT drop it.
- For threshold lists such as "above 80%", include over-capacity bins, and flag them:
  "N of these bins are above 100% of capacity."

## 6. Worked examples
Q: Show bins above 80% utilization in Plant 7228 and 1268
-> Entity = Bin | Metric = Utilization % | Filter = Utilization > 80 | Scope = Plants 7228, 1268 (combined)
-> WHERE b.Plant IN ('7228','1268') AND utilization > 80
-> Columns: Bin | Plant | Bin Capacity | Occupied Volume | Utilization %
-> Answer states the true total and the per-plant split.

Q: How many bins are above 80% in Plant 7228 and 1268?
-> One COUNT over both plants, plus the per-plant counts.

Q: Show bins above 80% utilization in each of Plant 7228 and 1268
-> GROUP BY Plant (counts per plant) and list bins with the Plant column.

Q: Bins at least 90% full in Plant 1258 or 1266
-> Utilization >= 90, Plant IN ('1258','1266').

Q: Bins above 80% utilization in Plant 7228   (follow-up: "and 1268?")
-> Keep entity, metric and threshold; ADD 1268 -> Plants 7228 and 1268.
   A follow-up that names a plant with "and/also/what about" ADDS to or replaces scope
   as worded; it never silently ignores the new plant.
