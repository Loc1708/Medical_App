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
│   ├── static\
│   │   ├── css\
│   │   ├── images\
│   │   └── js\
│   └── templates\
│       ├── index.html
│       ├── admin\
│       └── layout\
│           ├── base.html
│           ├── header.html
│           └── footer.html
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
- `app\admin.py`: nơi bổ sung các view quản trị khi triển khai.
- `templates`: giao diện Jinja2; `layout` chứa bố cục dùng chung.
- `static`: CSS, JavaScript và hình ảnh.

Các tệp `models.py`, `dao.py`, `utils.py`, `admin.py` hiện chỉ là khung,
chưa triển khai nghiệp vụ. Không tạo lại các thư mục `controllers`,
`models`, `services` của bộ khung cũ.

## Cài đặt và chạy local

Máy cần có Python. Mở terminal tại gốc repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.index
```

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

Mặc định dùng SQLite tại `instance\medical.db`, chưa cần MySQL để mở trang test.
SQLAlchemy chưa tạo bảng hay lưu dữ liệu khi chỉ mở trang này.
Để dùng CSDL khác, thiết lập biến môi trường `DATABASE_URL` và cài driver phù hợp.
Không ghi mật khẩu hay khóa dịch vụ vào mã nguồn.
Thư mục `.venv`, `instance`, các tệp `.env` và Python cache được Git bỏ qua.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```