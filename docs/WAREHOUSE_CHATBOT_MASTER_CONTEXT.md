# WAREHOUSE CHATBOT — MASTER CONTEXT
## Bin Utilization + Comparison + Ranking + Context Handling + Validation

### 1. PRIMARY OBJECTIVE

The warehouse chatbot must understand the user's **meaning and intent**, not depend on exact question-answer pairs.

The chatbot must be able to understand different ways of asking the same thing.

For example:

- "What is the bin utilization?"
- "How much of the warehouse capacity is currently being used?"
- "Show warehouse utilization."
- "How full are the bins?"
- "What percentage of bin capacity is occupied?"
- "Give me the overall utilization."
- "Show me bin utilization for Plant 1258."

These questions may use different wording but can represent the same underlying intent.

The chatbot must therefore perform:

**USER QUESTION → INTENT → ENTITY → METRIC → FILTER → CALCULATION → VALIDATION → OUTPUT FORMAT**

Do not implement the chatbot as a collection of exact question-answer mappings.

---

# 2. BIN UTILIZATION — COMPLETE CONTEXT

## 2.1 What is Bin Utilization?

Bin utilization represents how much of a bin's available storage capacity is currently occupied.

### Formula

```text
Bin Utilization % =
(Occupied Volume / Total Bin Capacity) × 100
```

Example:

```text
Total Capacity = 100 FT³
Occupied Volume = 75 FT³

Utilization = (75 / 100) × 100
            = 75%
```

The chatbot must always use the project's actual capacity and occupied-volume fields.

Do not invent values.

---

# 3. BIN UTILIZATION RELATED METRICS

The chatbot must understand these concepts separately.

### Total Capacity

Maximum storage capacity of the bin.

### Occupied Volume

Volume currently occupied by inventory.

### Available Capacity

```text
Available Capacity =
Total Capacity - Occupied Volume
```

### Utilization %

```text
Utilization % =
(Occupied Volume / Total Capacity) × 100
```

### Empty Bin

Normally:

```text
Occupied Volume = 0
```

unless the project defines empty bins differently.

### Fully Utilized Bin

Normally:

```text
Utilization = 100%
```

### Overutilized Bin

If the data produces:

```text
Utilization > 100%
```

the chatbot must not silently treat this as normal.

It should flag the record as potentially invalid/over-capacity data.

---

# 4. TYPES OF BIN UTILIZATION QUESTIONS

The chatbot must recognize all of the following semantic categories.

## 4.1 Overall Utilization

Examples:

- What is the overall warehouse bin utilization?
- What percentage of warehouse capacity is being used?
- How full is the warehouse?
- Give me current warehouse utilization.
- What is the overall utilization right now?

For overall utilization:

```text
SUM(Occupied Volume) / SUM(Total Capacity) × 100
```

Do NOT calculate overall utilization by simply averaging individual bin percentages unless the project explicitly defines that behavior.

---

# 5. BIN-LEVEL UTILIZATION

Examples:

- Show utilization of bin NRJP2124D2.
- How full is NRJP2124D2?
- What is the utilization percentage of this bin?
- Show capacity and utilization for NRJP2124D2.
- Is this bin highly utilized?

The chatbot must return information for the requested bin only.

Possible output:

| Bin | Total Capacity | Occupied Volume | Available Capacity | Utilization |
|---|---:|---:|---:|---:|
| NRJP2124D2 | ... | ... | ... | ...% |

Do not replace a requested bin-level result with plant-level statistics.

---

# 6. PLANT-WISE BIN UTILIZATION

Examples:

- Show bin utilization for Plant 1258.
- What is the utilization of Plant 7228?
- How full are the bins in Plant 1258?
- Give me warehouse utilization for this plant.
- Compare utilization within Plant 1258.

The chatbot must:

1. Identify the requested plant.
2. Retrieve only records belonging to that plant.
3. Calculate the requested metric.
4. Return the result at the level requested by the user.

If asking for plant-level utilization:

```text
Plant Utilization =
SUM(Occupied Volume for Plant) /
SUM(Total Capacity for Plant) × 100
```

---

# 7. BIN UTILIZATION RANGES

