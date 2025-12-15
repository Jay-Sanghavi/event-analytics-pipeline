"""
Capstone Event Analytics ETL Pipeline
Bronze -> Silver -> Gold medallion architecture with incremental processing

INCREMENTAL PROCESSING STRATEGY:
- Uses AWS Glue Job Bookmarks to track processed S3 files
- On first run: Processes all files in source bucket
- On subsequent runs: Only processes NEW files since last run
- Job bookmark is committed at end via job.commit()
- This prevents reprocessing data and reduces cost/runtime

DESIGN RATIONALE:
- Bronze: Raw JSON converted to Parquet for faster downstream processing
- Silver: Cleaned, deduplicated, with derived fields (event_date, amount, etc.)
- Gold: Pre-aggregated analytics tables optimized for query performance
"""

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    to_timestamp,
    hour,
    date_format,
    sum as _sum,
    count,
    avg,
    concat_ws,
    max as _max,
    when,
    row_number,
    lit,
    current_timestamp,
    monotonically_increasing_id,
    concat,
    coalesce,
)
from pyspark.sql.window import Window
from pyspark.sql.types import DecimalType
from datetime import datetime

# Initialize Glue context with job bookmarks enabled
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

# S3 paths
SOURCE_BUCKET = "s3://capstone-events-jsanghvi-778274425587"
ANALYTICS_BUCKET = "s3://capstone-analytics-jsanghvi-778274425587"

BRONZE_PATH = f"{ANALYTICS_BUCKET}/bronze/events"
SILVER_PATH = f"{ANALYTICS_BUCKET}/silver/events_cleaned"
GOLD_HOURLY_REVENUE = f"{ANALYTICS_BUCKET}/gold/hourly_revenue"
GOLD_TOP_PRODUCTS = f"{ANALYTICS_BUCKET}/gold/top_products"
GOLD_USER_ACTIVITY = f"{ANALYTICS_BUCKET}/gold/user_activity"
GOLD_CATEGORY_PERFORMANCE = f"{ANALYTICS_BUCKET}/gold/category_performance"
GOLD_CONVERSION_FUNNEL = f"{ANALYTICS_BUCKET}/gold/conversion_funnel"

print(f"Starting ETL job at {datetime.now()}")

# 1. BRONZE LAYER: Load raw events using Glue DynamicFrame with bookmarks
print("Creating Bronze layer...")

# Use Glue's create_dynamic_frame to enable job bookmarks
# This tracks which files have been processed and only reads new ones
datasource = glueContext.create_dynamic_frame.from_options(
    connection_type="s3",
    connection_options={
        "paths": [f"{SOURCE_BUCKET}/events/"],
        "recurse": True,
    },
    format="json",
    transformation_ctx="datasource_bronze",  # Required for bookmarks
)

# Convert to DataFrame for Spark operations
raw_df = datasource.toDF()
print(f"New/unprocessed records loaded: {raw_df.count()}")

# Write to bronze (append mode for incremental processing)
raw_df.write.mode("append").parquet(BRONZE_PATH)
print(f"Bronze layer updated")

# 2. SILVER LAYER: Clean and deduplicate
print("Creating Silver layer...")

# Read ALL bronze data (includes historical + new)
bronze_df = spark.read.parquet(BRONZE_PATH)

# Parse timestamp string to timestamp, generate event_id, compute amount from price*quantity
silver_df = (
    bronze_df.withColumn("event_time", to_timestamp(col("timestamp")))
    .withColumn("event_hour", hour(col("event_time")))
    .withColumn("event_date", date_format(col("event_time"), "yyyy-MM-dd"))
    .withColumn(
        "event_id",
        concat(
            col("user_id"),
            lit("_"),
            col("session_id"),
            lit("_"),
            monotonically_increasing_id(),
        ),
    )
    .withColumn(
        "amount",
        when(col("event_type") == "purchase", col("price") * col("quantity")).otherwise(
            lit(0)
        ),
    )
    .withColumn("product_name", concat(lit("Product "), col("product_id")))
)

# Deduplicate by user_id, session_id, timestamp, event_type, product_id
window_spec = Window.partitionBy(
    "user_id", "session_id", "timestamp", "event_type", "product_id"
).orderBy(col("event_time").desc())
silver_df = (
    silver_df.withColumn("row_num", row_number().over(window_spec))
    .filter(col("row_num") == 1)
    .drop("row_num")
)

