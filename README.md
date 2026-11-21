# Medical_App

Ứng dụng quản lý phòng mạch tư. Cấu trúc bám theo dự án mẫu
`cs2401saleapp\saleapp\eapp` của lớp, giữ tên package là `app`
ngay tại gốc repository.

## Cấu trúc

```text
Medical_App\
├── app\
│   ├── __init__.py
│   ├── index.py
│   ├── models.py
│   ├── dao.py
│   ├── utils.py
│   ├── migration.py
│   ├── routes\
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── cashier.py
│   │   ├── doctor.py
│   │   ├── nurse.py
│   │   └── patient.py
│   ├── static\
│   │   ├── css\
│   │   ├── images\
│   │   └── js\
│   │       └── admin\
│   │           ├── catalog.js
│   │           └── reports.js
│   └── templates\
│       ├── index.html
│       ├── auth\
│       ├── admin\
│       ├── components\
│       ├── patient\
│       ├── nurse\
│       ├── cashier\
│       ├── doctor\
│       └── layout\
│           ├── base.html
│           ├── header.html
│           ├── footer.html
│           └── sidebar.html
├── tests\
├── .gitignore
├── README.md
└── requirements.txt
```

- `app\__init__.py`: khởi tạo đối tượng Flask `app`, cấu hình và SQLAlchemy `db`.
- `app\index.py`: route dùng chung, xác thực, điều hướng dashboard và xử lý lỗi.
- `app\routes\`: route/API nghiệp vụ theo từng vai trò, bao gồm cả quản trị.
- `app\models.py`: khai báo các model và quan hệ CSDL.
- `app\dao.py`: truy vấn, thêm, sửa và xóa dữ liệu.
- `app\utils.py`: hàm tính toán và tiện ích dùng chung.
- `app\routes\admin.py`: các route quản trị tài khoản, thuốc, đơn vị, quy định và báo cáo.
- `app\migration.py`: chuyển khóa UUID cũ sang số nguyên, giữ bảng dự phòng.
- `templates`: giao diện Jinja2; `layout` chứa bố cục dùng chung,
  `components` chứa thông báo, khung modal, form tài khoản và ô mật khẩu tái sử dụng.
- `static`: CSS, JavaScript và hình ảnh.

Đợt hiện tại triển khai tài khoản/hồ sơ và luồng bác sĩ (tra cứu bệnh nhân,
lịch sử khám, tra cứu thuốc, lưu nháp và lập phiếu), quản lý thuốc/đơn vị,
quy định, báo cáo tháng và thanh toán.
Không tạo lại các thư mục `controllers`, `models`, `services` của bộ khung cũ.
Controller được thể hiện bằng các hàm route trong `index.py` và `routes\` theo vai trò;
truy cập dữ liệu ở `dao.py`. JavaScript chung nằm trong `static/js/main.js`;
mỗi vai trò có file riêng (bác sĩ `doctor.js`, y tá `nurse.js`, thu ngân `cashier.js`),
các thao tác quản trị tài khoản nằm trong `static/js/admin/accounts.js`.
Các hàm DAO chính dùng tên gần với sơ đồ lớp, ví dụ `dangKyKham`,
`xacNhanDanhSach`, `lapPhieuKham`, `themThuoc` và `suaThuoc`. Chúng là hàm
trong DAO, không phải phương thức của các lớp entity trên sơ đồ.
Các hàm do ứng dụng định nghĩa được đặt tên tiếng Việt không dấu. Tên bắt buộc
theo Flask-Login, tên endpoint, lệnh CLI và tên kiểm thử được giữ để tương thích.
Frontend dùng HTML/Jinja2, Bootstrap 5.0.2 và JavaScript thuần; không có npm build.
Logo trên header và favicon của các trang dùng chung biểu tượng
`static\images\2.png`.
Chart.js 4.4.1 qua CDN được dùng cho báo cáo. Flask-Admin cung cấp trang
`/admin-console` chỉ dành cho ADMIN để xem tài khoản, bệnh nhân, nhân viên,
thuốc, hóa đơn và quy định; mật khẩu không được hiển thị. Trang này chỉ cho xem,
không hỗ trợ thêm, sửa, xóa hoặc xuất dữ liệu. Các màn hình quản trị hiện tại
vẫn được dùng để thao tác dữ liệu và kiểm tra quy tắc nghiệp vụ.

## Cài đặt và chạy local

### Cập nhật chức năng quản trị thuốc, quy định và báo cáo

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app init-db
.\.venv\Scripts\python.exe -m flask --app app.index:app seed-admin-demo
```

