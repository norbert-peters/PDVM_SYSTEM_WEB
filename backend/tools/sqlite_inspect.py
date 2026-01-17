import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a SQLite DB table schema and basic stats")
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--table", default="persondaten")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--show-types",
        action="store_true",
        help="Print column name + Python type for the first sample row",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        raise SystemExit(f"DB not found: {args.db_path}")

    con = sqlite3.connect(str(args.db_path))
    try:
        cur = con.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (args.table,)
        )
        has_table = cur.fetchone() is not None
        print(f"table_exists={has_table}")
        if not has_table:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]
            print(f"tables={tables}")
            return

        cur.execute(f"PRAGMA table_info({args.table})")
        cols = cur.fetchall()
        print(f"columns={[c[1] for c in cols]}")

        cur.execute(f"SELECT COUNT(*) FROM {args.table}")
        print(f"row_count={cur.fetchone()[0]}")

        if args.limit > 0:
            cur.execute(f"SELECT * FROM {args.table} LIMIT ?", (args.limit,))
            rows = cur.fetchall()
            print(f"sample_rows_count={len(rows)}")
            if rows:
                print(f"sample_row_first3={rows[0][:3]}")
                if args.show_types:
                    col_names = [c[1] for c in cols]
                    first = rows[0]
                    preview = []
                    for name, value in zip(col_names, first):
                        preview.append((name, type(value).__name__, value))
                    print(f"sample_row_typed={preview}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
