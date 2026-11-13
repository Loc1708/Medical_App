(() => {
    const warning = document.querySelector("#chart-error");
    if (!window.Chart) {
        warning.textContent = "Không tải được Chart.js. Bạn vẫn có thể xem số liệu trong các bảng bên dưới.";
        warning.hidden = false;
        return;
    }
    const data = JSON.parse(document.querySelector("#report-data").textContent);
    const formatMoney = value => new Intl.NumberFormat("vi-VN").format(value) + " VNĐ";
    new Chart(document.querySelector("#revenue-chart"), {
        type: "bar",
        data: {
            labels: data.days,
            datasets: [
                {label: "Doanh thu (VNĐ)", data: data.revenue, backgroundColor: "#5bb9a6", yAxisID: "money"},
                {type: "line", label: "Số bệnh nhân", data: data.patients, borderColor: "#d59e2a", yAxisID: "patients", tension: 0.2}
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                money: {beginAtZero: true, position: "left", ticks: {callback: formatMoney}},
                patients: {beginAtZero: true, position: "right", ticks: {precision: 0}, grid: {drawOnChartArea: false}}
            }
        }
    });
    const medicineCanvas = document.querySelector("#medicine-chart");
    if (medicineCanvas) {
        new Chart(medicineCanvas, {
            type: "bar",
            data: {
                labels: data.medicines,
                datasets: [
                    {label: "Số lần dùng (phiếu khám)", data: data.uses, backgroundColor: "#1a5f5a"}
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {y: {beginAtZero: true, ticks: {precision: 0}}},
                plugins: {tooltip: {callbacks: {
                    afterLabel: context => "Số lượng đã kê: " + data.quantities[context.dataIndex]
                }}}
            }
        });
    }
})();
