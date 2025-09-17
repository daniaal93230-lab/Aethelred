import sqlite3  # Built-in library for working with SQLite
import os  # To check file existence and paths

# Define the path to the schema file
SCHEMA_PATH = os.path.join("db", "schema.sql")
DB_PATH = "trades.db"  # Name of our SQLite database file


def init_db():
    """
    This function reads the schema.sql file and executes it
    to create the 'trades' table in a new or existing SQLite database.
    """
    # Open and read schema definition (table structure)
    with open(SCHEMA_PATH, "r") as f:
        schema = f.read()

    # Connect to SQLite database file (or create it if not exists)
    conn = sqlite3.connect(DB_PATH)

    # Execute the SQL schema (CREATE TABLE IF NOT EXISTS ...)
    conn.executescript(schema)

    # Save changes and close the connection
    conn.commit()
    conn.close()


# This block ensures the function runs only when this file is executed directly
if __name__ == "__main__":
    init_db()