The chatbot must understand natural-language ranges.

Examples:

### "Between 50% and 80%"

```text
50% <= Utilization <= 80%
```

### "Above 80%"

```text
Utilization > 80%
```

### "At least 80%"

```text
Utilization >= 80%
```

### "Below 20%"

```text
Utilization < 20%
```

### "20% or below"

```text
Utilization <= 20%
```

### "Around 70%"

This is ambiguous unless the project defines a tolerance.

Do not invent a tolerance silently.

If necessary, ask:

> What range should I consider "around 70%"?

---

# 8. RANGE FILTER VALIDATION — VERY IMPORTANT

If the user asks:

> Show only bins between 50% and 80% utilization.

Every returned bin MUST satisfy:

```text
50% <= displayed utilization <= 80%
```

The chatbot must calculate the same utilization metric that it displays.

Never:

- filter using one utilization calculation,
- display another utilization calculation,
- return rows outside the requested range.

Before responding, perform:

```text
CALCULATE → FILTER → VALIDATE → DISPLAY
```

Every displayed row must pass the requested condition.

---

# 9. HIGH / LOW UTILIZATION

The chatbot must understand:

- highly utilized bins
- heavily utilized bins
- almost full bins
- overutilized bins
- low utilization bins
- underutilized bins
- lightly utilized bins
- nearly empty bins
- inefficiently utilized bins

If a threshold is already defined by project configuration, use it.

If no threshold exists, do NOT randomly invent one.

For example, do not assume:

```text
High = >80%
Low = <20%
```

unless the project configuration explicitly defines those thresholds.

---

# 10. EMPTY BIN QUESTIONS

Examples:

- Show me empty bins.
- Which bins are empty?
- Find bins with no inventory.
- How many bins are currently empty?
- List all completely empty bins.
- Show empty bins in Plant 1258.
- Are there any empty bins available for put-away?

Interpret empty according to the project's data definition.

Normally:

```text
Occupied Volume = 0
```

For empty bins:

```text
Available Capacity = Total Capacity
```

assuming the project definition supports this.

---

# 11. AVAILABLE CAPACITY QUESTIONS

Examples:

- How much space is still available?
- Show available capacity.
- Which bins have the most free space?
- Find bins with more than 500 FT³ available.
- How much capacity is left in Plant 1258?
- How much capacity is still available in the top 10 utilized bins?

Use:

```text
Available Capacity =
Total Capacity - Occupied Volume
```

Do not confuse available capacity with utilization.

---

# 12. OCCUPIED VOLUME QUESTIONS

Examples:

- Which bins have the highest occupied volume?
- Show occupied volume by plant.
- How much warehouse volume is occupied?
- Rank bins by occupied volume.
- Which plant occupies the most warehouse space?

Occupied volume and utilization are different metrics.

Do not substitute one for the other.

---

# 13. CAPACITY + UTILIZATION COMPOUND QUESTIONS

The chatbot must support multiple conditions in one question.

Example:

> Find bins with low capacity but high utilization.

Interpret as:

```text
Entity = Bin

Condition 1 = Low Capacity
Condition 2 = High Utilization

Final Filter =
Condition 1 AND Condition 2
```

If project thresholds are:

```text
Low Capacity < 500 FT³
High Utilization > 80%
```

then:

```text
Total Capacity < 500
AND
Utilization > 80%
```

Every returned bin must satisfy BOTH conditions.

If thresholds are not configured, ask the user or use explicitly configured project thresholds.

Never invent thresholds silently.

---

# 14. ENTITY PRESERVATION RULE

If the user asks:

> Find bins with low capacity but high utilization.

The final answer MUST contain bins.

Do not answer only with:

- plant summaries
- warehouse summaries
- averages
- unrelated material information

The requested entity must be preserved throughout the processing pipeline.

---

# 15. BIN UTILIZATION RANKING

The chatbot must support:

- top utilized bins
- least utilized bins
- highest utilization
- lowest utilization
- top 5
- top 10
- bottom 10
- rank all bins
- rank bins by occupied volume
- rank bins by available capacity
- rank bins by total capacity

Examples:

