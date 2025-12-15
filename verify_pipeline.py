#!/usr/bin/env python3
"""
Verify the capstone analytics pipeline end-to-end and optionally clean up outputs.

What it does:
1) Resolves stack outputs (source + analytics buckets) from CloudFormation
2) Checks for data in Bronze/Silver/Gold prefixes
3) Runs lightweight Athena sanity checks on the 5 gold tables
4) (Optional) Deletes analytics-layer files after verification

Usage examples:
  # Verify only
  python verify_pipeline.py --student-id jsanghvi

  # Verify and then delete analytics outputs (bronze/silver/gold/athena-results)
  python verify_pipeline.py --student-id jsanghvi --cleanup

Note: This script avoids deleting the source events bucket. Cleanup only touches
analytics outputs so you can safely rerun the ETL later.
"""

import argparse
import gzip
import json
import sys
import time
from pathlib import Path
from typing import Dict

import boto3
from botocore.exceptions import ClientError


def get_stack_outputs(cfn, stack_name: str) -> Dict[str, str]:
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def list_prefix_sample(s3, bucket: str, prefix: str, limit: int = 5):
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=limit)
    keys = [obj["Key"] for obj in resp.get("Contents", [])]
    return keys


def run_athena_query(athena, query: str, database: str, output_s3: str, workgroup: str):
    exec_resp = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_s3},
        WorkGroup=workgroup,
    )
    exec_id = exec_resp["QueryExecutionId"]

    while True:
        resp = athena.get_query_execution(QueryExecutionId=exec_id)
        state = resp["QueryExecution"]["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(1)

    if state != "SUCCEEDED":
        reason = resp["QueryExecution"]["Status"].get("StateChangeReason", "")
        raise RuntimeError(f"Athena query failed: {state} {reason}")

    results = athena.get_query_results(QueryExecutionId=exec_id, MaxResults=10)
    rows = results.get("ResultSet", {}).get("Rows", [])
    # Skip header row if present
    if rows and "VarCharValue" in rows[0]["Data"][0]:
        return [list(map(lambda d: d.get("VarCharValue"), r["Data"])) for r in rows[1:]]
    return []


def delete_prefix(s3, bucket: str, prefix: str):
    paginator = s3.get_paginator("list_objects_v2")
    to_delete = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get("Contents", [])
        if not contents:
            continue
        for obj in contents:
            to_delete.append({"Key": obj["Key"]})
        # Batch delete every 1000
        if len(to_delete) >= 1000:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
            to_delete.clear()
    if to_delete:
        s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})


