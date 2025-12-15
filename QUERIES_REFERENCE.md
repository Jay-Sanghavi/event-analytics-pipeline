# SQL Queries Reference Guide

## Connecting to Athena

### AWS Console
1. Navigate to Athena
2. Set Query Result Location: `s3://capstone-analytics-jsanghvi-{ACCOUNT}/athena-results/`
3. Select Database: `gold_jsanghvi`
4. Execute queries from `queries.sql`

### AWS CLI
```bash
aws athena start-query-execution \
  --query-string file://queries.sql \
  --query-execution-context Database=gold_jsanghvi \
  --result-configuration OutputLocation=s3://capstone-analytics-jsanghvi-{ACCOUNT}/athena-results/ \
  --region us-west-2
```

### Python (Pandas)
```python
import pandas as pd
import boto3
from pyathena import connect

cursor = connect(
    s3_output_location='s3://capstone-analytics-jsanghvi-{ACCOUNT}/athena-results/',
    region_name='us-west-2'
).cursor()

# Query 1
df = pd.read_sql(
    "SELECT * FROM gold_jsanghvi.conversion_funnel ORDER BY purchases DESC LIMIT 20",
    conn=cursor
)
print(df)
```

---

## Query Details

### Query 1: Conversion Funnel
**File**: queries.sql (lines 1-23)
**Purpose**: Understand product-level conversion rates
**Expected Columns**: 8 columns, varies by number of products
**Performance**: <1 second

**Key Metrics**:
- `view_to_cart_conversion_pct`: % of page views that resulted in add-to-cart
- `view_to_purchase_conversion_pct`: % of page views that resulted in purchase
- `cart_to_purchase_conversion_pct`: % of cart additions that resulted in purchase

**Business Use**:
- Products with high views but low cart: Fix product page/pricing
- Products with high cart but low purchase: Fix checkout process
- Products with both low rates: Needs investigation

---

### Query 2: Hourly Revenue
**File**: queries.sql (lines 25-42)
**Purpose**: Track revenue generation patterns
**Expected Columns**: 4 columns, one row per hour
**Performance**: <1 second

**Key Metrics**:
- `total_revenue`: Sum of (price × quantity) for all purchases
- `transaction_count`: Number of purchase transactions
- `avg_order_value`: Average revenue per transaction

**Business Use**:
- Peak revenue hours: When to staff up/promote
- Hourly trends: Daily patterns in customer behavior
- AOV trends: Product mix and pricing effectiveness

---

### Query 3: Top 10 Products
**File**: queries.sql (lines 44-58)
**Purpose**: Identify most-viewed products
**Expected Columns**: 4 columns, exactly 10 rows (top products)
**Performance**: <1 second

**Key Metrics**:
- `rank`: 1-10 ranking by view count
- `view_count`: Number of page views

**Business Use**:
- Guide inventory investment
- Analyze product success patterns
- Compare with sales figures (views vs. purchases)
- Detect category trends

---

### Query 4: Category Performance
**File**: queries.sql (lines 60-78)
**Purpose**: Track engagement by product category
**Expected Columns**: 4 columns (one row per date-category combination)
**Performance**: <1 second

**Key Metrics**:
- `event_count`: Total events (all types) for category on that day
- `daily_rank`: Ranking within that day (which category drove most activity)

**Business Use**:
- Identify emerging categories
- Track seasonality (e.g., holidays)
- Allocate marketing budget by category
- Compare category momentum

---

### Query 5: User Activity
**File**: queries.sql (lines 80-95)
**Purpose**: Measure platform engagement
**Expected Columns**: 4 columns, one row per day
**Performance**: <1 second

**Key Metrics**:
- `unique_users`: Distinct user count for the day
- `unique_sessions`: Distinct session count for the day
- `avg_sessions_per_user`: Sessions per user on that day

**Business Use**:
- User acquisition trends
- Session quality (average sessions per user)
- Identify bot activity (sessions > users)
- Platform engagement over time

---

## Sample Expected Results

### Conversion Funnel Sample
```
product_id | category    | views | add_to_carts | purchases | view_to_cart_pct | view_to_purch_pct | cart_to_purch_pct
p_1001     | electronics | 1250  | 350          | 45        | 28.00            | 3.60              | 12.86
p_2001     | clothing    | 890   | 125          | 18        | 14.04            | 2.02              | 14.40
```

### Hourly Revenue Sample
```
event_date | event_hour | total_revenue | transaction_count | avg_order_value
2025-11-18 | 14         | 1523.47       | 42                | 36.27
2025-11-18 | 15         | 1876.92       | 51                | 36.80
```

### Top 10 Products Sample
```
rank | product_id | category    | view_count
1    | p_1001     | electronics | 1250
2    | p_2001     | clothing    | 890
3    | p_3001     | home        | 762
```

### Category Performance Sample
```
event_date | category    | event_count | daily_rank
2025-11-18 | electronics | 4521        | 1
2025-11-18 | clothing    | 3892        | 2
2025-11-18 | home        | 3124        | 3
```

### User Activity Sample
```
event_date | unique_users | unique_sessions | avg_sessions_per_user
2025-11-18 | 1523         | 2147            | 1.41
2025-11-17 | 1456         | 2031            | 1.39
```

---

## Query Optimization Tips