> Show the top 10 most utilized bins.

Interpret:

```text
Entity = Bin
Metric = Utilization %
Direction = Descending
Limit = 10
```

Example output:

| Rank | Bin | Utilization |
|---:|---|---:|
| 1 | ... | ...% |
| 2 | ... | ...% |
| 3 | ... | ...% |

---

# 16. LEAST UTILIZED BINS

Example:

> Show the least utilized bins.

Interpret:

```text
Entity = Bin
Metric = Utilization %
Direction = Ascending
```

If no number is specified, follow project default behavior.

Do not randomly choose a limit such as 10 if the user asked for all matching bins.

---

# 17. RANKING FOLLOW-UP CONTEXT

The chatbot must maintain previous ranking context.

Example:

User:

> Show the top 10 most utilized bins.

Assistant returns top 10.

User:

> What about the least utilized ones?

Interpret:

```text
Entity = Bin
Metric = Utilization
Direction = Ascending
```

User:

> Only for Plant 1258.

Interpret:

```text
Entity = Bin
Metric = Utilization
Direction = Ascending
Plant = 1258
```

User:

> Show the top 5 instead.

Only change:

```text
Limit = 5
```

Do NOT reset:

- entity
- metric
- plant
- ranking context

---

# 18. REFERENTIAL CONTEXT

Words such as:

- them
- these
- those
- ones
- these bins
- those bins
- same bins
- these plants
- those plants
- remaining ones
- the above bins

must refer to the most relevant previous result.

Example:

> Show the top 10 utilized bins.

Then:

> How much capacity is still available in them?

"them" = the same top 10 bins.

The chatbot must not perform a completely new unrelated search.

---

# 19. COMPARISON SYSTEM

The chatbot must support semantic comparisons between:

- Plant vs Plant
- Bin vs Bin
- Material vs Material
- Plant vs Plant for utilization
- Plant vs Plant for capacity
- Plant vs Plant for inventory
- Bin vs Bin for utilization
- Bin vs Bin for capacity
- Material vs Material for inventory quantity
- Multiple plants
- Multiple bins
- Multiple materials

Example:

> Compare Plant 1258 and Plant 7228 based on bin utilization.

Interpret:

```text
Entities = Plant 1258, Plant 7228
Metric = Bin Utilization
Comparison = Plant vs Plant
```

---

# 20. PLANT COMPARISON

The chatbot should understand:

- Compare Plant 1258 and Plant 7228.
- Which plant has higher utilization?
- Which plant is more efficiently utilized?
- Compare their capacities.
- Compare their occupied volume.
- Compare their available capacity.
- Compare number of bins.
- Compare inventory.
- Show differences between Plant 1258 and Plant 7228.
- Which plant is better utilized?
- How much higher is Plant 1258 than Plant 7228?

Where relevant, provide:

| Metric | Plant 1258 | Plant 7228 | Difference |
|---|---:|---:|---:|
| Total Capacity | ... | ... | ... |
| Occupied Volume | ... | ... | ... |
| Available Capacity | ... | ... | ... |
| Utilization % | ... | ... | ... |

Only include metrics relevant to the question.

---

# 21. COMPARISON CALCULATIONS

### Absolute Difference

```text
Difference = Value A - Value B
```

### Percentage Difference

Use only when meaningful and clearly defined.

For directional comparison:

```text
Percentage Difference =
((A - B) / B) × 100
```

The chatbot must clearly state what the percentage is relative to.

Do not confuse:

- percentage difference
- percentage-point difference
- utilization percentage

Example:

Plant A = 80% utilization  
Plant B = 70%

The difference is:

```text
10 percentage points
```

not simply "10% higher" unless the relative increase is specifically calculated.

---

# 22. MULTI-PLANT COMPARISON

The chatbot should support:

> Compare Plant 1258, 7228 and 3000.

It should generate a comparison table.

If the user asks:

> Which plant has the highest utilization?

Return the winner rather than unnecessary full data.

If the user asks:

> Rank these plants by utilization.

Use the ranking system.

---

# 23. COMPARISON + FILTER

Example:

> Compare the top 5 most utilized bins in Plant 1258 and Plant 7228.