`init-db` chỉ tạo bảng chưa tồn tại (đợt này bổ sung `QuyDinh`), không sửa bảng cũ.
`seed-admin-demo` tạo quy định ban đầu 40 bệnh nhân/ngày và tiền khám 100000 VNĐ,
3 đơn vị chuẩn Viên, Chai, Vỉ và 3 thuốc mã `SAMPLE-T001`–`SAMPLE-T003` có tên đánh dấu dữ liệu mẫu.
Lệnh không ghi đè giá trị/thuốc đã có và không tạo hóa đơn hoặc bệnh nhân giả.
Nếu nhóm dùng chung TiDB, chỉ cần một người khởi tạo; không cần chạy lại mỗi lần pull.

Các trang chỉ dành cho ADMIN:
- `/admin/medicines`: tìm theo tên khi gõ, phân trang, thêm/sửa qua modal và xóa có xác nhận.
- `/admin/units`: xem/tìm danh sách đơn vị cố định Viên, Chai, Vỉ; không cho thêm/sửa/xóa loại khác.
- `/admin/regulations`: cập nhật số bệnh nhân tối đa và tiền khám trong cùng transaction.
- `/admin/reports?month=2026-11`: bảng và biểu đồ tháng được chọn.

Để chuyển dữ liệu đơn vị cũ, sao lưu cơ sở dữ liệu, dừng ứng dụng/worker và chạy một lần:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app migrate-medicine-units --maintenance
```

Lệnh chuyển thuốc đang dùng `Gói` hoặc `Đơn vị kiểm thử` sang `Viên`, giữ nguyên số lượng,
rồi xóa các đơn vị cũ. Nếu gặp tên đơn vị cũ khác, lệnh dừng và yêu cầu ánh xạ rõ ràng.
Mã thuốc nhập khi tạo không thay đổi khi sửa. Thuốc đã nằm trong đơn thuốc
(kể cả nháp) không được xóa để giữ lịch sử.
JavaScript danh mục nằm ở `static\js\admin\catalog.js`; biểu đồ ở
`static\js\admin\reports.js`, không thêm logic mới vào `main.js`.

### Cách tính báo cáo và ánh xạ thiết kế

Báo cáo truy vấn SQL theo khoảng đầu tháng đến trước đầu tháng kế tiếp:
- Doanh thu: tổng `TienKham + TienThuoc` trên hóa đơn `TrangThai = DA_THANH_TOAN`,
  nhóm theo ngày của `NgayLap` (thời gian lưu trong CSDL). Không tính hóa đơn chưa thanh toán.
- Số bệnh nhân: đếm bệnh nhân khác nhau trên phiếu `DA_LAP` mỗi ngày `ngayKham`.
  Một bệnh nhân khám ở nhiều ngày được tính vào từng ngày; không tính phiếu `NHAP`.
- Tỷ lệ: doanh thu ngày / tổng doanh thu tháng × 100; tháng không có doanh thu là 0%.
- Sử dụng thuốc: tổng `ChiTietDonThuoc.soLuong` và số phiếu `DA_LAP` khác nhau chứa thuốc,
  theo tháng khám. Không phụ thuộc việc hóa đơn đã thanh toán.
- Hai truy vấn doanh thu/thuốc độc lập tránh nhân đôi doanh thu khi phiếu có nhiều thuốc.
  Bảng doanh thu có đủ mọi ngày trong tháng; biểu đồ vẫn có bảng thay thế nếu CDN lỗi.

Theo xác nhận của nhóm, `HoaDon` ánh xạ bảng thật hiện có trên TiDB
(`MaHoaDon`, `MaPhieuKham`, `MaNV`, `NgayLap`, `TienKham`, `TienThuoc`,
`TongTien`, `PhuongThuc`, `TrangThai`), không chuyển đổi theo lược đồ PDF cũ.
Không thay đổi dữ liệu/schema hóa đơn do đồng đội tạo.
Các cột tiền của hóa đơn và đơn giá thuốc giữ kiểu floating-point đang tồn tại;
khi báo cáo doanh thu, tổng được chuyển sang Decimal và làm tròn 2 chữ số để hiển thị.

`QuyDinh` giữ lược đồ `MaQD`, `tenQuyDinh`, `giaTri` (Numeric), thay cho
`key:Object`/`value:List<Object>` không khớp lược đồ trong hình lớp.
Theo xác nhận, `capNhatTienKham(giaTriMoi)` và `capNhatQuyDinhKham(soBenhNhan)`
nhận giá trị mới; `laySoBenhNhanToiDa()` trả int. DAO kiểm tra quyền, khóa hàng và commit.
Tiền khám mới không sửa hóa đơn cũ. Giới hạn tiếp nhận được lưu để luồng danh sách khám
sử dụng khi triển khai; đợt này chưa tự áp giới hạn vào chức năng bác sĩ hoặc đặt lịch.

`requirements.txt` bao gồm Flask, Flask-Admin, Flask-Login, Flask-SQLAlchemy,
PyMySQL và các phụ thuộc. Cloudinary chưa được cấu hình hoặc sử dụng.
Tệp được lưu UTF-8 để dễ đọc và cập nhật.

Máy cần có Python. Mở terminal tại gốc repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Sao chép `.env.example` thành `.env` và điền thông tin kết nối trước.
Database nghiệp vụ phải được tạo sẵn trên TiDB/MySQL. Với database mới,
khởi tạo các bảng và tạo quản trị đầu tiên bằng CLI (không có tài khoản/mật khẩu mặc định):

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app init-db
.\.venv\Scripts\python.exe -m flask --app app.index:app create-admin
.\.venv\Scripts\python.exe -m app.index
```

