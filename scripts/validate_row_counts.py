from contextlib import closing

import pyodbc

from scripts.db_connection import get_connection


EXPECTED_COUNTS = (
    ("reporting.dim_products", 49_688),
    ("reporting.fact_orders", 3_214_874),
    ("reporting.fact_order_products", 32_434_489),
)


def main():
    failed_checks = 0

    try:
        with closing(get_connection()) as connection:
            with closing(connection.cursor()) as cursor:
                for view_name, expected in EXPECTED_COUNTS:
                    print(f"Checking {view_name}...", flush=True)

                    # View names come from our fixed list above.
                    cursor.execute(
                        f"SELECT COUNT_BIG(*) FROM {view_name};"
                    )
                    actual = cursor.fetchone()[0]

                    if actual == expected:
                        status = "PASS"
                    else:
                        status = "FAIL"
                        failed_checks += 1

                    print(
                        f"{status} | {view_name} | "
                        f"Expected: {expected:,} | Actual: {actual:,}"
                    )

    except pyodbc.Error as error:
        print(f"ERROR | Validation could not finish: {error}")
        return 1

    if failed_checks:
        print(f"\nValidation failed: {failed_checks} count mismatch(es).")
        return 1

    print("\nAll 3 row-count checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())