The chatbot must understand:

```text
Plants = 1258, 7228
Entity = Bin
Metric = Utilization
Ranking = Top 5
Grouping = Plant
```

Do not merge the two plants incorrectly.

---

# 24. RANKING SYSTEM — COMPLETE CONTEXT

Ranking questions may use words such as:

- top
- highest
- lowest
- bottom
- best
- worst
- maximum
- minimum
- most
- least
- rank
- ranking
- sorted
- order
- highest to lowest
- lowest to highest
- most utilized
- least utilized

The chatbot must infer ranking intent semantically.

---

# 25. RANKING ENTITIES

Ranking may be applied to:

- bins
- plants
- materials
- inventory items
- storage locations
- material groups
- warehouses
- other valid project entities

---

# 26. RANKING METRICS

Possible ranking metrics include:

- Utilization %
- Total Capacity
- Occupied Volume
- Available Capacity
- Inventory Quantity
- Number of Bins
- Number of Materials
- Average Inventory
- Other valid project metrics

Never rank using a different metric from the one requested.

Example:

> Rank bins by utilization.

Must rank by:

```text
Utilization %
```

not occupied volume.

---

# 27. TOP VS BOTTOM

### Top / Highest / Most

Sort descending.

```text
ORDER BY metric DESC
```

### Bottom / Lowest / Least

Sort ascending.

```text
ORDER BY metric ASC
```

---

# 28. RANKING WITH FILTERS

Filters must be applied BEFORE ranking.

Example:

> Show the top 10 most utilized bins in Plant 1258.

Correct:

```text
Filter Plant = 1258
        ↓
Calculate utilization
        ↓
Sort descending
        ↓
Take top 10
```

Do NOT:

```text
Take global top 10
        ↓
Filter Plant 1258
```

because that can produce incorrect results.

---

# 29. RANKING WITH MULTIPLE CONDITIONS

Example:

> Show the top 5 most utilized bins in Plant 1258 with capacity below 500 FT³.

Correct pipeline:

```text
Plant = 1258
AND
Capacity < 500
        ↓
Calculate utilization
        ↓
Sort utilization descending
        ↓
Top 5
```

---

# 30. RANKING TIES

If two records have equal ranking values, the chatbot must handle ties consistently.

Preferred competition ranking:

```text
1
2
2
4
```

Do not randomly break ties unless a secondary sorting rule is defined.

---

# 31. "WHICH ONE" QUESTIONS

If the user asks:

> Which plant has the highest utilization?

Return the highest plant.

Do not automatically return a full ranking unless useful.

Similarly:

> Which bin has the lowest utilization?

Return the lowest matching bin.

---

# 32. "HOW MANY" QUESTIONS

If the user asks:

> How many bins have utilization above 80%?

Return the count.

Do not dump the entire list unless the user asks for it.

Example:

> 37 bins have utilization above 80%.

---

# 33. LIST QUESTIONS

If user says:

> List bins with utilization above 80%.

Return a list/table of matching bins.

Do not return only the count.

---

# 34. SINGLE-LINE RESPONSE MODE

The chatbot should infer when a question requires a short single-line answer.

Examples:

> How many empty bins are there?

Response:

> There are 42 completely empty bins.

Example:

> Which plant has the highest utilization?

Response:

> Plant 1258 has the highest bin utilization at 87.4%.

Do not provide unnecessary tables for simple questions.

---

# 35. DETAIL MODE

If the user says:

- show me in detail
- explain
- explain in detail
- give details
- detailed
- elaborate
- deep dive
- break it down
- full details
- detailed analysis
- detailed report
- tell me everything about it
- give me the full picture
- go deeper
- explain what is happening

switch automatically to DETAIL MODE.

Detail mode should provide relevant additional information.

Example:

```text
Summary
↓
Calculation / Metrics
↓
Relevant Table
↓
Key Findings
↓
Chart if useful/requested
```

Do not provide irrelevant database rows just because the user requested detail.

---

# 36. CHART RULE

Charts are NOT mandatory for every question.

Generate/display a chart when:

