"""One-time UUID-to-integer migration, run only with application writers stopped."""

from sqlalchemy import Column, Enum, ForeignKey, Integer, MetaData, Table, inspect, select
from sqlalchemy.engine import Engine

from app import db


TABLE_NAMES = ("TaiKhoan", "NhanVien", "BenhNhan", "BacSi")
ID_COLUMNS = {"TaiKhoan": "MaTK", "NhanVien": "MaNV", "BenhNhan": "MaBN", "BacSi": "MaNV"}
STAGE = "_integer_stage"
BACKUP = "_uuid_backup"


def migrate_account_ids(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    if not set(TABLE_NAMES).issubset(names):
        raise ValueError("All four existing account/profile tables are required.")
    integer_tables = {
        name for name in TABLE_NAMES
        if any(c["name"] == ID_COLUMNS[name] and isinstance(c["type"], Integer)
               for c in inspector.get_columns(name))
    }
    if integer_tables == set(TABLE_NAMES):
        return False
    if integer_tables:
        raise ValueError("Mixed identifier schema detected; manual inspection required.")
    if any(name + suffix in names for name in TABLE_NAMES for suffix in (STAGE, BACKUP)):
        raise ValueError("Migration staging/backup tables already exist; inspect before retrying.")
    for name in names - set(TABLE_NAMES):
        if any(fk["referred_table"] in TABLE_NAMES for fk in inspector.get_foreign_keys(name)):
            raise ValueError("Other tables reference account/profile IDs; extend the migration first.")

    original = MetaData()
    original.reflect(engine, only=TABLE_NAMES)
    for name in TABLE_NAMES:
        if set(original.tables[name].columns.keys()) != set(db.metadata.tables[name].columns.keys()):
            raise ValueError(f"Unexpected columns in {name}; refusing to discard data.")

    staging = MetaData()
    for name in TABLE_NAMES:
        model_table = db.metadata.tables[name]
        columns = []
        for column in model_table.columns:
            foreign_keys = [
                ForeignKey(f"{fk.column.table.name}{STAGE}.{fk.column.name}")
                for fk in column.foreign_keys
            ]
            column_type = column.type.copy()
            if isinstance(column_type, Enum) and column_type.name:
                column_type.name += STAGE
            columns.append(Column(
                column.name, column_type, *foreign_keys, primary_key=column.primary_key,
                nullable=column.nullable, unique=column.unique, autoincrement=column.autoincrement,
            ))
        Table(
            name + STAGE, staging, *columns,
            sqlite_autoincrement=model_table.dialect_options["sqlite"].get("autoincrement", False),
        )

    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        source = {
            name: [dict(row) for row in connection.execute(
                select(original.tables[name]).order_by(original.tables[name].c[ID_COLUMNS[name]])
            ).mappings()]
            for name in TABLE_NAMES
        }
        account_ids = {row["MaTK"]: i for i, row in enumerate(source["TaiKhoan"], 1)}
        employee_ids = {row["MaNV"]: i for i, row in enumerate(source["NhanVien"], 1)}
        converted = {}
        for name in TABLE_NAMES:
            rows = []
            for i, row in enumerate(source[name], 1):
                new_row = row.copy()
                if name == "TaiKhoan":
                    new_row["MaTK"] = account_ids[row["MaTK"]]
                elif name == "BacSi":
                    new_row["MaNV"] = employee_ids[row["MaNV"]]
                else:
                    new_row[ID_COLUMNS[name]] = i
                    new_row["MaTK"] = account_ids[row["MaTK"]]
                rows.append(new_row)
            converted[name] = rows

        staging.create_all(connection)
        for name in TABLE_NAMES:
            table = staging.tables[name + STAGE]
            rows = converted[name]
            if rows:
                connection.execute(table.insert(), rows)
            actual = [dict(row) for row in connection.execute(
                select(table).order_by(table.c[ID_COLUMNS[name]])
            ).mappings()]
            if actual != sorted(rows, key=lambda row: row[ID_COLUMNS[name]]):
                raise ValueError(f"Copied rows do not match in {name}; original tables unchanged.")

        for name in TABLE_NAMES:
            current = [dict(row) for row in connection.execute(
                select(original.tables[name]).order_by(original.tables[name].c[ID_COLUMNS[name]])
            ).mappings()]
            if current != source[name]:
                raise ValueError("Source changed during migration; stop all writers before retrying.")

        quote = connection.dialect.identifier_preparer.quote
        if engine.dialect.name == "mysql":
            pairs = []
            for name in TABLE_NAMES:
                pairs.extend((
                    f"{quote(name)} TO {quote(name + BACKUP)}",
                    f"{quote(name + STAGE)} TO {quote(name)}",
                ))
            connection.exec_driver_sql("RENAME TABLE " + ", ".join(pairs))
        else:
            for name in TABLE_NAMES:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote(name)} RENAME TO {quote(name + BACKUP)}"
                )
            for name in TABLE_NAMES:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote(name + STAGE)} RENAME TO {quote(name)}"
                )
    return True
