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
- `app\admin.py`: các route quản trị tài khoản.
- `app\migration.py`: chuyển khóa UUID cũ sang số nguyên, giữ bảng dự phòng.
- `templates`: giao diện Jinja2; `layout` chứa bố cục dùng chung,
  `components` chứa thông báo, khung modal, form tài khoản và ô mật khẩu tái sử dụng.
- `static`: CSS, JavaScript và hình ảnh.

Đợt hiện tại triển khai tài khoản và hồ sơ liên quan, chưa triển khai nghiệp vụ
khám, thuốc, thanh toán và báo cáo. Không tạo lại các thư mục `controllers`,
`models`, `services` của bộ khung cũ. Controller được thể hiện bằng các hàm route
trong `index.py`, `admin.py`; truy cập dữ liệu ở `dao.py`.
Frontend dùng HTML/Jinja2, Bootstrap 5.0.2 và JavaScript thuần; không có npm build.
Logo trên header và favicon của các trang dùng chung biểu tượng
`static\images\2.png`.
Chart.js sẽ được dùng khi triển khai báo cáo, Flask-Admin đã có trong dependencies;
màn hình tài khoản hiện là các view Jinja2 tùy chỉnh để quản lý đồng bộ hồ sơ.

## Cài đặt và chạy local

`requirements.txt` bao gồm các thư viện trong mẫu lớp: Flask, Flask-Admin,
Flask-Login, Flask-SQLAlchemy, PyMySQL, Cloudinary, WTForms và các phụ thuộc.
Giữ Flask-Migrate của dự án cùng SQLAlchemy 2.1.6 đang dùng
(mẫu lớp dùng 2.1.5). Tệp được lưu UTF-8 để dễ đọc và cập nhật.
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
Đợt tài khoản chỉ tạo các bảng `TaiKhoan`, `NhanVien`, `BacSi`, `BenhNhan`.

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
  Các trang ngoài quản trị hiện hiển thị rõ chức năng nghiệp vụ chưa triển khai,
  không có nút giả hoặc thông báo thành công cho thao tác chưa thực hiện.

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

- Đã có các lớp `TaiKhoan`, `NhanVien`, `BacSi`, `BenhNhan` theo lược đồ PDF.
- Model dùng `Mapped`/`mapped_column` của SQLAlchemy để trình kiểm tra kiểu
  hiểu đúng thuộc tính và quan hệ; vẫn giữ cấu trúc file của mẫu lớp.
  `TaiKhoan` cung cấp trực tiếp các thuộc tính giao tiếp Flask-Login
  (`is_active`, `is_authenticated`, `is_anonymous`, `get_id`).
- Đã có `TaiKhoan.dangNhap`, `dangXuat`, `doiMatKhau`.
  `doiMatKhau` thay hash trên đối tượng, việc xác thực quyền và commit do DAO/route đảm nhiệm.
- Bổ sung `TaiKhoan.trangThai` theo xác nhận để khóa/mở tài khoản.
- Chưa tạo lớp/phương thức giả cho nghiệp vụ ngoài phạm vi đợt này.
  Các controller/UI khám, thuốc, thanh toán và lớp nghiệp vụ tương ứng triển khai sau.
- Điểm đã báo để nhóm sửa thiết kế: `NhanVien.capNhatThongTin(quyDinh): QuyDinh`
  không khớp tên thao tác; `HoaDon.inHoaDon(): Double` không khớp việc xuất bản in.
  Chưa triển khai các chữ ký này hay tự đổi chúng trong code.
- `BenhNhan.dangKyKham()` trong sơ đồ là đăng ký lượt khám, không phải đăng ký tài khoản.
  Chức năng đó sẽ làm trong đợt danh sách khám, không gán nhầm vào `/register`.

## Kiểm tra

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:\DATABASE_URL
```

Thiết lập SQLite trên chỉ dành cho kiểm tra local, không truy cập TiDB.
Các bài kiểm tra tài khoản từ chối chạy trên database khác để không xóa dữ liệu thật.