# StarRocks Table Creation Best Practices

## Required Information Checklist

Before giving recommendations, collect the following information (listed by priority). When something is missing, ask proactively:

| Information | Purpose | Example |
|------|------|------|
| **Business scenario** | Determines the table model | OLAP analysis / real-time updates / log storage / CDC sync |
| **Data volume** | Determines partition granularity and bucket count | 5 million rows/day, 1 billion total, 90-day retention |
| **Query pattern** | Determines sort key and indexes | Point lookup by user_id / time-range aggregation / multi-table JOIN |
| **Primary filter columns** | Determines partition column and sort key | Time, tenant ID, region |
| **Update requirements** | Determines the table model | Append-only / upsert by primary key / partial column updates |
| **Cluster information** | Determines bucket count and replica count | shared-nothing 3 BE / shared-data 10 CN |
| **JOIN requirements** | Whether to use Colocate | Fact table + dimension table frequent JOIN |
| **Existing DDL** (optimization scenarios) | Locate current issues | The user provides an existing CREATE TABLE statement |

## Table Creation Decision Flow

```
Step 1: Choose table model     → Based on update requirements (see schema/table-types.md)
    ↓
Step 2: Design partitioning    → Based on data volume and time dimension (see schema/partitioning.md)
    ↓
Step 3: Design bucketing       → Based on query pattern and data volume (see schema/bucketing.md)
    ↓
Step 4: Design sort key        → Based on high-frequency query filter columns (see schema/sort-key-and-indexes.md)
    ↓
Step 5: Choose indexes         → Based on non-prefix column query requirements (see schema/sort-key-and-indexes.md)
    ↓
Step 6: Set storage properties → Based on performance/space trade-offs (see schema/storage-properties.md)
        On shared-data (存算分离), see the "Shared-data properties" section there for the
        required checklist (storage_volume, datacache.*, persistent_index_type) and the
        properties that are silently stripped or rejected.
```

Detailed rules for each step are in the corresponding reference file; read as needed.

## Official-First Design Playbook

When a user asks for table design or DDL, optimize for the real workload, not for a generic template:

1. **Model update semantics first.** Append-only detail rows -> Duplicate Key. CDC/upsert/delete -> Primary Key. Pre-aggregated metric state -> Aggregate. Simple latest-row dedup -> Unique Key only when a Primary Key table is not a better fit.
2. **Partition for pruning and lifecycle.** The partition key should appear in common WHERE predicates or in TTL/drop/hot-cold management. For most BI/reporting facts, start with daily expression partitioning. Use hourly partitions only for short-retention or "last few hours" workloads with high ingest pressure.
3. **Bucket for distribution, parallelism, and locality.** Pick HASH only when there is a stable high-cardinality equality filter, JOIN key, aggregation key, or Primary Key access path. Use RANDOM when there is no useful locality requirement and the table type supports it.
4. **Sort for scan reduction.** Pick sort keys from the most common filters and arrange them for leftmost-prefix matching. Normally use about 3 columns and avoid going beyond 4 because the prefix index is limited to 36 bytes.
5. **Add secondary indexes only for repeated misses.** Prefer sort key and partition pruning first; add Bitmap/Bloom/N-Gram/GIN indexes only when representative queries repeatedly filter on non-prefix columns.
6. **Validate with the optimizer.** For existing tables or slow queries, require `EXPLAIN VERBOSE` and inspect partition/tablet pruning before recommending DDL changes, MV creation, or scale-out.

## Table Model Quick Reference

| Scenario | Recommended Model | Key Rationale |
|------|---------|---------|
| Logs / event streams / detail data | **Duplicate Key** | No update requirement, append-only writes, supports Random bucketing |
| Pre-aggregated metrics (PV/UV/GMV) | **Aggregate** | Automatic aggregation reduces storage, queries avoid GROUP BY |
| Real-time upsert / CDC sync | **Primary Key** | Delete+Insert strategy, much better query performance than Unique Key |
| Simple deduplication (no real-time updates) | **Unique Key** | merge-on-read deduplication (use Primary Key directly for new scenarios) |

## Partition and Bucketing Quick Reference

| Data Characteristics | Partitioning Strategy | Bucketing Strategy |
|---------|---------|---------|
| Time-series data (with date column) | `PARTITION BY date_trunc('day', ts)` | `HASH(business ID)` |
| High-frequency write log streams | `PARTITION BY date_trunc('hour', ts)` | `RANDOM` + `bucket_size` |
| Multi-tenant SaaS | Daily partition + tenant in sort key, or `PARTITION BY (tenant_id, region)` (LIST) | `HASH(tenant_id)` |
| Dimension tables (< 10 million rows) | No partitioning | `HASH(primary key)` |
| Very large fact tables + frequent JOIN | `PARTITION BY date_trunc('day', ts)` | `HASH(JOIN key)` + Colocate |
| No clear partition key | No partitioning | `RANDOM` + `bucket_size` |

## Automatic Bucketing Clarification

There are two different "automatic" behaviors. Keep them separate in answers:

