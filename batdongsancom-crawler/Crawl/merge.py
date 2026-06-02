"""
Step 3: Merge all worker tmp CSV files into a single deduplicated CSV file.

Works with both listing URL and listing detail tmp files.

Usage:
    python merge.py                                       # merge listing_details tmp files
    python merge.py --output ../listing_details.csv       # explicit output
    python merge.py --output ../listing_url.csv           # merge listing URL tmp files
    python merge.py --keep-tmp                            # don't delete tmp files after merge
"""

import argparse
import csv
import glob
import os
import sys


def merge_tmp_files(output: str, keep_tmp: bool = False) -> int:
    """
    Read all matching worker tmp CSVs, deduplicate by product_id,
    and write the final merged output.

    Parameters
    ----------
    output : str
        Path to the output CSV file (e.g. "listing_details.csv").
    keep_tmp : bool
        If True, keep the tmp files after merging instead of deleting them.

    Returns
    -------
    int
        Number of unique rows written.
    """
    # Resolve paths: absolute paths used as-is, relative resolved from script dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = output if os.path.isabs(output) else os.path.normpath(os.path.join(script_dir, output))
    pattern = f"{output_path}.worker*.tmp"

    tmp_files = sorted(glob.glob(pattern))
    if not tmp_files:
        print(f"[WARN] No tmp files found matching: {pattern}")
        return 0

    print(f"Found {len(tmp_files)} tmp file(s):")
    for f in tmp_files:
        size_kb = os.path.getsize(f) / 1024
        print(f"  - {os.path.basename(f)}  ({size_kb:.1f} KB)")

    # --- Read existing output (for resume support) ---
    all_rows: list[dict] = []
    fieldnames: list[str] | None = None

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        with open(output_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            existing = list(reader)
            print(f"  Existing output: {len(existing)} rows")
            all_rows.extend(existing)

    # --- Read all tmp files ---
    for tmp in tmp_files:
        with open(tmp, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            rows = list(reader)
            print(f"  {os.path.basename(tmp)}: {len(rows)} rows")
            all_rows.extend(rows)

    if not all_rows or fieldnames is None:
        print("[WARN] All files are empty.")
        return 0

    # --- Deduplicate by product_id (keep first occurrence) ---
    seen: set[str] = set()
    deduped: list[dict] = []
    duplicates = 0

    for row in all_rows:
        pid = row.get("product_id", "")
        if pid and pid not in seen:
            seen.add(pid)
            deduped.append(row)
        else:
            duplicates += 1

    # --- Write merged CSV ---
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped)

    print(f"\nMerge complete!")
    print(f"  Total rows read : {len(all_rows)}")
    print(f"  Duplicates       : {duplicates}")
    print(f"  Unique rows      : {len(deduped)}")
    print(f"  Output           : {output_path}")

    # --- Clean up tmp files ---
    if not keep_tmp:
        for tmp in tmp_files:
            os.remove(tmp)
            print(f"  Removed {os.path.basename(tmp)}")
    else:
        print("  (tmp files kept)")

    return len(deduped)


def main():
    parser = argparse.ArgumentParser(
        description="Step 3: Merge worker tmp CSV files into a single deduplicated CSV."
    )
    parser.add_argument(
        "--output", default="../listing_details.csv",
        help="Output CSV filename (default: ../listing_details.csv)",
    )
    parser.add_argument(
        "--keep-tmp", action="store_true",
        help="Keep tmp files after merging instead of deleting them",
    )
    args = parser.parse_args()

    count = merge_tmp_files(args.output, args.keep_tmp)
    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
