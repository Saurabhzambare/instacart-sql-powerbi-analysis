from contextlib import closing

import pyodbc

from scripts.db_connection import get_connection


CHECKS = (
    (
        "Orders: hour between 0 and 23",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_orders
        WHERE order_hour_of_day IS NULL
           OR order_hour_of_day NOT BETWEEN 0 AND 23;
        """,
    ),
    (
        "Orders: day code between 0 and 6",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_orders
        WHERE order_dow IS NULL
           OR order_dow NOT BETWEEN 0 AND 6;
        """,
    ),
    (
        "Orders: positive order number",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_orders
        WHERE order_number IS NULL
           OR order_number < 1;
        """,
    ),
    (
        "Order products: reordered flag is 0 or 1",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_order_products
        WHERE reordered IS NULL
           OR reordered NOT IN (0, 1);
        """,
    ),
    (
        "Order products: positive cart position",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_order_products
        WHERE add_to_cart_order IS NULL
           OR add_to_cart_order < 1;
        """,
    ),
    (
        "Orders: valid gap and first-order logic",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_orders
        WHERE
            (order_number = 1
             AND days_since_prior_order IS NOT NULL)
            OR
            (order_number > 1
             AND days_since_prior_order IS NULL)
            OR days_since_prior_order < 0
            OR days_since_prior_order > 30;
        """,
    ),
    (
        "Orders: positive basket size",
        """
        SELECT COUNT_BIG(*)
        FROM reporting.fact_orders
        WHERE distinct_products_in_order IS NULL
           OR distinct_products_in_order < 1;
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
                        f"Invalid rows: {affected_rows:,}"
                    )

    except pyodbc.Error as error:
        print(f"ERROR | Validation could not finish: {error}")
        return 1

    if failed_checks:
        print(f"\nValidation failed: {failed_checks} check(s).")
        return 1

    print(f"\nAll {len(CHECKS)} value checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())