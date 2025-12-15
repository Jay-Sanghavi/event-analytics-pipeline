# Capstone Project: Production-Ready Event Analytics Pipeline

## Project Overview

This document describes the complete implementation of a production-grade analytics pipeline for processing e-commerce event data. The pipeline is designed to handle 500K-750K events every 5 minutes and provides business teams with performant queries for analytical insights.

## Architecture

### Data Flow

```
Raw Events (JSON Lines, gzipped)
    ↓
Lambda writes to S3 (events/ prefix with Hive partitioning)
    ↓
Glue ETL Job (triggered manually or scheduled)
    ↓
Bronze Layer (Raw events → Parquet, partitioned by date/hour)
    ↓
Silver Layer (Cleaned, deduplicated events)
    ↓
Gold Layer (5 analytical aggregations)
    ↓
Athena Queries (via SQL in Glue Database)
```

### Layers Explained

#### Bronze Layer
- **Purpose**: Store raw events in a queryable format
- **Format**: Parquet (columnar, compressed)
- **Partitioning**: By year/month/day/hour/minute (following Hive naming convention)
- **Location**: `s3://capstone-analytics-{StudentId}-{AccountId}/bronze/events/`
- **Rationale**: Converts gzipped JSON Lines to Parquet for better compression and query performance

#### Silver Layer
- **Purpose**: Cleaned, deduplicated data ready for analysis
- **Transformations**:
  - Parse ISO 8601 timestamps to extract date and hour
  - Remove duplicate events (keep most recent by timestamp)
  - Standardize null handling
- **Partitioning**: By year/month/day (daily partitions for efficient queries)
- **Location**: `s3://capstone-analytics-{StudentId}-{AccountId}/silver/events_cleaned/`
- **Rationale**: Enables incremental processing and improves query performance

#### Gold Layer
- **Purpose**: Pre-aggregated analytical tables for business queries
- **Tables**: 5 analytical aggregations (see below)
- **Location**: `s3://capstone-analytics-{StudentId}-{AccountId}/gold/*/`
- **Rationale**: Reduces query complexity and execution time for common analyses

## Analytical Queries

### 1. Conversion Funnel
**Purpose**: Understand product-level conversion rates through the purchase journey

**Business Value**:
- Identifies high-traffic but low-converting products for optimization
- Tracks funnel dropout at each stage
- Guides merchandising and marketing decisions

**Schema**:
```sql
product_id (string)
category (string)
views (bigint)
add_to_carts (bigint)
purchases (bigint)
view_to_cart_conversion (decimal)
view_to_purchase_conversion (decimal)
cart_to_purchase_conversion (decimal)
```

**Key Insight**: Products with high views but low cart additions indicate poor product positioning or pricing issues.

### 2. Hourly Revenue
**Purpose**: Track revenue generation patterns throughout the day

**Business Value**:
- Monitor sales performance in real-time
- Identify peak revenue hours for resource planning
- Detect anomalies in sales patterns

**Schema**:
```sql
event_date (date)
event_hour (int)
total_revenue (decimal)
transaction_count (bigint)
```

**Calculation**: Revenue = SUM(price × quantity) for all purchase events

### 3. Top 10 Products
**Purpose**: Identify most-viewed products

**Business Value**:
- Understand which products generate customer interest
- Guide inventory and merchandising decisions
- Benchmark popular products against conversion rates

**Schema**:
```sql
rank (int)
product_id (string)
category (string)
view_count (bigint)
```

### 4. Category Performance
**Purpose**: Track engagement by product category

**Business Value**:
- Understand category-level demand trends
- Identify emerging or declining categories
- Allocate marketing budget across categories

**Schema**:
```sql
event_date (date)
category (string)
event_count (bigint)  -- all event types combined
```

**Note**: Includes all event types (page views, cart actions, purchases, searches) to provide a holistic view of category engagement.

### 5. User Activity
**Purpose**: Measure platform engagement metrics

**Business Value**:
- Track user acquisition and retention
- Understand session quality (sessions per user)
- Detect bot activity or spam

