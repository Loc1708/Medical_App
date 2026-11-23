# Hướng dẫn chạy ứng dụng quản lý phòng mạch

Ứng dụng được xây dựng bằng Python, Flask và SQLAlchemy. Hướng dẫn dưới đây
dùng PowerShell trên Windows và cơ sở dữ liệu MySQL.

## 1. Chuẩn bị môi trường

Giải nén tệp ZIP, mở thư mục dự án trong VS Code hoặc PowerShell. Mở terminal
tại thư mục chứa `README.md` và `requirements.txt`.

Cài Python và MySQL Server, sau đó kiểm tra Python:

```powershell
py --version
```

Tạo môi trường ảo và cài các thư viện:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Các lệnh bên dưới dùng trực tiếp Python trong `.venv`, không cần kích hoạt
môi trường ảo. Không cần cài npm để chạy giao diện.

## 2. Tạo và cấu hình MySQL

Khởi động MySQL Server. Dùng MySQL Workbench hoặc công cụ dòng lệnh MySQL để
đăng nhập và tạo cơ sở dữ liệu:

```sql
CREATE DATABASE medical_app CHARACTER SET utf8mb4;
```

Nếu cơ sở dữ liệu đã tồn tại, không cần tạo lại. Tài khoản MySQL được dùng phải
có quyền kết nối, tạo bảng và đọc/ghi dữ liệu trong cơ sở dữ liệu này.
Trong thư mục gốc dự án, tạo tệp có tên `.env` và điền thông tin MySQL:

```dotenv
MYSQL_HOST=<dia_chi_may_chu_mysql>
MYSQL_PORT=3306
MYSQL_USER=<ten_nguoi_dung>
MYSQL_PASSWORD='<mat_khau>'
MYSQL_DATABASE=medical_app
SMS_MODE=mock
```

Thay các giá trị trong dấu `<>` bằng thông tin thực tế; không giữ dấu `<>`.
`MYSQL_HOST` là tên máy chủ trên chứng chỉ MySQL; điều chỉnh cổng theo cấu hình
máy chủ. Mật khẩu phải có giá trị. Ứng dụng yêu cầu kết nối TLS, kiểm tra
chứng chỉ và tên máy chủ bằng CA trong thư viện `certifi`. Máy chủ MySQL cần
bật TLS và có chứng chỉ phù hợp, được CA đó tin cậy; chứng chỉ tự ký mặc định
có thể không kết nối được.

Ứng dụng tự đọc `.env`. Nếu môi trường đã có `DATABASE_URL`, giá trị đó được
ưu tiên hơn `MYSQL_*`; các biến môi trường có sẵn cũng được ưu tiên hơn `.env`.
Không đưa mật khẩu hoặc khóa dịch vụ vào bản ZIP hay Git; người chạy tự tạo
`.env` trên máy của mình. Cần xác nhận đúng cơ sở dữ liệu trước khi chạy lệnh
làm thay đổi dữ liệu.

Kiểm tra kết nối, không tạo bảng hoặc thay đổi dữ liệu:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app check-db
```

## 3. Khởi tạo lần đầu

Các lệnh dưới đây dành cho **cơ sở dữ liệu mới**, không cần chạy lại mỗi lần
khởi động. Nếu dùng cơ sở dữ liệu chung đã có dữ liệu, hãy hỏi nhóm trước khi
khởi tạo hoặc tạo tài khoản.

Tạo các bảng còn thiếu:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app init-db
```

`init-db` không cập nhật cấu trúc bảng đã tồn tại. Với cơ sở dữ liệu cũ cần
nâng cấp schema, sao lưu và kiểm tra migration phù hợp trước; không xóa hoặc
tạo lại bảng để thay thế migration.

Tạo tài khoản quản trị đầu tiên:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app create-admin
```

Nhập tên đăng nhập, mật khẩu và họ tên theo yêu cầu trong terminal. Mật khẩu
được nhập ẩn, cần xác nhận lại và có từ 10 đến 128 ký tự. Không có tài khoản
quản trị mặc định.

Mật khẩu mới và mật khẩu được đặt lại dùng MD5 giống dự án mẫu của lớp; tài
khoản đã lưu bằng Werkzeug vẫn đăng nhập được. MD5 không có salt và dễ bị dò,
chỉ phù hợp cho mục đích học tập, không nên dùng cho triển khai thực tế.

Để chạy thử các nghiệp vụ, khởi tạo quy định, đơn vị và thuốc **mẫu**:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app seed-admin-demo
```

Lệnh tạo quy định mặc định, đơn vị Viên/Chai/Vỉ và ba thuốc được đánh dấu dữ
liệu mẫu; không ghi đè các giá trị đã tồn tại. Không dùng thuốc mẫu cho điều trị.
Đây là lệnh ghi vào CSDL: chỉ chạy trên cơ sở dữ liệu được phép dùng dữ liệu mẫu.

## 4. Chạy ứng dụng

```powershell
.\.venv\Scripts\python.exe -m flask --app app.index:app run --debug
```

Mở địa chỉ `http://127.0.0.1:5000` trong trình duyệt. Đăng nhập bằng tài khoản
quản trị vừa tạo; bệnh nhân có thể đăng ký tài khoản tại trang đăng ký. Quản trị
viên có thể tạo tài khoản nhân viên theo vai trò trong giao diện. Nhấn `Ctrl+C`
trong terminal để dừng ứng dụng.

Chế độ `--debug` chỉ dành cho phát triển trên máy cá nhân, không dùng để triển
khai công khai. Nếu không đặt `SECRET_KEY`, ứng dụng tạo khóa phiên tại
`instance\session-secret`; khi triển khai cần đặt khóa mạnh và bảo vệ giá trị này.

`run.bat` là lựa chọn khác, nhưng tệp này yêu cầu môi trường riêng `.venv313`
với Python 3.13; nó không sử dụng `.venv` được tạo theo hướng dẫn trên.

Với `SMS_MODE=mock`, SMS chỉ được mô phỏng, không gửi tin nhắn thật.