def main():
    parser = argparse.ArgumentParser(
        description="Verify capstone pipeline and optionally clean outputs"
    )
    parser.add_argument(
        "--student-id", required=True, help="Student ID used in stack naming"
    )
    parser.add_argument(
        "--stack-name",
        default=None,
        help="CloudFormation stack name (default: capstone-<student-id>)",
    )
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: verify local sample-data without AWS",
    )
    parser.add_argument(
        "--sample-dir",
        default="sample-data",
        help="Directory with local sample gz files (offline mode)",
    )
    parser.add_argument(
        "--analytics-bucket", default=None, help="Override analytics bucket name"
    )
    parser.add_argument(
        "--source-bucket", default=None, help="Override source bucket name"
    )
    parser.add_argument(
        "--athena-workgroup", default="primary", help="Athena workgroup"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete analytics outputs after verification (offline: deletes sample files)",
    )
    args = parser.parse_args()

    if args.offline:
        sample_dir = Path(args.sample_dir)
        if not sample_dir.exists():
            print(f"ERROR: sample directory not found: {sample_dir}")
            sys.exit(1)

        gz_files = sorted(sample_dir.glob("*.jsonl.gz"))
        if not gz_files:
            print(f"No .jsonl.gz files found under {sample_dir}")
            sys.exit(1)

        total_events = 0
        print("=== Offline verification (local sample-data) ===")
        print(f"Files found: {len(gz_files)} under {sample_dir}\n")

        for path in gz_files:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                lines = fh.readlines()
            total_events += len(lines)
            # Show a tiny peek at the first event for sanity
            first_line = lines[0].strip() if lines else "<empty>"
            try:
                parsed = json.loads(first_line)
                summary = {
                    "event_type": parsed.get("event_type"),
                    "category": parsed.get("category"),
                    "product_id": parsed.get("product_id"),
                }
            except json.JSONDecodeError:
                summary = {"raw_first_line": first_line[:120]}
            print(f"- {path.name}: {len(lines):,} events | first={summary}")

        print(f"\nTotal events across files: {total_events:,}")

        if args.cleanup:
            print("\nCleanup requested: deleting local sample files...")
            for path in gz_files:
                path.unlink(missing_ok=True)
                print(f"  deleted {path.name}")
            print("Cleanup complete (sample-data only).")
        else:
            print(
                "\nCleanup not requested. Use --cleanup to remove local sample files."
            )

        return

    stack_name = args.stack_name or f"capstone-{args.student_id}"

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    cfn = session.client("cloudformation")
    athena = session.client("athena")

    try:
        outputs = get_stack_outputs(cfn, stack_name)
    except ClientError as e:
        print(f"ERROR: Could not read stack outputs for {stack_name}: {e}")
        sys.exit(1)

    source_bucket = args.source_bucket or outputs.get("SourceBucketName")
    analytics_bucket = args.analytics_bucket or outputs.get("AnalyticsOutputBucket")
    if not source_bucket or not analytics_bucket:
        print(
            "ERROR: Missing bucket names (source or analytics). Pass them explicitly or check stack outputs."
        )
        sys.exit(1)

    bronze_db = f"bronze_{args.student_id}"
    silver_db = f"silver_{args.student_id}"
    gold_db = f"gold_{args.student_id}"

    print("=== Buckets ===")
    print(f"Source bucket:    {source_bucket}")
    print(f"Analytics bucket: {analytics_bucket}")

    print("\n=== Checking S3 prefixes ===")
    prefixes = {
        "bronze": "bronze/events/",
        "silver": "silver/events_cleaned/",
        "gold": "gold/",
    }
    for name, prefix in prefixes.items():
        keys = list_prefix_sample(s3, analytics_bucket, prefix)
        if keys:
            print(f"{name.capitalize()}: FOUND sample objects (showing up to 5):")
            for k in keys:
                print(f"  - {k}")
        else:
            print(f"{name.capitalize()}: NO objects found under {prefix}")

    print("\n=== Running Athena sanity checks on gold tables ===")
    athena_output = f"s3://{analytics_bucket}/athena-results/"
    checks = {
        "conversion_funnel": f"SELECT count(*) AS cnt FROM {gold_db}.conversion_funnel",
        "hourly_revenue": f"SELECT count(*) AS cnt FROM {gold_db}.hourly_revenue",
        "top_products": f"SELECT count(*) AS cnt FROM {gold_db}.top_products",
        "category_performance": f"SELECT count(*) AS cnt FROM {gold_db}.category_performance",
        "user_activity": f"SELECT count(*) AS cnt FROM {gold_db}.user_activity",
    }

    for table, query in checks.items():
        try:
            rows = run_athena_query(
                athena,
                query=query,
                database=gold_db,
                output_s3=athena_output,
                workgroup=args.athena_workgroup,
            )
            count_val = rows[0][0] if rows else "0"
            print(f"{table}: OK (rows={count_val})")
        except Exception as e:
            print(f"{table}: FAILED ({e})")

    if args.cleanup:
        print("\n=== Cleanup (analytics outputs only) ===")
        for prefix in ["bronze/", "silver/", "gold/", "athena-results/"]:
            print(f"Deleting s3://{analytics_bucket}/{prefix} ...")
            delete_prefix(s3, analytics_bucket, prefix)
        print("Cleanup complete. Source bucket untouched.")
    else:
        print(
            "\nCleanup not requested. Use --cleanup to remove analytics outputs after verification."
        )


if __name__ == "__main__":
    main()
