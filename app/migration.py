"""One-time UUID-to-integer migration, run only with application writers stopped."""

from sqlalchemy import (
    Column, Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index,
    Integer, MetaData, String, Table, UniqueConstraint, inspect, select, text,
)
from sqlalchemy.engine import Engine

from app import db


TABLE_NAMES = ("TaiKhoan", "NhanVien", "BenhNhan", "BacSi")
ID_COLUMNS = {"TaiKhoan": "MaTK", "NhanVien": "MaNV", "BenhNhan": "MaBN", "BacSi": "MaNV"}
STAGE = "_integer_stage"
BACKUP = "_uuid_backup"
NURSE_SLOT_INDEX = "uq_dskham_ngay_thu_tu"
NURSE_DAY_INDEX = "ix_dskham_ngay_trang_thai"
NURSE_DETAIL_PROFILE_COLUMNS = ("HoTen", "GioiTinh", "NamSinh", "DiaChi")
NURSE_DETAIL_REQUIRED_COLUMNS = {
    "MaDSKham", "MaBN", "NgayKham",
    "SoThuTu", "NgayDangKy", "TrangThai",
}
DON_VI_THUOC_CU = {"gói", "đơn vị kiểm thử"}


def chuyenDonViThuocVeBaLoai(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "mariadb", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")
    if not {"DonViThuoc", "Thuoc"}.issubset(inspect(engine).get_table_names()):
        raise ValueError("DonViThuoc and Thuoc are required; run init-db first.")

    don_vi_chuan = (
        ("SAMPLE-VIEN", "Viên"),
        ("SAMPLE-CHAI", "Chai"),
        ("SAMPLE-VI", "Vỉ"),
    )
    with engine.begin() as connection:
        don_vis = connection.execute(
            text("SELECT MaDonVi, tenDonVi FROM DonViThuoc ORDER BY MaDonVi")
        ).mappings().all()
        ten_hop_le = {ten.casefold() for _, ten in don_vi_chuan}
        ten_cu = {row["tenDonVi"].strip().casefold() for row in don_vis}
        ten_khong_ro = ten_cu - ten_hop_le - DON_VI_THUOC_CU
        if ten_khong_ro:
            raise ValueError(
                "Unmapped existing medicine unit(s): "
                + ", ".join(sorted(ten_khong_ro))
                + ". Add an explicit mapping before retrying."
            )

        don_vis_theo_ten = {}
        for don_vi in don_vis:
            don_vis_theo_ten.setdefault(don_vi["tenDonVi"].strip().casefold(), []).append(
                don_vi["MaDonVi"]
            )

        ma_dich = {}
        ma_dang_dung = {row["MaDonVi"] for row in don_vis}
        da_thay_doi = False
        for ma_mac_dinh, ten_chuan in don_vi_chuan:
            ten_khoa = ten_chuan.casefold()
            ma_cac_dong = don_vis_theo_ten.get(ten_khoa, [])
            if ma_cac_dong:
                ma_dich[ten_khoa] = ma_cac_dong[0]
            else:
                ma_moi = ma_mac_dinh
                hau_to = 1
                while ma_moi in ma_dang_dung:
                    ma_moi = f"{ma_mac_dinh}-{hau_to}"
                    hau_to += 1
                connection.execute(
                    text(
                        "INSERT INTO DonViThuoc (MaDonVi, tenDonVi) "
                        "VALUES (:ma, :ten)"
                    ),
                    {"ma": ma_moi, "ten": ten_chuan},
                )
                ma_dang_dung.add(ma_moi)
                ma_dich[ten_khoa] = ma_moi
                da_thay_doi = True

        ma_vien = ma_dich["viên"]
        for don_vi in don_vis:
            ma_cu = don_vi["MaDonVi"]
            ten_cu = don_vi["tenDonVi"].strip().casefold()
            ma_moi = ma_dich.get(ten_cu, ma_vien)
            ten_chuan = next(
                (ten for _, ten in don_vi_chuan if ten.casefold() == ten_cu), None
            )
            if ma_cu != ma_moi:
                connection.execute(
                    text("UPDATE Thuoc SET MaDonVi = :ma_moi WHERE MaDonVi = :ma_cu"),
                    {"ma_moi": ma_moi, "ma_cu": ma_cu},
                )
                connection.execute(
                    text("DELETE FROM DonViThuoc WHERE MaDonVi = :ma_cu"),
                    {"ma_cu": ma_cu},
                )
                da_thay_doi = True
            elif ten_chuan is not None and don_vi["tenDonVi"] != ten_chuan:
                connection.execute(
                    text("UPDATE DonViThuoc SET tenDonVi = :ten WHERE MaDonVi = :ma"),
                    {"ten": ten_chuan, "ma": ma_cu},
                )
                da_thay_doi = True

        return da_thay_doi


def xoaCotHoSoTrung(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "mariadb", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")
    if "ChiTietDanhSachKham" not in inspect(engine).get_table_names():
        raise ValueError("ChiTietDanhSachKham is missing; run init-db first.")

    def xoaCacCot(connection) -> bool:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("ChiTietDanhSachKham")
        }
        missing = NURSE_DETAIL_REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                "ChiTietDanhSachKham has an incomplete schema; inspect before retrying."
            )
        quote = connection.dialect.identifier_preparer.quote
        changed = False
        for column in NURSE_DETAIL_PROFILE_COLUMNS:
            if column in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('ChiTietDanhSachKham')} "
                    f"DROP COLUMN {quote(column)}"
                )
                changed = True
        return changed

    if engine.dialect.name != "sqlite":
        with engine.begin() as connection:
            return xoaCacCot(connection)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                changed = xoaCacCot(connection)
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            raise ValueError(
                "Foreign-key violations found after migration; inspect the database."
            )
        return changed


