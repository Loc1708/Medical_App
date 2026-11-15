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
    const waitingRows = nurseApp.querySelector("[data-waiting-rows]");
    const pagination = nurseApp.querySelector("[data-pagination]");
    const waitingPagination = nurseApp.querySelector("[data-waiting-pagination]");
    const listSummary = nurseApp.querySelector("[data-list-summary]");
    const waitingSummary = nurseApp.querySelector("[data-waiting-summary]");
    const patientCount = nurseApp.querySelector("[data-patient-count]");
    const waitingCount = nurseApp.querySelector("[data-waiting-count]");
    const approvalTarget = nurseApp.querySelector("[data-approval-target]");
    const status = nurseApp.querySelector("[data-nurse-status]");
    const confirmedStatus = nurseApp.querySelector("[data-confirmed-status]");
    const confirmButton = nurseApp.querySelector("[data-confirm-list]");
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    let selectedDate = "";
    let clinicToday = todayValue();
    let currentPage = 1;
    let currentWaitingPage = 1;
    let searchTerm = "";
    let dailyLimit = 0;
    let patientSearchTimer = null;
    let patientLookupRequestId = 0;
    let matchedPatients = [];
    let matchedPatient = null;
    let activePatients = [];
    let waitingPatients = [];
    let dayConfirmed = false;
    let dayLocked = false;

    function todayValue() {
        const now = new Date();
        return [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
        ].join("-");
    }

    function showStatus(message, kind = "info") {
        status.textContent = message;
        status.classList.toggle("is-error", kind === "error");
        status.classList.toggle("is-success", kind === "success");
        status.hidden = !message;
    }

    function normalize(value) {
        return value.toLocaleLowerCase("vi")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d");
    }

    function formatDate(value) {
        const [year, month, day] = value.split("-").map(Number);
        return new Intl.DateTimeFormat("vi-VN").format(new Date(year, month - 1, day));
    }

    async function requestApi(url, options = {}) {
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

    async function refreshDay() {
        const data = await requestApi(
            `/nurse/api/lists?date=${encodeURIComponent(selectedDate)}`
        );
        dailyLimit = data.limit;
        clinicToday = data.today;
        activePatients = data.active;
        waitingPatients = data.waiting;
        dayConfirmed = data.confirmed;
        dayLocked = data.locked;
        nurseApp.dataset.maxPatients = String(dailyLimit);
        limitLabel.textContent = `Giới hạn: ${dailyLimit} bệnh nhân/ngày`;
        renderAll();
    }

    function makeCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
        return cell;
    }

    function makeButton(label, className, action, id, disabled = false) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className;
        button.dataset[action] = id;
        button.textContent = label;
        button.disabled = disabled;
        return button;
    }

    function makeIconButton(label, action, id) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "catalog-icon";
        button.dataset[action] = id;
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

    function clearPatientLookup() {
        matchedPatient = null;
        patientLookupResult.replaceChildren();
        patientLookupResult.hidden = true;
    }

    function clearPatientSuggestions() {
        matchedPatients = [];
        patientSuggestions.replaceChildren();
        patientSuggestions.hidden = true;
    }

    function renderPatientSuggestions(patients) {
        if (dayLocked) {
            clearPatientSuggestions();
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
                const button = makeButton(
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

    async function searchPatientsByCode(query, requestId) {
        if (dayLocked) return;
        try {
            const url = new URL("/nurse/api/patients", window.location.origin);
            url.searchParams.set("q", query);
            const data = await requestApi(url);
            if (requestId === patientLookupRequestId) {
                renderPatientSuggestions(data.patients);
            }
        } catch (error) {
            if (requestId === patientLookupRequestId) {
                showStatus(error.message, "error");
            }
        }
    }

    function showPatientLookup(patient) {
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

        const addButton = makeButton(
            "Thêm vào danh sách", "btn btn-primary", "addFoundPatient",
            patient.code, dayLocked
        );
        patientLookupResult.replaceChildren(details, addButton);
        patientLookupResult.hidden = false;
    }

    function addPagination(container, pageCount, page, action) {
        container.replaceChildren();
        if (pageCount <= 1) return;

        function addPageButton(label, target, disabled = false, current = false) {
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

        addPageButton("< Trước", page - 1, page === 1);
        for (let target = 1; target <= pageCount; target += 1) {
            addPageButton(String(target), target, false, target === page);
        }
        addPageButton("Sau >", page + 1, page === pageCount);
    }

    function filtered(items) {
        const query = normalize(searchTerm.trim());
        return items.filter(patient => (
            !query || normalize(patient.name).includes(query)
        ));
    }

    function renderPatients() {
        const patients = filtered(activePatients);
        const pageCount = Math.ceil(patients.length / pageSize);
        currentPage = Math.min(currentPage, Math.max(pageCount, 1));
        const start = (currentPage - 1) * pageSize;
        const visible = patients.slice(start, start + pageSize);

        patientRows.replaceChildren();
        patientCount.textContent = `${activePatients.length}/${dailyLimit}`;
        confirmedStatus.textContent = dayConfirmed
            ? `Danh sách khám ngày ${formatDate(selectedDate)} đã được xác nhận và chốt. Không thể thêm bệnh nhân mới vào ngày này.`
            : dayLocked
                ? `Ngày ${formatDate(selectedDate)} đã có lượt được xác nhận; không thể thêm bệnh nhân. Hãy xác nhận các lượt còn lại để chốt danh sách.`
                : "";
        dayLockedWarning.hidden = !dayLocked;
        if (dayLocked) {
            dayLockedWarning.textContent = dayConfirmed
                ? `Danh sách khám ngày ${formatDate(selectedDate)} đã được xác nhận và chốt. Không thể thêm hoặc duyệt thêm bệnh nhân vào ngày này.`
                : `Ngày ${formatDate(selectedDate)} đã có lượt được xác nhận; không thể thêm hoặc duyệt thêm bệnh nhân vào ngày này. Hãy xác nhận các lượt còn lại để hoàn tất.`;
            clearPatientSuggestions();
        }
        patientCodeInput.disabled = dayLocked;
        const addButton = patientLookupResult.querySelector("[data-add-found-patient]");
        if (addButton) addButton.disabled = dayLocked;
        confirmButton.disabled = dayConfirmed;
        confirmButton.textContent = dayConfirmed ? "Danh sách đã chốt" : "Xác nhận danh sách";

        if (!visible.length) {
            const row = document.createElement("tr");
            const cell = makeCell(
                row,
                searchTerm ? "Không tìm thấy bệnh nhân phù hợp." : "Chưa có bệnh nhân trong ngày này."
            );
            cell.colSpan = 6;
            cell.className = "nurse-table-empty";
            patientRows.append(row);
        } else {
            visible.forEach((patient, index) => {
                const row = document.createElement("tr");
                makeCell(row, String(start + index + 1));
                makeCell(row, patient.name);
                makeCell(row, patient.gender);
                makeCell(row, patient.phone);
                makeCell(row, String(patient.birthYear));
                const actionsCell = document.createElement("td");
                const actions = document.createElement("div");
                actions.className = "nurse-row-actions";
                actions.append(makeIconButton("Hủy lượt khám", "cancelPatient", patient.id));
                actionsCell.append(actions);
                row.append(actionsCell);
                patientRows.append(row);
            });
        }

        const end = Math.min(start + pageSize, patients.length);
        listSummary.textContent = patients.length
            ? `Hiển thị ${start + 1}–${end} trên ${patients.length} kết quả · ${activePatients.length}/${dailyLimit} bệnh nhân trong danh sách`
            : `0 kết quả · ${activePatients.length}/${dailyLimit} bệnh nhân trong danh sách`;
        addPagination(pagination, pageCount, currentPage, "page");
    }

    function renderWaiting() {
        const patients = filtered(waitingPatients);
        const pageCount = Math.ceil(patients.length / pageSize);
        currentWaitingPage = Math.min(currentWaitingPage, Math.max(pageCount, 1));
        const start = (currentWaitingPage - 1) * pageSize;
        const visible = patients.slice(start, start + pageSize);

        waitingRows.replaceChildren();
        waitingCount.textContent = String(waitingPatients.length);
        const targetIsPast = selectedDate < clinicToday;
        approvalTarget.textContent = dayLocked
            ? `Ngày khám đích ${formatDate(selectedDate)} đã được chốt; không thể duyệt thêm bệnh nhân.`
            : targetIsPast
                ? "Không thể duyệt vào ngày đã qua."
                : `Ngày khám đích: ${formatDate(selectedDate)}`;
        if (!visible.length) {
            const row = document.createElement("tr");
            const cell = makeCell(
                row,
                searchTerm ? "Không tìm thấy bệnh nhân phù hợp." : "Chưa có bệnh nhân chờ duyệt."
            );
            cell.colSpan = 6;
            cell.className = "nurse-table-empty";
            waitingRows.append(row);
        } else {
            visible.forEach((patient, index) => {
                const row = document.createElement("tr");
                makeCell(row, String(start + index + 1));
                makeCell(row, patient.name);
                makeCell(row, formatDate(patient.examDate));
                makeCell(row, patient.phone);
                makeCell(row, String(patient.birthYear));
                const actionsCell = document.createElement("td");
                const actions = document.createElement("div");
                actions.className = "nurse-row-actions";
                actions.append(
                    makeButton(
                        "Duyệt vào ngày đã chọn", "btn btn-sm btn-outline-success",
                        "approvePatient", patient.id,
                        dayLocked || targetIsPast || activePatients.length >= dailyLimit
                    ),
                    makeIconButton("Hủy lượt khám", "cancelPatient", patient.id)
                );
                actionsCell.append(actions);
                row.append(actionsCell);
                waitingRows.append(row);
            });
        }

        const end = Math.min(start + pageSize, patients.length);
        waitingSummary.textContent = patients.length
            ? `Hiển thị ${start + 1}–${end} trên ${patients.length} bệnh nhân đang chờ`
            : "Chưa có bệnh nhân chờ duyệt.";
        addPagination(waitingPagination, pageCount, currentWaitingPage, "waitingPage");
    }

    function renderAll() {
        renderPatients();
        renderWaiting();
    }

    async function cancelPatient(patientId) {
        const patient = [...activePatients, ...waitingPatients]
            .find(item => String(item.id) === String(patientId));
        if (!patient || !window.confirm(`Hủy lượt khám của ${patient.name}?`)) return;
        try {
            const result = await requestApi(`/nurse/api/lists/${patient.id}`, {
                method: "DELETE",
            });
            await refreshDay();
            showStatus(result.message, "success");
        } catch (error) {
            showStatus(error.message, "error");
        }
    }

    async function approvePatient(patientId) {
        try {
            const result = await requestApi(`/nurse/api/lists/${patientId}/approve`, {
                method: "POST",
                body: JSON.stringify({ date: selectedDate }),
            });
            await refreshDay();
            showStatus(result.message, "success");
        } catch (error) {
            showStatus(error.message, "error");
        }
    }

    patientCodeInput.addEventListener("input", () => {
        window.clearTimeout(patientSearchTimer);
        const requestId = ++patientLookupRequestId;
        const query = patientCodeInput.value.trim();
        clearPatientLookup();
        clearPatientSuggestions();
        if (query) {
            patientSearchTimer = window.setTimeout(
                () => searchPatientsByCode(query, requestId), 250
            );
        }
    });
    patientLookupForm.addEventListener("submit", async event => {
        event.preventDefault();
        window.clearTimeout(patientSearchTimer);
        patientSearchTimer = null;
        const query = patientCodeInput.value.trim();
        const requestId = ++patientLookupRequestId;
        clearPatientLookup();
        clearPatientSuggestions();
        if (query) await searchPatientsByCode(query, requestId);
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
        clearPatientSuggestions();
        showPatientLookup(patient);
    });
    patientLookupResult.addEventListener("click", async event => {
        const button = event.target.closest("[data-add-found-patient]");
        if (!button || button.disabled || !matchedPatient) return;
        if (dayLocked) {
            showStatus(
                `Danh sách khám ngày ${formatDate(selectedDate)} đã được xác nhận và chốt; không thể thêm bệnh nhân mới.`,
                "error"
            );
            return;
        }
        button.disabled = true;
        const patientName = matchedPatient.name;
        const statusKind = activePatients.length >= dailyLimit ? "info" : "success";
        try {
            const result = await requestApi("/nurse/api/lists", {
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
            clearPatientSuggestions();
            clearPatientLookup();
            currentPage = 1;
            currentWaitingPage = 1;
            searchTerm = "";
            searchInput.value = "";
            await refreshDay();
            showStatus(
                result.patient.status === "CHO_DUYET"
                    ? `${patientName} đã được thêm vào danh sách chờ duyệt.`
                    : result.message,
                result.patient.status === "CHO_DUYET" ? "info" : statusKind
            );
        } catch (error) {
            showStatus(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    dateInput.value = dateInput.value || todayValue();
    selectedDate = dateInput.value;
    dateInput.addEventListener("change", async () => {
        selectedDate = dateInput.value;
        currentPage = 1;
        currentWaitingPage = 1;
        searchTerm = "";
        searchInput.value = "";
        activePatients = [];
        waitingPatients = [];
        dayConfirmed = false;
        dayLocked = false;
        renderAll();
        showStatus("");
        try {
            await refreshDay();
        } catch (error) {
            showStatus(error.message, "error");
        }
    });

    searchForm.addEventListener("submit", event => {
        event.preventDefault();
        searchTerm = searchInput.value.trim();
        currentPage = 1;
        currentWaitingPage = 1;
        renderAll();
        showStatus("");
    });
    nurseApp.querySelector("[data-clear-search]").addEventListener("click", () => {
        searchInput.value = "";
        searchTerm = "";
        currentPage = 1;
        currentWaitingPage = 1;
        renderAll();
        showStatus("");
        searchInput.focus();
    });

    patientRows.addEventListener("click", async event => {
        const cancelButton = event.target.closest("[data-cancel-patient]");
        if (cancelButton) await cancelPatient(cancelButton.dataset.cancelPatient);
    });
    waitingRows.addEventListener("click", async event => {
        const cancelButton = event.target.closest("[data-cancel-patient]");
        const approveButton = event.target.closest("[data-approve-patient]");
        if (cancelButton) await cancelPatient(cancelButton.dataset.cancelPatient);
        if (approveButton && !approveButton.disabled) {
            await approvePatient(approveButton.dataset.approvePatient);
        }
    });

    pagination.addEventListener("click", event => {
        const button = event.target.closest("[data-page]");
        if (!button || button.disabled) return;
        currentPage = Number(button.dataset.page);
        renderPatients();
    });
    waitingPagination.addEventListener("click", event => {
        const button = event.target.closest("[data-waiting-page]");
        if (!button || button.disabled) return;
        currentWaitingPage = Number(button.dataset.waitingPage);
        renderWaiting();
    });

    confirmButton.addEventListener("click", async () => {
        if (!activePatients.length) {
            showStatus("Danh sách đang trống; hãy thêm ít nhất một bệnh nhân trước khi xác nhận.", "error");
            return;
        }
        if (dayConfirmed) {
            showStatus("Danh sách ngày này đã được xác nhận.");
            return;
        }
        if (!window.confirm(
            `Xác nhận danh sách ngày ${formatDate(selectedDate)} gồm ${activePatients.length} bệnh nhân?`
        )) return;
        try {
            const result = await requestApi("/nurse/api/lists/confirm", {
                method: "POST",
                body: JSON.stringify({ date: selectedDate }),
            });
            await refreshDay();
            showStatus(result.message, "success");
        } catch (error) {
            showStatus(error.message, "error");
        }
    });

    refreshDay().catch(error => showStatus(error.message, "error"));
}
