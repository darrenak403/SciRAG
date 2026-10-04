# ScientRAG

Hỏi đáp trên bài báo khoa học, có trích dẫn nguồn.

Hiện có: đăng ký / đăng nhập, upload và quản lý thư viện PDF, lưu kết nối tới nhà cung cấp model theo từng tài khoản. Phần xử lý PDF và hỏi đáp chưa có.

## Yêu cầu

Chỉ cần Docker (kèm Docker Compose). Không cần cài Python hay uv trên máy.

## Chạy

```bash
cp .env.example .env
```

Mở `.env` và điền hai giá trị:

- `POSTGRES_PASSWORD`: mật khẩu cho PostgreSQL. Chỉ dùng chữ và số: các ký tự `@ : / # ?` làm hỏng chuỗi kết nối.
- `SECRETS_KEY`: tạo bằng `openssl rand -base64 32 | tr '+/' '-_'`. Thiếu hoặc sai định dạng thì API không khởi động.

```bash
docker compose up        # bật mọi thứ, migration tự chạy
docker compose down      # tắt, dữ liệu giữ nguyên
```

API chạy ở <http://127.0.0.1:8000>, tài liệu API ở <http://127.0.0.1:8000/docs>.

Sửa code trong `src/` hoặc `apps/` thì API tự nạp lại. Chỉ cần `docker compose build` khi đổi `pyproject.toml` hoặc `uv.lock`.

> `docker compose down -v` xoá toàn bộ dữ liệu: tài khoản, bài báo và file đã upload.

> Đổi `SECRETS_KEY` sau khi đã có người dùng thì mọi key model đã lưu không còn đọc được; người dùng phải nhập lại.

## Test và kiểm tra code

```bash
docker compose run --rm api pytest
docker compose run --rm api ruff check .
docker compose run --rm api ruff format .
```

Test chạy trên một database riêng (`scientrag_test`), được tạo và xoá mỗi lần chạy; dữ liệu dev không bị đụng tới.

## Migration

```bash
docker compose run --rm api alembic revision --autogenerate -m "mô tả thay đổi"
docker compose run --rm migrate
```

## Thêm dependency

```bash
docker compose run --rm -v ./uv.lock:/app/uv.lock api uv add <tên-gói>
docker compose build
```

## Cấu trúc

```text
apps/api/        FastAPI: routers, schemas, dependencies
src/scientrag/   config, db (models, repositories, migrations), auth, storage
tests/           unit và integration
docs/decisions/  quyết định kỹ thuật đã chốt
```