- user explicitly asks for a graph/chart
- comparison is easier to understand visually
- detailed analysis would benefit from visualization
- ranking/trend analysis clearly benefits from it

Do not add charts unnecessarily to simple questions.

---

# 37. INVALID PLANT / BIN / ENTITY HANDLING

This is a HIGH-PRIORITY RULE.

If the user specifies a plant, bin, material, or other entity that does not exist in the available warehouse database, the chatbot must NOT:

- invent a result
- use another plant
- silently remove the filter
- return random records
- return Plant 1258 by default
- return 1000 rows
- substitute a similar-looking bin
- give a warehouse-wide answer

Instead return:

> **No matching warehouse records were found for your query in the database.**

Preferred exact standard response:

```text
No matching warehouse records were found for your query in the database.
```

---

# 38. INVALID PLANT EXAMPLE

User:

> Show bin utilization for Plant 99999.

If Plant 99999 does not exist:

```text
No matching warehouse records were found for your query in the database.
```

Do not return another plant.

---

# 39. INVALID BIN EXAMPLE

User:

> Show utilization for bin ABC999999.

If the bin does not exist:

```text
No matching warehouse records were found for your query in the database.
```

Do not return another bin.

---

# 40. INVALID PLANT + BIN

User:

> Show bin ABC999 in Plant 99999.

If no matching record exists:

```text
No matching warehouse records were found for your query in the database.
```

Both filters must be respected.

---

# 41. INVALID ENTITY MUST NOT BE SILENTLY IGNORED

Incorrect behavior:

User:

> Show utilization for Plant 99999.

Chatbot:

> Plant 1258 utilization is 72%.

This is WRONG.

Correct:

> No matching warehouse records were found for your query in the database.

---

# 42. EMPTY RESULT VS VALID ZERO RESULT

The chatbot must distinguish:

### No database records

```text
No matching warehouse records were found for your query in the database.
```

### Valid record with zero value

For example:

```text
Plant 1258 has 0 empty bins.
```

Do not confuse zero with no matching records.

---

# 43. DATA VALIDATION

Before returning utilization results, validate:

### Capacity

- Missing capacity
- Zero capacity
- Negative capacity

### Occupied Volume

- Missing occupied volume
- Negative occupied volume

### Utilization

- Missing utilization inputs
- Utilization >100%
- Unexpected negative utilization

### Data consistency

Check:

```text
Occupied Volume <= Total Capacity
```

where appropriate according to the business rules.

If data violates the expected rule, do not silently hide the problem.

---

# 44. ZERO CAPACITY

If:

```text
Total Capacity = 0
```

the chatbot must NOT calculate:

```text
Occupied / 0
```

as a normal utilization percentage.

Handle it as invalid/undefined utilization according to project rules.

---

# 45. UNIT HANDLING

The chatbot must preserve units.

Examples:

- FT³
- m³
- liters
- quantity
- percentage

Do not mix units.

If conversion is required, perform it explicitly and clearly.

Never compare:

```text
500 FT³
```

against:

```text
500 m³
```

as if they were equal.

---

# 46. "ALL" MEANS ALL

If the user asks:

> Show all empty bins.

Do not silently return only:

- first 100 rows
- first 1000 rows
- current page
- top N

unless the UI explicitly indicates pagination and the chatbot clearly states that limitation.

If all matching records cannot be displayed at once, say so clearly and provide the available mechanism for accessing the complete result.

---

# 47. NO ARBITRARY LIMITS

The chatbot must NEVER automatically apply:

```text
LIMIT 1000
```

or another arbitrary limit unless that limit is part of the actual user request or a clearly defined application/UI behavior.

Example:

> Total warehouse inventory

must NOT automatically become:

> Plant 1258 + 1000 rows

unless the user actually requested Plant 1258 and 1000 records.

---

# 48. QUERY INTENT MUST CONTROL OUTPUT

Examples:

### User asks for count

Return count.

### User asks for list

Return list/table.

### User asks for ranking

Return ranking.

### User asks for comparison

Return comparison.

### User asks for one value

Return concise metric.

### User asks for details

Return detailed structured response.

### User asks for graph

Return relevant graph + summary.

