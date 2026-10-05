# SciRAG

Hỏi đáp trên bài báo khoa học, có trích dẫn nguồn.

Hiện có:

- Đăng ký / đăng nhập; mỗi tài khoản tự thêm kết nối tới nhà cung cấp model của mình (Gemini, Amazon Bedrock, hoặc endpoint tương thích OpenAI). Server không giữ key model nào.
- Upload và quản lý thư viện PDF; worker xử lý từng paper ở nền (parse, chia chunk, tóm tắt, embedding, index vào Qdrant).
- Hỏi đáp trên các paper đã xử lý, mỗi nhận định dẫn về đúng đoạn, đúng trang, tô sáng trong PDF.
- Collection gom paper để hỏi chung; so sánh nhiều paper thành bảng; tổng hợp trên cả collection.
- Giao diện web cho tất cả những việc trên, và bộ đo chất lượng chạy bằng một lệnh.

Chưa có: chia sẻ collection giữa các tài khoản, cấu hình triển khai production. Kiến trúc chi tiết: [scirag-architecture.md](scirag-architecture.md).

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

Giao diện web ở <http://localhost:3000>: đăng ký tài khoản, vào **Settings → Model providers** để thêm key model của bạn, rồi **Add papers**. API chạy ở <http://127.0.0.1:8000>, tài liệu API ở <http://127.0.0.1:8000/docs>. Phoenix (xem trace của từng câu hỏi) ở <http://127.0.0.1:6006>.

Mở giao diện bằng đúng địa chỉ `localhost:3000`: ở chế độ dev, Next.js chặn script khi vào bằng tên máy khác.

Sửa code trong `src/` hoặc `apps/api/` thì API tự nạp lại; worker thì cần `docker compose restart worker`. Sửa code trong `apps/web/` thì trang tự nạp lại. Chỉ cần `docker compose build` khi đổi `pyproject.toml` hoặc `uv.lock`; đổi `apps/web/package.json` thì `docker compose restart web` là đủ (service cài lại package khi khởi động).

Lần đầu worker xử lý một PDF, nó tải model của parser (khoảng 500 MB) vào volume `models`; các lần sau không tải lại.

> `docker compose down -v` xoá toàn bộ dữ liệu: tài khoản, bài báo và file đã upload.

> Đổi `SECRETS_KEY` sau khi đã có người dùng thì mọi key model đã lưu không còn đọc được; người dùng phải nhập lại.

## Giao diện web

| Trang | Việc làm |
|-------|----------|
| `/` | Đặt câu hỏi, chọn nguồn (paper hoặc collection), mở lại phiên gần đây. |
| `/library` | Thư viện: thêm paper, lọc, sắp xếp, sửa metadata, xoá, chạy lại paper lỗi. Bấm một paper để đọc PDF kèm mục lục và tóm tắt. |
| `/research/{id}` | Phiên hỏi đáp. Bấm marker `[S1]` hoặc một ô của bảng so sánh để mở PDF đúng trang, đoạn nguồn được tô sáng. |
| `/collections` | Tạo collection, thêm bớt paper; từ trang một collection chọn Ask, Compare hoặc Synthesize. |
| `/settings` | Kết nối model, model cho từng vai trò, lượng token đã dùng. **Advanced** bật các chi tiết kỹ thuật: từng bước xử lý của paper, danh sách chunk, cách tìm nguồn của mỗi câu trả lời, cấu hình tìm kiếm của server. |

Ảnh các màn hình chính: `docs/screenshots/web-ui/`.

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

Một cuộc trò chuyện gắn với một tập paper (`paper_ids`) hoặc một collection (`collection_id`: phạm vi là các paper đang nằm trong collection lúc hỏi); câu hỏi chỉ được tìm trong các paper đó, và chỉ trong paper của chính tài khoản đang hỏi.

```bash
# tạo cuộc trò chuyện, rồi hỏi (cookie đăng nhập nằm trong file jar)
curl -b jar -X POST localhost:8000/chats -H 'content-type: application/json' \
  -d '{"paper_ids": ["<id của paper>"]}'
curl -N -b jar -X POST localhost:8000/chats/<id>/messages -H 'content-type: application/json' \
  -d '{"content": "Adam dùng beta1 mặc định là bao nhiêu?"}'
```

Câu hỏi có ba cách trả lời, chọn bằng `mode` trong body (mặc định `auto`: model nhanh tự xếp loại câu hỏi):

