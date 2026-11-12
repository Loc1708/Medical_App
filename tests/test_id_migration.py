import unittest

from sqlalchemy import Column, ForeignKey, MetaData, String, Table, create_engine, event, inspect, select
from werkzeug.security import generate_password_hash

from app import db
from app.migration import BACKUP, TABLE_NAMES, migrate_account_ids
from app.models import Role


class IdentifierMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        self.legacy = MetaData()
        for name in TABLE_NAMES:
            columns = []
            for column in db.metadata.tables[name].columns:
                foreign_keys = [ForeignKey(fk.target_fullname) for fk in column.foreign_keys]
                column_type = String(36) if column.name in {"MaTK", "MaNV", "MaBN"} else column.type.copy()
                columns.append(Column(
                    column.name, column_type, *foreign_keys, primary_key=column.primary_key,
                    nullable=column.nullable, unique=column.unique,
                ))
            Table(name, self.legacy, *columns)
        self.legacy.create_all(self.engine)
        self.password_hash = generate_password_hash("Migration-test-123!")
        with self.engine.begin() as connection:
            connection.execute(self.legacy.tables["TaiKhoan"].insert(), [
                dict(MaTK="uuid-doctor", tenDangNhap="doctor", matKhau=self.password_hash,
                     role=Role.DOCTOR, trangThai=True),
                dict(MaTK="uuid-patient", tenDangNhap="patient", matKhau=self.password_hash,
                     role=Role.PATIENT, trangThai=False),
            ])
            connection.execute(self.legacy.tables["NhanVien"].insert(), dict(
                MaNV="uuid-employee", MaTK="uuid-doctor", hoTen="Doctor", soDienThoai="",
            ))
            connection.execute(self.legacy.tables["BacSi"].insert(), dict(
                MaNV="uuid-employee", chuyenKhoa="General",
            ))
            connection.execute(self.legacy.tables["BenhNhan"].insert(), [
                dict(MaBN="uuid-patient-profile", MaTK="uuid-patient", hoTen="Patient",
                     soDienThoai="0900000000", gioiTinh="Nam", namSinh=2000, diaChi="Address"),
                dict(MaBN="uuid-historical-profile", MaTK="uuid-doctor", hoTen="Old patient",
                     soDienThoai="0900000001", gioiTinh="Nam", namSinh=1990, diaChi="Old address"),
            ])

    def tearDown(self):
        self.engine.dispose()

    def test_preserves_data_relationships_backups_and_autoincrement(self):
        self.assertTrue(migrate_account_ids(self.engine))
        metadata = MetaData()
        metadata.reflect(self.engine)
        self.assertTrue(all(name + BACKUP in metadata.tables for name in TABLE_NAMES))
        with self.engine.begin() as connection:
            accounts = {row["tenDangNhap"]: row for row in connection.execute(
                select(metadata.tables["TaiKhoan"])
            ).mappings()}
            doctor = accounts["doctor"]
            patient = accounts["patient"]
            self.assertIsInstance(doctor["MaTK"], int)
            self.assertEqual(doctor["matKhau"], self.password_hash)
            self.assertFalse(patient["trangThai"])
            employee = connection.execute(select(metadata.tables["NhanVien"])).mappings().one()
            specialist = connection.execute(select(metadata.tables["BacSi"])).mappings().one()
            self.assertEqual(employee["MaTK"], doctor["MaTK"])
            self.assertEqual(specialist["MaNV"], employee["MaNV"])
            profiles = list(connection.execute(select(metadata.tables["BenhNhan"])).mappings())
            self.assertEqual({row["MaTK"] for row in profiles}, {doctor["MaTK"], patient["MaTK"]})
            backup = metadata.tables["TaiKhoan" + BACKUP]
            self.assertEqual(set(connection.scalars(select(backup.c.MaTK))),
                             {"uuid-doctor", "uuid-patient"})
            result = connection.execute(metadata.tables["TaiKhoan"].insert(), dict(
                tenDangNhap="next", matKhau=self.password_hash, role="ADMIN", trangThai=True,
            ))
            self.assertGreater(result.inserted_primary_key[0], max(r["MaTK"] for r in accounts.values()))
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
        self.assertFalse(migrate_account_ids(self.engine))

    def test_refuses_unmigrated_external_references(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                'CREATE TABLE Extra (id INTEGER PRIMARY KEY, account_id VARCHAR(36) '
                'REFERENCES "TaiKhoan" ("MaTK"))'
            )
        with self.assertRaisesRegex(ValueError, "Other tables reference"):
            migrate_account_ids(self.engine)
        self.assertNotIn("TaiKhoan" + BACKUP, inspect(self.engine).get_table_names())

    def test_cli_requires_explicit_maintenance_confirmation(self):
        from app.index import app
        result = app.test_cli_runner().invoke(args=["migrate-account-ids"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--maintenance", result.output)