`init-db` chỉ tạo bảng còn thiếu, không sửa schema của bảng đã tồn tại.
Khi đổi schema cần migration được kiểm tra riêng, không dùng xóa/tạo lại dữ liệu.
`create-admin` nhập mật khẩu ẩn và yêu cầu xác nhận, không truyền mật khẩu qua tham số CLI.
Số điện thoại nhân viên có thể bổ sung sau; số điện thoại bệnh nhân bắt buộc.

Sau khi cập nhật code có cột trạng thái phiếu khám, chạy lệnh migration dưới đây
trên database đã có bảng `PhieuKham`. Lệnh chỉ thêm `trangThai`; các phiếu cũ
nhận trạng thái `DA_LAP`, không xóa hoặc sửa nội dung hồ sơ:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app upgrade-clinical-schema
```

Database mới đã có cột này sau `init-db`, nên migration sẽ báo không cần thay đổi.
Phiếu khám cũng lưu dự đoán loại bệnh trong cột `DuDoanLoaiBenh`.
Lệnh `upgrade-clinical-schema` thêm cột này khi database cũ chưa có, giữ
các phiếu khám và dữ liệu hiện có.

Với database đang dùng cấu trúc đăng ký cũ, dừng server/tiến trình đang ghi và
sao lưu database trước khi đổi cấu trúc. Chạy migration sau một lần:

```powershell
.\.venv313\Scripts\python.exe -m flask --app app.index:app upgrade-nurse-many-to-many-schema
```

Lệnh chuẩn bị schema hàng chờ nếu cần, chuyển mỗi ngày thành một dòng `DanhSachKham`
và mỗi lượt bệnh nhân thành một dòng `ChiTietDanhSachKham`. Trạng thái, số thứ tự
và thời điểm đăng ký được giữ ở bảng chi tiết; hồ sơ bệnh nhân được tham chiếu
bằng `MaBN`. Các dòng cũ được sao chép và kiểm tra; bảng cũ được giữ nguyên với tên
`DanhSachKham_legacy`. `MaNV` để trống cho đến khi y tá thao tác với danh sách ngày.
Ở dữ liệu cũ, lượt vượt giới hạn có thể mang trạng thái `CHO_DUYET`.
Nếu migration báo lỗi và để lại `_DanhSachKham_m2m` hoặc
`_ChiTietDanhSachKham_m2m`, hãy kiểm tra database trước khi chạy lại; không tự xóa
các bảng này hay bảng backup.

Nếu database còn lượt `CHO_DUYET` cũ, sao lưu database và dừng tất cả server,
tiến trình đang ghi trước khi chạy riêng lệnh sau (không tự chạy khi khởi động):

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app move-waiting-registrations --maintenance
```