| `mode` | Cách trả lời |
|--------|--------------|
| `factual` | Tìm các đoạn hợp nhất trong cả phạm vi rồi trả lời. Phạm vi một paper luôn đi đường này. |
| `comparison` | Lấy vài đoạn từ từng paper, trả về một bảng (mỗi paper một hàng, ô nào cũng kèm nguồn) và một đoạn nhận xét. |
| `synthesis` | Lấy vài đoạn từ từng paper, model nhanh chấm và tóm tắt từng đoạn, rồi viết bài gồm bốn phần: Overview, Areas of agreement, Disagreements, Research gaps. Phần nào thiếu bằng chứng thì ghi rõ là thiếu. |

Hai cách sau xem tối đa `MULTI_PAPER_MAX_PAPERS` paper; phạm vi lớn hơn thì chọn các paper sát câu hỏi nhất và câu trả lời ghi rõ đã xem bao nhiêu paper.

Câu trả lời về dưới dạng server-sent events:

| Event | Nội dung |
|-------|----------|
| `sources` | Các đoạn văn đưa cho model, mỗi đoạn một nhãn `S1`, `S2`… kèm paper, trang, mục. |
| `status` | Câu so sánh và tổng hợp: `mode` đã chọn, bước đang làm (`selecting`, `gathering`, `comparing`, `writing`) và số đoạn đã đọc trên tổng số. |
| `table` | Câu so sánh: `columns` và `rows`, mỗi paper một hàng, mỗi ô có `text` và các nhãn nguồn `markers`. |
| `delta` | Từng mẩu chữ của câu trả lời, đúng như model viết ra. |
| `done` | Bản cuối đã kiểm trích dẫn (nhãn không có trong `sources` bị bỏ), danh sách nhãn được dùng, và `outcome`: `answered`, `no_evidence` (không tìm thấy trong paper) hoặc `no_papers` (phạm vi không có paper nào đã xử lý xong). |
| `error` | `code` và `message` khi nhà cung cấp model lỗi. Không có gì được lưu. |

Chỉ khi có `done` thì câu hỏi và câu trả lời mới được lưu; người đọc ngắt kết nối giữa chừng thì lời gọi model dừng và không lưu gì. `GET /chats/{id}/messages` trả lịch sử kèm trích dẫn, `GET /chunks/{id}` trả nguyên văn đoạn được trích, `GET /chats/messages/{id}/retrieval` cho biết câu trả lời đó đã tìm và xếp hạng thế nào.

Paper được index bằng model embedding khác với kết nối đang dùng thì không được tìm (vector khác không gian): gọi `POST /papers/reindex`.

Mỗi câu hỏi là một trace trong Phoenix (project `scientrag`) với các bước `rewrite_question` (`analyze_question` khi phải xếp loại câu hỏi), `embed_query`, `retrieve`, `rerank`, `generate`; câu tổng hợp có thêm `gather_evidence`. Trace chứa câu hỏi và các đoạn văn, nên cổng 6006 chỉ mở trên máy chạy Docker.

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `RERANK_ENABLED` | `true` | Tắt để bỏ bước model nhanh xếp hạng lại các đoạn tìm được (bớt một lời gọi model mỗi câu hỏi). |
| `CONTEXT_CHUNKS` | `8` | Số đoạn văn tối đa đưa cho model trả lời. |
| `MULTI_PAPER_MAX_PAPERS` | `20` | Số paper tối đa được xem trong một câu so sánh hoặc tổng hợp. |
| `MULTI_PAPER_CHUNKS` | `3` | Số đoạn lấy từ mỗi paper trong câu so sánh hoặc tổng hợp. |
| `MULTI_PAPER_PARALLEL_CALLS` | `4` | Số lời gọi model nhanh chạy cùng lúc khi chấm các đoạn cho câu tổng hợp. |
| `EVIDENCE_MIN_RELEVANCE` | `4` | Đoạn bị model nhanh chấm dưới mức này (thang 0–10) không được đưa vào bài tổng hợp. |

Một câu tổng hợp gọi model nhanh một lần cho mỗi đoạn: trên 12 paper là 36 lời gọi, khoảng 85 nghìn token vào. `GET /settings/rag` trả các giá trị server đang chạy; giao diện hiện chúng ở Settings → Advanced.

## Collection

Collection gom các paper của một tài khoản để hỏi chung. Paper vẫn nằm trong thư viện: xoá collection không xoá paper, và một paper có thể ở nhiều collection.