The chatbot should infer the output format automatically.

---

# 49. COMBINED QUERY SUPPORT

The chatbot must support multiple requirements in one question.

Example:

> Show the top 10 most utilized bins in Plant 1258 with capacity below 500 FT³.

Interpret:

```text
Entity = Bin
Plant = 1258
Capacity < 500 FT³
Metric = Utilization %
Direction = Descending
Limit = 10
```

Another example:

> Compare the top 5 utilized bins of Plant 1258 and Plant 7228.

Interpret:

```text
Entities = Bins
Plants = 1258, 7228
Metric = Utilization %
Ranking = Top 5
Comparison = Plant-wise
```

---

# 50. CONVERSATIONAL FOLLOW-UP EXAMPLES

### Flow 1 — Ranking

User:

> Show top 10 most utilized bins.

Assistant:

> Returns top 10.

User:

> What about the least utilized ones?

System keeps:

```text
Entity = Bin
Metric = Utilization
```

and changes:

```text
Direction = Ascending
```

User:

> Only Plant 1258.

Adds:

```text
Plant = 1258
```

User:

> Show top 5 instead.

Changes only:

```text
Limit = 5
```

---

### Flow 2 — Empty bins

User:

> Show me empty bins.

Assistant:

> Returns empty bins.

User:

> Only in Plant 1258.

Adds Plant filter.

User:

> How many are there?

Uses the previous filtered result and returns the count.

---

### Flow 3 — Capacity

User:

> Show the top 10 most utilized bins.

User:

> How much capacity is still available in them?

"them" refers to those same 10 bins.

Do not search for a new group of bins.

---

### Flow 4 — Comparison

User:

> Compare Plant 1258 and Plant 7228.

User:

> Which one has higher utilization?

"Which one" refers to those two plants.

---

# 51. MATERIAL / INVENTORY CONNECTION

Bin utilization questions may be combined with inventory/material questions.

Examples:

- Which materials are stored in highly utilized bins?
- Show materials in bins above 80% utilization.
- Which bins contain the most inventory?
- Compare inventory in highly utilized vs low-utilized bins.
- Show material information for the top 10 utilized bins.

The chatbot must preserve the primary requested entity.

If the user asks for bins, return bins.

If the user asks for materials, return materials.

---

# 52. INVENTORY MASTER + VOLUME MASTER

The chatbot must understand questions such as:

- Which inventory materials are missing from the Volume Master?
- Find materials in inventory but missing from the volume master.
- Are there materials without physical dimensions?
- How many inventory items do not have corresponding Volume Master entries?
- Show missing volume information.
- Which materials do not have dimensions?

Possible output depends on the request:

### Count

Return count.

### List

Return material list.

### Detailed

Return relevant material fields and missing information.

Do not invent missing dimensions.

---

# 53. SEMANTIC SYNONYM HANDLING

The chatbot should understand equivalent terms.

### Utilization

- utilization
- used capacity
- usage
- occupancy percentage
- capacity usage
- fullness
- how full
- space utilization
- storage utilization

### Capacity

- total capacity
- maximum capacity
- storage capacity
- bin capacity
- holding capacity

### Available

- free capacity
- remaining capacity
- unused capacity
- available space
- free space
- space left

### Occupied

- occupied volume
- used volume
- consumed capacity
- stored volume
- filled volume

### Ranking

- top
- highest
- most
- maximum
- best
- bottom
- lowest
- least
- minimum
- worst
- rank
- sorted

### Comparison

- compare
- difference
- versus
- vs
- better
- higher
- lower
- more
- less
- which is greater
- which performs better

---

# 54. RESPONSE CORRECTNESS RULE

A response is considered correct only if ALL of the following are correct:

1. User intent
2. Entity
3. Metric
4. Filters
5. Calculation
6. Aggregation
7. Ranking direction
8. Ranking limit
9. Comparison logic
10. Conversation context
11. Data validation
12. Response format

Correct data with incorrect intent is still an incorrect answer.

---

# 55. FINAL VALIDATION BEFORE RESPONSE

Before returning any warehouse answer, internally validate:

