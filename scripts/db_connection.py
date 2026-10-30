import os

import pyodbc


def get_connection():
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

    return pyodbc.connect(connection_string, timeout=10)