| Lời gọi | Việc làm |
|---------|----------|
| `POST /collections` | Tạo, với `name`, `description` và `paper_ids` (tuỳ chọn). |
| `GET /collections`, `GET /collections/{id}` | Danh sách, và một collection kèm `paper_ids`. |
| `PATCH /collections/{id}` | Đổi tên hoặc mô tả. |
| `DELETE /collections/{id}` | Xoá collection. |
| `PUT` / `DELETE /collections/{id}/papers/{paper_id}` | Thêm hoặc bỏ một paper. |
| `GET /papers?collection_id=…` | Các paper trong collection. |
| `GET /chats?collection_id=…` | Các cuộc trò chuyện gắn với collection. |

## Đo chất lượng

Bộ đo chạy câu hỏi qua đúng đường mà câu hỏi của người dùng đi (`rag.engine.answer`), trên dữ liệu nạp vào các tài khoản riêng `chunk-<n>@eval.invalid`. Nó gọi model thật bằng key trong biến môi trường `GEMINI_API_KEY` (đặt trong `.env`), nên có tốn token.

```bash
# một cấu hình: nạp paper (lần đầu), chạy câu hỏi, in bảng và lưu vào eval-results/
docker compose run --rm -e GIT_COMMIT=$(git rev-parse --short HEAD) api \
  python -m scientrag.evaluation.run --config eval/configs/baseline.toml

# so sánh hai lần chạy
docker compose run --rm --no-deps api \
  python -m scientrag.evaluation.report eval-results/<a>.json eval-results/<b>.json

# xoá các tài khoản đo cùng paper, point và file của chúng
docker compose run --rm api python -m scientrag.evaluation.run --clean
```

Hai bộ dữ liệu:

- **QASPER**: câu hỏi trên paper NLP, có đánh dấu đoạn bằng chứng. Tải về `eval-data/` ở lần chạy đầu. Paper ở dạng văn bản nên không đo được parser.
- **Golden** (`eval/golden/`): câu hỏi của dự án trên PDF thật, đi qua parser thật. Cấu hình dùng bộ này phải chạy bằng image `worker` (thay `api` bằng `worker` trong lệnh trên) ở lần đầu, để parse PDF. Thêm câu hỏi: thêm một dòng vào `factual.jsonl`, với `evidence_chunk_text` là các câu chép nguyên văn từ paper. `comparison.jsonl` và `synthesis.jsonl` là câu hỏi trên nhiều paper; mỗi câu ghi `expected_papers`, các paper phải có mặt trong trích dẫn.

Mỗi file trong `eval/configs/` là một thí nghiệm, đổi một thứ so với `baseline.toml` (các file `*-no-rerank` so với `no-rerank.toml`). Lượt nào có lỗi (`errors` khác 0 ở dòng đầu bảng, thường do key hết quota) thì chạy lại trước khi dùng số. `mode = "retrieval"` dừng ở bước chọn đoạn văn (rẻ); `mode = "answer"` chạy tới câu trả lời, và `judge = true` dùng model chấm thêm. Với bộ golden, `kinds` chọn loại câu hỏi được chạy (mặc định `["factual"]`), và `mode = "classify"` chỉ đo việc xếp loại câu hỏi. Kết quả và cấu hình đã chốt: [docs/decisions/0002-eval-results-and-config.md](docs/decisions/0002-eval-results-and-config.md); phần nhiều paper: [docs/decisions/0003-multi-paper-config.md](docs/decisions/0003-multi-paper-config.md).

## Test và kiểm tra code

```bash
docker compose run --rm worker pytest
docker compose run --rm api ruff check .
docker compose run --rm api ruff format .
```

Giao diện web (cần service `web` đang chạy):

```bash
docker compose exec web npx tsc --noEmit
docker compose exec web npx eslint app components lib
docker compose build web      # chạy next build, lỗi type thì dừng
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
apps/web/        giao diện Next.js: app (các trang), components, lib (gọi API, SSE, upload)
src/scientrag/   config, db (models, repositories, migrations), auth, storage,
                 providers (Gemini, Bedrock, OpenAI-compatible), parsing, chunking,
                 index (Qdrant), ingestion (các bước và workflow), access (quyền đọc paper),
                 rag (xếp loại câu hỏi, tìm, xếp hạng, dựng ngữ cảnh, ba đường trả lời, kiểm trích dẫn),
                 telemetry (trace),
                 evaluation (bộ đo)
tests/           unit và integration
eval/            bộ câu hỏi golden và cấu hình thí nghiệm
scirag-architecture.md  kiến trúc của hệ thống
docs/decisions/  quyết định kỹ thuật đã chốt
docs/screenshots/ ảnh chụp các màn hình chính
```