| Question | Correct answer |
|------|------|
| Can StarRocks choose the bucket count automatically? | Yes, on supported versions you can omit `BUCKETS` after `DISTRIBUTED BY HASH(col)` and StarRocks chooses the count. You still designed the HASH key manually. |
| Can I omit `DISTRIBUTED BY` entirely? | Only in specific cases. Duplicate Key tables on v3.1+ can default to random bucketing. Async MVs on v3.1+ can also default to random bucketing. Do not apply this rule blindly to Primary Key / Aggregate / Unique Key tables. |
| Can random bucketing grow automatically? | From v3.2+, random bucketing can use `PROPERTIES ("bucket_size" = "...")` so tablets split as they grow. It grows; it does not give HASH locality. |
| Can random bucketing support Colocate Join? | No. If Colocate Join or bucket pruning matters, choose HASH bucketing with a deliberate key and bucket count/auto-count. |

**Default answer pattern for "是不是能自动分桶":**

```text
Yes, but clarify whether the user means automatic bucket count or random bucketing.
For Duplicate Key detail/log tables and async MVs, automatic random bucketing can be a good default.
For PK/Aggregate/Unique tables, CDC tables, and frequent JOIN/filter paths, still design HASH explicitly.
```

## Common Anti-Patterns

Proactively check for and avoid these in your table design:

| Anti-Pattern | Consequence | Correct Approach |
|--------|------|---------|
| Picking a low-cardinality column (gender/status) as the bucket column | Data skew, some tablets too large | Pick a high-cardinality column (user_id/order_id) |
| Over-fine partitioning (hourly + 365-day retention) | Massive empty partitions, FE memory pressure | Match granularity to the retention period (day/month) |
| Primary Key too long (>128 bytes) | Index bloat, slower writes | Trim primary key columns; use the shortest combination that uniquely identifies a row |
| Too many sort key columns (>4, or long strings early) | Write performance degrades, prefix index truncated past 36 bytes | Pick about 3 frequently filtered columns; rarely exceed 4, and put long string columns late |
| Large tables not partitioned | No partition pruning, full table scans | Partition by time or business dimension |
| Tables in the same Colocate group with different bucket counts | Colocate Join no longer works | Tables in the same group must have identical bucket count, bucket key type, and replica count |
| Using FLOAT/DOUBLE for amounts | Precision loss | Use `DECIMAL(p, s)` |
| Using VARCHAR for fixed-length data | Wastes storage, hurts prefix index efficiency | Use `CHAR` for fixed lengths |
| Duplicate Key table using HASH bucketing without a clear query key | Cannot leverage bucket pruning, worse than Random | Switch to `RANDOM` bucketing |
| Saying "manual BUCKETS is always required" | Outdated or over-prescriptive guidance | Separate HASH key design from automatic bucket-count selection; mention random auto bucketing where supported |
| Using hourly partitions for long-retention BI tables | Thousands of partitions per year, FE metadata pressure | Use daily/monthly partitions unless last-hour pruning is a hard requirement |
| Building DDL without representative queries | Sort key, partition, and bucket choices are guesses | Ask for the top query patterns or inspect query history/audit logs |

## Reference File Index

When you need the detailed rules for a step, read the corresponding file:

| Topic | Reference File | Contents |
|------|--------------|---------|
| Table model selection | [schema/table-types.md](schema/table-types.md) | Detailed comparison of the four table models, syntax, constraints, selection decision tree |
| Partitioning strategy | [schema/partitioning.md](schema/partitioning.md) | Expression/Range/List/Dynamic partitioning, partition count control |
| Bucketing strategy | [schema/bucketing.md](schema/bucketing.md) | Hash/Random bucketing, bucket count calculation, Colocate Group |
| Sort key and indexes | [schema/sort-key-and-indexes.md](schema/sort-key-and-indexes.md) | Prefix index, ORDER BY, Bitmap/Bloom Filter/full-text indexes |
| Storage properties | [schema/storage-properties.md](schema/storage-properties.md) | Compression, replicas, hot/cold storage tiering, Schema Evolution |

## Output Template

When giving table creation recommendations, use the following structured format:

```markdown
## Table Design

### 1. Table Model: {Duplicate Key / Aggregate / Primary Key / Unique Key}
**Rationale:** {Why this model fits the user's scenario}

### 2. Partitioning Strategy
**Design:** {PARTITION BY ...}
**Rationale:** {Data volume, retention period, pruning benefit}
**Estimated partition count:** {Approximately N partitions}

### 3. Bucketing Strategy
**Design:** {DISTRIBUTED BY HASH(col) BUCKETS N / DISTRIBUTED BY RANDOM}
**Bucket count:** {N} (about {X} GB per tablet)
**Rationale:** {Why this bucket key and count}

### 4. Sort Key and Indexes
**Sort key:** ORDER BY (col1, col2, ...)
**Additional indexes:** {Bitmap / Bloom Filter / None}
**Rationale:** {Which high-frequency query filter conditions this matches}

### 5. Storage Properties
- Compression: {LZ4 / ZSTD / ...}
- Replicas: {N}
- Other: {As needed}

### 6. Full CREATE TABLE Statement

​```sql
CREATE TABLE ...
​```

### 7. Caveats
- {Version requirements, migration notes, follow-up optimization suggestions, etc.}

### 8. Verification Plan
- `SHOW CREATE TABLE {table}` confirms table type, partitioning, bucketing, sort key, and properties.
- `EXPLAIN VERBOSE {representative query}` checks partition/tablet pruning.
- Query Profile checks prefix-index/index effectiveness when available.
```