def chuyenMaTaiKhoan(engine: Engine) -> bool:
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


def _choPhepBenhNhanKhongCoTaiKhoanSqlite(connection) -> bool:
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


def _nangCapCauTrucYTa(connection, engine: Engine) -> bool:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required = {"TaiKhoan", "BenhNhan", "DanhSachKham", "QuyDinh"}
    missing = required - tables
    if missing:
        raise ValueError(
            "Required tables are missing; run init-db first: " + ", ".join(sorted(missing))
        )
    if "ChiTietDanhSachKham" in tables:
        detail_columns = {
            column["name"]
            for column in inspector.get_columns("ChiTietDanhSachKham")
        }
        day_columns = {
            column["name"] for column in inspector.get_columns("DanhSachKham")
        }
        detail_primary_key = inspector.get_pk_constraint(
            "ChiTietDanhSachKham"
        ).get("constrained_columns")
        has_registration_identity = (
            detail_primary_key == ["MaDSKham", "MaBN"]
            or (
                detail_primary_key == ["MaCTDSKham"]
                and "MaCTDSKham" in detail_columns
            )
        )
        if (
            {"MaDSKham", "MaBN", "NgayKham", "SoThuTu", "TrangThai"}
            <= detail_columns
            and has_registration_identity
            and {"MaDSKham", "NgayKham", "MaNV"} <= day_columns
        ):
            return False
        raise ValueError(
            "ChiTietDanhSachKham exists with an incomplete schema; inspect before retrying."
        )

    changed = False
    if engine.dialect.name == "sqlite":
        changed |= _choPhepBenhNhanKhongCoTaiKhoanSqlite(connection)
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


