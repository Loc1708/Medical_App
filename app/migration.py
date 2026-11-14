"""One-time UUID-to-integer migration, run only with application writers stopped."""

from sqlalchemy import (
    Column, Enum, ForeignKey, Integer, MetaData, Table, inspect, select, text,
)
from sqlalchemy.engine import Engine

from app import db


TABLE_NAMES = ("TaiKhoan", "NhanVien", "BenhNhan", "BacSi")
ID_COLUMNS = {"TaiKhoan": "MaTK", "NhanVien": "MaNV", "BenhNhan": "MaBN", "BacSi": "MaNV"}
STAGE = "_integer_stage"
BACKUP = "_uuid_backup"
NURSE_SLOT_INDEX = "uq_dskham_ngay_thu_tu"
NURSE_DAY_INDEX = "ix_dskham_ngay_trang_thai"


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


def _make_sqlite_patient_account_optional(connection) -> bool:
    columns = {column["name"]: column for column in inspect(connection).get_columns("BenhNhan")}
    if "MaTK" not in columns:
        raise ValueError("Unexpected BenhNhan schema; inspect it before retrying.")
    if columns["MaTK"]["nullable"]:
        return False
    expected = {"MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "SoDienThoai", "MaTK"}
    if set(columns) != expected:
        raise ValueError("BenhNhan has unexpected columns; inspect it before retrying.")

    connection.exec_driver_sql(
        'CREATE TABLE "BenhNhan_nurse_tmp" ('
        '"MaBN" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
        '"HoTen" VARCHAR(100) NOT NULL, '
        '"GioiTinh" VARCHAR(10) NOT NULL, '
        '"NamSinh" INTEGER NOT NULL, '
        '"DiaChi" VARCHAR(255) NOT NULL, '
        '"SoDienThoai" VARCHAR(20) NOT NULL, '
        '"MaTK" INTEGER, '
        'FOREIGN KEY ("MaTK") REFERENCES "TaiKhoan" ("MaTK"), '
        'UNIQUE ("MaTK"))'
    )
    connection.exec_driver_sql(
        'INSERT INTO "BenhNhan_nurse_tmp" '
        '("MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "SoDienThoai", "MaTK") '
        'SELECT "MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "SoDienThoai", "MaTK" '
        'FROM "BenhNhan"'
    )
    connection.exec_driver_sql('DROP TABLE "BenhNhan"')
    connection.exec_driver_sql(
        'ALTER TABLE "BenhNhan_nurse_tmp" RENAME TO "BenhNhan"'
    )
    return True


def _upgrade_nurse_schema(connection, engine: Engine) -> bool:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required = {"TaiKhoan", "BenhNhan", "DanhSachKham", "QuyDinh"}
    missing = required - tables
    if missing:
        raise ValueError(
            "Required tables are missing; run init-db first: " + ", ".join(sorted(missing))
        )

    changed = False
    if engine.dialect.name == "sqlite":
        changed |= _make_sqlite_patient_account_optional(connection)
    else:
        patient_columns = {
            column["name"]: column
            for column in inspector.get_columns("BenhNhan")
        }
        account_column = patient_columns.get("MaTK")
        if account_column is None:
            raise ValueError("BenhNhan.MaTK is missing; inspect the schema before retrying.")
        if not account_column["nullable"]:
            quote = engine.dialect.identifier_preparer.quote
            column_type = str(account_column["type"])
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('BenhNhan')} MODIFY COLUMN "
                f"{quote('MaTK')} {column_type} NULL"
            )
            changed = True

    registration_columns = {
        column["name"] for column in inspect(connection).get_columns("DanhSachKham")
    }
    quote = engine.dialect.identifier_preparer.quote
    if "NgayKham" not in registration_columns:
        connection.exec_driver_sql(
            f"ALTER TABLE {quote('DanhSachKham')} ADD COLUMN {quote('NgayKham')} DATE NULL"
        )
        changed = True
    if "SoThuTu" not in registration_columns:
        connection.exec_driver_sql(
            f"ALTER TABLE {quote('DanhSachKham')} ADD COLUMN {quote('SoThuTu')} INTEGER NULL"
        )
        changed = True

    connection.execute(text(
        f"UPDATE {quote('DanhSachKham')} SET {quote('NgayKham')} = "
        f"DATE({quote('NgayDangKy')}) WHERE {quote('NgayKham')} IS NULL"
    ))
    unresolved_dates = connection.execute(text(
        f"SELECT COUNT(*) FROM {quote('DanhSachKham')} "
        f"WHERE {quote('NgayKham')} IS NULL"
    )).scalar_one()
    if unresolved_dates:
        raise ValueError("Some registrations have no valid registration date; inspect them first.")

    rows = connection.execute(text(
        f"SELECT {quote('MaDSKham')}, {quote('NgayKham')}, {quote('SoThuTu')}, "
        f"{quote('TrangThai')} FROM {quote('DanhSachKham')} ORDER BY "
        f"{quote('NgayKham')}, {quote('NgayDangKy')}, {quote('MaDSKham')}"
    )).mappings().all()
    used_slots: dict[object, set[int]] = {}
    for row in rows:
        exam_date = row["NgayKham"]
        day_slots = used_slots.setdefault(exam_date, set())
        slot = row["SoThuTu"]
        if row["TrangThai"] not in {"CHO_KHAM", "DA_XAC_NHAN"}:
            if slot is not None:
                connection.execute(
                    text(
                        f"UPDATE {quote('DanhSachKham')} SET {quote('SoThuTu')} = NULL "
                        f"WHERE {quote('MaDSKham')} = :id"
                    ),
                    {"id": row["MaDSKham"]},
                )
                changed = True
            continue
        if slot is None or slot in day_slots:
            slot = 1
            while slot in day_slots:
                slot += 1
            connection.execute(
                text(
                    f"UPDATE {quote('DanhSachKham')} SET {quote('SoThuTu')} = :slot "
                    f"WHERE {quote('MaDSKham')} = :id"
                ),
                {"slot": slot, "id": row["MaDSKham"]},
            )
            changed = True
        day_slots.add(slot)

    if engine.dialect.name in {"mysql", "mariadb"}:
        day_column = next(
            column for column in inspect(connection).get_columns("DanhSachKham")
            if column["name"] == "NgayKham"
        )
        if day_column["nullable"]:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('DanhSachKham')} MODIFY COLUMN "
                f"{quote('NgayKham')} DATE NOT NULL"
            )
            changed = True

    indexes = {
        index["name"]: index for index in inspect(connection).get_indexes("DanhSachKham")
    }
    if NURSE_SLOT_INDEX not in indexes:
        connection.exec_driver_sql(
            f"CREATE UNIQUE INDEX {quote(NURSE_SLOT_INDEX)} "
            f"ON {quote('DanhSachKham')} ({quote('NgayKham')}, {quote('SoThuTu')})"
        )
        changed = True
    elif not indexes[NURSE_SLOT_INDEX]["unique"]:
        raise ValueError("The nurse slot index exists but is not unique; inspect it first.")
    if NURSE_DAY_INDEX not in indexes:
        connection.exec_driver_sql(
            f"CREATE INDEX {quote(NURSE_DAY_INDEX)} "
            f"ON {quote('DanhSachKham')} ({quote('NgayKham')}, {quote('TrangThai')})"
        )
        changed = True

    if connection.execute(
        text(f"SELECT 1 FROM {quote('QuyDinh')} WHERE {quote('MaQD')} = :code"),
        {"code": "SO_BENH_NHAN_TOI_DA"},
    ).first() is None:
        connection.execute(
            text(
                f"INSERT INTO {quote('QuyDinh')} "
                f"({quote('MaQD')}, {quote('TenQuyDinh')}, {quote('GiaTri')}) "
                "VALUES (:code, :name, :value)"
            ),
            {
                "code": "SO_BENH_NHAN_TOI_DA",
                "name": "Số bệnh nhân tối đa trong ngày",
                "value": 40,
            },
        )
        changed = True
    return changed


def upgrade_nurse_queue_schema(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "mariadb", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")
    if engine.dialect.name != "sqlite":
        with engine.begin() as connection:
            return _upgrade_nurse_schema(connection, engine)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                changed = _upgrade_nurse_schema(connection, engine)
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            raise ValueError("Foreign-key violations found after migration; inspect the database.")
        return changed