### 1. Use Date Filters
```sql
-- SLOW: Scans entire dataset
SELECT * FROM gold_jsanghvi.hourly_revenue;

-- FAST: Filters by date partition
SELECT * FROM gold_jsanghvi.hourly_revenue
WHERE event_date >= '2025-11-18';
```

### 2. Limit Result Sets
```sql
-- Always use LIMIT for exploratory queries
SELECT * FROM gold_jsanghvi.conversion_funnel
LIMIT 20;
```

### 3. Pre-filter in WHERE clause
```sql
-- Filter before aggregation when possible
SELECT category, SUM(event_count)
FROM gold_jsanghvi.category_performance
WHERE event_date >= '2025-11-15'
GROUP BY category;
```

### 4. Check Partition Info
```sql
-- See available date ranges
SELECT DISTINCT event_date
FROM gold_jsanghvi.user_activity
ORDER BY event_date DESC;
```

---

## Troubleshooting Query Issues

### No Results Returned
- [ ] Check Gold database exists: `SHOW DATABASES`
- [ ] Verify tables exist: `SHOW TABLES IN gold_jsanghvi`
- [ ] Check Glue job ran successfully
- [ ] Verify data exists: `SELECT COUNT(*) FROM silver_jsanghvi.events_cleaned`

### Query Times Out
- [ ] Use narrower date range
- [ ] Add more WHERE clause filters
- [ ] Check table partitions: `SHOW PARTITIONS gold_jsanghvi.hourly_revenue`

### Unexpected NULL Values
- [ ] Check for missing product_id entries in raw data
- [ ] Verify deduplication didn't remove expected records
- [ ] Check aggregate functions handle NULL correctly

### Large Result Sets
- [ ] Always use LIMIT for exploratory queries
- [ ] Export to S3 for large datasets: `CREATE TABLE AS SELECT ...`

---

## Advanced Queries

### Compare Daily Trends
```sql
SELECT
    DATE_TRUNC('day', event_date) as date,
    COUNT(*) as user_count,
    COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY DATE_TRUNC('day', event_date)) as user_change
FROM gold_jsanghvi.user_activity
GROUP BY DATE_TRUNC('day', event_date)
ORDER BY date DESC;
```

### Identify Poor Performers
```sql
SELECT
    product_id,
    category,
    views,
    purchases,
    CASE
        WHEN views > 100 AND purchases < 5 THEN 'High View, Low Sales'
        WHEN views > 50 AND add_to_carts < 10 THEN 'Low Cart Addition'
        WHEN add_to_carts > 20 AND purchases < 3 THEN 'Cart Abandonment'
        ELSE 'Good Performer'
    END as product_status
FROM gold_jsanghvi.conversion_funnel
ORDER BY views DESC;
```

### Revenue Analysis by Category
```sql
SELECT
    category,
    SUM(total_revenue) as total_category_revenue,
    COUNT(*) as transaction_count,
    ROUND(AVG(total_revenue / transaction_count), 2) as avg_order_value
FROM gold_jsanghvi.hourly_revenue
GROUP BY category
ORDER BY total_category_revenue DESC;
```

---

## Exporting Results

### To CSV
```bash
# Query and export to CSV
aws athena start-query-execution \
  --query-string "SELECT * FROM gold_jsanghvi.conversion_funnel LIMIT 1000" \
  --query-execution-context Database=gold_jsanghvi \
  --result-configuration OutputLocation=s3://capstone-analytics-jsanghvi-{ACCOUNT}/athena-results/ \
  --region us-west-2

# Download result
aws s3 cp s3://capstone-analytics-jsanghvi-{ACCOUNT}/athena-results/{query-id}.csv ./
```

### Via Python
```python
import pandas as pd
import boto3

s3 = boto3.client('s3')
obj = s3.get_object(Bucket='capstone-analytics-jsanghvi-{ACCOUNT}', 
                    Key='athena-results/{query-id}.csv')
df = pd.read_csv(obj['Body'])
df.to_csv('results.csv', index=False)
```

---

## Performance Benchmarks

| Query | Typical Runtime | Data Scanned | Cost |
|-------|-----------------|--------------|------|
| Conversion Funnel | <500ms | 50MB | $0.00025 |
| Hourly Revenue | <300ms | 30MB | $0.00015 |
| Top Products | <200ms | 20MB | $0.00010 |
| Category Performance | <400ms | 40MB | $0.00020 |
| User Activity | <200ms | 15MB | $0.00007 |

**Total for all 5 queries**: ~$0.0007 (~0.07 cents per run)

---

## FAQ

**Q: Why are some queries running slow?**
A: Use WHERE clauses to filter by date. Queries on entire dataset take longer.

**Q: Can I modify the queries?**
A: Yes! The provided queries are templates. Adapt them for your analysis needs.

**Q: How often is the data updated?**
A: Glue job must be run manually (or scheduled via EventBridge). Data is as fresh as the last job run.

**Q: Why are some products missing from Conversion Funnel?**
A: Only products with at least one event appear in the funnel. Add CROSS JOIN with product catalog if needed.

**Q: How do I track data freshness?**
A: Check max timestamp in silver table:
```sql
SELECT MAX(event_timestamp) FROM silver_jsanghvi.events_cleaned;
```

---

**Last Updated**: December 8, 2025