def nangCapCauTrucHangCho(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "mariadb", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")
    if engine.dialect.name != "sqlite":
        with engine.begin() as connection:
            return _nangCapCauTrucYTa(connection, engine)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                changed = _nangCapCauTrucYTa(connection, engine)
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            raise ValueError("Foreign-key violations found after migration; inspect the database.")
        return changed


def nangCapCauTrucDanhSachKham(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "mariadb", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")

    tables = set(inspect(engine).get_table_names())
    if "DanhSachKham" not in tables or "BenhNhan" not in tables or "NhanVien" not in tables:
        raise ValueError(
            "DanhSachKham, BenhNhan, and NhanVien are required; run init-db first."
        )
    if "ChiTietDanhSachKham" in tables:
        day_columns = {
            column["name"] for column in inspect(engine).get_columns("DanhSachKham")
        }
        detail_columns = {
            column["name"]
            for column in inspect(engine).get_columns("ChiTietDanhSachKham")
        }
        detail_primary_key = inspect(engine).get_pk_constraint(
            "ChiTietDanhSachKham"
        ).get("constrained_columns")
        has_registration_identity = (
            detail_primary_key == ["MaDSKham", "MaBN"]
            or (
                detail_primary_key == ["MaCTDSKham"]
                and "MaCTDSKham" in detail_columns
            )
        )
        if (
            {"MaDSKham", "NgayKham", "MaNV"} <= day_columns
            and {
                "MaDSKham", "MaBN", "NgayKham",
                "SoThuTu", "NgayDangKy", "TrangThai",
            } <= detail_columns
            and has_registration_identity
        ):
            return False
        raise ValueError(
            "ChiTietDanhSachKham exists with an incomplete schema; inspect before retrying."
        )

    stage_day_name = "_DanhSachKham_m2m"
    stage_detail_name = "_ChiTietDanhSachKham_m2m"
    backup_name = "DanhSachKham_legacy"
    if {stage_day_name, stage_detail_name, backup_name} & tables:
        raise ValueError(
            "Migration staging or backup tables already exist; inspect before retrying."
        )

    day_columns = {
        column["name"] for column in inspect(engine).get_columns("DanhSachKham")
    }
    if "MaBN" not in day_columns:
        raise ValueError(
            "DanhSachKham does not match the legacy registration schema; inspect it first."
        )

    nangCapCauTrucHangCho(engine)
    source_metadata = MetaData()
    source_day = Table("DanhSachKham", source_metadata, autoload_with=engine)
    expected_source_columns = {
        "MaDSKham", "MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi",
        "NgayKham", "SoThuTu", "NgayDangKy", "TrangThai",
    }
    if not expected_source_columns <= set(source_day.columns.keys()):
        raise ValueError(
            "DanhSachKham has unexpected columns; inspect it before migration."
        )

    staging_metadata = MetaData()
    Table("NhanVien", staging_metadata, autoload_with=engine)
    Table("BenhNhan", staging_metadata, autoload_with=engine)
    staged_day = Table(
        stage_day_name,
        staging_metadata,
        Column("MaDSKham", Integer, primary_key=True, autoincrement=True),
        Column("NgayKham", Date, nullable=False),
        Column("MaNV", Integer, ForeignKey("NhanVien.MaNV"), nullable=True),
        UniqueConstraint("NgayKham", name="uq_dskham_ngay"),
        UniqueConstraint("MaDSKham", "NgayKham", name="uq_dskham_id_ngay"),
        sqlite_autoincrement=True,
    )
    staged_detail = Table(
        stage_detail_name,
        staging_metadata,
        Column("MaDSKham", Integer, primary_key=True),
        Column("MaBN", Integer, ForeignKey("BenhNhan.MaBN"), primary_key=True),
        Column("NgayKham", Date, nullable=False),
        Column("SoThuTu", Integer, nullable=True),
        Column("NgayDangKy", DateTime, nullable=False),
        Column("TrangThai", String(20), nullable=False),
        ForeignKeyConstraint(
            ["MaDSKham", "NgayKham"],
            [f"{stage_day_name}.MaDSKham", f"{stage_day_name}.NgayKham"],
            name="fk_ctdsk_list_date",
        ),
        Index("uq_ctdsk_ngay_thu_tu", "NgayKham", "SoThuTu", unique=True),
        Index("ix_ctdsk_ngay_trang_thai", "NgayKham", "TrangThai"),
        sqlite_autoincrement=True,
    )

    def saoChepVaThayBang(connection) -> None:
        source_rows = connection.execute(
            select(source_day).order_by(source_day.c.NgayKham, source_day.c.MaDSKham)
        ).mappings().all()
        dates = sorted({row["NgayKham"] for row in source_rows})
        day_ids = {exam_date: index for index, exam_date in enumerate(dates, 1)}
        day_rows = [
            {"MaDSKham": day_ids[exam_date], "NgayKham": exam_date, "MaNV": None}
            for exam_date in dates
        ]
        detail_rows_by_pair = {}
        for row in source_rows:
            pair = (day_ids[row["NgayKham"]], row["MaBN"])
            detail_rows_by_pair[pair] = {
                "MaDSKham": pair[0],
                "MaBN": pair[1],
                "NgayKham": row["NgayKham"],
                "SoThuTu": row["SoThuTu"],
                "NgayDangKy": row["NgayDangKy"],
                "TrangThai": row["TrangThai"],
            }
        detail_rows = list(detail_rows_by_pair.values())

        staging_metadata.create_all(connection)
        if day_rows:
            connection.execute(staged_day.insert(), day_rows)
        if detail_rows:
            connection.execute(staged_detail.insert(), detail_rows)

        copied_rows = connection.execute(
            select(
                staged_detail.c.MaDSKham,
                staged_detail.c.MaBN,
                staged_detail.c.NgayKham,
                staged_detail.c.SoThuTu,
                staged_detail.c.NgayDangKy,
                staged_detail.c.TrangThai,
            ).order_by(staged_detail.c.MaDSKham, staged_detail.c.MaBN)
        ).all()
        expected_rows = [
            (
                row["MaDSKham"], row["MaBN"], row["NgayKham"],
                row["SoThuTu"], row["NgayDangKy"], row["TrangThai"],
            )
            for row in sorted(
                detail_rows,
                key=lambda item: (item["MaDSKham"], item["MaBN"]),
            )
        ]
        if copied_rows != expected_rows:
            raise ValueError(
                "Migrated registration rows do not match the source; original table retained."
            )

        quote = connection.dialect.identifier_preparer.quote
        if engine.dialect.name in {"mysql", "mariadb"}:
            connection.exec_driver_sql(
                "RENAME TABLE "
                f"{quote('DanhSachKham')} TO {quote(backup_name)}, "
                f"{quote(stage_day_name)} TO {quote('DanhSachKham')}, "
                f"{quote(stage_detail_name)} TO {quote('ChiTietDanhSachKham')}"
            )
        else:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('DanhSachKham')} RENAME TO {quote(backup_name)}"
            )
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(stage_day_name)} RENAME TO {quote('DanhSachKham')}"
            )
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(stage_detail_name)} "
                f"RENAME TO {quote('ChiTietDanhSachKham')}"
            )

    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    saoChepVaThayBang(connection)
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if violations:
                raise ValueError(
                    "Foreign-key violations found after migration; inspect the database."
                )
    else:
        with engine.begin() as connection:
            saoChepVaThayBang(connection)
    return True