```text
1. What exactly did the user ask?
2. What entity did they ask about?
3. What metric did they ask for?
4. Did they specify a plant?
5. Did they specify a bin?
6. Did they specify materials?
7. Did they specify a range?
8. Did they specify thresholds?
9. Did they ask for ranking?
10. Did they ask for comparison?
11. Did they ask for count/list/table/detail?
12. Is this a follow-up to a previous question?
13. Are all requested records actually present?
14. Did every returned record satisfy the filters?
15. Did I accidentally introduce another plant/bin?
16. Did I accidentally apply an arbitrary limit?
17. Is the displayed metric the same metric used for filtering?
18. Are calculations valid?
19. Is the response format appropriate?
20. Is any information missing?
```

Only after these checks should the chatbot generate the response.

---

# 56. MASTER PROCESSING PIPELINE

For every warehouse question:

```text
USER QUESTION
      ↓
Detect Intent
      ↓
Identify Entity
      ↓
Identify Metric
      ↓
Identify Plant / Bin / Material
      ↓
Identify Filters
      ↓
Identify Range / Threshold
      ↓
Identify Ranking
      ↓
Identify Comparison
      ↓
Identify Requested Limit
      ↓
Resolve Previous Conversation Context
      ↓
Validate Entity Existence
      ↓
Retrieve Required Records
      ↓
Calculate Required Metrics
      ↓
Apply Filters
      ↓
Validate Filtered Results
      ↓
Aggregate / Group if Required
      ↓
Rank if Required
      ↓
Compare if Required
      ↓
Validate Final Result
      ↓
Select Response Format
      ↓
Generate Answer
```

---

# 57. NO-MATCH SAFETY RULE

If the requested plant/bin/material/entity does not exist or no database record satisfies the complete query, return:

> **No matching warehouse records were found for your query in the database.**

Do not fabricate data.

Do not silently change the user's filters.

Do not substitute another plant.

Do not substitute another bin.

Do not return unrelated records.

Do not return a generic warehouse summary.

---

# 58. IMPORTANT EXAMPLES OF WRONG BEHAVIOR

### Wrong

User:

> Show utilization for Plant 99999.

Chatbot:

> Plant 1258 utilization is 72%.

Reason: requested plant was ignored.

---

### Wrong

User:

> Show bins between 50% and 80% utilization.

Chatbot returns:

```text
671.1%
364.5%
353.8%
```

Reason: returned values violate the requested filter.

---

### Wrong

User:

> Find bins with low capacity and high utilization.

Chatbot returns only:

> Plant 1258 has high utilization.

Reason: user requested BIN-level results.

---

### Wrong

User:

> Total warehouse inventory.

Chatbot automatically returns:

> Plant 1258 — 1000 rows.

Reason: Plant and arbitrary limit were invented.

---

# 59. IMPORTANT PRINCIPLE

The chatbot must never answer:

> "What can I retrieve?"

It must answer:

> **"What exactly did the user ask, and what data/result satisfies that request?"**

The database retrieval layer, calculation layer, context layer and response layer must all follow the user's intent.

---

# 60. FINAL GOLDEN RULES

### Rule 1
Understand meaning, not exact wording.

### Rule 2
Never invent a plant, bin, material, threshold or value.

### Rule 3
Never silently remove a user-specified filter.

### Rule 4
Never substitute one entity for another.

### Rule 5
The requested entity must remain the final output entity.

### Rule 6
The metric used for filtering must be the same metric displayed.

### Rule 7
Apply filters before ranking.

### Rule 8
Preserve previous context in follow-up questions.

### Rule 9
Do not add arbitrary limits.

### Rule 10
Do not dump unrelated database fields.

### Rule 11
Use the requested response format automatically.

### Rule 12
Explicit "detail" requests activate DETAIL MODE.

### Rule 13
Charts are optional unless requested or clearly useful.

### Rule 14
Validate calculations before displaying results.

### Rule 15
For invalid/nonexistent plant, bin or entity, return:

**"No matching warehouse records were found for your query in the database."**

### Rule 16
If data is genuinely unavailable, say that it is unavailable rather than inventing an answer.

### Rule 17
For range queries, every returned row must satisfy the range.

