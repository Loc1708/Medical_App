function updateRoleFields(root = document) {
    const selector = root.querySelector("[data-role-select]");
    const selected = selector ? selector.value : "PATIENT";
    const phone = root.querySelector("#phone");
    if (phone) phone.required = selected === "PATIENT";
    root.querySelectorAll("[data-role-fields]").forEach(section => {
        const enabled = section.dataset.roleFields === selected;
        section.hidden = !enabled;
        section.querySelectorAll("input, select").forEach(field => {
            field.disabled = !enabled;
            field.required = enabled;
        });
    });
}

document.addEventListener("change", event => {
    if (event.target.matches("[data-role-select]")) {
        updateRoleFields(event.target.closest("form"));
    }
});
updateRoleFields();
document.addEventListener("click", event => {
    const button = event.target.closest("[data-password-toggle]");
    if (!button) return;
    const input = document.getElementById(button.dataset.passwordToggle);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Ẩn" : "Hiện";
    button.setAttribute("aria-label", show ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    button.setAttribute("aria-pressed", String(show));
});

const doctorStatus = document.querySelector("#doctor-status");
if (doctorStatus) {
    const patientQuery = document.querySelector("#patient-query");
    const patientHistoryMessage = document.querySelector("#patient-history-message");
    const patientCard = document.querySelector("#patient-card");
    const historyTable = document.querySelector("#patient-history-table");
    const historyRows = document.querySelector("#patient-history-rows");
    const medicineQuery = document.querySelector("#medicine-query");
    const medicineResults = document.querySelector("#medicine-results");
    const prescriptionItems = document.querySelector("#prescription-items");
    const draftsPanel = document.querySelector("#doctor-drafts");
    const draftsRows = document.querySelector("[data-drafts-rows]");
    const draftsEmpty = document.querySelector("[data-drafts-empty]");
    const draftsTable = document.querySelector("[data-drafts-table]");
    const draftsCount = document.querySelector("[data-drafts-count]");
    const selectedMedicines = new Map();
    let selectedPatientCode = "";
    let currentDraftId = null;
    let autosaveTimer = null;
    let autosaveInFlight = Promise.resolve();
    let autosaveRequestActive = false;
    let draftDirty = false;
    let draftRevision = 0;
    const activeDraftStorageKey = "medical-app-doctor-active-draft";

    function showDoctorStatus(message, isError = false) {
        doctorStatus.textContent = message;
        doctorStatus.classList.toggle("is-error", isError);
        doctorStatus.hidden = false;
    }

    function showPatientHistoryMessage(message) {
        patientHistoryMessage.textContent = message;
        patientHistoryMessage.hidden = false;
        historyTable.hidden = true;
    }

    function setCurrentDraftId(draftId) {
        currentDraftId = draftId;
        if (draftId) {
            sessionStorage.setItem(activeDraftStorageKey, draftId);
        } else {
            sessionStorage.removeItem(activeDraftStorageKey);
        }
    }

    patientQuery.addEventListener("input", () => {
        if (patientQuery.value.trim().toUpperCase() === selectedPatientCode.toUpperCase()) return;
        if (draftDirty && selectedPatientCode) {
            window.clearTimeout(autosaveTimer);
            if (!autosaveRequestActive) {
                autosaveInFlight = saveExam(null, "NHAP", { silent: true });
            }
        }
        const discardedDraft = currentDraftId !== null;
        const discardedForm = selectedMedicines.size > 0
            || document.querySelector("#symptoms").value.trim() !== "";
        selectedPatientCode = "";
        setCurrentDraftId(null);
        draftDirty = false;
        draftRevision += 1;
        selectedMedicines.clear();
        document.querySelector("#symptoms").value = "";
        renderPrescription();
        patientCard.hidden = true;
        showPatientHistoryMessage(
            "Hãy tìm bệnh nhân theo mã trước khi xem danh sách phiếu khám."
        );
        if (discardedDraft || discardedForm) {
            showDoctorStatus(
                "Đã đổi mã bệnh nhân; nội dung chưa lưu trong biểu mẫu đã được xóa. Bản nháp đã lưu vẫn còn trong lịch sử."
            );
        }
    });

    async function readJson(response) {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Yêu cầu không thành công.");
        return data;
    }

    function addCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
        return cell;
    }

    function showPatient(patient) {
        selectedPatientCode = patient.code;
        patientCard.hidden = false;
        document.querySelector("#patient-code").textContent = patient.code;
        document.querySelector("#patient-name").textContent = patient.name;
        document.querySelector("#patient-demographics").textContent =
            `${patient.gender} · ${patient.birth_year}`;
        document.querySelector("#patient-phone").textContent = patient.phone;
        document.querySelector("#patient-address").textContent = patient.address;
        patientQuery.value = patient.code;
        showPatientHistoryMessage(
            `Đã tìm thấy ${patient.name}. Nhấn “Xem lịch sử khám” để tải phiếu khám của bệnh nhân.`
        );
    }

    async function findPatient() {
        const code = patientQuery.value.trim();
        if (!code) {
            selectedPatientCode = "";
            patientCard.hidden = true;
            showPatientHistoryMessage(
                "Chưa nhập mã bệnh nhân. Vui lòng nhập mã bệnh nhân để xem danh sách phiếu khám."
            );
            patientQuery.focus();
            return;
        }
        try {
            const response = await fetch(
                `/doctor/api/patients?code=${encodeURIComponent(code)}`
            );
            const data = await readJson(response);
            showPatient(data.patient);
            if (document.querySelector("#symptoms").value.trim() || selectedMedicines.size) {
                scheduleDraftAutosave();
            }
        } catch (error) {
            selectedPatientCode = "";
            patientCard.hidden = true;
            showPatientHistoryMessage(error.message);
        }
    }

    async function loadPatientHistory() {
        if (!selectedPatientCode) {
            await findPatient();
            if (!selectedPatientCode) return;
        }
        try {
            const response = await fetch(
                `/doctor/api/patients/${encodeURIComponent(selectedPatientCode)}/history`
            );
            const data = await readJson(response);
            historyRows.replaceChildren();
            if (!data.exams.length) {
                showPatientHistoryMessage("Bệnh nhân chưa có phiếu khám trước đó.");
                return;
            }
            data.exams.forEach(exam => {
                const row = document.createElement("tr");
                addCell(row, exam.date);
                addCell(row, exam.id);
                addCell(row, exam.symptoms);
                addCell(row, exam.doctor);
                addCell(row, String(exam.prescription_count));
                addCell(row, exam.status === "NHAP" ? "Bản nháp" : "Đã lập");
                const action = document.createElement("td");
                if (exam.can_resume) {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "btn btn-outline-primary btn-sm";
                    button.dataset.resumeDraft = exam.id;
                    button.textContent = "Tiếp tục";
                    action.append(button);
                } else {
                    action.textContent = "—";
                }
                row.append(action);
                historyRows.append(row);
            });
            patientHistoryMessage.hidden = true;
            historyTable.hidden = false;
        } catch (error) {
            showPatientHistoryMessage(error.message);
        }
    }

    async function resumeDraft(examId) {
        try {
            const response = await fetch(`/doctor/api/exams/${encodeURIComponent(examId)}`);
            const data = await readJson(response);
            const patientResponse = await fetch(
                `/doctor/api/patients?code=${encodeURIComponent(data.exam.patient_code)}`
            );
            const patientData = await readJson(patientResponse);
            showPatient(patientData.patient);
            setCurrentDraftId(data.exam.id);
            document.querySelector("#symptoms").value = data.exam.symptoms;
            selectedMedicines.clear();
            data.exam.prescriptions.forEach(item => {
                selectedMedicines.set(item.medicine_code, {
                    code: item.medicine_code,
                    name: item.name,
                    unit: item.unit,
                    stock: item.stock,
                    quantity: item.quantity,
                    instructions: item.instructions,
                    editing: false,
                });
            });
            renderPrescription();
            showDoctorStatus(`Đang tiếp tục bản nháp ${examId}.`);
            await loadPatientHistory();
            await loadDoctorDrafts();
            document.querySelector("#exam-details").scrollIntoView({
                block: "start", behavior: "smooth",
            });
        } catch (error) {
            showDoctorStatus(error.message, true);
        }
    }

    async function loadDoctorDrafts() {
        try {
            const response = await fetch("/doctor/api/drafts");
            const data = await readJson(response);
            draftsRows.replaceChildren();
            draftsCount.textContent = String(data.drafts.length);
            draftsEmpty.hidden = data.drafts.length > 0;
            draftsTable.hidden = data.drafts.length === 0;
            data.drafts.forEach(draft => {
                const row = document.createElement("tr");
                addCell(row, draft.date);
                addCell(row, `${draft.patient_name} (${draft.patient_code})`);
                addCell(row, draft.symptoms || "Chưa nhập");
                addCell(row, String(draft.prescription_count));
                const action = document.createElement("td");
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn btn-outline-primary btn-sm";
                button.dataset.resumeDraft = draft.id;
                button.textContent = "Mở bản nháp";
                const removeButton = document.createElement("button");
                removeButton.type = "button";
                removeButton.className = "btn btn-outline-danger btn-sm ms-2";
                removeButton.dataset.deleteDraft = draft.id;
                removeButton.textContent = "Xóa";
                action.append(button, removeButton);
                row.append(action);
                draftsRows.append(row);
            });
        } catch (error) {
            draftsCount.textContent = "!";
            draftsEmpty.textContent = error.message;
            draftsEmpty.hidden = false;
            draftsTable.hidden = true;
        }
    }

    async function restoreActiveDraft() {
        const draftId = sessionStorage.getItem(activeDraftStorageKey);
        if (!draftId) return;
        await resumeDraft(draftId);
    }

    async function deleteDraft(draftId, button) {
        if (!window.confirm("Bạn có chắc muốn xóa bản nháp này? Thao tác này không thể hoàn tác.")) {
            return;
        }
        button.disabled = true;
        try {
            if (draftId === currentDraftId) {
                window.clearTimeout(autosaveTimer);
                await autosaveInFlight;
            }
            const response = await fetch(
                `/doctor/api/drafts/${encodeURIComponent(draftId)}`,
                {
                    method: "DELETE",
                    headers: {
                        "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
                    },
                }
            );
            const result = await readJson(response);
            if (draftId === currentDraftId) {
                setCurrentDraftId(null);
                draftDirty = false;
                draftRevision += 1;
                document.querySelector("#symptoms").value = "";
                selectedMedicines.clear();
                renderPrescription();
            }
            showDoctorStatus(result.message);
            await loadDoctorDrafts();
            if (selectedPatientCode) await loadPatientHistory();
        } catch (error) {
            showDoctorStatus(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function searchMedicines() {
        const keyword = medicineQuery.value.trim();
        medicineResults.replaceChildren();
        if (keyword.length < 2) {
            const row = document.createElement("tr");
            const cell = addCell(row, "Nhập ít nhất 2 ký tự để tìm thuốc.");
            cell.colSpan = 5;
            cell.className = "doctor-table-empty";
            medicineResults.append(row);
            return;
        }
        try {
            const response = await fetch(
                `/doctor/api/medicines?q=${encodeURIComponent(keyword)}`
            );
            const data = await readJson(response);
            if (!data.medicines.length) {
                const row = document.createElement("tr");
                const cell = addCell(row, "Không tìm thấy thuốc còn tồn kho phù hợp.");
                cell.colSpan = 5;
                cell.className = "doctor-table-empty";
                medicineResults.append(row);
                return;
            }
            data.medicines.forEach(medicine => {
                const row = document.createElement("tr");
                addCell(row, medicine.code);
                addCell(row, medicine.name);
                addCell(row, medicine.unit);
                addCell(row, String(medicine.stock));
                const action = document.createElement("td");
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn btn-outline-primary btn-sm";
                button.dataset.addMedicine = medicine.code;
                button.textContent = "Thêm";
                action.append(button);
                row.append(action);
                medicineResults.append(row);
            });
        } catch (error) {
            showDoctorStatus(error.message, true);
        }
    }

    function renderPrescription() {
        prescriptionItems.replaceChildren();
        if (!selectedMedicines.size) {
            const row = document.createElement("tr");
            const cell = addCell(row, "Chưa có thuốc trong đơn.");
            cell.colSpan = 5;
            cell.className = "doctor-table-empty";
            prescriptionItems.append(row);
            return;
        }
        selectedMedicines.forEach(medicine => {
            const row = document.createElement("tr");
            addCell(row, `${medicine.name} (${medicine.code})`);
            addCell(row, medicine.unit);

            const quantityCell = document.createElement("td");
            const quantity = document.createElement("input");
            quantity.type = "number";
            quantity.min = "1";
            quantity.max = String(medicine.stock);
            quantity.value = String(medicine.editQuantity ?? medicine.quantity);
            quantity.disabled = !medicine.editing;
            quantity.className = "form-control form-control-sm";
            quantity.setAttribute("aria-label", `Số lượng ${medicine.name}`);
            quantity.addEventListener("input", () => {
                medicine.editQuantity = Number(quantity.value);
            });
            quantityCell.append(quantity);
            row.append(quantityCell);

            const instructionCell = document.createElement("td");
            const instructions = document.createElement("input");
            instructions.type = "text";
            instructions.maxLength = 255;
            instructions.value = medicine.editInstructions ?? medicine.instructions;
            instructions.disabled = !medicine.editing;
            instructions.placeholder = "Nhập cách dùng";
            instructions.className = "form-control form-control-sm";
            instructions.setAttribute("aria-label", `Cách dùng ${medicine.name}`);
            instructions.addEventListener("input", () => {
                medicine.editInstructions = instructions.value;
            });

            instructionCell.append(instructions);
            row.append(instructionCell);

            const actionCell = document.createElement("td");
            const actionGroup = document.createElement("div");
            actionGroup.className = "doctor-medicine-actions";
            const edit = document.createElement("button");
            edit.type = "button";
            edit.className = "btn btn-outline-primary btn-sm";
            edit.dataset.editMedicine = medicine.code;
            edit.textContent = medicine.editing ? "Lưu" : "Chỉnh sửa";
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn btn-outline-danger btn-sm";
            remove.textContent = "Xóa";
            remove.setAttribute("aria-label", `Xóa ${medicine.name} khỏi đơn`);
            remove.dataset.removeMedicine = medicine.code;
            actionGroup.append(edit, remove);
            actionCell.append(actionGroup);
            row.append(actionCell);
            prescriptionItems.append(row);
        });
    }

    function scheduleDraftAutosave() {
        if (!selectedPatientCode) return;
        draftDirty = true;
        draftRevision += 1;
        window.clearTimeout(autosaveTimer);
        autosaveTimer = window.setTimeout(() => {
            autosaveInFlight = autosaveInFlight.then(() => {
                if (!draftDirty) return true;
                autosaveRequestActive = true;
                return saveExam(null, "NHAP", { silent: true }).finally(() => {
                    autosaveRequestActive = false;
                });
            });
        }, 500);
    }

    document.querySelector("#symptoms").addEventListener("input", scheduleDraftAutosave);
    window.addEventListener("pagehide", () => {
        window.clearTimeout(autosaveTimer);
        if (!draftDirty || !selectedPatientCode
            || autosaveRequestActive
            || Array.from(selectedMedicines.values()).some(item => item.editing)) {
            return;
        }
        autosaveRequestActive = true;
        autosaveInFlight = saveExam(null, "NHAP", {
            silent: true, keepalive: true,
        }).finally(() => {
            autosaveRequestActive = false;
        });
    });

    document.addEventListener("click", event => {
        const draftsButton = event.target.closest("[data-toggle-drafts]");
        const searchButton = event.target.closest("[data-patient-search]");
        const historyButton = event.target.closest("[data-patient-history]");
        const medicineButton = event.target.closest("[data-medicine-search]");
        const addButton = event.target.closest("[data-add-medicine]");
        const editMedicineButton = event.target.closest("[data-edit-medicine]");
        const removeMedicineButton = event.target.closest("[data-remove-medicine]");
        const resumeButton = event.target.closest("[data-resume-draft]");
        const deleteDraftButton = event.target.closest("[data-delete-draft]");
        const saveDraftButton = event.target.closest("[data-save-draft]");
        const saveExamButton = event.target.closest("[data-save-exam]");
        if (draftsButton) {
            const isOpening = draftsPanel.hidden;
            draftsPanel.hidden = !isOpening;
            draftsButton.setAttribute("aria-expanded", String(isOpening));
            draftsButton.classList.toggle("doctor-drafts-open", isOpening);
            loadDoctorDrafts();
            if (isOpening) {
                draftsPanel.scrollIntoView({ block: "start", behavior: "smooth" });
            }
            return;
        }
        if (searchButton) {
            findPatient();
            return;
        }
        if (historyButton) {
            loadPatientHistory();
            return;
        }
        if (medicineButton) {
            searchMedicines();
            return;
        }
        if (resumeButton) {
            resumeDraft(resumeButton.dataset.resumeDraft);
            return;
        }
        if (deleteDraftButton) {
            deleteDraft(deleteDraftButton.dataset.deleteDraft, deleteDraftButton);
            return;
        }
        if (editMedicineButton) {
            const medicine = selectedMedicines.get(editMedicineButton.dataset.editMedicine);
            if (!medicine) return;
            if (medicine.editing) {
                const quantity = medicine.editQuantity;
                const instructions = medicine.editInstructions ?? "";
                if (!Number.isInteger(quantity) || quantity < 1 || quantity > medicine.stock
                    || instructions.length > 255) {
                    showDoctorStatus("Số lượng phải nằm trong tồn kho và cách dùng không vượt quá 255 ký tự.", true);
                    return;
                }
                medicine.quantity = quantity;
                medicine.instructions = instructions.trim();
                delete medicine.editQuantity;
                delete medicine.editInstructions;
                medicine.editing = false;
                scheduleDraftAutosave();
            } else {
                medicine.editQuantity = medicine.quantity;
                medicine.editInstructions = medicine.instructions;
                medicine.editing = true;
            }
            renderPrescription();
            return;
        }
        if (removeMedicineButton) {
            selectedMedicines.delete(removeMedicineButton.dataset.removeMedicine);
            renderPrescription();
            scheduleDraftAutosave();
            return;
        }
        if (addButton) {
            const row = addButton.closest("tr");
            const cells = row.querySelectorAll("td");
            const code = addButton.dataset.addMedicine;
            if (!selectedMedicines.has(code)) {
                selectedMedicines.set(code, {
                    code,
                    name: cells[1].textContent,
                    unit: cells[2].textContent,
                    stock: Number(cells[3].textContent),
                    quantity: 1,
                    instructions: "",
                    editing: false,
                });
                renderPrescription();
                scheduleDraftAutosave();
            }
            return;
        }
        if (saveDraftButton) {
            saveExam(saveDraftButton, "NHAP");
            return;
        }
        if (saveExamButton) saveExam(saveExamButton, "DA_LAP");
    });

    async function saveExam(button, status, { silent = false, keepalive = false } = {}) {
        if (status === "DA_LAP" || (status === "NHAP" && !silent)) {
            window.clearTimeout(autosaveTimer);
            await autosaveInFlight;
            window.clearTimeout(autosaveTimer);
        }
        if (!selectedPatientCode) {
            if (!silent) showDoctorStatus("Hãy tìm bệnh nhân trước khi lưu phiếu.", true);
            patientQuery.focus();
            return false;
        }
        const symptoms = document.querySelector("#symptoms").value.trim();
        if (status === "DA_LAP" && !symptoms) {
            if (!silent) showDoctorStatus("Vui lòng nhập triệu chứng trước khi lập phiếu.", true);
            document.querySelector("#symptoms").focus();
            return false;
        }
        const prescriptions = Array.from(selectedMedicines.values());
        if (prescriptions.some(item => item.editing)) {
            if (!silent) {
                showDoctorStatus("Hãy bấm “Lưu” ở từng dòng thuốc đang chỉnh sửa trước khi lưu phiếu.", true);
            }
            return false;
        }
        if (prescriptions.some(item =>
            !Number.isInteger(item.quantity) || item.quantity < 1
            || item.quantity > item.stock
            || (status === "DA_LAP" && !item.instructions.trim())
        )) {
            if (!silent) {
                showDoctorStatus("Kiểm tra lại số lượng tồn kho và cách dùng của từng thuốc.", true);
            }
            return false;
        }
        if (button) button.disabled = true;
        if (status === "NHAP") autosaveRequestActive = true;
        const requestRevision = draftRevision;
        const requestPatientCode = selectedPatientCode;
        const requestDraftId = currentDraftId;
        try {
            const response = await fetch("/doctor/api/exams", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
                },
                keepalive,
                body: JSON.stringify({
                    patient_code: requestPatientCode,
                    symptoms,
                    status,
                    draft_id: requestDraftId,
                    prescriptions: prescriptions.map(item => ({
                        medicine_code: item.code,
                        quantity: item.quantity,
                        instructions: item.instructions.trim(),
                    })),
                }),
            });
            const result = await readJson(response);
            if (status === "DA_LAP") {
                if (requestPatientCode === selectedPatientCode) {
                    setCurrentDraftId(null);
                    draftDirty = false;
                    document.querySelector("#symptoms").value = "";
                    selectedMedicines.clear();
                    renderPrescription();
                }
            } else if (requestPatientCode === selectedPatientCode) {
                setCurrentDraftId(result.exam_id);
                if (requestRevision === draftRevision) {
                    draftDirty = false;
                } else {
                    scheduleDraftAutosave();
                }
            }
            if (!keepalive) {
                showDoctorStatus(
                    silent ? `Đã tự lưu bản nháp ${result.exam_id}.`
                        : `${result.message} Mã phiếu: ${result.exam_id}`
                );
                if (requestPatientCode === selectedPatientCode) {
                    await loadPatientHistory();
                }
                await loadDoctorDrafts();
            }
            return true;
        } catch (error) {
            if (!keepalive) showDoctorStatus(error.message, true);
            return false;
        } finally {
            if (button) button.disabled = false;
            if (status === "NHAP") autosaveRequestActive = false;
        }
    }

    loadDoctorDrafts();
    restoreActiveDraft();

    document.addEventListener("keydown", event => {
        if (event.key !== "Enter") return;
        if (event.target === patientQuery) {
            event.preventDefault();
            findPatient();
        } else if (event.target === medicineQuery) {
            event.preventDefault();
            searchMedicines();
        }
    });

    document.addEventListener("click", event => {
        const button = event.target.closest("[data-doctor-prototype]");
        if (!button) return;
        showDoctorStatus(button.dataset.doctorPrototype);
        doctorStatus.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
}

const modalElement = document.querySelector("#account-modal");
if (modalElement) {
    const content = modalElement.querySelector(".modal-content");
    const errorBox = document.querySelector("#modal-error");
    let loading = false;
    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        errorBox.scrollIntoView({ block: "nearest" });
    }
    document.addEventListener("click", async event => {
        const link = event.target.closest("[data-account-modal]");
        if (!link || !window.bootstrap || event.ctrlKey || event.metaKey || event.shiftKey) return;
        event.preventDefault();
        if (loading) return;
        loading = true;
        errorBox.hidden = true;
        const url = new URL(link.href);
        url.searchParams.set("modal", "1");
        try {
            const response = await fetch(url);
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error("Không tải được biểu mẫu. Vui lòng tải lại trang hoặc thử lại.");
            content.innerHTML = await response.text();
            updateRoleFields(content);
            bootstrap.Modal.getOrCreateInstance(modalElement).show();
        } catch (error) {
            showError(error.message);
        } finally {
            loading = false;
        }
    });
    document.addEventListener("submit", async event => {
        const form = event.target;
        if (!form.matches("[data-modal-form]")) return;
        event.preventDefault();
        if (form.dataset.saving) return;
        form.dataset.saving = "true";
        const button = form.querySelector('button:not([type="button"])');
        button.disabled = true;
        errorBox.hidden = true;
        try {
            const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
            if (response.redirected) {
                window.location.assign(response.url);
            } else if (response.status === 204) {
                window.location.reload();
            } else if (response.status === 422) {
                content.innerHTML = await response.text();
                updateRoleFields(content);
                content.querySelector("[role='alert']")?.scrollIntoView({ block: "nearest" });
            } else {
                throw new Error("Không lưu được tài khoản. Vui lòng kiểm tra kết quả trước khi thử lại.");
            }
        } catch (error) {
            showError(error.message);
            bootstrap.Modal.getInstance(modalElement)?.hide();
        } finally {
            button.disabled = false;
            delete form.dataset.saving;
        }
    });
}

function searchPatientByCode() {
    // 1. Lấy từ khóa từ ô input
    let kw = document.getElementById('kw').value.trim();
    let list = document.getElementById('list');

    if (!kw) {
        list.innerHTML = '';
        list.classList.add('d-none');
        return;
    }
    fetch(`/cashier/api/dashboard?kw=${encodeURIComponent(kw)}`)
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error);
                });
            }
            return response.json();
        })
        .then(data => {
            let patients = data.patients || [];

            if (patients.length > 0) {
                let html = '';

                patients.forEach(p => {
                    html += `
                        <li class="list-group-item list-group-item-action"
                            style="cursor: pointer;"
                            onclick="selectPatient('${p.code}', '${p.name}')">
                            <strong>${p.name}</strong>
                            <small class="text-muted">(${p.code})</small>
                        </li>`;
                });
                list.innerHTML = html;
                list.classList.remove('d-none');
            }
        })
        .catch(err => {
            list.innerHTML = `<li class="list-group-item text-danger">${err.message}</li>`;
            list.classList.remove('d-none');
        });
}