def chuyenChiTietDanhSachKhamSangKhoaGhep(engine: Engine) -> bool:
    if engine.dialect.name not in {"mysql", "mariadb", "sqlite"}:
        raise ValueError("This migration supports MySQL/TiDB and SQLite only.")

    table_name = "ChiTietDanhSachKham"
    stage_name = "_ChiTietDanhSachKham_composite"
    backup_name = "ChiTietDanhSachKham_legacy"
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise ValueError("ChiTietDanhSachKham is missing; run init-db first.")

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns")
    if primary_key == ["MaDSKham", "MaBN"] and "MaCTDSKham" not in columns:
        return False
    required = {
        "MaCTDSKham", "MaDSKham", "MaBN", "NgayKham",
        "SoThuTu", "NgayDangKy", "TrangThai",
    }
    if primary_key != ["MaCTDSKham"] or not required <= columns:
        raise ValueError(
            "ChiTietDanhSachKham has an unexpected schema; inspect it before migration."
        )
    existing_tables = set(inspector.get_table_names())
    if {stage_name, backup_name} & existing_tables:
        raise ValueError(
            "Migration staging or backup table already exists; inspect before retrying."
        )

    source_metadata = MetaData()
    source = Table(table_name, source_metadata, autoload_with=engine)
    staging_metadata = MetaData()
    Table("DanhSachKham", staging_metadata, autoload_with=engine)
    Table("BenhNhan", staging_metadata, autoload_with=engine)
    staged = Table(
        stage_name,
        staging_metadata,
        Column("MaDSKham", Integer, primary_key=True),
        Column("MaBN", Integer, ForeignKey("BenhNhan.MaBN"), primary_key=True),
        Column("NgayKham", Date, nullable=False),
        Column("SoThuTu", Integer, nullable=True),
        Column("NgayDangKy", DateTime, nullable=False),
        Column("TrangThai", String(20), nullable=False),
        ForeignKeyConstraint(
            ["MaDSKham", "NgayKham"],
            ["DanhSachKham.MaDSKham", "DanhSachKham.NgayKham"],
            name="fk_ctdsk_list_date",
        ),
    )

    def saoChepVaThayBang(connection) -> None:
        source_rows = connection.execute(
            select(source).order_by(source.c.MaCTDSKham)
        ).mappings().all()
        latest_by_pair = {}
        for row in source_rows:
            pair = (row["MaDSKham"], row["MaBN"])
            latest_by_pair[pair] = {
                "MaDSKham": row["MaDSKham"],
                "MaBN": row["MaBN"],
                "NgayKham": row["NgayKham"],
                "SoThuTu": row["SoThuTu"],
                "NgayDangKy": row["NgayDangKy"],
                "TrangThai": row["TrangThai"],
            }
        copied = sorted(
            latest_by_pair.values(),
            key=lambda row: (row["MaDSKham"], row["MaBN"]),
        )

        staged.create(connection)
        if copied:
            connection.execute(staged.insert(), copied)
        staged_rows = connection.execute(
            select(staged).order_by(staged.c.MaDSKham, staged.c.MaBN)
        ).all()
        expected_rows = [
            (
                row["MaDSKham"], row["MaBN"], row["NgayKham"],
                row["SoThuTu"], row["NgayDangKy"], row["TrangThai"],
            )
            for row in copied
        ]
        if staged_rows != expected_rows:
            raise ValueError(
                "Composite-key migration verification failed; original table retained."
            )

        quote = connection.dialect.identifier_preparer.quote
        old_indexes = inspect(connection).get_indexes(table_name)
        if engine.dialect.name in {"mysql", "mariadb"}:
            connection.exec_driver_sql(
                "RENAME TABLE "
                f"{quote(table_name)} TO {quote(backup_name)}, "
                f"{quote(stage_name)} TO {quote(table_name)}"
            )
            for index in old_indexes:
                if index.get("name"):
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote(backup_name)} "
                        f"DROP INDEX {quote(index['name'])}"
                    )
        else:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(table_name)} RENAME TO {quote(backup_name)}"
            )
            for index in old_indexes:
                if index.get("name"):
                    connection.exec_driver_sql(f"DROP INDEX {quote(index['name'])}")
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(stage_name)} RENAME TO {quote(table_name)}"
            )

        migrated = Table(table_name, MetaData(), autoload_with=connection)
        Index(
            "uq_ctdsk_ngay_thu_tu",
            migrated.c.NgayKham,
            migrated.c.SoThuTu,
            unique=True,
        ).create(connection)
        Index(
            "ix_ctdsk_ngay_trang_thai",
            migrated.c.NgayKham,
            migrated.c.TrangThai,
        ).create(connection)

    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    saoChepVaThayBang(connection)
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if violations:
                raise ValueError(
                    "Foreign-key violations found after migration; inspect the database."
                )
    else:
        with engine.begin() as connection:
            saoChepVaThayBang(connection)
    return True
