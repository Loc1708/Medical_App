let receiptPaidState = "DA_THANH_TOAN";
let receiptUnpaidState = "CHUA_THANH_TOAN";

function timKiemBenhNhan() {
    let kw = document.getElementById("kw").value.trim();
    let list = document.getElementById("list");

    if (!kw) {
        lamMoiBieuMauThuNgan();
        return;
    }
    fetch(`/cashier/api/patients?kw=${encodeURIComponent(kw)}`)
        .then((response) => {
            if (!response.ok) {
                return response.json().then((err) => {
                    throw new Error(err.error);
                });
            }
            return response.json();
        })
        .then((data) => {
            let patients = data.patients || [];
            list.replaceChildren();

            if (patients.length === 0) {
                let message = document.createElement("p");
                message.className = "nurse-patient-no-results";
                message.textContent = "Không tìm thấy bệnh nhân phù hợp.";
                list.append(message);
                list.hidden = false;
                return;
            }

            patients.forEach((p) => {
                let button = document.createElement("button");
                button.type = "button";
                button.className = "nurse-patient-suggestion";
                button.textContent = p.code;
                button.addEventListener("click", () => {
                    chonBenhNhan(p.code, p.name);
                });

                let details = document.createElement("small");
                details.textContent = `${p.name} · ${p.phone}`;
                button.append(details);
                list.append(button);
            });
            list.hidden = false;
        })
        .catch((err) => {
            let message = document.createElement("p");
            message.className = "nurse-patient-no-results text-danger";
            message.textContent = err.message;
            list.replaceChildren(message);
            list.hidden = false;
        });
}

function chonBenhNhan(patientCode, patientName) {
    document.getElementById("kw").value = patientName;
    let list = document.getElementById("list");
    list.replaceChildren();
    list.hidden = true;

    layDanhSachHoaDonChuaThanhToan(patientCode);
}

let currentReceipt = [];

function layDanhSachHoaDonChuaThanhToan(patientCode) {
    let dropdown = document.getElementById("receipts_list");

    fetch(`/cashier/api/receipts?ma_bn=${encodeURIComponent(patientCode)}`)
        .then((response) => {
            if (!response.ok) {
                return response.json().then((err) => {
                    throw new Error(err.error || "Lỗi tải dữ liệu");
                });
            }
            return response.json();
        })
        .then((data) => {
            currentReceipt = data.receipts || [];
            let html = '<option value="">-- Chọn hóa đơn cần thanh toán --</option>';

            currentReceipt.forEach((r) => {
                html += `<option value="${r.id}">
                            HĐ #${r.id} - Ngày khám: ${r.date} - Tổng: ${r.total.toLocaleString("vi-VN")} VNĐ
                         </option>`;
            });
            dropdown.innerHTML = html;
            capNhatHoaDon(null);
        })
        .catch((err) => {
            dropdown.innerHTML = `<option value="">${err.message}</option>`;
        });
}

function chonHoaDon() {
    let id = document.getElementById("receipts_list").value;
    let receipt = currentReceipt.find((r) => String(r.id) === id);
    capNhatHoaDon(receipt || null);
}

function capNhatHoaDon(r) {
    document.getElementById("hoTenBN").innerText = r
        ? document.getElementById("kw").value
        : "---";
    document.getElementById("ngayKham").innerText = r ? r.date : "---";
    document.getElementById("tienKham").innerText =
        (r ? r.medical_fee : 0).toLocaleString("vi-VN") + " VNĐ";
    document.getElementById("tienThuoc").innerText =
        (r ? r.medicine_fee : 0).toLocaleString("vi-VN") + " VNĐ";
    document.getElementById("tongTien").innerText =
        (r ? r.total : 0).toLocaleString("vi-VN") + " VNĐ";
    document.getElementById("btnThanhToan").disabled = !r;
}

function lamMoiBieuMauThuNgan() {
    document.getElementById("kw").value = "";

    let list = document.getElementById("list");
    list.replaceChildren();
    list.hidden = true;

    document.getElementById("receipts_list").innerHTML =
        '<option value="" selected disabled hidden> --Danh sách hóa đơn chưa thanh toán-- </option>';

    currentReceipt = [];
    capNhatHoaDon(null);
}

function thanhToan() {
    let id = document.getElementById("receipts_list").value;
    if (!id) return;

    fetch("/cashier/api/receipts/pay", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
        },
        body: JSON.stringify({ id: id }),
    })
        .then((response) =>
            response.json().then((data) => {
                if (!response.ok) {
                    throw new Error(data.error || "Lỗi thanh toán");
                }
                return data;
            }),
        )
        .then((data) => {
            alert(data.message);
            lamMoiBieuMauThuNgan();
        })
        .catch((err) => alert(err.message));
}