Lệnh giữ nguyên mã và thời điểm đăng ký, chuyển từng lượt từ hôm nay hoặc ngày
đăng ký khám cũ (ngày nào muộn hơn) sang ngày gần nhất còn chỗ, chưa chốt và
không trùng lượt hoạt động của bệnh nhân. Lệnh có thể chạy lại; kiểm tra kết quả
trước khi khởi động ứng dụng. Không gửi SMS trong bước chuyển dữ liệu.

Với database đang có bốn cột hồ sơ trùng trong `ChiTietDanhSachKham`, dừng ứng dụng,
sao lưu database và chạy migration:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app drop-nurse-exam-profile-columns --maintenance
```

Migration xóa `HoTen`, `GioiTinh`, `NamSinh`, `DiaChi` khỏi bảng chi tiết và giữ
nguyên các lượt khám. Thông tin bệnh nhân được đọc qua `MaBN` từ bảng `BenhNhan`;
vì vậy lịch sử hiển thị thông tin hồ sơ hiện tại, không còn giữ bản chụp thông tin
tại thời điểm đăng ký.

Để đổi khóa chính `ChiTietDanhSachKham` từ `MaCTDSKham` sang cặp
`(MaDSKham, MaBN)`, dừng ứng dụng/tiến trình đang ghi, sao lưu database rồi chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app migrate-exam-list-composite-key --maintenance
```

Migration lưu các dòng và cột cũ tại `ChiTietDanhSachKham_legacy`. Nếu một cặp
danh sách–bệnh nhân có nhiều dòng, dòng có `MaCTDSKham` lớn nhất được giữ trong
bảng hoạt động; các dòng còn lại vẫn nằm trong bảng legacy để tra cứu. Sau khi
chuyển khóa, hủy lượt chỉ đổi trạng thái và đăng ký lại sẽ khôi phục dòng của cùng
cặp khóa. Kiểm tra dữ liệu và backup trước khi khởi động lại ứng dụng.

Sau khi chuyển khóa ghép, có thể loại bỏ cột `NgayKham` dư thừa khỏi
`ChiTietDanhSachKham`. Ngày khám sẽ được lấy qua quan hệ:

```text
ChiTietDanhSachKham.MaDSKham -> DanhSachKham.MaDSKham -> DanhSachKham.NgayKham
```

Dừng toàn bộ tiến trình ghi và chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app remove-exam-detail-date-column --maintenance
```

Để tạo dữ liệu DEMO cho luồng bác sĩ trên database hiện cấu hình, sau migration, chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app seed-doctor-demo
```

Lệnh này có thể chạy lặp lại; tạo tổng cộng 11 hồ sơ bệnh nhân kiểm thử
(bao gồm Nguyễn Khánh Như Quỳnh), tám mặt hàng được ghi rõ là DEMO và một phiếu
lịch sử có nội dung kiểm thử. Tài khoản bệnh nhân DEMO bị khóa đăng nhập;
thông tin liên hệ/địa chỉ là giả. Không dùng dữ liệu này cho khám chữa bệnh.
Lưu hoặc cập nhật bản nháp không làm thay đổi tồn kho. Khi bác sĩ lập phiếu chính
thức, số lượng thuốc trong đơn được trừ khỏi tồn kho trong cùng transaction với
phiếu và hóa đơn; nếu tồn kho không đủ thì không lưu phiếu.

Để tạo riêng bảng danh sách đăng ký khám trên database đang cấu hình, chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app create-patient-registration-table
```

Lệnh này tạo `DanhSachKham` và `ChiTietDanhSachKham` khi chưa có. Với database
cũ còn bảng `DanhSachKham` dạng từng lượt đăng ký, hãy chạy migration phía trên
thay vì tạo bảng thủ công. Bệnh nhân đăng ký qua bảng chi tiết liên kết hồ sơ
`BenhNhan`, còn bảng danh sách lưu ngày khám và y tá phụ trách. Khi bệnh nhân
bấm đăng ký, ứng dụng lấy họ tên, giới tính, năm sinh và địa chỉ trực tiếp từ
liên kết hồ sơ đã lưu; bệnh nhân không cần nhập lại và dữ liệu gửi từ trình duyệt
không thay thế được thông tin trong hồ sơ. Tại `/patient/profile`,
bệnh nhân có thể sửa họ tên, số điện thoại và địa chỉ; giới tính và năm sinh
không sửa được. Lịch sử lượt khám hiển thị hồ sơ hiện tại của bệnh nhân.

Mở http://127.0.0.1:5000. Dừng bằng Ctrl+C.
Lệnh trên bật debug, chỉ dùng cho môi trường development.

Cũng có thể dùng Flask CLI:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app run --debug
```

