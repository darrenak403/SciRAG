# ScientRAG

Hỏi đáp trên bài báo khoa học, có trích dẫn nguồn.

Hiện có: đăng ký / đăng nhập, upload và quản lý thư viện PDF, kết nối tới nhà cung cấp model theo từng tài khoản (mỗi người nhập key của mình), và worker xử lý PDF: parse, chia chunk, embedding, index vào Qdrant. Phần hỏi đáp chưa có.

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

Sửa code trong `src/` hoặc `apps/` thì API tự nạp lại; worker thì cần `docker compose restart worker`. Chỉ cần `docker compose build` khi đổi `pyproject.toml` hoặc `uv.lock`.

Lần đầu worker xử lý một PDF, nó tải model của parser (khoảng 500 MB) vào volume `models`; các lần sau không tải lại.

> `docker compose down -v` xoá toàn bộ dữ liệu: tài khoản, bài báo và file đã upload.

> Đổi `SECRETS_KEY` sau khi đã có người dùng thì mọi key model đã lưu không còn đọc được; người dùng phải nhập lại.

## Xử lý PDF

Upload xong, paper tự vào hàng đợi và worker đưa nó qua các bước `parse → metadata → chunk → summarize → embed → index → validate`. `GET /papers/{id}` cho biết đang ở bước nào; `GET /papers/{id}/ingestion` cho biết từng lần thử.

Mọi lời gọi model dùng key của chính chủ paper. Tài khoản chưa có kết nối model thì paper dừng ở `FAILED` với `error_code = provider_not_configured`: thêm kết nối ở `POST /settings/providers`, rồi gọi `POST /papers/{id}/reingest`.

Worker bị tắt giữa chừng (kể cả `docker compose down`) thì lần bật sau chạy tiếp từ bước đang dở.

Cấu hình trong `.env` (đều có mặc định):

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `INGEST_CONCURRENCY` | `1` | Số paper worker xử lý cùng lúc. Mỗi paper cần 2–3 GB RAM khi parse. |
| `MAX_PAPER_PAGES` | `150` | PDF dài hơn bị từ chối. |
| `CHUNK_MAX_TOKENS` | `400` | Kích thước tối đa của một chunk. |
| `SUMMARIZE_PAPERS` | `true` | Tắt để không gọi model tóm tắt từng paper. |
| `ALLOW_PRIVATE_PROVIDER_URLS` | `false` | Bật khi người dùng trỏ kết nối OpenAI-compatible vào router trong mạng nội bộ. |

## Test và kiểm tra code

```bash
docker compose run --rm worker pytest
docker compose run --rm api ruff check .
docker compose run --rm api ruff format .
```

Test chạy trong image `worker` vì chỉ image này có parser PDF (chạy bằng `api` cũng được, khi đó nhóm test parser bị bỏ qua). Cần `postgres` và `qdrant` đang chạy. Test dùng database riêng (`scientrag_test`) và các collection Qdrant riêng, tạo và xoá mỗi lần chạy; dữ liệu dev không bị đụng tới.

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
apps/worker/     tiến trình chạy các workflow xử lý PDF
src/scientrag/   config, db (models, repositories, migrations), auth, storage,
                 providers (Gemini, Bedrock, OpenAI-compatible), parsing, chunking,
                 index (Qdrant), ingestion (các bước và workflow)
tests/           unit và integration
docs/decisions/  quyết định kỹ thuật đã chốt
```
