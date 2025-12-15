#!/usr/bin/env python3
"""
Generate sample event data for capstone project exploration.

Creates representative files matching Lambda output format:
- Gzipped JSON Lines
- Same schema as production Lambda
- Smaller volume for local testing (1000 events per file)
- Output to local directory
"""

import json
import gzip
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random


# Product catalog
CATEGORIES = ["electronics", "clothing", "home", "books", "sports", "toys"]
PRODUCTS = {
    "electronics": ["p_1001", "p_1002", "p_1003", "p_1004", "p_1005"],
    "clothing": ["p_2001", "p_2002", "p_2003", "p_2004", "p_2005"],
    "home": ["p_3001", "p_3002", "p_3003", "p_3004", "p_3005"],
    "books": ["p_4001", "p_4002", "p_4003", "p_4004", "p_4005"],
    "sports": ["p_5001", "p_5002", "p_5003", "p_5004", "p_5005"],
    "toys": ["p_6001", "p_6002", "p_6003", "p_6004", "p_6005"],
}

SEARCH_QUERIES = [
    "wireless headphones",
    "running shoes",
    "coffee maker",
    "python books",
    "yoga mat",
    "laptop stand",
    "winter jacket",
    "desk lamp",
]


def generate_product_context():
    category = random.choice(CATEGORIES)
    product_id = random.choice(PRODUCTS[category])
    quantity = random.randint(1, 5)
    price = round(random.uniform(9.99, 299.99), 2)
    return {
        "product_id": product_id,
        "category": category,
        "quantity": quantity,
        "price": price,
    }


def generate_event(timestamp):
    user_id = f"u_{random.randint(10000, 99999)}"
    session_id = f"s_{random.randint(10000, 99999)}"
    event_type = random.choices(
        ["page_view", "add_to_cart", "remove_from_cart", "purchase", "search"],
        weights=[50, 20, 10, 10, 10],
        k=1,
    )[0]

    event = {
        "timestamp": timestamp,
        "user_id": user_id,
        "session_id": session_id,
        "event_type": event_type,
        "product_id": None,
        "quantity": None,
        "price": None,
        "category": None,
        "search_query": None,
    }

    if event_type == "search":
        event["search_query"] = random.choice(SEARCH_QUERIES)
    else:
        product_context = generate_product_context()
        event["product_id"] = product_context["product_id"]
        event["category"] = product_context["category"]
        if event_type in ["add_to_cart", "remove_from_cart", "purchase"]:
            event["quantity"] = product_context["quantity"]
            event["price"] = product_context["price"]

    return event


def generate_events(count, timestamp):
    """Generate events with given timestamp."""
    return [generate_event(timestamp) for _ in range(count)]


def generate_sample_files(
    output_dir: Path, num_files: int = 6, events_per_file: int = 1000
):
    """
    Generate sample event files.

    Args:
        output_dir: Directory to write sample files
        num_files: Number of files to generate (default 6 = 1 hour at 10-min intervals)
        events_per_file: Events per file (default 1000 for quick testing)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {num_files} sample files with {events_per_file:,} events each")
    print(f"Output directory: {output_dir}")

    # Generate files with realistic timestamps (10-minute intervals)
    base_time = datetime.now(timezone.utc) - timedelta(hours=1)

    for i in range(num_files):
        # Calculate timestamp for this file
        file_time = base_time + timedelta(minutes=10 * i)
        timestamp_str = file_time.strftime("%Y%m%d-%H%M%S")
        timestamp_iso = file_time.isoformat()

        # Generate events
        events = generate_events(events_per_file, timestamp_iso)

        # Convert to JSON Lines (with trailing newline for proper line counting)
        jsonl_content = "\n".join(json.dumps(event) for event in events) + "\n"

        # Compress
        compressed_content = gzip.compress(jsonl_content.encode("utf-8"))

        # Write file with realistic path structure
        file_path = output_dir / f"events-{timestamp_str}.jsonl.gz"
        file_path.write_bytes(compressed_content)

        print(
            f"  Created: {file_path.name} ({len(compressed_content):,} bytes, {events_per_file:,} events)"
        )

    print(f"\nSample data generation complete!")
    print(f"Total events: {num_files * events_per_file:,}")
    print(f"\nTo explore the data:")
    print(f"  1. Decompress: gunzip {output_dir}/events-*.jsonl.gz")
    print(f"  2. View: head {output_dir}/events-*.jsonl")
    print(f"  3. Count: wc -l {output_dir}/events-*.jsonl")


def main():
    parser = argparse.ArgumentParser(
        description="Generate sample event data for capstone project"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("sample-data"),
        help="Output directory for sample files (default: sample-data)",
    )
    parser.add_argument(
        "--num-files",
        type=int,
        default=6,
        help="Number of files to generate (default: 6 for 1 hour)",
    )
    parser.add_argument(
        "--events-per-file",
        type=int,
        default=1000,
        help="Events per file (default: 1000 for testing, production is 500k-750k)",
    )

    args = parser.parse_args()

    generate_sample_files(
        output_dir=args.output_dir,
        num_files=args.num_files,
        events_per_file=args.events_per_file,
    )


if __name__ == "__main__":
    main()
