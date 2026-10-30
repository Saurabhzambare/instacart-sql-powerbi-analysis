from contextlib import closing

import pyodbc

from scripts.db_connection import get_connection


CHECKS = (
    (
        "Products: required product ID",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.dim_products
        WHERE product_id IS NULL;
        """,
    ),
    (
        "Orders: required order and user IDs",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_orders
        WHERE order_id IS NULL
           OR user_id IS NULL;
        """,
    ),
    (
        "Order products: required order and product IDs",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_order_products
        WHERE order_id IS NULL
           OR product_id IS NULL;
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
                        f"Rows with missing IDs: {affected_rows:,}"
                    )

    except pyodbc.Error as error:
        print(f"ERROR | Validation could not finish: {error}")
        return 1

    if failed_checks:
        print(f"\nValidation failed: {failed_checks} check(s).")
        return 1

    print("\nAll 3 required-ID checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())