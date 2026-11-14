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
│   ├── admin.py
│   ├── migration.py
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
- `app\index.py`: khai báo route, xử lý request và chạy server local.
- `app\models.py`: khai báo các model và quan hệ CSDL.
- `app\dao.py`: truy vấn, thêm, sửa và xóa dữ liệu.
- `app\utils.py`: hàm tính toán và tiện ích dùng chung.
- `app\admin.py`: các route quản trị tài khoản, thuốc, đơn vị, quy định và báo cáo.
- `app\migration.py`: chuyển khóa UUID cũ sang số nguyên, giữ bảng dự phòng.
- `templates`: giao diện Jinja2; `layout` chứa bố cục dùng chung,
  `components` chứa thông báo, khung modal, form tài khoản và ô mật khẩu tái sử dụng.
- `static`: CSS, JavaScript và hình ảnh.

Đợt hiện tại triển khai tài khoản/hồ sơ và luồng bác sĩ (tra cứu bệnh nhân,
lịch sử khám, tra cứu thuốc, lưu nháp và lập phiếu), quản lý thuốc/đơn vị,
quy định và báo cáo tháng. Luồng thanh toán chưa triển khai trong code hiện tại.
Không tạo lại các thư mục `controllers`, `models`, `services` của bộ khung cũ.
Controller được thể hiện bằng các hàm route trong `index.py`, `admin.py`;
truy cập dữ liệu ở `dao.py`.
Frontend dùng HTML/Jinja2, Bootstrap 5.0.2 và JavaScript thuần; không có npm build.
Logo trên header và favicon của các trang dùng chung biểu tượng
`static\images\2.png`.
Chart.js 4.4.1 qua CDN được dùng cho báo cáo, Flask-Admin đã có trong dependencies;
màn hình tài khoản hiện là các view Jinja2 tùy chỉnh để quản lý đồng bộ hồ sơ.

## Cài đặt và chạy local

### Cập nhật chức năng quản trị thuốc, quy định và báo cáo

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app init-db
.\.venv\Scripts\python.exe -m flask --app app.index:app seed-admin-demo
```

`init-db` chỉ tạo bảng chưa tồn tại (đợt này bổ sung `QuyDinh`), không sửa bảng cũ.
`seed-admin-demo` tạo quy định ban đầu 40 bệnh nhân/ngày và tiền khám 100000 VNĐ,
3 đơn vị mẫu và 3 thuốc mã `SAMPLE-T001`–`SAMPLE-T003` có tên đánh dấu dữ liệu mẫu.
Lệnh không ghi đè giá trị/thuốc đã có và không tạo hóa đơn hoặc bệnh nhân giả.
Nếu nhóm dùng chung TiDB, chỉ cần một người khởi tạo; không cần chạy lại mỗi lần pull.

Các trang chỉ dành cho ADMIN:
- `/admin/medicines`: tìm theo tên khi gõ, phân trang, thêm/sửa qua modal và xóa có xác nhận.
- `/admin/units`: thêm/xóa/sửa/tìm các đơn vị tính.
- `/admin/regulations`: cập nhật số bệnh nhân tối đa và tiền khám trong cùng transaction.
- `/admin/reports?month=2026-11`: bảng và biểu đồ tháng được chọn.

Mã thuốc/đơn vị nhập khi tạo, không thay đổi khi sửa. Thuốc đã nằm trong đơn thuốc
(kể cả nháp) và đơn vị còn thuốc tham chiếu không được xóa để giữ lịch sử.
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

`requirements.txt` bao gồm các thư viện trong mẫu lớp: Flask, Flask-Admin,
Flask-Login, Flask-SQLAlchemy, PyMySQL, Cloudinary, WTForms và các phụ thuộc.
Giữ Flask-Migrate của dự án cùng SQLAlchemy 2.0.57.
Tệp được lưu UTF-8 để dễ đọc và cập nhật.
Cloudinary chưa được cấu hình hoặc sử dụng trong đợt tài khoản.

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

Với database đang dùng cấu trúc đăng ký cũ, dừng server/tiến trình đang ghi và
sao lưu database trước khi đổi cấu trúc. Chạy migration sau một lần:

```powershell
.\.venv313\Scripts\python.exe -m flask --app app.index:app upgrade-nurse-many-to-many-schema
```

Lệnh chuẩn bị schema hàng chờ nếu cần, chuyển mỗi ngày thành một dòng `DanhSachKham`
và mỗi lượt bệnh nhân thành một dòng `ChiTietDanhSachKham`. Trạng thái, số thứ tự,
thời điểm đăng ký và thông tin tại thời điểm đăng ký được giữ ở bảng chi tiết.
Các dòng cũ được sao chép và kiểm tra; bảng cũ được giữ nguyên với tên
`DanhSachKham_legacy`. `MaNV` để trống cho đến khi y tá thao tác với danh sách ngày.
Mỗi ngày danh sách chính nhận tối đa theo `SO_BENH_NHAN_TOI_DA`; lượt vượt giới hạn
được lưu với trạng thái `CHO_DUYET`. Chỉ duyệt từ hôm nay trở đi và khi ngày đích
còn chỗ. Hủy lượt khám giải phóng chỗ nhưng vẫn giữ bản ghi trạng thái `DA_HUY`.
Nếu migration báo lỗi và để lại `_DanhSachKham_m2m` hoặc
`_ChiTietDanhSachKham_m2m`, hãy kiểm tra database trước khi chạy lại; không tự xóa
các bảng này hay bảng backup.

Để tạo dữ liệu DEMO cho luồng bác sĩ trên database hiện cấu hình, sau migration, chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app seed-doctor-demo
```

