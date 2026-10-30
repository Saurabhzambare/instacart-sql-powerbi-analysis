import os
from contextlib import closing

import pyodbc


def main():
    server = os.getenv("INSTACART_SQL_SERVER", "localhost")
    database = os.getenv("INSTACART_SQL_DATABASE", "InstacartAnalytics")

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    try:
        with closing(
            pyodbc.connect(connection_string, timeout=10)
        ) as connection:
            with closing(connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT
                        CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128)),
                        DB_NAME();
                """)

                row = cursor.fetchone()

                print("Connection successful.")
                print(f"Server: {row[0]}")
                print(f"Database: {row[1]}")

        print("Connection closed.")
        return 0

    except pyodbc.Error as error:
        print(f"Connection failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())