Không dùng lệnh `--app app:create_app` của bộ khung cũ.
Các tệp trong package import bằng `from app import app, db`
hoặc `from app import dao, utils` tùy nhu cầu, tương tự package `eapp` của lớp.
Chạy bằng `-m app.index` từ gốc repository, không chạy trực tiếp
`python app\index.py` để tránh lỗi import package.

## Cấu hình CSDL

Ứng dụng nạp `.env` tại gốc repository; biến môi trường của hệ điều hành được ưu tiên.
Đồng đội sao chép `.env.example` thành `.env`, điền `MYSQL_USER`,
`MYSQL_PASSWORD` và tên database từ trang Connect của TiDB Cloud.
Nếu mật khẩu chứa ký tự đặc biệt, đặt toàn bộ giá trị trong dấu nháy đơn
theo cú pháp dotenv. Không cần URL-encode mật khẩu khi dùng các biến `MYSQL_*`.

Kết nối TiDB dùng PyMySQL, charset utf8mb4 và TLS có kiểm tra chứng chỉ
lẫn hostname, sử dụng CA từ certifi. Thiếu mật khẩu khi đã đặt `MYSQL_HOST`
sẽ báo lỗi, không tự chuyển sang SQLite.
Database nghiệp vụ hiện dùng là `medical_app`, tách biệt khỏi `sys`.
Model hiện có các bảng tài khoản/hồ sơ và các bảng khám thuốc
`DonViThuoc`, `Thuoc`, `PhieuKham`, `ChiTietDonThuoc`, cùng
`DanhSachKham` cho đăng ký khám, `HoaDon` và `QuyDinh` cho quản trị/báo cáo.