Lệnh này có thể chạy lặp lại; tạo tổng cộng 11 hồ sơ bệnh nhân kiểm thử
(bao gồm Nguyễn Khánh Như Quỳnh), tám mặt hàng được ghi rõ là DEMO và một phiếu
lịch sử có nội dung kiểm thử. Tài khoản bệnh nhân DEMO bị khóa đăng nhập;
thông tin liên hệ/địa chỉ là giả. Không dùng dữ liệu này cho khám chữa bệnh.
Lưu nháp có thể bổ sung sau; lập phiếu hoàn chỉnh không giảm tồn kho vì tồn kho
thuộc quy trình nghiệp vụ của thu ngân.

Để tạo riêng bảng danh sách đăng ký khám trên database đang cấu hình, chạy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app create-patient-registration-table
```

Lệnh này tạo `DanhSachKham` và `ChiTietDanhSachKham` khi chưa có. Với database
cũ còn bảng `DanhSachKham` dạng từng lượt đăng ký, hãy chạy migration phía trên
thay vì tạo bảng thủ công. Bệnh nhân đăng ký qua bảng chi tiết liên kết hồ sơ
`BenhNhan`, còn bảng danh sách lưu ngày khám và y tá phụ trách.

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
  Trang y tá có thể thao tác thêm/sửa/xóa/tìm kiếm, chọn ngày, phân trang và xác nhận
  danh sách đã lưu; danh sách chính và hàng chờ được lưu vào database, chưa gửi SMS.
  Hàng chờ hiển thị trên mọi ngày đang chọn; y tá có thể chuyển lượt chờ sang ngày
  từ hôm nay trở đi nếu ngày đó còn chỗ.
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
  và lập phiếu khám hoàn chỉnh kèm chi tiết đơn thuốc. Bản nháp được cập nhật
  thành phiếu đã lập thay vì tạo thêm lịch sử trùng lặp; hồ sơ và chi tiết thuốc
  được lưu trên database cấu hình hiện tại. Biểu mẫu đang làm được tự lưu thành
  bản nháp trên máy chủ sau khi có bệnh nhân và nội dung thay đổi; nút hình hộp
  ở đầu trang mở danh sách bản nháp để tiếp tục hoặc xóa, kể cả sau khi tải lại
  trang. Xóa bản nháp yêu cầu xác nhận và chỉ áp dụng cho bản nháp của bác sĩ
  đang đăng nhập.
  Model hóa đơn đã ánh xạ bảng thật để truy vấn báo cáo. Bệnh nhân có thể
  đăng ký và xem trạng thái lượt đăng ký của mình; y tá quản lý danh sách theo ngày
  trong database, duyệt lượt vượt giới hạn từ hàng chờ vào ngày đã chọn khi còn chỗ.
- Điểm đã báo để nhóm sửa thiết kế: `NhanVien.capNhatThongTin(quyDinh): QuyDinh`
  không khớp tên thao tác; `HoaDon.inHoaDon(): Double` không khớp việc xuất bản in.
  Chưa triển khai các chữ ký này hay tự đổi chúng trong code.
- `BenhNhan.dangKyKham()` trong sơ đồ là đăng ký lượt khám, không phải đăng ký tài khoản.
  Luồng đăng ký lượt khám dùng `/patient/exam-registrations`, không gán nhầm
  vào `/register`. Giới hạn tiếp nhận áp dụng vào luồng đăng ký này; lượt vượt giới hạn
  được lưu vào hàng chờ để y tá duyệt.

## Kiểm tra

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:\DATABASE_URL
```

Thiết lập SQLite trên chỉ dành cho kiểm tra local, không truy cập TiDB.
Các bài kiểm tra tài khoản từ chối chạy trên database khác để không xóa dữ liệu thật.