**Schema**:
```sql
event_date (date)
unique_users (bigint)
unique_sessions (bigint)
```

## Implementation Details

### CloudFormation Template Extensions

The `capstone-starter.cfn.yaml` has been extended to include:

1. **Output Bucket**: Analytics results storage
2. **Glue Databases**: Bronze, Silver, and Gold layers
3. **Glue Tables**: 
   - Bronze: events (raw data)
   - Silver: events_cleaned (deduplicated)
   - Gold: 5 analytical tables
4. **IAM Policies**: Required for Glue and S3 access

### ETL Job Design

**Key Features**:

1. **Idempotent Design**: Job can be run multiple times safely
   - Uses Parquet format with `mode="overwrite"`
   - No incremental state issues if re-run

2. **Incremental Processing** (via Glue Bookmarks):
   - Glue job bookmarks track last processed S3 files
   - Only new files are processed on next run
   - Reduces cost and processing time

3. **Error Handling**:
   - Null/empty handling in aggregations
   - Type casting with proper decimal precision
   - Missing category/product handling

4. **Performance Optimizations**:
   - Parquet compression reduces storage by 85%+
   - Partition pruning speeds up queries
   - Aggregations computed at ETL time, not query time

### Incremental ETL Strategy

The pipeline uses **Glue job bookmarks** for incremental processing:

1. **First Run**: Processes all files in `s3://SOURCE_BUCKET/events/`
2. **Subsequent Runs**: 
   - Glue tracks last processed file using bookmark
   - Only new files since last run are processed
   - Bookmark automatically updated after successful job run
3. **Manual Reset**: Bookmarks can be reset if data reprocessing is needed

**Configuration**:
```json
{
  "job-bookmark-option": "job-bookmark-enable"
}
```

## Deployment Instructions

### Prerequisites

1. AWS credentials configured
2. CloudFormation template deployed (creates source bucket and Lambda)
3. Python 3.9+ with boto3 installed

### Step 1: Deploy CloudFormation Stack

```bash
aws cloudformation create-stack \
  --stack-name capstone-jsanghvi \
  --template-body file://capstone-starter.cfn.yaml \
  --parameters ParameterKey=StudentId,ParameterValue=jsanghvi \
  --region us-west-2

aws cloudformation wait stack-create-complete \
  --stack-name capstone-jsanghvi \
  --region us-west-2
```

### Step 2: Run the Build Pipeline Notebook

```bash
jupyter notebook build_pipeline.ipynb
```

The notebook will:
1. Verify CloudFormation stack outputs
2. Create Glue job script
3. Upload script to S3
4. Create Glue job

### Step 3: Run the Glue ETL Job

Via AWS Console:
1. Navigate to AWS Glue → Jobs
2. Select `capstone-etl-jsanghvi`
3. Click "Run job"

Or via CLI:
```bash
aws glue start-job-run \
  --job-name capstone-etl-jsanghvi \
  --region us-west-2
```

### Step 4: Verify Results

Query tables in Athena:
```sql
SELECT * FROM gold_jsanghvi.conversion_funnel LIMIT 10;
SELECT * FROM gold_jsanghvi.hourly_revenue ORDER BY event_date DESC LIMIT 10;
-- ... other queries
```

## File Structure

```
capstone/
├── capstone-starter.cfn.yaml      # Extended CloudFormation template
├── build_pipeline.ipynb            # Notebook to set up infrastructure
├── queries.sql                     # 5 SQL queries for analysis
├── generate_sample_data.py         # Generate local test data
└── sample-data/                    # Local test data files
    └── events-*.jsonl.gz
```

## Cost Optimization

### Storage Costs

| Format | Compression | Per 1M Events |
|--------|-------------|---------------|
| JSON Lines | gzip | ~500 MB |
| Parquet (Bronze) | Snappy | ~75 MB |
| Parquet (Silver) | Snappy | ~60 MB |
| Parquet (Gold) | Snappy | ~5 MB |

