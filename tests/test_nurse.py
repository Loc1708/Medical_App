import unittest
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from flask import g
from flask.testing import FlaskClient
from sqlalchemy import create_engine, inspect, text

from app import dao, db
from app.index import app
from app.migration import (
    drop_nurse_exam_profile_columns,
    upgrade_nurse_many_to_many_schema,
    upgrade_nurse_queue_schema,
)
from app.models import BenhNhan, ChiTietDanhSachKham, DanhSachKham, QuyDinh, Role


class AuthClient(FlaskClient):
    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


class NurseQueueTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        if db.engine.url.drivername != "sqlite" or db.engine.url.database != ":memory:":
            self.context.pop()
            raise RuntimeError("Nurse queue tests require DATABASE_URL=sqlite:///:memory:")
        app.config["TESTING"] = True
        sms_mock = patch("app.routes.nurse.send_sms", return_value=(True, {}))
        self.sms_mock = sms_mock.start()
        self.addCleanup(sms_mock.stop)
        self.previous_client_class = app.test_client_class
        app.test_client_class = AuthClient
        db.create_all()
        self.client = app.test_client()
        self.password = "Test-password-123!"
        self.nurse = dao.create_account({
            "tenDangNhap": "nurse_queue_test",
            "password": self.password,
            "role": Role.NURSE,
            "hoTen": "Y tá kiểm thử",
            "soDienThoai": "0900000000",
            "trangThai": True,
        })
        self.limit = QuyDinh(
            maQD="SO_BENH_NHAN_TOI_DA",
            tenQuyDinh="Số bệnh nhân tối đa trong ngày",
            giaTri=Decimal("40"),
        )
        db.session.add(self.limit)
        db.session.commit()
        self._sign_in(self.client, "nurse_queue_test")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.test_client_class = self.previous_client_class

    def _sign_in(self, client, username):
        login_page = client.get("/login")
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            login_page.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        response = client.post("/login", data={
            "tenDangNhap": username,
            "matKhau": self.password,
            "csrf_token": match.group(1),
        })
        self.assertEqual(response.status_code, 302)
        client.get("/dashboard")

    def _api(self, method, path, payload=None):
        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        return self.client.open(
            path,
            method=method,
            json=payload,
            headers={"X-CSRF-Token": token},
        )

    def _patient(self, index, exam_date="2026-11-14"):
        patient = BenhNhan(
            hoTen=f"Bệnh nhân {index}",
            gioiTinh="Nữ",
            namSinh=1990,
            soDienThoai=f"0901234{index:04d}",
            diaChi="Địa chỉ kiểm thử",
        )
        db.session.add(patient)
        db.session.flush()
        return {
            "date": exam_date,
            "patient_code": patient.maHienThi,
        }

    def _legacy_waiting(self, index, exam_date):
        payload = self._patient(index, exam_date.isoformat())
        patient = dao.find_patient_by_code(payload["patient_code"])
        day = db.session.scalar(
            db.select(DanhSachKham).where(DanhSachKham.ngayKham == exam_date)
        )
        if day is None:
            day = DanhSachKham(ngayKham=exam_date)
        registration = ChiTietDanhSachKham(
            danhSachKham=day, benhNhan=patient, ngayKham=exam_date,
            ngayDangKy=datetime.now(), trangThai="CHO_DUYET",
        )
        db.session.add(registration)
        db.session.commit()
        return registration

    def test_nurse_dashboard_explains_finalized_day_restrictions(self):
        response = self.client.get("/dashboard")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("data-day-locked-warning", html)
        self.assertIn(
            "không thể thêm bệnh nhân vào ngày này",
            html,
        )

    def test_nurse_cannot_add_patient_to_full_day(self):
        responses = [
            self._api("POST", "/nurse/api/lists", self._patient(index))
            for index in range(1, 42)
        ]
        self.assertTrue(all(response.status_code == 201 for response in responses[:40]))
        self.assertEqual(responses[-1].status_code, 409)
        self.assertIn("đã đủ chỗ", responses[-1].get_json()["error"])
        accepted = db.session.scalars(
            db.select(ChiTietDanhSachKham).where(
                ChiTietDanhSachKham.trangThai == "CHO_KHAM"
            )
        ).all()
        waiting = db.session.scalars(
            db.select(ChiTietDanhSachKham).where(
                ChiTietDanhSachKham.trangThai == "CHO_DUYET"
            )
        ).all()
        exam_day = db.session.scalar(
            db.select(DanhSachKham).where(
                DanhSachKham.ngayKham == date(2026, 11, 14)
            )
        )
        self.assertEqual(len(accepted), 40)
        self.assertEqual(len(waiting), 0)
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count()).select_from(DanhSachKham)
            ),
            1,
        )
        self.assertEqual(
            {entry.maDSKham for entry in accepted},
            {exam_day.maDSKham},
        )
        self.assertEqual(len(exam_day.benhNhans), 40)
        self.assertEqual(exam_day.maNV, self.nurse.nhanVien.maNV)

        page = self._api("GET", "/nurse/api/lists?date=2026-11-14")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.get_json()["active"]), 40)
        self.assertEqual(len(page.get_json()["waiting"]), 0)
        self.assertEqual(page.get_json()["limit"], 40)

    def test_waiting_patient_requires_a_freed_slot_before_approval(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        exam_date = dao.clinic_today().isoformat()
        first = self._api("POST", "/nurse/api/lists", self._patient(1, exam_date))
        waiting = self._legacy_waiting(2, date.fromisoformat(exam_date))
        first_id = first.get_json()["patient"]["id"]
        waiting_id = waiting.maCTDSKham

        blocked = self._api(
            "POST", f"/nurse/api/lists/{waiting_id}/approve", {"date": exam_date}
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(
            db.session.get(ChiTietDanhSachKham, waiting_id).trangThai, "CHO_DUYET"
        )

        cancelled = self._api("DELETE", f"/nurse/api/lists/{first_id}")
        self.assertEqual(cancelled.status_code, 200)
        approved = self._api(
            "POST", f"/nurse/api/lists/{waiting_id}/approve", {"date": exam_date}
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.get_json()["patient"]["slot"], 1)
        self.assertEqual(
            db.session.get(ChiTietDanhSachKham, waiting_id).trangThai, "CHO_KHAM"
        )
        self.assertEqual(
            db.session.get(ChiTietDanhSachKham, first_id).trangThai, "DA_HUY"
        )

    def test_waiting_list_remains_visible_and_can_move_to_selected_future_date(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        source_date = dao.clinic_today()
        target_date = source_date + timedelta(days=1)
        first = self._api(
            "POST", "/nurse/api/lists", self._patient(1, source_date.isoformat())
        )
        waiting = self._legacy_waiting(2, source_date)
        self.assertEqual(first.status_code, 201)
        waiting_id = waiting.maCTDSKham

        target_list = self._api(
            "GET", f"/nurse/api/lists?date={target_date.isoformat()}"
        )
        self.assertEqual(target_list.status_code, 200)
        self.assertEqual(target_list.get_json()["active"], [])
        self.assertEqual(len(target_list.get_json()["waiting"]), 1)
        self.assertEqual(
            target_list.get_json()["waiting"][0]["examDate"], source_date.isoformat()
        )

        approved = self._api(
            "POST",
            f"/nurse/api/lists/{waiting_id}/approve",
            {"date": target_date.isoformat()},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.get_json()["patient"]["id"], waiting_id)
        self.assertEqual(
            approved.get_json()["patient"]["examDate"], target_date.isoformat()
        )
        registration = db.session.get(ChiTietDanhSachKham, waiting_id)
        self.assertEqual(registration.trangThai, "CHO_KHAM")
        self.assertEqual(registration.ngayKham, target_date)

        source_list = self._api(
            "GET", f"/nurse/api/lists?date={source_date.isoformat()}"
        )
        target_list = self._api(
            "GET", f"/nurse/api/lists?date={target_date.isoformat()}"
        )
        self.assertEqual(len(source_list.get_json()["active"]), 1)
        self.assertEqual(source_list.get_json()["waiting"], [])
        self.assertEqual(len(target_list.get_json()["active"]), 1)
        self.assertEqual(target_list.get_json()["waiting"], [])

    def test_nurse_can_add_patient_to_a_future_exam_date(self):
        future_date = dao.clinic_today() + timedelta(days=1)
        patient_payload = self._patient(1, future_date.isoformat())
        lookup = self.client.get(
            "/nurse/api/patients?q=BN-000"
        )
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(
            [patient["code"] for patient in lookup.get_json()["patients"]],
            [patient_payload["patient_code"]],
        )
        self.assertEqual(lookup.get_json()["patients"][0]["name"], "Bệnh nhân 1")
        substring_lookup = self.client.get("/nurse/api/patients?q=001")
        self.assertEqual(
            [patient["code"] for patient in substring_lookup.get_json()["patients"]],
            [patient_payload["patient_code"]],
        )
        self.assertEqual(
            self.client.get("/nurse/api/patients?q=BN-999999").get_json()["patients"],
            [],
        )

        response = self._api(
            "POST",
            "/nurse/api/lists",
            {
                **patient_payload,
                "name": "Tên không được tin cậy",
            },
        )

        self.assertEqual(response.status_code, 201)
        patient = response.get_json()["patient"]
        self.assertEqual(patient["name"], "Bệnh nhân 1")
        self.assertEqual(patient["status"], "CHO_KHAM")
        self.assertEqual(patient["examDate"], future_date.isoformat())
        day = self._api(
            "GET", f"/nurse/api/lists?date={future_date.isoformat()}"
        )
        self.assertEqual(len(day.get_json()["active"]), 1)

    def test_confirmed_exam_day_rejects_new_patient_additions(self):
        exam_date = dao.clinic_today()
        first = self._api(
            "POST", "/nurse/api/lists", self._patient(1, exam_date.isoformat())
        )
        self.assertEqual(first.status_code, 201)
        confirmed = self._api(
            "POST",
            "/nurse/api/lists/confirm",
            {"date": exam_date.isoformat()},
        )
        self.assertEqual(confirmed.status_code, 200)

        rejected = self._api(
            "POST", "/nurse/api/lists", self._patient(2, exam_date.isoformat())
        )

        self.assertEqual(rejected.status_code, 409)
        self.assertIn("đã được xác nhận và chốt", rejected.get_json()["error"])
        day = self._api(
            "GET", f"/nurse/api/lists?date={exam_date.isoformat()}"
        ).get_json()
        self.assertTrue(day["confirmed"])
        self.assertTrue(day["locked"])
        self.assertEqual(len(day["active"]), 1)
        self.assertEqual(day["active"][0]["status"], "DA_XAC_NHAN")

    def test_confirmed_exam_day_can_be_reopened_and_accept_supplemental_patient(self):
        exam_date = dao.clinic_today()
        first = self._api(
            "POST", "/nurse/api/lists", self._patient(1, exam_date.isoformat())
        )
        self.assertEqual(first.status_code, 201)
        confirmed = self._api(
            "POST",
            "/nurse/api/lists/confirm",
            {"date": exam_date.isoformat()},
        )
        self.assertEqual(confirmed.status_code, 200)

        reopened = self._api(
            "POST",
            "/nurse/api/lists/reopen",
            {"date": exam_date.isoformat()},
        )
        self.assertEqual(reopened.status_code, 200)

        supplemental = self._api(
            "POST", "/nurse/api/lists", self._patient(2, exam_date.isoformat())
        )
        self.assertEqual(supplemental.status_code, 201)

        day = self._api(
            "GET", f"/nurse/api/lists?date={exam_date.isoformat()}"
        ).get_json()
        statuses = {entry["status"] for entry in day["active"]}
        self.assertIn("DA_MO_LAI", statuses)
        self.assertIn("CHO_KHAM", statuses)
        self.assertFalse(day["confirmed"])

        self.sms_mock.reset_mock()
        final_confirm = self._api(
            "POST",
            "/nurse/api/lists/confirm",
            {"date": exam_date.isoformat()},
        )
        self.assertEqual(final_confirm.status_code, 200)
        self.assertEqual(self.sms_mock.call_count, 2)
        self.assertEqual(
            {call.args[0] for call in self.sms_mock.call_args_list},
            {first.get_json()["patient"]["phone"],
             supplemental.get_json()["patient"]["phone"]},
        )
        self.assertIn("Đã gửi 2 SMS, lỗi 0", final_confirm.get_json()["message"])
        final_day = self._api(
            "GET", f"/nurse/api/lists?date={exam_date.isoformat()}"
        ).get_json()
        self.assertTrue(final_day["confirmed"])
        self.assertTrue(all(
            entry["status"] == "DA_XAC_NHAN"
            for entry in final_day["active"]
        ))
        self.sms_mock.reset_mock()
        self._api("POST", "/nurse/api/lists/confirm", {"date": exam_date.isoformat()})
        self.sms_mock.assert_not_called()

    def test_reconfirming_reopened_list_resends_sms_without_new_patients(self):
        exam_date = dao.clinic_today().isoformat()
        self._api("POST", "/nurse/api/lists", self._patient(1, exam_date))
        self._api("POST", "/nurse/api/lists/confirm", {"date": exam_date})
        self._api("POST", "/nurse/api/lists/reopen", {"date": exam_date})
        self.sms_mock.reset_mock()

        confirmed = self._api("POST", "/nurse/api/lists/confirm", {"date": exam_date})

        self.assertEqual(confirmed.status_code, 200)
        self.sms_mock.assert_called_once()
        self.assertIn("Đã gửi 1 SMS, lỗi 0", confirmed.get_json()["message"])

    def test_reconfirming_reopened_list_reports_sms_failures(self):
        exam_date = dao.clinic_today().isoformat()
        self._api("POST", "/nurse/api/lists", self._patient(1, exam_date))
        self._api("POST", "/nurse/api/lists/confirm", {"date": exam_date})
        self._api("POST", "/nurse/api/lists/reopen", {"date": exam_date})
        self.sms_mock.reset_mock()
        self.sms_mock.return_value = (False, {"error": "test failure"})

        confirmed = self._api("POST", "/nurse/api/lists/confirm", {"date": exam_date})

        self.assertEqual(confirmed.status_code, 200)
        self.sms_mock.assert_called_once()
        self.assertIn("Đã gửi 0 SMS, lỗi 1", confirmed.get_json()["message"])

    def test_waiting_patient_cannot_be_approved_into_confirmed_exam_day(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        exam_date = dao.clinic_today()
        active = self._api(
            "POST", "/nurse/api/lists", self._patient(1, exam_date.isoformat())
        )
        waiting = self._legacy_waiting(2, exam_date)
        self.assertEqual(active.status_code, 201)
        waiting_id = waiting.maCTDSKham
        self._api(
            "POST",
            "/nurse/api/lists/confirm",
            {"date": exam_date.isoformat()},
        )

        rejected = self._api(
            "POST",
            f"/nurse/api/lists/{waiting_id}/approve",
            {"date": exam_date.isoformat()},
        )

        self.assertEqual(rejected.status_code, 409)
        self.assertIn("đã được xác nhận và chốt", rejected.get_json()["error"])
        self.assertEqual(
            db.session.get(ChiTietDanhSachKham, waiting_id).trangThai,
            "CHO_DUYET",
        )

    def test_nurse_cannot_add_patient_from_unrecognized_code_or_raw_fields(self):
        baseline = db.session.scalar(
            db.select(db.func.count()).select_from(BenhNhan)
        )
        missing_code = self._api(
            "POST",
            "/nurse/api/lists",
            {
                "date": "2026-11-14",
                "name": "Không tồn tại trong hồ sơ",
                "gender": "Nam",
                "birthYear": 1990,
                "phone": "09011112222",
                "address": "Địa chỉ tự nhập",
            },
        )
        unknown_code = self._api(
            "POST",
            "/nurse/api/lists",
            {"patient_code": "BN-999999", "date": "2026-11-14"},
        )
        self.assertEqual(missing_code.status_code, 400)
        self.assertEqual(unknown_code.status_code, 404)
        self.assertEqual(
            db.session.scalar(db.select(db.func.count()).select_from(BenhNhan)),
            baseline,
        )

    def test_waiting_patient_cannot_be_approved_into_a_past_date(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        today = dao.clinic_today()
        self._api(
            "POST", "/nurse/api/lists", self._patient(1, today.isoformat())
        )
        waiting = self._legacy_waiting(2, today)
        registration_id = waiting.maCTDSKham

        past_date = (today - timedelta(days=1)).isoformat()
        rejected = self._api(
            "POST",
            f"/nurse/api/lists/{registration_id}/approve",
            {"date": past_date},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("ngày đã qua", rejected.get_json()["error"])
        registration = db.session.get(ChiTietDanhSachKham, registration_id)
        self.assertEqual(registration.trangThai, "CHO_DUYET")
        self.assertEqual(registration.ngayKham, today)

    def test_patient_self_registration_moves_to_next_day(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        exam_date = dao.clinic_today().isoformat()
        accepted = self._api(
            "POST", "/nurse/api/lists", self._patient(1, exam_date=exam_date)
        )
        self.assertEqual(accepted.status_code, 201)

        patient = dao.create_account({
            "tenDangNhap": "patient_queue_test",
            "password": self.password,
            "role": Role.PATIENT,
            "hoTen": "Bệnh nhân tự đăng ký",
            "soDienThoai": "09000000111",
            "trangThai": True,
            "namSinh": 1995,
            "gioiTinh": "Nam",
            "diaChi": "Địa chỉ kiểm thử",
        })
        patient_client = app.test_client()
        self._sign_in(patient_client, "patient_queue_test")
        with patient_client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]
        response = patient_client.post("/patient/exam-registrations", data={
            "hoTen": "Không được dùng thay cho hồ sơ",
            "gioiTinh": "Khác",
            "namSinh": 1900,
            "diaChi": "Địa chỉ khác",
            "csrf_token": csrf_token,
        })
        self.assertEqual(response.status_code, 302)
        registration = db.session.scalar(
            db.select(ChiTietDanhSachKham).where(
                ChiTietDanhSachKham.maBN == patient.benhNhan.maBN
            )
        )
        self.assertIsNotNone(registration)
        self.assertEqual(registration.trangThai, "CHO_KHAM")
        self.assertEqual(registration.ngayKham, dao.clinic_today() + timedelta(days=1))
        self.assertEqual(registration.benhNhan.hoTen, patient.benhNhan.hoTen)
        self.assertEqual(registration.benhNhan.gioiTinh, patient.benhNhan.gioiTinh)
        self.assertEqual(registration.benhNhan.namSinh, patient.benhNhan.namSinh)
        self.assertEqual(registration.benhNhan.diaChi, patient.benhNhan.diaChi)
        self.assertIsNotNone(registration.danhSachKham)
        self.assertIsNone(registration.danhSachKham.maNV)
        page = patient_client.get("/dashboard")
        page_html = page.get_data(as_text=True)
        self.assertIn("ngày gần nhất còn chỗ", page_html)
        self.assertNotIn(registration.ngayKham.strftime("%d/%m/%Y"), page_html)
        duplicate = patient_client.post("/patient/exam-registrations", data={
            "csrf_token": csrf_token,
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(len(dao.patient_exam_registrations(patient.benhNhan.maBN)), 1)
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists/confirm",
            {"date": registration.ngayKham.isoformat()},
        ).status_code, 200)
        confirmed_html = patient_client.get("/dashboard").get_data(as_text=True)
        self.assertIn(registration.ngayKham.strftime("%d/%m/%Y"), confirmed_html)

    def test_patient_registration_skips_full_and_confirmed_days(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        today = dao.clinic_today()
        tomorrow = today + timedelta(days=1)
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists", self._patient(1, today.isoformat())
        ).status_code, 201)
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists", self._patient(2, tomorrow.isoformat())
        ).status_code, 201)
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists/confirm", {"date": tomorrow.isoformat()}
        ).status_code, 200)

        payload = self._patient(3, today.isoformat())
        patient = dao.find_patient_by_code(payload["patient_code"])
        registration = dao.register_patient_exam(patient)
        self.assertEqual(registration.ngayKham, today + timedelta(days=2))
        self.assertEqual(registration.soThuTu, 1)
        self.assertEqual(registration.trangThai, "CHO_KHAM")

    def test_patient_registration_skips_a_confirmed_day_with_free_capacity(self):
        today = dao.clinic_today()
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists", self._patient(1, today.isoformat())
        ).status_code, 201)
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists/confirm", {"date": today.isoformat()}
        ).status_code, 200)
        patient = dao.find_patient_by_code(self._patient(2)["patient_code"])
        registration = dao.register_patient_exam(patient)
        self.assertEqual(registration.ngayKham, today + timedelta(days=1))

    def test_legacy_waiting_migration_requires_maintenance_and_preserves_rows(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        today = dao.clinic_today()
        self.assertEqual(self._api(
            "POST", "/nurse/api/lists", self._patient(1, today.isoformat())
        ).status_code, 201)
        first = self._legacy_waiting(2, today)
        second = self._legacy_waiting(3, today - timedelta(days=1))
        first_id, second_id = first.maCTDSKham, second.maCTDSKham
        original_data = {
            row.maCTDSKham: (row.maBN, row.ngayDangKy)
            for row in (first, second)
        }

        runner = app.test_cli_runner()
        refused = runner.invoke(args=["move-waiting-registrations"])
        self.assertNotEqual(refused.exit_code, 0)
        self.assertEqual(first.trangThai, "CHO_DUYET")

        result = runner.invoke(args=["move-waiting-registrations", "--maintenance"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Moved 2", result.output)
        db.session.expire_all()
        moved = [db.session.get(ChiTietDanhSachKham, row_id)
                 for row_id in (first_id, second_id)]
        self.assertEqual({row.ngayKham for row in moved},
                         {today + timedelta(days=1), today + timedelta(days=2)})
        self.assertTrue(all(row.trangThai == "CHO_KHAM" and row.soThuTu == 1
                            for row in moved))
        self.assertTrue(all((row.maBN, row.ngayDangKy) == original_data[row.maCTDSKham]
                            for row in moved))
        repeated = runner.invoke(args=["move-waiting-registrations", "--maintenance"])
        self.assertEqual(repeated.exit_code, 0, repeated.output)
        self.assertIn("Moved 0", repeated.output)

    def test_legacy_waiting_migration_rolls_back_all_rows_on_failure(self):
        today = dao.clinic_today()
        first = self._legacy_waiting(1, today)
        second = self._legacy_waiting(2, today)
        ids = (first.maCTDSKham, second.maCTDSKham)
        find_slot = dao._find_next_available_exam_date
        with patch("app.dao._find_next_available_exam_date",
                   side_effect=[find_slot(today), ValueError("No available date")]):
            result = app.test_cli_runner().invoke(
                args=["move-waiting-registrations", "--maintenance"]
            )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("No available date", result.output)
        db.session.expire_all()
        for row_id in ids:
            row = db.session.get(ChiTietDanhSachKham, row_id)
            self.assertEqual(row.trangThai, "CHO_DUYET")
            self.assertIsNone(row.soThuTu)
            self.assertEqual(row.ngayKham, today)

    def test_nurse_endpoints_enforce_role_and_csrf(self):
        missing_csrf = self.client.post(
            "/nurse/api/lists",
            json=self._patient(1),
        )
        self.assertEqual(missing_csrf.status_code, 400)

        doctor_data = {
            "tenDangNhap": "doctor_queue_test",
            "password": self.password,
            "role": Role.DOCTOR,
            "hoTen": "Bác sĩ kiểm thử",
            "soDienThoai": "0900000001",
            "trangThai": True,
            "chuyenKhoa": "Nội khoa",
        }
        dao.create_account(doctor_data)
        doctor_client = app.test_client()
        self._sign_in(doctor_client, "doctor_queue_test")
        response = doctor_client.get("/nurse/api/lists?date=2026-11-14")
        self.assertEqual(response.status_code, 403)

    def test_confirmed_list_history_has_its_own_nurse_page(self):
        today = dao.clinic_today()
        future_date = today + timedelta(days=1)
        first = self._api(
            "POST", "/nurse/api/lists", self._patient(1, today.isoformat())
        )
        second = self._api(
            "POST", "/nurse/api/lists", self._patient(2, today.isoformat())
        )
        unconfirmed = self._api(
            "POST", "/nurse/api/lists", self._patient(3, future_date.isoformat())
        )
        self.assertEqual(
            self._api(
                "POST", "/nurse/api/lists/confirm", {"date": today.isoformat()}
            ).status_code,
            200,
        )

        page = self.client.get("/nurse/history")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Danh sách ngày", html)
        details_start = html.index('<details class="panel nurse-history-day mt-4">')
        summary_start = html.index("<summary", details_start)
        summary_end = html.index("</summary>", summary_start)
        details_end = html.index("</details>", summary_end)
        self.assertNotIn("open", html[details_start:summary_start])
        self.assertNotIn("Bệnh nhân 1", html[summary_start:summary_end])
        self.assertIn("Bệnh nhân 1", html[summary_end:details_end])
        self.assertIn("Bệnh nhân 1", html)
        self.assertIn("Bệnh nhân 2", html)
        self.assertNotIn("Bệnh nhân 3", html)
        self.assertIn('href="/nurse/history"', html)
        self.assertIn('class="nav-item active" href="/nurse/history"', html)

        dashboard = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn("data-toggle-history", dashboard)
        self.assertIn('href="/nurse/history"', dashboard)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(unconfirmed.status_code, 201)

        patient = dao.create_account({
            "tenDangNhap": "history_forbidden_patient",
            "password": self.password,
            "role": Role.PATIENT,
            "hoTen": "Bệnh nhân kiểm thử",
            "soDienThoai": "09000000222",
            "trangThai": True,
            "namSinh": 1995,
            "gioiTinh": "Nam",
            "diaChi": "Địa chỉ kiểm thử",
        })
        patient_client = app.test_client()
        self._sign_in(patient_client, "history_forbidden_patient")
        self.assertEqual(patient_client.get("/nurse/history").status_code, 403)


class NurseQueueMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_rows_and_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'CREATE TABLE "TaiKhoan" ("MaTK" INTEGER PRIMARY KEY AUTOINCREMENT)'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "NhanVien" ('
                '"MaNV" INTEGER PRIMARY KEY AUTOINCREMENT, "MaTK" INTEGER NOT NULL UNIQUE, '
                'FOREIGN KEY ("MaTK") REFERENCES "TaiKhoan" ("MaTK"))'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "BenhNhan" ('
                '"MaBN" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
                '"HoTen" VARCHAR(100) NOT NULL, "GioiTinh" VARCHAR(10) NOT NULL, '
                '"NamSinh" INTEGER NOT NULL, "DiaChi" VARCHAR(255) NOT NULL, '
                '"SoDienThoai" VARCHAR(20) NOT NULL, "MaTK" INTEGER NOT NULL UNIQUE, '
                'FOREIGN KEY ("MaTK") REFERENCES "TaiKhoan" ("MaTK"))'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "DanhSachKham" ('
                '"MaDSKham" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
                '"MaBN" INTEGER NOT NULL, "HoTen" VARCHAR(100) NOT NULL, '
                '"GioiTinh" VARCHAR(10) NOT NULL, "NamSinh" INTEGER NOT NULL, '
                '"DiaChi" VARCHAR(255) NOT NULL, "NgayDangKy" DATETIME NOT NULL, '
                '"TrangThai" VARCHAR(20) NOT NULL, '
                'FOREIGN KEY ("MaBN") REFERENCES "BenhNhan" ("MaBN"))'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "QuyDinh" ('
                '"MaQD" VARCHAR(30) PRIMARY KEY, "TenQuyDinh" VARCHAR(100) NOT NULL, '
                '"GiaTri" NUMERIC(15, 2) NOT NULL)'
            )
            connection.exec_driver_sql('INSERT INTO "TaiKhoan" ("MaTK") VALUES (1)')
            connection.exec_driver_sql(
                'INSERT INTO "BenhNhan" '
                '("MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "SoDienThoai", "MaTK") '
                'VALUES (1, "Bệnh nhân cũ", "Nữ", 1990, "Địa chỉ cũ", "0900000000", 1)'
            )
            connection.exec_driver_sql(
                'INSERT INTO "DanhSachKham" '
                '("MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "NgayDangKy", "TrangThai") '
                'VALUES (1, "Bệnh nhân cũ", "Nữ", 1990, "Địa chỉ cũ", '
                '"2026-11-14 08:00:00", "CHO_KHAM")'
            )
            connection.exec_driver_sql(
                'INSERT INTO "DanhSachKham" '
                '("MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "NgayDangKy", "TrangThai") '
                'VALUES (1, "Bệnh nhân cũ", "Nữ", 1990, "Địa chỉ cũ", '
                '"2026-11-14 09:00:00", "DA_HUY")'
            )

        self.assertTrue(upgrade_nurse_queue_schema(engine))
        self.assertFalse(upgrade_nurse_queue_schema(engine))
        self.assertTrue(upgrade_nurse_many_to_many_schema(engine))
        self.assertFalse(upgrade_nurse_many_to_many_schema(engine))
        columns = {column["name"]: column for column in inspect(engine).get_columns("BenhNhan")}
        self.assertTrue(columns["MaTK"]["nullable"])
        table_names = set(inspect(engine).get_table_names())
        self.assertIn("DanhSachKham_legacy", table_names)
        self.assertIn("ChiTietDanhSachKham", table_names)
        detail_columns = {
            column["name"]
            for column in inspect(engine).get_columns("ChiTietDanhSachKham")
        }
        self.assertTrue({
            "HoTen", "GioiTinh", "NamSinh", "DiaChi",
        }.isdisjoint(detail_columns))
        with engine.connect() as connection:
            registration = connection.execute(text(
                'SELECT "NgayKham", "SoThuTu", "TrangThai" '
                'FROM "ChiTietDanhSachKham" WHERE "MaCTDSKham" = 1'
            )).one()
            day = connection.execute(text(
                'SELECT "NgayKham", "MaNV" FROM "DanhSachKham"'
            )).one()
            registration_count = connection.execute(text(
                'SELECT COUNT(*) FROM "ChiTietDanhSachKham"'
            )).scalar_one()
            legacy_count = connection.execute(text(
                'SELECT COUNT(*) FROM "DanhSachKham_legacy"'
            )).scalar_one()
            patient_count = connection.execute(text(
                'SELECT COUNT(*) FROM "BenhNhan"'
            )).scalar_one()
            rule = connection.execute(text(
                'SELECT "GiaTri" FROM "QuyDinh" WHERE "MaQD" = :code'
            ), {"code": "SO_BENH_NHAN_TOI_DA"}).scalar_one()
            foreign_key_errors = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        self.assertEqual(registration.NgayKham, "2026-11-14")
        self.assertEqual(registration.SoThuTu, 1)
        self.assertEqual(registration.TrangThai, "CHO_KHAM")
        self.assertEqual(day.NgayKham, "2026-11-14")
        self.assertIsNone(day.MaNV)
        self.assertEqual(registration_count, 2)
        self.assertEqual(legacy_count, 2)
        self.assertEqual(patient_count, 1)
        self.assertEqual(rule, 40)
        self.assertEqual(foreign_key_errors, [])
        engine.dispose()

    def test_drop_profile_columns_preserves_exam_detail_rows_and_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'CREATE TABLE "ChiTietDanhSachKham" ('
                '"MaCTDSKham" INTEGER PRIMARY KEY, "MaDSKham" INTEGER NOT NULL, '
                '"MaBN" INTEGER NOT NULL, "NgayKham" DATE NOT NULL, '
                '"SoThuTu" INTEGER, "NgayDangKy" DATETIME NOT NULL, '
                '"TrangThai" VARCHAR(20) NOT NULL, "HoTen" VARCHAR(100) NOT NULL, '
                '"GioiTinh" VARCHAR(10) NOT NULL, "NamSinh" INTEGER NOT NULL, '
                '"DiaChi" VARCHAR(255) NOT NULL)'
            )
            connection.exec_driver_sql(
                'INSERT INTO "ChiTietDanhSachKham" VALUES '
                '(1, 2, 3, "2026-11-14", 1, "2026-11-14 08:00:00", '
                '"CHO_KHAM", "Bệnh nhân", "Nữ", 1990, "Địa chỉ")'
            )

        self.assertTrue(drop_nurse_exam_profile_columns(engine))
        self.assertFalse(drop_nurse_exam_profile_columns(engine))
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("ChiTietDanhSachKham")
        }
        self.assertTrue({
            "HoTen", "GioiTinh", "NamSinh", "DiaChi",
        }.isdisjoint(columns))
        with engine.connect() as connection:
            registration = connection.execute(text(
                'SELECT "MaBN", "NgayKham", "TrangThai" '
                'FROM "ChiTietDanhSachKham" WHERE "MaCTDSKham" = 1'
            )).one()
        self.assertEqual(registration.MaBN, 3)
        self.assertEqual(registration.NgayKham, "2026-11-14")
        self.assertEqual(registration.TrangThai, "CHO_KHAM")
        engine.dispose()
