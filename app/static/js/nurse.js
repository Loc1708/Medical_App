const nurseApp = document.querySelector("[data-nurse-app]");

if (nurseApp) {
    const pageSize = 10;
    const dateInput = nurseApp.querySelector("#nurse-exam-date");
    const limitLabel = nurseApp.querySelector("[data-daily-limit]");
    const patientLookupForm = nurseApp.querySelector("[data-patient-lookup-form]");
    const patientCodeInput = nurseApp.querySelector("#nurse-patient-code");
    const patientSuggestions = nurseApp.querySelector("[data-patient-suggestions]");
    const patientLookupResult = nurseApp.querySelector("[data-patient-lookup-result]");
    const dayLockedWarning = nurseApp.querySelector("[data-day-locked-warning]");
    const searchForm = nurseApp.querySelector("[data-search-form]");
    const searchInput = nurseApp.querySelector("#nurse-search");
    const patientRows = nurseApp.querySelector("[data-patient-rows]");
    const pagination = nurseApp.querySelector("[data-pagination]");
    const listSummary = nurseApp.querySelector("[data-list-summary]");
    const patientCount = nurseApp.querySelector("[data-patient-count]");
    const legacyWaitingWarning = nurseApp.querySelector("[data-legacy-waiting-warning]");
    const status = nurseApp.querySelector("[data-nurse-status]");
    const confirmedStatus = nurseApp.querySelector("[data-confirmed-status]");
    const confirmButton = nurseApp.querySelector("[data-confirm-list]");
    const reopenButton = nurseApp.querySelector("[data-reopen-list]");
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    let selectedDate = "";
    let clinicToday = layNgayHomNay();
    let currentPage = 1;
    let searchTerm = "";
    let dailyLimit = 0;
    let patientSearchTimer = null;
    let patientLookupRequestId = 0;
    let matchedPatients = [];
    let matchedPatient = null;
    let activePatients = [];
    let dayConfirmed = false;
    let dayLocked = false;

    function layNgayHomNay() {
        const now = new Date();
        return [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
        ].join("-");
    }

    function hienThiTrangThai(message, kind = "info") {
        status.textContent = message;
        status.classList.toggle("is-error", kind === "error");
        status.classList.toggle("is-success", kind === "success");
        status.hidden = !message;
    }

    function chuanHoaChuoi(value) {
        return value.toLocaleLowerCase("vi")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d");
    }

    function dinhDangNgay(value) {
        const [year, month, day] = value.split("-").map(Number);
        return new Intl.DateTimeFormat("vi-VN").format(new Date(year, month - 1, day));
    }

    async function goiApi(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken,
                ...options.headers,
            },
        });
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error("Máy chủ trả về dữ liệu không hợp lệ.");
        }
        if (!response.ok) {
            throw new Error(data.error || "Không thể hoàn thành thao tác.");
        }
        return data;
    }

    async function taiLaiDanhSachNgay() {
        const data = await goiApi(
            `/nurse/api/lists?date=${encodeURIComponent(selectedDate)}`
        );
        dailyLimit = data.limit;
        clinicToday = data.today;
        activePatients = data.active;
        legacyWaitingWarning.hidden = data.waiting.length === 0;
        legacyWaitingWarning.textContent = data.waiting.length
            ? `Còn ${data.waiting.length} lượt chờ cũ chưa được chuyển lịch. Hãy liên hệ quản trị viên.`
            : "";
        dayConfirmed = data.confirmed;
        dayLocked = data.locked;
        nurseApp.dataset.maxPatients = String(dailyLimit);
        limitLabel.textContent = `Giới hạn: ${dailyLimit} bệnh nhân/ngày`;
        hienThiDanhSach();
    }

    function taoO(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
        return cell;
    }

    function taoNut(label, className, action, id, disabled = false) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className;
        button.dataset[action] = id;
        button.textContent = label;
        button.disabled = disabled;
        return button;
    }

    function taoNutBieuTuong(label, action, listId, patientId) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "catalog-icon";
        button.dataset[`${action}ListId`] = listId;
        button.dataset[`${action}PatientId`] = patientId;
        button.setAttribute("aria-label", label);
        button.title = label;

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7");
        svg.append(path);
        button.append(svg);
        return button;
    }

    function xoaKetQuaTimBenhNhan() {
        matchedPatient = null;
        patientLookupResult.replaceChildren();
        patientLookupResult.hidden = true;
    }

    function xoaGoiYBenhNhan() {
        matchedPatients = [];
        patientSuggestions.replaceChildren();
        patientSuggestions.hidden = true;
    }

    function hienThiGoiYBenhNhan(patients) {
        if (dayLocked) {
            xoaGoiYBenhNhan();
            return;
        }
        matchedPatients = patients;
        patientSuggestions.replaceChildren();
        if (!patients.length) {
            const emptyMessage = document.createElement("p");
            emptyMessage.className = "nurse-patient-no-results";
            emptyMessage.textContent = "Không tìm thấy mã bệnh nhân phù hợp.";
            patientSuggestions.append(emptyMessage);
        } else {
            patients.forEach(patient => {
                const button = taoNut(
                    patient.code, "nurse-patient-suggestion", "selectPatient",
                    patient.code
                );
                const details = document.createElement("small");
                details.textContent = `${patient.name} · ${patient.phone}`;
                button.append(details);
                patientSuggestions.append(button);
            });
        }
        patientSuggestions.hidden = false;
    }

    async function timBenhNhanTheoMa(query, requestId) {
        if (dayLocked) return;
        try {
            const url = new URL("/nurse/api/patients", window.location.origin);
            url.searchParams.set("q", query);
            const data = await goiApi(url);
            if (requestId === patientLookupRequestId) {
                hienThiGoiYBenhNhan(data.patients);
            }
        } catch (error) {
            if (requestId === patientLookupRequestId) {
                hienThiTrangThai(error.message, "error");
            }
        }
    }

    function hienThiBenhNhanDaTim(patient) {
        matchedPatient = patient;
        const details = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = `${patient.code} · ${patient.name}`;
        const demographics = document.createElement("p");
        demographics.textContent = [
            patient.gender,
            `Năm sinh ${patient.birth_year}`,
            patient.phone,
        ].join(" · ");
        details.append(name, demographics);

        const addButton = taoNut(
            "Thêm vào danh sách", "btn btn-primary", "addFoundPatient",
            patient.code, dayLocked
        );
        patientLookupResult.replaceChildren(details, addButton);
        patientLookupResult.hidden = false;
    }

    function themPhanTrang(container, pageCount, page, action) {
        container.replaceChildren();
        if (pageCount <= 1) return;

        function themNutTrang(label, target, disabled = false, current = false) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = current
                ? "btn btn-sm btn-primary"
                : "btn btn-sm btn-outline-primary";
            button.textContent = label;
            button.dataset[action] = String(target);
            button.disabled = disabled;
            if (current) button.setAttribute("aria-current", "page");
            container.append(button);
        }

        themNutTrang("< Trước", page - 1, page === 1);
        for (let target = 1; target <= pageCount; target += 1) {
            themNutTrang(String(target), target, false, target === page);
        }
        themNutTrang("Sau >", page + 1, page === pageCount);
    }

    function locBenhNhan(items) {
        const query = chuanHoaChuoi(searchTerm.trim());
        return items.filter(patient => (
            !query || chuanHoaChuoi(patient.name).includes(query)
        ));
    }

    function hienThiBenhNhan() {
        const patients = locBenhNhan(activePatients);
        const pageCount = Math.ceil(patients.length / pageSize);
        currentPage = Math.min(currentPage, Math.max(pageCount, 1));
        const start = (currentPage - 1) * pageSize;
        const visible = patients.slice(start, start + pageSize);

        patientRows.replaceChildren();
        patientCount.textContent = `${activePatients.length}/${dailyLimit}`;
        confirmedStatus.textContent = dayConfirmed
            ? `Danh sách khám ngày ${dinhDangNgay(selectedDate)} đã được xác nhận và chốt. Không thể thêm bệnh nhân mới vào ngày này.`
            : dayLocked
                ? `Ngày ${dinhDangNgay(selectedDate)} đã có lượt được xác nhận; không thể thêm bệnh nhân. Hãy xác nhận các lượt còn lại để chốt danh sách.`
                : "";
        dayLockedWarning.hidden = !dayLocked;
        if (dayLocked) {
            dayLockedWarning.textContent = dayConfirmed
                ? `Danh sách khám ngày ${dinhDangNgay(selectedDate)} đã được xác nhận và chốt. Không thể thêm bệnh nhân vào ngày này.`
                : `Ngày ${dinhDangNgay(selectedDate)} đã có lượt được xác nhận; không thể thêm bệnh nhân vào ngày này. Hãy xác nhận các lượt còn lại để hoàn tất.`;
            xoaGoiYBenhNhan();
        }
        patientCodeInput.disabled = dayLocked;
        const addButton = patientLookupResult.querySelector("[data-add-found-patient]");
        if (addButton) addButton.disabled = dayLocked;
        confirmButton.disabled = dayConfirmed;
        confirmButton.textContent = dayConfirmed ? "Danh sách đã chốt" : "Xác nhận danh sách";
        reopenButton.hidden = !dayConfirmed || selectedDate < clinicToday;
        reopenButton.disabled = selectedDate < clinicToday;

        if (!visible.length) {
            const row = document.createElement("tr");
            const cell = taoO(
                row,
                searchTerm ? "Không tìm thấy bệnh nhân phù hợp." : "Chưa có bệnh nhân trong ngày này."
            );
            cell.colSpan = 6;
            cell.className = "nurse-table-empty";
            patientRows.append(row);
        } else {
            visible.forEach((patient, index) => {
                const row = document.createElement("tr");
                taoO(row, String(start + index + 1));
                taoO(row, patient.name);
                taoO(row, patient.gender);
                taoO(row, patient.phone);
                taoO(row, String(patient.birthYear));
                const actionsCell = document.createElement("td");
                const actions = document.createElement("div");
                actions.className = "nurse-row-actions";
                actions.append(taoNutBieuTuong(
                    "Hủy lượt khám", "cancelPatient", patient.listId, patient.patientId
                ));
                actionsCell.append(actions);
                row.append(actionsCell);
                patientRows.append(row);
            });
        }

        const end = Math.min(start + pageSize, patients.length);
        listSummary.textContent = patients.length
            ? `Hiển thị ${start + 1}–${end} trên ${patients.length} kết quả · ${activePatients.length}/${dailyLimit} bệnh nhân trong danh sách`
            : `0 kết quả · ${activePatients.length}/${dailyLimit} bệnh nhân trong danh sách`;
        themPhanTrang(pagination, pageCount, currentPage, "page");
    }

    function hienThiDanhSach() {
        hienThiBenhNhan();
    }

    async function huyLuotKham(listId, patientId) {
        const patient = activePatients
            .find(item => (
                String(item.listId) === String(listId)
                && String(item.patientId) === String(patientId)
            ));
        if (!patient || !window.confirm(`Hủy lượt khám của ${patient.name}?`)) return;
        try {
            const result = await goiApi(
                `/nurse/api/lists/${patient.listId}/${patient.patientId}`, {
                method: "DELETE",
                }
            );
            await taiLaiDanhSachNgay();
            hienThiTrangThai(result.message, "success");
        } catch (error) {
            hienThiTrangThai(error.message, "error");
        }
    }

    patientCodeInput.addEventListener("input", () => {
        window.clearTimeout(patientSearchTimer);
        const requestId = ++patientLookupRequestId;
        const query = patientCodeInput.value.trim();
        xoaKetQuaTimBenhNhan();
        xoaGoiYBenhNhan();
        if (query) {
            patientSearchTimer = window.setTimeout(
                () => timBenhNhanTheoMa(query, requestId), 250
            );
        }
    });
    patientLookupForm.addEventListener("submit", async event => {
        event.preventDefault();
        window.clearTimeout(patientSearchTimer);
        patientSearchTimer = null;
        const query = patientCodeInput.value.trim();
        const requestId = ++patientLookupRequestId;
        xoaKetQuaTimBenhNhan();
        xoaGoiYBenhNhan();
        if (query) await timBenhNhanTheoMa(query, requestId);
    });
    patientSuggestions.addEventListener("click", event => {
        const button = event.target.closest("[data-select-patient]");
        if (!button) return;
        const patient = matchedPatients.find(item => item.code === button.dataset.selectPatient);
        if (!patient) return;
        window.clearTimeout(patientSearchTimer);
        patientSearchTimer = null;
        patientLookupRequestId += 1;
        patientCodeInput.value = patient.code;
        xoaGoiYBenhNhan();
        hienThiBenhNhanDaTim(patient);
    });
    patientLookupResult.addEventListener("click", async event => {
        const button = event.target.closest("[data-add-found-patient]");
        if (!button || button.disabled || !matchedPatient) return;
        if (dayLocked) {
            hienThiTrangThai(
                `Danh sách khám ngày ${dinhDangNgay(selectedDate)} đã được xác nhận và chốt; không thể thêm bệnh nhân mới.`,
                "error"
            );
            return;
        }
        button.disabled = true;
        try {
            const result = await goiApi("/nurse/api/lists", {
                method: "POST",
                body: JSON.stringify({
                    patient_code: matchedPatient.code,
                    date: selectedDate,
                }),
            });
            patientLookupForm.reset();
            patientLookupRequestId += 1;
            window.clearTimeout(patientSearchTimer);
            patientSearchTimer = null;
            xoaGoiYBenhNhan();
            xoaKetQuaTimBenhNhan();
            currentPage = 1;
            searchTerm = "";
            searchInput.value = "";
            await taiLaiDanhSachNgay();
            hienThiTrangThai(result.message, "success");
        } catch (error) {
            hienThiTrangThai(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    dateInput.value = dateInput.value || layNgayHomNay();
    selectedDate = dateInput.value;
    dateInput.addEventListener("change", async () => {
        selectedDate = dateInput.value;
        currentPage = 1;
        searchTerm = "";
        searchInput.value = "";
        activePatients = [];
        dayConfirmed = false;
        dayLocked = false;
        hienThiDanhSach();
        hienThiTrangThai("");
        try {
            await taiLaiDanhSachNgay();
        } catch (error) {
            hienThiTrangThai(error.message, "error");
        }
    });

    searchForm.addEventListener("submit", event => {
        event.preventDefault();
        searchTerm = searchInput.value.trim();
        currentPage = 1;
        hienThiDanhSach();
        hienThiTrangThai("");
    });
    nurseApp.querySelector("[data-clear-search]").addEventListener("click", () => {
        searchInput.value = "";
        searchTerm = "";
        currentPage = 1;
        hienThiDanhSach();
        hienThiTrangThai("");
        searchInput.focus();
    });

    patientRows.addEventListener("click", async event => {
        const cancelButton = event.target.closest("[data-cancel-patient-list-id]");
        if (cancelButton) {
            await huyLuotKham(
                cancelButton.dataset.cancelPatientListId,
                cancelButton.dataset.cancelPatientPatientId,
            );
        }
    });
    pagination.addEventListener("click", event => {
        const button = event.target.closest("[data-page]");
        if (!button || button.disabled) return;
        currentPage = Number(button.dataset.page);
        hienThiBenhNhan();
    });
    confirmButton.addEventListener("click", async () => {
        if (!activePatients.length) {
            hienThiTrangThai("Danh sách đang trống; hãy thêm ít nhất một bệnh nhân trước khi xác nhận.", "error");
            return;
        }
        if (dayConfirmed) {
            hienThiTrangThai("Danh sách ngày này đã được xác nhận.");
            return;
        }
        if (!window.confirm(
            `Xác nhận danh sách ngày ${dinhDangNgay(selectedDate)} gồm ${activePatients.length} bệnh nhân?`
        )) return;
        try {
            const result = await goiApi("/nurse/api/lists/confirm", {
                method: "POST",
                body: JSON.stringify({ date: selectedDate }),
            });
            await taiLaiDanhSachNgay();
            hienThiTrangThai(result.message, "success");
        } catch (error) {
            hienThiTrangThai(error.message, "error");
        }
    });

    reopenButton.addEventListener("click", async () => {
        if (!dayConfirmed) return;
        if (selectedDate < clinicToday) {
            hienThiTrangThai("Không thể mở lại danh sách của ngày đã qua.", "error");
            return;
        }
        if (!window.confirm(
            `Mở lại danh sách ngày ${dinhDangNgay(selectedDate)} để bổ sung bệnh nhân?`
        )) return;
        try {
            const result = await goiApi("/nurse/api/lists/reopen", {
                method: "POST",
                body: JSON.stringify({ date: selectedDate }),
            });
            await taiLaiDanhSachNgay();
            hienThiTrangThai(result.message, "success");
        } catch (error) {
            hienThiTrangThai(error.message, "error");
        }
    });

    taiLaiDanhSachNgay().catch(error => hienThiTrangThai(error.message, "error"));
}