### Rule 18
For compound conditions, every returned row must satisfy ALL conditions.

### Rule 19
"How many" means count, not full list.

### Rule 20
"Which one" means identify the relevant winner/loser, not automatically dump a full ranking.

---

# 61. SUCCESS CRITERIA

The warehouse chatbot should be considered successfully context-based when a user can ask the same business question in many different ways and receive the same logically correct result.

For example:

> Show me the top 10 most utilized bins.

and:

> Which ten bins are using the highest percentage of their storage capacity?

and:

> Give me the 10 fullest bins.

and:

> What are the bins with the highest utilization?

should all resolve to the same underlying intent:

```text
Entity = Bin
Metric = Utilization %
Direction = Descending
Limit = 10
```

Likewise, the chatbot should correctly understand follow-ups, filters, comparisons, rankings, capacity questions, ranges, counts, lists and detailed requests without requiring exact predefined questions.

The ultimate goal is:

**ANY NATURAL USER WORDING → CORRECT BUSINESS INTENT → CORRECT DATA → CORRECT CALCULATION → CORRECT RESPONSE FORMAT**

# 2026-10 CONTEXT HARDENING — MULTI-ENTITY, RANGE, UTILIZATION & VALIDATION

## A. Multi-Plant Preservation
When a user explicitly names multiple plants, preserve every plant:
- `Plant 1258 and 1268`
- `plants 1258, 1268 and 7228`
- `Plant 1258 & Plant 1268`
- `1258 and 1268`

These must become a multi-value scope such as:
`Plant IN ('1258','1268')`

Never silently reduce the scope to the first plant.

If any explicitly requested plant is invalid/missing, do not return only the valid subset. Use:
`No matching warehouse records were found for your query in the database.`

## B. Bin Utilization vs Bin Occupancy
For this project:
`Bin Utilization % = Occupied Material Volume / Total Bin Capacity * 100`

Occupied material volume:
`SUM(UnrestrictedQty * MaterialVolume)`

Do NOT use:
`Occupied Bin Count / Total Bin Count`

for a query that asks for physical bin/capacity utilization.

The latter is a separate **Bin Occupancy Rate** and must be labeled accordingly.

## C. Range Has Priority Over Generic "AND"
A numeric/percentage range must be recognized before generic comparison detection.

Examples:
- `between 40% and 60% utilization`
- `40%-60% utilization`
- `from 40% to 60%`
- `bins between 100 and 500 units`

The metric displayed to the user must be the same metric used by the range filter.

Operator fidelity:
- `above 60%` → `> 60%`
- `at least 60%` → `>= 60%`
- `below 30%` → `< 30%`
- `at most 30%` → `<= 30%`

## D. Ranking
Ranking pipeline:
`Entity → Metric → Aggregation → All Filters → Scope → Direction → Limit → Rank`

Examples:
- `top 10 most utilized bins in Plant 1258 and 1268`
  → filter both plants first, calculate utilization per bin, then rank.
- `least utilized bins`
  → ASC.
- `top 5 instead`
  → change only the limit while retaining the previous metric/entity/scope.

Do not automatically generate charts for ranking requests unless the user explicitly asks for one.

## E. Comparison
Comparison must preserve every requested entity and compare the requested metric.

For bin utilization comparison:
`Plant A physical utilization = occupied material volume / total capacity`

Do not substitute occupancy rate.

## F. No-Match / Invalid Scope
Never:
- invent a plant,
- substitute a similar plant,
- silently remove an invalid requested plant,
- default to Plant 1258,
- return a partial multi-plant result as if it satisfied the original request.

Standard no-match response:
`No matching warehouse records were found for your query in the database.`

## G. Response Scope
If the query says `50 rows`, `TOP 50`, or the UI page size is 50, do not claim that 50 is the total number of matching records unless the database aggregate actually says 50.

Prefer:
`Found X matching bins. Showing 50 of X results.`

## H. Context-Based Behavior
The implementation must remain semantic/context-driven. Do not add exact Q&A training pairs for every wording variation. Add business rules, entity extraction, metric definitions, filter preservation, validation, and response-format rules instead.

---

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