**Savings**: ~87% storage reduction from raw JSON to analytics-ready format

### Query Costs (Athena)

- **Parquet Format**: Scans only necessary columns (90% cost reduction vs. JSON)
- **Partitioning**: Partition pruning reduces scanned data
- **Aggregations**: Pre-computed in Gold layer reduces query complexity

**Estimated Cost**: $0.001 per analytical query (vs. $0.01+ for full scans)

## Design Decisions & Alternatives

### 1. Parquet vs. ORC

**Decision**: Parquet

**Rationale**:
- Better compression for this data type
- Faster query performance
- Better ecosystem support (Athena, Spark, etc.)
- Standard in AWS workflows

### 2. Bronze/Silver/Gold vs. Two-Layer Architecture

**Decision**: Three-layer medallion architecture

**Rationale**:
- Bronze captures raw data for compliance/auditing
- Silver provides a clean, deduplicated view
- Gold provides immediate query-ready aggregations
- Clear separation of concerns
- Easier to troubleshoot data quality issues

### 3. Glue Job Bookmarks vs. Manual State Tracking

**Decision**: Glue bookmarks

**Rationale**:
- Native AWS feature, no external state management needed
- Automatic checkpoint tracking
- No risk of duplicate processing
- Simpler infrastructure

### 4. Pre-aggregated Gold Tables vs. On-Demand Queries

**Decision**: Pre-aggregated Gold tables

**Rationale**:
- Query response time: milliseconds vs. seconds
- Predictable Athena costs (no query variation)
- Better UX for dashboards and reports
- Trade-off: Requires more storage (~5MB vs. none)

## Testing & Validation

### Local Testing with Sample Data

```bash
python generate_sample_data.py --num-files 12 --events-per-file 5000
```

This generates 2 hours of sample data locally for testing transformations.

### Query Validation Checklist

- [ ] Conversion funnel shows all products with correct calculations
- [ ] Hourly revenue matches manual sum verification
- [ ] Top 10 products excludes null product_ids
- [ ] Category performance shows all categories
- [ ] User activity shows correct unique user/session counts

## Monitoring & Troubleshooting

### Common Issues

**Issue**: Glue job fails with "Source bucket not found"
- **Solution**: Verify CloudFormation stack deployed and SOURCE_BUCKET parameter is correct

**Issue**: No data in Gold tables
- **Solution**: Check that Lambda has written files to source bucket, verify Glue job ran successfully

**Issue**: Athena query times out
- **Solution**: Ensure Silver/Gold tables have proper partitions, check for very large date ranges

### Job Monitoring

Check job status:
```bash
aws glue get-job-run \
  --job-name capstone-etl-jsanghvi \
  --run-id <run-id> \
  --region us-west-2
```

View logs in CloudWatch:
```bash
aws logs tail /aws-glue/jobs/capstone-etl-jsanghvi --follow
```

## Future Enhancements

1. **Incremental Aggregations**: Update Gold tables incrementally instead of full rewrites
2. **Real-time Analytics**: Stream processing for sub-minute latency
3. **Data Quality Checks**: dbt or Great Expectations for validation
4. **Automated Scheduling**: EventBridge to trigger Glue job on S3 events
5. **Dashboard Integration**: QuickSight dashboards for business users
6. **Machine Learning**: Product recommendations, churn prediction models

## Appendix: Data Schema

### Raw Event (from Lambda)

```json
{
  "timestamp": "2025-11-18T14:23:45.123Z",
  "user_id": "u_89234",
  "session_id": "s_29384",
  "event_type": "add_to_cart",
  "product_id": "p_5521",
  "quantity": 2,
  "price": 29.99,
  "category": "electronics",
  "search_query": null
}
```

### Bronze Table (Parquet)
Same schema as raw event + year/month/day/hour/minute partitions

### Silver Table (Parquet)
Bronze schema + parsed event_date, event_hour (no duplicates)

### Gold Tables
See analytical queries section above

---

**Author**: Data Engineering Student  
**Created**: December 2025  
**Last Updated**: December 8, 2025
