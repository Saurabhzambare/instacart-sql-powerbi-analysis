from contextlib import closing

import pyodbc

from scripts.db_connection import get_connection


CHECKS = (
    (
        "Products: unique product ID",
        """
        SELECT COUNT_BIG(*)
        FROM (
            SELECT product_id
            FROM reporting.dim_products
            GROUP BY product_id
            HAVING COUNT_BIG(*) > 1
        ) AS duplicate_keys;
        """,
    ),
    (
        "Orders: unique order ID",
        """
        SELECT COUNT_BIG(*)
        FROM (
            SELECT order_id
            FROM reporting.fact_orders
            GROUP BY order_id
            HAVING COUNT_BIG(*) > 1
        ) AS duplicate_keys;
        """,
    ),
    (
        "Order products: unique order-product pair",
        """
        SELECT COUNT_BIG(*)
        FROM (
            SELECT order_id, product_id
            FROM reporting.fact_order_products
            GROUP BY order_id, product_id
            HAVING COUNT_BIG(*) > 1
        ) AS duplicate_keys;
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
                        f"Duplicate key groups: {affected_rows:,}"
                    )

    except pyodbc.Error as error:
        print(f"ERROR | Validation could not finish: {error}")
        return 1

    if failed_checks:
        print(f"\nValidation failed: {failed_checks} check(s).")
        return 1

    print("\nAll 3 uniqueness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())