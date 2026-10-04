# ScientRAG

Hỏi đáp trên bài báo khoa học, có trích dẫn nguồn.

Hiện có: đăng ký / đăng nhập, upload và quản lý thư viện PDF, kết nối tới nhà cung cấp model theo từng tài khoản (mỗi người nhập key của mình), worker xử lý PDF (parse, chia chunk, embedding, index vào Qdrant), và hỏi đáp trên các bài báo đã xử lý, có trích dẫn tới đúng đoạn văn. Chưa có giao diện web.

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

API chạy ở <http://127.0.0.1:8000>, tài liệu API ở <http://127.0.0.1:8000/docs>. Phoenix (xem trace của từng câu hỏi) ở <http://127.0.0.1:6006>.

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

## Hỏi đáp

Một cuộc trò chuyện gắn với một tập paper (`paper_ids`); câu hỏi chỉ được tìm trong các paper đó, và chỉ trong paper của chính tài khoản đang hỏi.

```bash
# tạo cuộc trò chuyện, rồi hỏi (cookie đăng nhập nằm trong file jar)
curl -b jar -X POST localhost:8000/chats -H 'content-type: application/json' \
  -d '{"paper_ids": ["<id của paper>"]}'
curl -N -b jar -X POST localhost:8000/chats/<id>/messages -H 'content-type: application/json' \
  -d '{"content": "Adam dùng beta1 mặc định là bao nhiêu?"}'
```

Câu trả lời về dưới dạng server-sent events:

| Event | Nội dung |
|-------|----------|
| `sources` | Các đoạn văn đưa cho model, mỗi đoạn một nhãn `S1`, `S2`… kèm paper, trang, mục. |
| `delta` | Từng mẩu chữ của câu trả lời, đúng như model viết ra. |
| `done` | Bản cuối đã kiểm trích dẫn (nhãn không có trong `sources` bị bỏ), danh sách nhãn được dùng, và `outcome`: `answered`, `no_evidence` (không tìm thấy trong paper) hoặc `no_papers` (phạm vi không có paper nào đã xử lý xong). |
| `error` | `code` và `message` khi nhà cung cấp model lỗi. Không có gì được lưu. |

Chỉ khi có `done` thì câu hỏi và câu trả lời mới được lưu; người đọc ngắt kết nối giữa chừng thì lời gọi model dừng và không lưu gì. `GET /chats/{id}/messages` trả lịch sử kèm trích dẫn, `GET /chunks/{id}` trả nguyên văn đoạn được trích, `GET /chats/messages/{id}/retrieval` cho biết câu trả lời đó đã tìm và xếp hạng thế nào.

Paper được index bằng model embedding khác với kết nối đang dùng thì không được tìm (vector khác không gian): gọi `POST /papers/reindex`.

Mỗi câu hỏi là một trace trong Phoenix (project `scientrag`) với các bước `rewrite_question`, `retrieve`, `rerank`, `generate`. Trace chứa câu hỏi và các đoạn văn, nên cổng 6006 chỉ mở trên máy chạy Docker.

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `RERANK_ENABLED` | `true` | Tắt để bỏ bước model nhanh xếp hạng lại các đoạn tìm được (bớt một lời gọi model mỗi câu hỏi). |
| `CONTEXT_CHUNKS` | `8` | Số đoạn văn tối đa đưa cho model trả lời. |

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
                 index (Qdrant), ingestion (các bước và workflow), access (quyền đọc paper),
                 rag (tìm, xếp hạng, dựng ngữ cảnh, kiểm trích dẫn), telemetry (trace)
tests/           unit và integration
docs/decisions/  quyết định kỹ thuật đã chốt
```
