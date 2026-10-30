from contextlib import closing

import pyodbc

from scripts.db_connection import get_connection


CHECKS = (
    (
        "Order products: matching product",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_order_products AS op
        LEFT JOIN reporting.dim_products AS p
            ON op.product_id = p.product_id
        WHERE p.product_id IS NULL;
        """,
    ),
    (
        "Order products: matching order",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_order_products AS op
        LEFT JOIN reporting.fact_orders AS o
            ON op.order_id = o.order_id
        WHERE o.order_id IS NULL;
        """,
    ),
)


def main():
    failed_checks = 0

    try:
        with closing(get_connection()) as connection:
            with closing(connection.cursor()) as cursor:
                for check_name, query in CHECKS:
                    print(f"Checking {check_name}...", flush=True)

                    cursor.execute(query)
                    affected_rows = cursor.fetchone()[0]

                    if affected_rows == 0:
                        status = "PASS"
                    else:
                        status = "FAIL"
                        failed_checks += 1

                    print(
                        f"{status} | {check_name} | "
                        f"Unmatched entries: {affected_rows:,}"
                    )

    except pyodbc.Error as error:
        print(f"ERROR | Validation could not finish: {error}")
        return 1

    if failed_checks:
        print(f"\nValidation failed: {failed_checks} check(s).")
        return 1

    print("\nAll 2 relationship checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())