Kiểm tra kết nối (chỉ chạy `SELECT 1`, không tạo bảng):

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app check-db
```

Chỉ mở trang chủ không chứng minh đã kết nối được CSDL.
Nếu cần, có thể thiết lập `DATABASE_URL` để ghi đè các biến `MYSQL_*`.
Khi không cấu hình cả hai cách, ứng dụng dùng SQLite tại `instance\medical.db`.
Không ghi mật khẩu hay khóa dịch vụ vào mã nguồn.
Thư mục `.venv`, `instance`, các tệp `.env` và Python cache được Git bỏ qua.

## Tài khoản và phân quyền

- `/register`: luôn tạo role `PATIENT`, bỏ qua role gửi từ client.
- `/login`, `/logout`: đăng nhập và đăng xuất; đăng xuất chỉ nhận POST.
- `/dashboard`: phân trang tổng quan theo role.
- `/admin/accounts`: chỉ ADMIN, tìm kiếm họ tên/tên đăng nhập, lọc role, phân trang.
- Nút Tạo/Sửa mở Bootstrap modal; liên kết vẫn mở trang form nếu không có JavaScript.
  Khi nhập mật khẩu mới phải xác nhận lại; để trống cả hai ô để giữ mật khẩu cũ.
- Công tắc trong bảng gửi POST có CSRF để khóa/mở khóa, không cần sửa lại hồ sơ.
- Quản trị tạo/sửa tài khoản, đổi role qua dropdown, khóa/mở khóa và đặt mật khẩu mới.
- Các role cố định: `PATIENT`, `NURSE`, `CASHIER`, `DOCTOR`, `ADMIN`.
  Mỗi tài khoản có một role hiện hành, không có chức năng tự thêm role mới.
- Không tự khóa hoặc tự bỏ quyền ADMIN. Có thể tạo thêm quản trị bằng CLI để khôi phục.
- Tài khoản bệnh nhân có hồ sơ `BenhNhan`; role nhân viên có `NhanVien`;
  bác sĩ có thêm `BacSi` với `MaNV` vừa PK vừa FK.
- Đổi role tạo hồ sơ còn thiếu nhưng giữ nguyên hồ sơ trước đó, không xóa lịch sử.
  Khi quay lại role cũ, hồ sơ cũ được cập nhật theo dữ liệu biểu mẫu.
- `MaTK` của từng bảng hồ sơ là FK, UNIQUE và NOT NULL. Khi có cả hồ sơ
  nhân viên và bệnh nhân, chúng cùng thuộc một người; role quyết định quyền hiện hành.
- `TaiKhoan.MaTK`, `NhanVien.MaNV`, `BenhNhan.MaBN` là số nguyên tự tăng do CSDL cấp;
  `BacSi.MaNV` dùng cùng mã nhân viên, không tự tăng riêng.
- Mã hồ sơ hiển thị được tính từ ID, không lưu trùng dữ liệu vào cột chuỗi:
  `BN-0001`, `YT-0001`, `TN-0001`, `BS-0001`, `QT-0001`.
  Bốn chữ số là độ rộng tối thiểu: sau `BN-9999` là `BN-10000`.
  Nhân viên dùng chung dãy số, không có bộ đếm riêng cho từng role.
  Đổi role nhân viên chỉ đổi tiền tố, giữ phần số và liên kết hồ sơ.
- Mật khẩu lưu hash scrypt trong cột `matKhau` dài 255, không lưu nguyên văn.
  Mật khẩu mới dài 10–128 ký tự; đặt lại mật khẩu làm phiên đăng nhập cũ hết hiệu lực.
- Role/trạng thái được đọc lại từ CSDL mỗi request. Các thao tác ghi có CSRF token,
  kiểm tra đầu vào và transaction; không cho phép chỉ dựa vào menu để kiểm soát quyền.
- Giao diện có header, sidebar, footer chung và thư mục riêng theo từng role.
  Trang y tá có thể tra cứu và thêm bệnh nhân theo mã hồ sơ đã có, hủy lượt khám,
  tìm kiếm, chọn ngày, phân trang và xác nhận danh sách đã lưu. Khi y tá xác nhận,
  ứng dụng thử gửi SMS cho bệnh nhân; khi mở lại và xác nhận lại, SMS được gửi
  lại cho các bệnh nhân trong danh sách. Kết quả phụ thuộc cấu hình dịch vụ SMS.
  Khi đã có lượt được xác nhận, ngày khám được chốt và không nhận thêm đăng ký.
  Y tá phải chọn ngày khác khi thêm trực tiếp vào ngày đã đầy.
  Nghiệp vụ thu ngân chưa được triển khai.

Tài khoản quản trị khởi tạo riêng cho máy này có thông tin trong
`instance\bootstrap-admin.txt` (không commit). Đăng nhập, sửa chính tài khoản,
đặt mật khẩu mới rồi xóa tệp này. Tệp bootstrap không được đọc lúc chạy ứng dụng.
Không chia sẻ mật khẩu qua chat hay repository.

### Chuyển CSDL cũ từ UUID sang ID số nguyên

Dừng tất cả server/tiến trình đang ghi vào CSDL trước khi chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app migrate-account-ids --maintenance
```

Lệnh sao chép và kiểm tra dữ liệu, chuyển các khóa ngoại tương ứng rồi đổi tên bảng.
Giữ nguyên bốn bảng UUID cũ với hậu tố `_uuid_backup`; không tự xóa bản dự phòng.
MySQL/TiDB đổi tên toàn bộ bảng trong một lệnh `RENAME TABLE`; SQLite dùng transaction.
Nếu có bảng nghiệp vụ khác tham chiếu các ID cũ, lệnh từ chối để tránh hỏng liên kết.
Nếu có lỗi để lại bảng `_integer_stage`, cần kiểm tra thủ công trước khi chạy lại;
không xóa bảng dự phòng một cách tùy tiện.
Các phiên đăng nhập UUID cũ hết hiệu lực; đăng nhập lại sau khi khởi động server.
Chạy lại khi toàn bộ khóa đã là số nguyên không thay đổi dữ liệu.
`init-db` không thay thế bước chuyển đổi này.

