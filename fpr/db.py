import contextlib
import json
import sqlite3
from typing import Iterator


@contextlib.contextmanager
def connect(db_file: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_file)
    try:
        yield conn
    finally:
        conn.close()


def create_crates_io_meta_table(cursor: sqlite3.Cursor):
    cursor.execute("DROP TABLE IF EXISTS crates_io_metadata")
    cursor.execute(
        "CREATE TABLE crates_io_metadata(id INTEGER PRIMARY KEY AUTOINCREMENT, crate_meta JSON NOT NULL)"
    )


def crate_name_in_db(cursor: sqlite3.Cursor, crate_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM crates_io_metadata WHERE json_extract(crate_meta, '$.crate.name') = ? LIMIT 1",
        (crate_name,),
    )
    return cursor.fetchone() is not None


def save_crate_meta(cursor: sqlite3.Cursor, json_str: str):
    cursor.execute(
        "INSERT INTO crates_io_metadata(crate_meta) VALUES (?)", (json.dumps(json_str),)
    )