silver_df.write.mode("overwrite").parquet(SILVER_PATH)
print(f"Silver layer complete. Records: {silver_df.count()}")

# 3. GOLD LAYER: Create analytical aggregations
print("Creating Gold layer aggregations...")

# Reload silver for gold transformations
events_df = spark.read.parquet(SILVER_PATH)

# 3.1 Hourly Revenue
print("Creating hourly_revenue...")
hourly_revenue = (
    events_df.filter(col("event_type") == "purchase")
    .groupBy("event_date", "event_hour")
    .agg(
        _sum("amount").cast(DecimalType(18, 2)).alias("total_revenue"),
        count("event_id").alias("transaction_count"),
    )
    .orderBy("event_date", "event_hour")
)
hourly_revenue.write.mode("overwrite").parquet(GOLD_HOURLY_REVENUE)
print(f"hourly_revenue complete. Records: {hourly_revenue.count()}")

# 3.2 Top Products
print("Creating top_products...")
top_products = (
    events_df.filter(col("product_id").isNotNull())
    .groupBy("product_id", "product_name", "category")
    .agg(
        count("event_id").alias("event_count"),
        _sum(when(col("event_type") == "purchase", col("amount")).otherwise(0))
        .cast(DecimalType(18, 2))
        .alias("revenue"),
    )
    .orderBy(col("event_count").desc())
    .limit(100)
)
top_products.write.mode("overwrite").parquet(GOLD_TOP_PRODUCTS)
print(f"top_products complete. Records: {top_products.count()}")

# 3.3 User Activity Summary
print("Creating user_activity...")
user_activity = events_df.groupBy("user_id").agg(
    count("event_id").alias("total_events"),
    _sum(when(col("event_type") == "page_view", 1).otherwise(0)).alias("page_views"),
    _sum(when(col("event_type") == "add_to_cart", 1).otherwise(0)).alias(
        "add_to_cart_count"
    ),
    _sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchase_count"),
    _sum(when(col("event_type") == "purchase", col("amount")).otherwise(0))
    .cast(DecimalType(18, 2))
    .alias("total_spent"),
    _max("event_time").alias("last_activity"),
)
user_activity.write.mode("overwrite").parquet(GOLD_USER_ACTIVITY)
print(f"user_activity complete. Records: {user_activity.count()}")

# 3.4 Category Performance
print("Creating category_performance...")
category_performance = (
    events_df.filter(col("category").isNotNull())
    .groupBy("category")
    .agg(
        count("event_id").alias("total_events"),
        _sum(when(col("event_type") == "page_view", 1).otherwise(0)).alias(
            "page_views"
        ),
        _sum(when(col("event_type") == "add_to_cart", 1).otherwise(0)).alias(
            "add_to_cart"
        ),
        _sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchases"),
        _sum(when(col("event_type") == "purchase", col("amount")).otherwise(0))
        .cast(DecimalType(18, 2))
        .alias("revenue"),
    )
    .orderBy(col("revenue").desc())
)
category_performance.write.mode("overwrite").parquet(GOLD_CATEGORY_PERFORMANCE)
print(f"category_performance complete. Records: {category_performance.count()}")

# 3.5 Conversion Funnel
print("Creating conversion_funnel...")
conversion_funnel = events_df.groupBy("user_id").agg(
    _max(when(col("event_type") == "page_view", 1).otherwise(0)).alias("has_page_view"),
    _max(when(col("event_type") == "add_to_cart", 1).otherwise(0)).alias(
        "has_add_to_cart"
    ),
    _max(when(col("event_type") == "purchase", 1).otherwise(0)).alias("has_purchase"),
)

funnel_summary = conversion_funnel.agg(
    _sum("has_page_view").alias("page_view_users"),
    _sum("has_add_to_cart").alias("add_to_cart_users"),
    _sum("has_purchase").alias("purchase_users"),
).withColumn("stage", lit("overall"))

funnel_summary.write.mode("overwrite").parquet(GOLD_CONVERSION_FUNNEL)
print(f"conversion_funnel complete. Records: {funnel_summary.count()}")

print(f"ETL job completed successfully at {datetime.now()}")

# Commit the job bookmark to track processed files
job.commit()
spark.stop()