`SECRET_KEY` lấy từ biến môi trường; nếu thiếu, development sinh khóa một lần
trong `instance\session-secret` để giữ phiên sau khi khởi động lại.
Khi triển khai nhiều instance phải cấu hình cùng một `SECRET_KEY` mạnh,
HTTPS, `COOKIE_SECURE=1`, tắt debug và dùng WSGI server.
Phiên bản này dành cho development; cần bổ sung giới hạn thử đăng nhập và
quy trình khôi phục mật khẩu trước khi công khai dịch vụ trên Internet.

## Đối chiếu thiết kế trong đợt tài khoản

- Đã có các lớp tài khoản/hồ sơ `TaiKhoan`, `NhanVien`, `BacSi`, `BenhNhan`
  và luồng bác sĩ `DonViThuoc`, `Thuoc`, `PhieuKham`, `ChiTietDonThuoc`.
- Model dùng `Mapped`/`mapped_column` của SQLAlchemy để trình kiểm tra kiểu
  hiểu đúng thuộc tính và quan hệ; vẫn giữ cấu trúc file của mẫu lớp.
  `TaiKhoan` cung cấp trực tiếp các thuộc tính giao tiếp Flask-Login
  (`is_active`, `is_authenticated`, `is_anonymous`, `get_id`).
- Đã có `TaiKhoan.dangNhap`, `dangXuat`, `doiMatKhau`.
  `doiMatKhau` thay hash trên đối tượng, việc xác thực quyền và commit do DAO/route đảm nhiệm.
- Bổ sung `TaiKhoan.trangThai` theo xác nhận để khóa/mở tài khoản.
- Luồng bác sĩ đã có route/DAO để tra cứu bệnh nhân theo mã, xem lịch sử,
  tra thuốc, lưu/cập nhật/tiếp tục bản nháp của chính bác sĩ đang đăng nhập,
  xem chi tiết đơn thuốc trong từng phiếu lịch sử (5 phiếu mỗi trang),
  và lập phiếu khám hoàn chỉnh kèm chi tiết đơn thuốc. Bản nháp được cập nhật
  thành phiếu đã lập thay vì tạo thêm lịch sử trùng lặp; hồ sơ và chi tiết thuốc
  được lưu trên database cấu hình hiện tại. Biểu mẫu đang làm được tự lưu thành
  bản nháp trên máy chủ sau khi có bệnh nhân và nội dung thay đổi; nút hình hộp
  ở đầu trang mở danh sách bản nháp để tiếp tục hoặc xóa, kể cả sau khi tải lại
  trang. Xóa bản nháp yêu cầu xác nhận và chỉ áp dụng cho bản nháp của bác sĩ
  đang đăng nhập.
  Model hóa đơn đã ánh xạ bảng thật để truy vấn báo cáo. Bệnh nhân có thể
  đăng ký và xem trạng thái lượt đăng ký của mình; y tá quản lý danh sách theo ngày
  trong database.
- Điểm đã báo để nhóm sửa thiết kế: `NhanVien.capNhatThongTin(quyDinh): QuyDinh`
  không khớp tên thao tác; `HoaDon.inHoaDon(): Double` không khớp việc xuất bản in.
  Chưa triển khai các chữ ký này hay tự đổi chúng trong code.
- `BenhNhan.dangKyKham()` trong sơ đồ là đăng ký lượt khám, không phải đăng ký tài khoản.
  Luồng đăng ký lượt khám dùng `/patient/exam-registrations`, không gán nhầm
  vào `/register`. Nếu hôm nay đầy hoặc đã chốt, lượt đăng ký được xếp tự động
  vào ngày gần nhất còn chỗ và chưa chốt. Mỗi bệnh nhân chỉ đăng ký khi chưa có
  lượt hoạt động từ hôm nay trở đi. Ngày khám chỉ hiển thị sau khi y tá xác nhận.
  Hủy lượt khám giải phóng chỗ nhưng vẫn giữ bản ghi `DA_HUY`.

## Kiểm tra

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
$env:SMS_MODE = "mock"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:\DATABASE_URL
Remove-Item Env:\SMS_MODE
```

Thiết lập SQLite trên chỉ dành cho kiểm tra local, không truy cập TiDB.
Các bài kiểm tra tài khoản từ chối chạy trên database khác để không xóa dữ liệu thật.