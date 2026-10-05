# SciRAG — Tài liệu kiến trúc

Cập nhật: 05/10/2026. Tài liệu mô tả hệ thống **đúng như code hiện có**; phần nào mới là dự định thì ghi rõ "chưa làm". Các số phiên bản đã được đối chiếu với nguồn chính thức ngày 04/10/2026 (xem [Nguồn](#16-nguồn)).

## 1. Mục tiêu và phạm vi

SciRAG là hệ thống hỏi đáp trên bài báo khoa học do người dùng tải lên. Hệ thống phải làm được bốn việc:

1. Trả lời câu hỏi cụ thể trong một hoặc vài paper ("Bảng 3 báo cáo F1 bao nhiêu cho BERT-base trên SciERC?").
2. So sánh nhiều paper theo một tiêu chí (phương pháp, dataset, kết quả).
3. Tổng hợp trên cả một collection (literature review, research gap).
4. Mọi nhận định trong câu trả lời đều dẫn về đúng đoạn, đúng trang của paper nguồn.

Ngoài phạm vi của phiên bản đầu: tìm paper trên internet, hiểu nội dung hình ảnh, cộng tác thời gian thực, fine-tune model.

**Quy mô và ràng buộc đã chốt.**

- Người dùng là cá nhân hoặc nhóm nhỏ: vài trăm đến vài nghìn paper, dưới một triệu chunk, tối đa vài chục người dùng đồng thời.
- **CPU-first.** Hệ thống chạy trên server không có GPU. Parsing, ingestion và retrieval chạy bằng CPU.
- **Model gọi qua API, bằng key của từng tài khoản.** Server không giữ key model nào: mỗi người dùng thêm kết nối tới nhà cung cấp của mình (Gemini, Amazon Bedrock, hoặc một endpoint tương thích OpenAI). Embedding, xếp hạng lại và sinh câu trả lời đều đi qua kết nối đó. Không model nào tự host ngoài các model layout của parser.

Mọi lựa chọn "nhẹ" bên dưới dựa trên các ràng buộc này; [mục 14](#14-đường-nâng-cấp) ghi rõ khi nào cần đổi sang phương án nặng hơn.

**Nguyên tắc thiết kế.**

- PostgreSQL là nguồn dữ liệu gốc. Qdrant là index dẫn xuất, xoá đi dựng lại được từ PostgreSQL.
- Mỗi thành phần hay thay đổi (parser, nhà cung cấp model, object storage) nằm sau một interface riêng.
- Lõi RAG tự viết, không phụ thuộc framework như LangChain, để kiểm soát và đo được từng bước.
- Không thêm service nào khi chưa có nhu cầu đo được.

## 2. Tổng quan kiến trúc

```text
                      ┌──────────────────────┐
                      │  Next.js Research UI │
                      └──────────┬───────────┘
                                 │ HTTP / SSE (qua proxy /api của Next.js)
                                 ▼
                      ┌──────────────────────┐
                      │       FastAPI        │
                      │ Auth · Papers · Chat │
                      │ Collections·Settings │
                      │      RAG Engine      │
                      └──┬─────┬─────┬────┬──┘
        ghi/đọc business │     │     │    │ gọi model bằng key
        + enqueue job    │     │     │    │ của tài khoản đang hỏi
                         ▼     │     ▼    └───────────────┐
              ┌──────────────┐ │ ┌──────────┐   ┌─────────▼─────────┐
              │ PostgreSQL 18│ │ │  Qdrant  │   │  Model providers  │
              │ business data│ │ │ dense +  │   │ Gemini · Bedrock  │
              │ chunks (gốc) │ │ │ BM25     │   │ OpenAI-compatible │
              │ job state    │ │ │ hybrid   │   │ (embedding, LLM)  │
              └──────▲───────┘ │ └────▲─────┘   └─────────▲─────────┘
                     │         │      │                   │
       dequeue job,  │         │      │ upsert / delete   │ embed, tóm tắt
       ghi chunks    │         ▼      │                   │ bằng key chủ paper
              ┌──────┴────────────────┴───────────────────┴─────────┐
              │              Ingestion worker (DBOS)                │
              │ parse → metadata → chunk → summarize → embed →      │
              │ index → validate                                    │
              └───────────────────────┬─────────────────────────────┘
                                      │ PDF, tài liệu đã parse, vector
                                      ▼
                           ┌─────────────────────┐
                           │   Object storage    │
                           │ (volume, sau        │
                           │  interface)         │
                           └─────────────────────┘

      FastAPI gửi trace của từng câu hỏi qua OpenTelemetry → Phoenix
```

API process không bao giờ parse PDF hay tính embedding hàng loạt. Nó chỉ ghi bản ghi `papers`, đưa job vào hàng đợi và trả về ngay. Worker là một process riêng chạy cùng codebase.

**Giao diện web** (`apps/web`) gọi API qua đường `/api` do Next.js chuyển tiếp, nên cookie đăng nhập cùng origin với trang. Các màn hình:

| Đường dẫn | Nội dung |
| --- | --- |
| `/login`, `/register` | Đăng nhập, đăng ký. |
| `/` | Ô hỏi, chọn nguồn (paper hoặc collection), các phiên gần đây. |
| `/library`, `/library/{paperId}` | Thư viện paper (lọc, sắp xếp, lọc theo collection); trang đọc một paper: PDF, mục lục, tóm tắt. |
| `/research/{sessionId}` | Phiên hỏi đáp: câu trả lời hiện dần, marker bấm được, panel Evidence mở PDF đúng trang và tô đúng đoạn; bảng so sánh; tiến độ của câu trả lời dài. |
| `/collections`, `/collections/{id}` | Danh sách collection; trang một collection với ba lối vào Ask / Compare / Synthesize. |
| `/settings`, `/settings/advanced` | Kết nối model và lượng token đã dùng; công tắc hiện chi tiết kỹ thuật. |

Thêm paper không khoá màn hình: file được upload và xử lý ở nền, một widget theo dõi tiến độ. Chế độ advanced (tắt mặc định, lưu trong trình duyệt) hiện thêm các bước xử lý của paper, danh sách chunk, cách tìm nguồn của từng câu trả lời và cấu hình tìm kiếm của server. Nó chỉ đổi phần hiển thị; quyền vẫn do API kiểm.

## 3. Stack

| Thành phần | Lựa chọn | Lý do |
| --- | --- | --- |
| Ngôn ngữ | Python 3.14 (hiện là 3.14.8) | Nhánh bugfix hiện hành. Python 3.15 vẫn ở trạng thái pre-release trên python.org. Docling, PyTorch, DBOS đều đã khai báo hỗ trợ 3.14. |
| Quản lý package | uv (`pyproject.toml` + `uv.lock`) | Một công cụ cho Python version, dependency, lockfile. |
| API | FastAPI 0.142 + Pydantic v2 | Async, streaming SSE, schema rõ ràng. |
| ORM / migration | SQLAlchemy 2.1 + Alembic | 2.1.3 là bản stable trên PyPI; project mới nên bắt đầu từ 2.1. |
| CSDL chính | PostgreSQL 18 (hiện là 18.6) | PostgreSQL 19 mới ở Beta 4. |
| Vector search | Qdrant 1.19 | Hybrid dense + sparse, RRF hoặc DBSF, BM25 phía server và lọc theo tenant đều có sẵn trong một Query API. |
| Parser PDF | Docling 2.x, sau interface `Parser` | Cho ra cấu trúc tài liệu kèm trang và bounding box, chạy được trên CPU, giấy phép MIT. Xem cảnh báo ở [mục 6](#6-parsing-và-chunking). |
| Chunking | `scientific_chunker` tự viết, chạy trên mô hình tài liệu nội bộ | Giữ ranh giới heading; bảng, caption, công thức là chunk riêng. Không dùng `HybridChunker` của Docling: kích thước ước lượng bằng số ký tự (khoảng 4 ký tự một token), không cần tokenizer của một model embedding cụ thể. |
| Background job | DBOS Transact 3.x | Durable workflow lưu trạng thái ngay trong PostgreSQL, không cần thêm service. |
| Object storage | Interface `ObjectStorage`; hiện chỉ có adapter thư mục local (volume `storage`) | Đủ cho một máy. Adapter S3 / R2 **chưa làm**; thêm khi triển khai nhiều máy. Không dùng MinIO: repo cộng đồng đã bị archive ngày 25/04/2026. |
| Embedding | Model embedding của kết nối mà tài khoản đang dùng | Mặc định `gemini-embedding-2` (768 chiều) với Gemini, `amazon.titan-embed-text-v2:0` (1.024 chiều) với Bedrock; endpoint tương thích OpenAI thì người dùng tự chọn. Mỗi model một collection Qdrant ([mục 4.2](#42-qdrant)). |
| Sparse | BM25 phía server của Qdrant (`Qdrant/bm25`) | Không cần thêm model; bắt tốt thuật ngữ, tên dataset, số liệu. |
| Xếp hạng lại | Model nhanh của tài khoản đọc các ứng viên và trả về thứ tự (`rag/reranker.py`) | Không có cross-encoder: các nhà cung cấp đang dùng không có API rerank, và tự host trên CPU quá chậm. Tắt được bằng `RERANK_ENABLED`; khi lời gọi hỏng thì dùng thứ tự tìm kiếm. |
| LLM | `ModelProvider` với ba adapter: Gemini, Amazon Bedrock, tương thích OpenAI | Một kết nối phục vụ ba vai trò: `answer` (viết câu trả lời), `fast` (xếp loại và viết lại câu hỏi, xếp hạng lại, chấm bằng chứng, metadata và tóm tắt paper) và `embedding`. Mặc định với Gemini: `gemini-3.5-flash`, `gemini-3.5-flash-lite`. Key được mã hoá bằng `SECRETS_KEY` của server (Fernet) trước khi lưu. |
| Evaluation | Metric retrieval và giám khảo tự viết | Giám khảo theo định nghĩa của Ragas nhưng không dùng thư viện Ragas (bớt một dependency). Xem [mục 9](#9-evaluation). |
| Tracing | OpenTelemetry → Arize Phoenix 20 | Xem được từng bước retrieve, rerank, gọi LLM. Miễn phí khi tự host. |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, shadcn/ui trên Base UI | TanStack Table v8 cho bảng; pdf.js cho trang đọc PDF; `react-markdown` + KaTeX cho câu trả lời. Khung chat tự viết trên SSE. |
| Triển khai | Docker Compose | Sáu service chạy thường trực: `web`, `api`, `worker`, `postgres`, `qdrant`, `phoenix`; thêm `migrate` chạy một lần khi khởi động. |

**Những thứ cố ý không đưa vào phiên bản đầu:**

- **pgvector thay cho Qdrant.** Làm được ở quy mô này, nhưng hybrid search phải tự ghép: full-text search có sẵn của PostgreSQL không xếp hạng theo BM25, còn fusion và gom nhóm theo paper phải tự viết bằng SQL. Qdrant cho cả ba trong một lời gọi.
- **Temporal.** Cần chạy thêm một cụm server và kho lưu trữ riêng. DBOS cho cùng khả năng resume workflow mà chỉ cần PostgreSQL sẵn có.
- **Redis.** Hàng đợi đã nằm trong PostgreSQL. Rate limit và cache ở quy mô này làm được trong process hoặc trong PostgreSQL.
- **Prometheus + Grafana, Kubernetes.** Chưa có nhu cầu vận hành tương ứng.

## 4. Mô hình dữ liệu

### 4.1 PostgreSQL

```text
users                  email, password_hash, active_connection_id
sessions               user_id, token_hash, expires_at
provider_connections   user_id, kind, label, config, secret_encrypted,
                       secret_last4, capabilities
provider_usage         user_id, connection_id, model, role, day,
                       input_tokens, output_tokens

papers                 owner_id, title, year, doi, page_count,
                       original_filename, file_sha256, storage_key,
                       status, processing_step, error_code, error, warnings,
                       embedding_model, index_collection, deleted_at
authors, paper_authors
collections            owner_id, name, description
collection_papers      collection_id, paper_id, created_at

paper_sections         paper_id, parent_id, position, level, title, page
chunks                 id, paper_id, chunk_index, kind, text, embed_text,
                       section_path, page_start, page_end, bboxes, token_count
paper_summaries        paper_id, summary, model, created_at

chat_sessions          user_id, title, scope
chat_messages          session_id, role, content, mode, table,
                       trace_id, retrieval
message_sources        message_id, marker, chunk_id, paper_id, paper_title,
                       page, section_path, snippet

ingestion_runs         paper_id, step, attempt, status, finished_at,
                       details, error
```

Trạng thái của DBOS (hàng đợi, workflow, kết quả step) nằm trong schema `dbos` của cùng database.

Ghi chú:

- `chunks` là nguồn gốc của mọi thứ trong Qdrant và là đích của citation. `kind` nhận một trong các giá trị `text`, `table`, `caption`, `formula`, `reference`. `text` là nguyên văn để trích dẫn; `embed_text` là bản đem đi embedding ([mục 6.2](#62-chunking)).
- `bboxes` lưu toạ độ từng vùng trên trang, tính theo tỉ lệ của trang, để giao diện tô sáng đúng đoạn trong PDF.
- `papers.file_sha256` có ràng buộc unique theo `owner_id` để chặn tải trùng.
- `papers.status` là một trong `UPLOADED`, `PROCESSING`, `READY`, `FAILED`. Bước đang chạy nằm ở `processing_step`; lỗi nằm ở `error_code` và `error`.
- `papers.embedding_model` và `index_collection` ghi paper đã được index bằng model nào, vào collection nào.
- `chat_sessions.scope` là `{"paper_ids": [...]}` hoặc `{"collection_id": ...}`. Với collection, danh sách paper được tính lại ở mỗi câu hỏi.
- `chat_messages.mode` là loại câu trả lời (`factual`, `comparison`, `synthesis`); `table` giữ bảng của câu so sánh; `retrieval` giữ số liệu của lượt tìm kiếm.
- `message_sources` chép sẵn tên paper, trang, mục và một đoạn trích, nên lịch sử vẫn đọc được khi paper nguồn đã bị xoá.
- `collection_members` (chia sẻ collection) **chưa làm**: hiện collection chỉ thuộc về một tài khoản.

### 4.2 Qdrant

Mỗi model embedding có một cặp collection:

| Collection | Một point là | Vector |
| --- | --- | --- |
| `chunks__<model>-<hash>__<số chiều>__v1` | một chunk | `dense`, `bm25` (sparse, bật IDF modifier) |
| `papers__<model>-<hash>__<số chiều>__v1` | một paper (tiêu đề + tóm tắt) | `dense`, `bm25` |

Hai collection ứng với hai tầng tìm kiếm. Vector cấp chunk dùng để tìm đúng đoạn bằng chứng. Vector cấp paper dùng để chọn paper nào đáng đọc khi phạm vi của câu so sánh hoặc tổng hợp vượt trần số paper ([mục 7.4](#74-synthesis-tổng-hợp-trên-nhiều-paper)); nó không thay được vector cấp chunk, vì một vector không đại diện nổi cho mọi phần của paper.

Tìm kiếm dense trong Qdrant là tìm gần đúng qua index HNSW, không so câu hỏi với từng vector. Kết quả có thể thiếu một vài điểm gần nhất thật sự; ở quy mô của dự án sai lệch này nhỏ và được đo gộp trong Recall@k.

Quy ước:

- **ID tất định.** ID của chunk là `uuid5(NAMESPACE, f"{paper_id}:{chunk_index}:{chunking_version}")`, dùng chung cho hàng trong PostgreSQL và point trong Qdrant. Chạy lại ingestion sẽ ghi đè, không tạo bản trùng. Point của paper có ID là `paper_id`.
- **Tên collection mang model và số chiều.** Hai tài khoản dùng cùng model embedding dùng chung collection (tách nhau bằng filter `owner_id`); khác model thì khác collection. Không có alias: code tính tên collection từ model embedding của kết nối đang dùng.
- **Đổi model embedding.** Paper index bằng model khác với kết nối đang dùng thì không được tìm (vector khác không gian), và câu trả lời ghi rõ đã bỏ bao nhiêu paper. `POST /papers/reindex` chạy lại workflow từ bước `embed`; point ở collection cũ bị xoá.
- **Payload** của mỗi chunk: `owner_id`, `paper_id`, `chunk_index`, `kind`. Text của chunk đọc từ PostgreSQL, không lưu bản thứ hai trong Qdrant.
- **Payload index:** `owner_id` (keyword, `is_tenant: true`), `paper_id` (keyword), `kind` (keyword).

### 4.3 Giữ PostgreSQL và Qdrant đồng bộ

- **Ghi:** ghi `chunks` vào PostgreSQL trước, upsert Qdrant sau; bước `validate` đếm point trong Qdrant và chỉ đặt `READY` khi khớp đúng số chunk. Truy vấn chỉ lấy paper ở trạng thái `READY`.
- **Xoá:** API đánh dấu `deleted_at` (paper biến mất khỏi mọi danh sách ngay), rồi một workflow xoá point, xoá file, cuối cùng mới xoá bản ghi.
- **Đối soát định kỳ** giữa hai bên: **chưa làm**.

## 5. Ingestion pipeline

Một paper là một DBOS workflow; mỗi bước là một step được lưu kết quả. Worker chết giữa chừng thì khi khởi động lại, các step đã xong không chạy lại; step đang dở chạy lại từ đầu step đó. Vì vậy paper không bị parse lại từ đầu, nhưng mỗi step phải chịu được việc chạy hai lần.

DBOS là thư viện chạy ngay trong process worker, không phải một service điều phối riêng. API chỉ đưa việc vào hàng đợi theo tên workflow (`ingestion/queue.py`), không nạp code của worker.

```text
upload (API)
  └─ lưu PDF vào object storage, tạo papers(status=UPLOADED), enqueue workflow

workflow ingest_paper(paper_id, first_step="parse")
  1. parse       PDF → ScientificDocument, lưu JSON vào object storage
  2. metadata    tiêu đề, tác giả, năm: model nhanh đọc trang đầu; DOI bằng regex.
                 Không ghi đè thứ chủ paper đã sửa tay.
  3. chunk       → paper_sections + chunks (PostgreSQL)
  4. summarize   model nhanh tóm tắt paper → paper_summaries (tắt được)
  5. embed       embedding cho mọi chunk và cho paper; vector lưu vào object storage
  6. index       upsert vào Qdrant (dense + văn bản cho BM25)
  7. validate    số point khớp số chunk → status=READY
```

Mọi lời gọi model trong workflow dùng kết nối của **chủ paper**. Tài khoản chưa có kết nối thì paper dừng ở `FAILED` với `error_code = provider_not_configured`.

Quy tắc khi viết step:

- **Idempotent.** Mỗi step xoá-rồi-ghi theo `paper_id` hoặc upsert theo ID tất định.
- **Step chỉ trả về số liệu nhỏ.** Tài liệu đã parse và vector nằm trong object storage; step sau tự đọc lại. Kết quả step (lưu trong PostgreSQL) chỉ là vài con số, cũng là thứ hiện ở "Processing details".
- **Giới hạn song song.** Hàng đợi chạy `INGEST_CONCURRENCY` paper cùng lúc (mặc định 1) vì Docling cần 2–3 GB RAM mỗi paper.
- **Retry có giới hạn** (3 lần) cho lỗi tạm thời: mạng, rate limit. Lỗi do nội dung file (PDF hỏng, bị khoá, quá `MAX_PAPER_PAGES`) hay do cấu hình (thiếu kết nối, key sai) chuyển thẳng sang `FAILED` kèm mã lỗi và thông báo cho người dùng.
- **Mỗi lần thử được ghi lại** trong `ingestion_runs` (bước, lần thử, thời gian, số liệu, lỗi).

Chạy lại: `POST /papers/{id}/reingest` bắt đầu từ `parse`; `POST /papers/reindex` bắt đầu từ `embed` cho các paper index bằng model embedding khác.

## 6. Parsing và chunking

### 6.1 Parser

Docling là parser đang dùng: nó trả về cây tài liệu (heading, đoạn, bảng, caption, công thức) kèm số trang và bounding box cho từng phần tử, đúng thứ citation cần. Docling không dùng LLM, nhưng vẫn chạy các model nhận diện layout và bảng; đó là lý do worker cần nhiều CPU và RAM. Cấu hình: tắt OCR, bật nhận diện bảng. Số đo trên CPU và lý do chọn: [docs/decisions/0001-cpu-spike-results.md](docs/decisions/0001-cpu-spike-results.md).

Cảnh báo cần biết: trên olmOCR-Bench, một bài so sánh tháng 7/2026 ghi Docling 2.116 đạt 50,3 điểm, so với 76,0 của Marker 2 (chế độ balanced, cần GPU) và 72,7 của MinerU 3.4. Các con số này lấy từ một bài blog, chưa được kiểm tra lại trên dữ liệu của dự án, và dự án chưa đo parser nào khác ngoài Docling.

Parser nằm sau interface để đổi được về sau:

```python
class Parser(Protocol):
    def parse(self, pdf: bytes) -> ScientificDocument: ...
```

`ScientificDocument` là mô hình nội bộ (section, block, vị trí trên trang). Mọi phần phía sau chỉ biết mô hình này, nên đổi parser không ảnh hưởng tới chunking hay retrieval.

### 6.2 Chunking

`scientific_chunker` đi qua các block của `ScientificDocument` theo thứ tự đọc:

- Các đoạn văn được gộp tới `CHUNK_MAX_TOKENS` (mặc định 400), không bao giờ gộp qua một heading. Block dài hơn giới hạn bị cắt ở cuối câu.
- Bảng, caption và công thức là chunk riêng (`table`, `caption`, `formula`), để không bị văn xuôi xung quanh làm loãng.
- Phần References được đánh dấu `reference` và bị loại khỏi mọi lượt tìm kiếm.
- Văn bản đem embedding (`embed_text`) được ghép thêm tiêu đề paper và đường dẫn section ("Experiments > Evaluation") ở đầu. Văn bản lưu trong `text` giữ nguyên bản gốc để trích dẫn.
- Kích thước tính bằng ước lượng 4 ký tự một token, nên không phụ thuộc tokenizer của model embedding nào.

Giá trị 400 được chốt bằng eval ([mục 13](#13-quyết-định-còn-mở)). Đổi quy tắc chunk thì tăng `CHUNKING_VERSION`, ID của chunk đổi theo.

## 7. Retrieval và generation

### 7.1 Định tuyến câu hỏi

Mỗi câu hỏi đi một trong ba đường: `factual`, `comparison`, `synthesis`. Người hỏi chọn thẳng bằng `mode` của yêu cầu (ba nút Ask / Compare / Synthesize trên giao diện), hoặc để `auto`.

- **`auto`:** model nhanh xếp loại câu hỏi, trong cùng lời gọi viết lại câu hỏi cho tự đứng được mà không cần lịch sử hội thoại. Lời gọi này chạy đồng thời với bước embedding câu hỏi. Không đọc được câu trả lời của model thì coi là `factual`: xếp nhầm một câu factual sang tổng hợp là lỗi đắt.
- **Phạm vi một paper luôn là `factual`**, bất kể `mode`.
- **Phạm vi** không do model suy ra: đó là `scope` của phiên (danh sách paper hoặc một collection), giao với các paper tài khoản được đọc và đang `READY`.

Trên 76 câu golden, `auto` xếp đúng 75 ([docs/decisions/0003-multi-paper-config.md](docs/decisions/0003-multi-paper-config.md)).

### 7.2 Factual: tìm đúng đoạn

```text
query
 ├─ dense  (top 50) ─┐
 └─ BM25   (top 50) ─┴─ RRF → 30 ứng viên → model nhanh xếp lại → 8 chunk → LLM
```

Hai nhánh prefetch và bước RRF chạy trong một lời gọi Query API của Qdrant. Kết quả trộn được sắp lại theo điểm rồi theo ID trước khi cắt, vì RRF cho điểm bằng nhau rất thường và Qdrant không giữ thứ tự cố định giữa các điểm bằng nhau. Các con số 50 / 30 / 8 đã được chốt bằng eval.

Vai trò của từng bước:

- **Dense** tìm theo nghĩa: bắt được cách diễn đạt khác và từ đồng nghĩa, nhưng dễ trượt tên riêng và ký hiệu.
- **BM25** tìm theo từ, và cho từ hiếm trọng số cao hơn từ phổ biến. "SciERC" hay "BERT-base" vì thế rất có giá trị; "Table 3" gần như không, vì paper nào cũng có.
- **RRF** gộp hai danh sách theo thứ hạng, không theo điểm số, nên không phải lo hai thang điểm khác nhau. `SEARCH_FUSION` cho đổi sang `dbsf` hoặc `none` (chỉ dense) để thí nghiệm.
- **Xếp lại** do model nhanh làm: nó đọc câu hỏi cùng 30 ứng viên (mỗi đoạn cắt ở 1.200 ký tự) và trả về thứ tự. Lời gọi hỏng hoặc kết nối được ghi nhận là trả JSON không ổn định thì giữ thứ tự tìm kiếm. Bước này đưa recall@1 từ 0,37 lên 0,53.

Context có trần 6.000 token; câu trả lời tối đa 2.048 token.

### 7.3 Comparison: mỗi paper đều phải có mặt

```text
mỗi paper trong phạm vi: 3 chunk sát câu hỏi nhất   (một truy vấn mỗi paper, gửi chung một lượt)
→ context chia khối theo paper → LLM trả JSON {columns, rows, summary}
→ kiểm tra bảng → sự kiện `table` → đoạn nhận xét
```

- Mỗi paper một truy vấn riêng với cùng prefetch và fusion như đường factual, gửi trong một lời gọi batch. Không dùng groups API của Qdrant, và không xếp lại trong từng nhóm.
- LLM tự chọn các cột tiêu chí từ câu hỏi và điền từng ô kèm marker. Sau khi sinh, bảng được kiểm: mỗi paper trong phạm vi có đúng một hàng (paper thiếu thì thêm hàng ghi không tìm thấy), marker trong ô phải thuộc paper của hàng đó.
- Bảng không dùng được thì thử lại một lần; vẫn hỏng thì trả lời bằng văn bản chia theo paper.
- Paper được nhắc bằng tên; mã nội bộ của paper trong prompt bị gỡ khỏi đoạn nhận xét.

### 7.4 Synthesis: tổng hợp trên nhiều paper

Một lượt top-k không đủ cho literature review. Đường này làm theo hướng của PaperQA2 (gom bằng chứng, tóm tắt theo câu hỏi, rồi mới tổng hợp):

```text
1. Chọn paper      mọi paper trong phạm vi; quá N (mặc định 20) thì hybrid search
                   trên collection cấp paper để giữ N paper sát câu hỏi nhất
2. Gom bằng chứng  với mỗi paper: M (mặc định 3) chunk sát câu hỏi nhất
3. Chấm và tóm tắt model nhanh chấm độ liên quan (0–10) của từng chunk và tóm tắt
                   nó theo câu hỏi; bỏ chunk dưới ngưỡng (mặc định 4)
4. Tổng hợp        LLM chính viết bài bốn phần từ các tóm tắt, kèm marker nguồn
```

- Bước 3 chạy song song, tối đa `MULTI_PAPER_PARALLEL_CALLS` lời gọi cùng lúc (mặc định 4). Một chunk không chấm được không làm hỏng cả câu hỏi; 8 chunk liên tiếp không chấm được thì thôi không gửi nữa.
- "Không tìm thấy" chỉ được nói khi **mọi** chunk đã được chấm và không chunk nào qua ngưỡng. Còn chunk chưa chấm được thì bài được viết từ các đoạn gốc.
- Bài viết có bốn phần cố định: tổng quan, điểm thống nhất, điểm khác biệt, khoảng trống nghiên cứu. Phần nào thiếu bằng chứng thì ghi rõ là thiếu.
- Marker trỏ về chunk gốc, không trỏ về bản tóm tắt.
- Client nhận sự kiện `status` theo từng bước (`selecting`, `gathering`, `comparing`, `writing`), kèm số chunk đã đọc.

Chi phí đo được trên 12 paper: 36 lời gọi model nhanh, khoảng 85 nghìn token vào, trung vị 56 giây. Context của hai đường nhiều paper có trần 16.000 token, câu trả lời 4.096 token.

### 7.5 Citation

- Mỗi chunk đưa vào context mang một marker (`[S1]`, `[S2]`, …). LLM được yêu cầu gắn marker sau từng nhận định.
- Bộ kiểm trích dẫn (`rag/citation.py`) loại mọi marker không có trong context. Marker model viết theo dạng khác được nhận lại: ngoặc tròn `(S1)` chỉ được coi là marker khi cả câu trả lời không có marker ngoặc vuông nào và ngoặc không đứng sát sau chữ hay số.
- Mỗi marker hợp lệ được lưu vào `message_sources`. Giao diện mở PDF tại đúng trang và tô sáng theo `bboxes`.
- Khi context không đủ để trả lời, hệ thống nói rõ là không tìm thấy trong các paper đã chọn (`outcome = no_evidence`), không suy đoán.

Giới hạn cần biết: bộ kiểm chỉ bảo đảm marker trỏ tới một chunk có thật trong context. Nó không bảo đảm chunk đó chứng minh được câu mang marker. Phần này được đo ở evaluation ([mục 9](#9-evaluation)): với câu factual, 95–99% câu có trích dẫn được nguồn chứng minh, nên không thêm bước kiểm tra lúc chạy. Với câu so sánh và tổng hợp, con số này **chưa đo**.

### 7.6 Giao diện của lõi RAG

```python
async for event in rag.engine.answer(connection, question, paper_ids=..., history=..., mode="auto"):
    ...
```

```text
engine.answer
  xếp loại + viết lại câu hỏi ‖ embedding câu hỏi
  → paths/factual | paths/comparison | paths/synthesis
  → kiểm trích dẫn → Done
```

`answer` là một async generator phát các sự kiện; API chuyển chúng thành SSE trên `POST /chats/{id}/messages`:

| Sự kiện | Nội dung |
| --- | --- |
| `sources` | Các chunk đưa cho model, mỗi chunk một marker kèm paper, trang, mục. |
| `status` | Loại câu trả lời, bước đang làm, số chunk đã đọc. |
| `table` | Bảng của câu so sánh. |
| `delta` | Từng mẩu chữ của câu trả lời. |
| `done` | Bản cuối đã kiểm trích dẫn, marker được dùng, `outcome`, thông báo khi chỉ một phần phạm vi được xem. |
| `error` | Mã lỗi và thông báo khi nhà cung cấp model lỗi. |

Câu hỏi và câu trả lời chỉ được lưu khi có `done`. Người đọc ngắt kết nối thì generator đóng, lời gọi model dừng và không có gì được lưu. Lượng token của mỗi lời gọi được cộng vào `provider_usage` theo ngày, model và vai trò; hệ thống chỉ đếm token, không quy ra tiền.

## 8. Xác thực và phân quyền

- **Xác thực:** email và mật khẩu (băm bằng Argon2). Phiên đăng nhập là một token ngẫu nhiên gửi trong cookie; server chỉ lưu hash của token. Đăng nhập sai nhiều lần bị giới hạn theo (IP, email), đếm trong bộ nhớ của process API. Tắt đăng ký mới bằng `ALLOW_REGISTRATION=false`.
- **Key model:** mỗi tài khoản lưu các kết nối của mình; bí mật được mã hoá bằng `SECRETS_KEY` và API chỉ trả về bốn ký tự cuối. Địa chỉ của endpoint tương thích OpenAI bị chặn nếu là địa chỉ mạng nội bộ, trừ khi bật `ALLOW_PRIVATE_PROVIDER_URLS`.
- **Quyền:** paper và collection thuộc về người tạo; hiện không có chia sẻ. Vai trò `owner` / `editor` / `viewer` trên collection **chưa làm**.
- **Áp quyền khi retrieve:** API tự tính danh sách `paper_id` người dùng được đọc từ PostgreSQL (`access/readable_papers.py`), rồi đưa vào filter của Qdrant cùng `owner_id`. Filter không bao giờ lấy từ dữ liệu client gửi lên. Mọi truy vấn Qdrant đều đi qua `index/search.py`, nơi filter này là tham số bắt buộc.
- **Nội dung paper là dữ liệu, không phải chỉ dẫn:** các prompt đặt đoạn văn của paper trong khối riêng và dặn model không làm theo chỉ dẫn nằm trong đó.

## 9. Evaluation

Dựng bộ đánh giá trước khi tối ưu bất kỳ thứ gì.

**Dữ liệu.**

- **QASPER** (5.049 câu hỏi trên 1.585 paper NLP, có đánh dấu đoạn bằng chứng) để đo retrieval và chất lượng câu trả lời trên paper thật.
- **Bộ golden tự xây** (`eval/golden/`): câu hỏi trên 12 PDF thật đi qua parser của dự án. 53 câu factual, mỗi câu có đoạn bằng chứng chép nguyên văn và câu trả lời tham chiếu; 15 câu so sánh và 10 câu tổng hợp, mỗi câu ghi các paper phải có mặt trong trích dẫn. Đây là bộ quyết định khi hai nguồn mâu thuẫn.

**Metric.**

| Tầng | Metric |
| --- | --- |
| Retrieval | Recall@k, MRR, nDCG@k (tự viết, so với chunk bằng chứng) |
| Context | context precision, context recall (model làm giám khảo, theo định nghĩa của Ragas) |
| Câu trả lời | faithfulness, answer relevance (model làm giám khảo, theo định nghĩa của Ragas) |
| Citation | tỉ lệ marker hợp lệ; tỉ lệ nhận định có nguồn thực sự chứng minh nó |
| Nhiều paper | độ chính xác xếp loại câu hỏi; độ phủ paper (paper mong đợi được trích dẫn); câu so sánh có ra bảng hay không |
| Vận hành | độ trễ từng bước, số token mỗi câu hỏi |

Định nghĩa các metric retrieval, tính trên từng câu hỏi rồi lấy trung bình cả bộ:

- **Recall@k:** tỉ lệ đoạn bằng chứng có chunk chứa nó trong k kết quả đầu. Một câu hỏi có ba đoạn bằng chứng mà tìm được hai thì Recall@k là 2/3.
- **MRR:** 1 chia cho thứ hạng của chunk bằng chứng đầu tiên tìm được. Chunk đúng đứng thứ ba thì được 1/3.
- **nDCG@k:** chất lượng thứ tự của cả k kết quả; chunk đúng càng ở trên điểm càng cao.

**Cách chạy.** Bộ đo đưa câu hỏi qua đúng `rag.engine.answer` mà câu hỏi của người dùng đi, trên các tài khoản riêng (`chunk-<n>@eval.invalid`), bằng key trong `GEMINI_API_KEY`. Mỗi file TOML trong `eval/configs/` là một thí nghiệm; kết quả lưu vào `eval-results/` kèm cấu hình và commit. Giám khảo trả về `None` khi không đọc được câu trả lời của model; các câu đó bị loại khỏi trung bình và được đếm riêng.

**Cách dùng.** Mỗi thay đổi về parser, chunk, embedding, sparse, xếp hạng lại hay prompt chạy lại bộ đánh giá và ghi kết quả kèm cấu hình. Thay đổi làm giảm metric chính thì không được gộp.

**Chưa đo:** faithfulness và citation support của câu so sánh và tổng hợp; hybrid so với chỉ dense trên phạm vi nhiều paper.

## 10. Observability

API phát trace bằng OpenTelemetry và gửi tới Phoenix (project `scientrag`). Mỗi câu hỏi là một trace, mỗi bước là một span: `analyze_question` hoặc `rewrite_question`, `embed_query`, `retrieve`, `rerank`, `gather_evidence` (câu tổng hợp), `generate`. Span ghi câu truy vấn, các chunk tìm được, model và số token.

`trace_id` được lưu cùng câu trả lời (`chat_messages.trace_id`), và `chat_messages.retrieval` giữ số liệu của lượt đó: loại câu hỏi, câu truy vấn đã viết lại, số paper và số ứng viên ở từng bước, model, thời gian tới lúc tìm xong và tới chữ đầu tiên, số token. `GET /chats/messages/{id}/retrieval` trả lại chúng; giao diện hiện ở "Retrieval details" khi bật advanced.

Tiến trình của từng paper nằm trong `ingestion_runs` (`GET /papers/{id}/ingestion`), không nằm trong trace.

Trace chứa câu hỏi và nội dung paper, nên cổng của Phoenix chỉ mở trên máy chạy Docker. Log ứng dụng dạng JSON có `trace_id` **chưa làm**.

## 11. Cấu trúc mã nguồn

```text
SciRAG/
├── apps/
│   ├── api/            FastAPI: routers (auth, papers, chunks, chats, collections,
│   │                   providers), schemas, SSE, giới hạn kích thước upload
│   ├── worker/         điểm khởi động worker DBOS
│   └── web/            Next.js: app (các trang), components, lib (gọi API, SSE, upload)
├── src/scientrag/
│   ├── config.py       mọi tham số, đọc từ biến môi trường
│   ├── db/             SQLAlchemy models, repositories, migrations (Alembic)
│   ├── auth/           mật khẩu, phiên đăng nhập, mã hoá key, giới hạn đăng nhập sai
│   ├── access/         paper nào một tài khoản được đọc
│   ├── storage/        ObjectStorage + adapter thư mục local
│   ├── parsing/        ScientificDocument + adapter Docling
│   ├── chunking/       scientific_chunker
│   ├── providers/      ModelProvider + adapter Gemini, Bedrock, OpenAI-compatible
│   ├── index/          Qdrant: collection, upsert, tìm kiếm có filter quyền
│   ├── ingestion/      hàng đợi, workflow và các step
│   ├── rag/            engine, analyzer, reranker, context_builder, citation,
│   │                   evidence_summarizer, prompts, paths/{factual,comparison,synthesis}
│   ├── telemetry/      trace
│   └── evaluation/     dataset, metric, giám khảo, runner, report
├── tests/              unit và integration
├── eval/               bộ golden và cấu hình thí nghiệm
├── docs/               decisions, journals, screenshots
├── compose.yaml
└── pyproject.toml
```

`requires-python = ">=3.14,<3.15"`.

## 12. Triển khai

Docker Compose: `web`, `api`, `worker`, `postgres`, `qdrant`, `phoenix`, và `migrate` (chạy Alembic và tạo bảng của DBOS một lần khi khởi động).

- `api` và `worker` build từ cùng một Dockerfile, hai target. Chỉ image `worker` có Docling và PyTorch (bản CPU), nên image `api` nhỏ và khởi động nhanh.
- `worker` giới hạn 4 GB RAM. Lần đầu xử lý một PDF, nó tải model của parser (khoảng 500 MB) vào volume `models`.
- Không service nào yêu cầu GPU, và không service nào giữ key model: key nằm trong database, đã mã hoá.
- Nội dung paper và câu hỏi được gửi tới nhà cung cấp model mà tài khoản đã chọn. Câu hỏi được embed bằng đúng model đã dùng để index.
- Cổng của API, web và Phoenix chỉ mở trên `127.0.0.1`.
- Sao lưu: PostgreSQL và volume `storage`. Qdrant dựng lại được bằng cách index lại.

Compose hiện là cấu hình dev (API và web tự nạp lại khi sửa code). Cấu hình production, HTTPS và sao lưu tự động **chưa làm**.

## 13. Quyết định còn mở

**Đã chốt** (số liệu và lý do: [0001](docs/decisions/0001-cpu-spike-results.md), [0002](docs/decisions/0002-eval-results-and-config.md), [0003](docs/decisions/0003-multi-paper-config.md)):

| Câu hỏi | Quyết định |
| --- | --- |
| Parser | Docling, tắt OCR, bật nhận diện bảng. Bounding box đủ tốt để tô sáng. |
| Embedding | Qua API, theo kết nối của từng tài khoản. Không tự host. |
| Xếp hạng lại | Model nhanh của tài khoản, 30 ứng viên, 8 đoạn vào model. Đưa recall@1 từ 0,37 lên 0,53. |
| Kích thước chunk | 400 token. Chunk 800 có recall cao hơn ở cùng số chunk nhưng thấp hơn ở cùng lượng token đưa vào model. |
| Fusion | RRF. DBSF thấp hơn ở recall@5 và recall@8. |
| Kiểm tra citation lúc chạy | Không thêm. Với câu factual, marker hợp lệ 100% và 95–99% câu có trích dẫn được nguồn chứng minh. |
| Nhiều paper | Tối đa 20 paper, 3 đoạn mỗi paper, ngưỡng liên quan 4, 4 lời gọi song song. Giữ mặc định: số đo hiện có không cho căn cứ để đổi. |

**Còn mở:**

| Câu hỏi | Cần gì để chốt |
| --- | --- |
| Faithfulness của câu so sánh và tổng hợp | Chạy ba cấu hình `golden-classify`, `golden-comparison`, `golden-synthesis` với giám khảo. |
| Ngưỡng liên quan của bước chấm bằng chứng | Đo lại bằng một model chấm nghiêm hơn; model miễn phí cho gần như mọi đoạn qua ngưỡng. |
| Hybrid so với chỉ dense trên nhiều paper | Chưa đo vì hết hạn mức model lúc làm eval. |
| So sánh gần 20 paper | Bảng có thể vượt trần token đầu ra; chưa thử ở quy mô đó. |
| Parser khác (Marker, MinerU) | Chỉ khi có GPU hoặc khi chất lượng parse trở thành điểm nghẽn. |
| ColBERT | Chỉ thử khi bước xếp lại hiện tại chưa đủ. |

**Hệ quả khi đổi model embedding.** Vector của hai model khác nhau không so được với nhau. Tài khoản đổi sang kết nối có model embedding khác thì các paper cũ phải được embed lại vào collection của model mới (`POST /papers/reindex`, [mục 4.2](#42-qdrant)). Chi phí là thời gian và token chạy lại, không phải sửa code. Đổi model trả lời hoặc model nhanh thì không cần index lại.

## 14. Đường nâng cấp

| Dấu hiệu | Thay đổi |
| --- | --- |
| Có GPU | Benchmark lại parser (thêm MinerU, Marker balanced), embedding (thêm Qwen3-Embedding) và reranker (thêm Qwen3-Reranker) ở dạng tự host; chuyển nếu chất lượng hoặc chi phí tốt hơn API. |
| Hàng nghìn workflow đồng thời, nhiều ngôn ngữ, workflow kéo dài nhiều tuần | DBOS → Temporal. Cấu trúc workflow / step chuyển sang workflow / activity gần như một-một. |
| Nhiều instance API cần chung rate limit hoặc cache | Thêm Redis 8. |
| Cần cảnh báo và dashboard vận hành | Thêm Prometheus + Grafana, dùng lại OpenTelemetry đã có. |
| Một máy không đủ tải | Docker Compose → Kubernetes; tách worker embedding sang node có GPU. |
| Hàng chục triệu chunk | Bật quantization và sharding trong Qdrant. |

## 15. Lộ trình

| Bước | Trạng thái |
| --- | --- |
| 1. Kiểm chứng stack trên CPU | Xong |
| 2. Nền tảng: schema, auth, upload, object storage, Docker Compose | Xong |
| 3. Ingestion: workflow bảy bước, resume, trạng thái từng bước | Xong |
| 4. Factual RAG: hybrid search, xếp lại, câu trả lời có citation qua SSE, trace | Xong |
| 5. Evaluation: QASPER và bộ golden, chốt cấu hình | Xong (bộ thí nghiệm rút gọn) |
| 6. Giao diện web: thư viện, phiên hỏi đáp, tô sáng nguồn trong PDF | Xong |
| 7. Nhiều paper: collection, comparison, synthesis, chế độ advanced | Xong (còn phép đo faithfulness) |
| 8. Hoàn thiện và triển khai: chia sẻ collection, đối soát index, cấu hình production | Chưa làm |

## 16. Nguồn

Phiên bản:

- [Python downloads](https://www.python.org/downloads/): 3.14.8 phát hành 30/09/2026, 3.15 còn pre-release
- [PostgreSQL](https://www.postgresql.org/): 18.6 phát hành 13/08/2026, 19 Beta 4 ngày 24/09/2026
- [SQLAlchemy trên PyPI](https://pypi.org/project/SQLAlchemy/): 2.1.3
- [Docling trên PyPI](https://pypi.org/project/docling/): 2.133.0, hỗ trợ Python 3.10–3.14
- [Qdrant releases](https://github.com/qdrant/qdrant/releases): 1.19.1
- [DBOS trên PyPI](https://pypi.org/project/dbos/): 3.2.0, MIT
- [FastAPI trên PyPI](https://pypi.org/project/fastapi/): 0.142.2
- [Ragas trên PyPI](https://pypi.org/project/ragas/): 0.4.3 (chỉ tham khảo định nghĩa metric; không cài)
- [Redis releases](https://github.com/redis/redis/releases): 8.10.2
- [MinIO repository](https://github.com/minio/minio): archive ngày 25/04/2026

Thiết kế:

- [Qdrant: Hybrid Search](https://qdrant.tech/documentation/search-tuning/hybrid-search/): prefetch, RRF, DBSF, BM25 phía server
- [Qdrant: Hybrid Queries](https://qdrant.tech/documentation/concepts/hybrid-queries/): truy vấn nhiều tầng
- [Qdrant: Multitenancy](https://qdrant.tech/documentation/guides/multitenancy/): `is_tenant`
- [Docling: Chunking](https://docling-project.github.io/docling/concepts/chunking/): `HierarchicalChunker`, `HybridChunker`
- [DBOS: Queues](https://docs.dbos.dev/python/tutorials/queue-tutorial) và [DBOS so với Temporal](https://www.dbos.dev/compare/dbos-vs-temporal)
- [PDF Parsing for RAG 2026: MinerU vs Docling vs Marker](https://builderai.tools/blog/pdf-parsing-for-rag-mineru-docling-marker-compared): điểm olmOCR-Bench, giấy phép
- [PaperQA2 (arXiv 2409.13740)](https://arxiv.org/abs/2409.13740): RAG dạng agent cho tài liệu khoa học
- [QASPER (arXiv 2105.03011)](https://arxiv.org/abs/2105.03011): bộ dữ liệu hỏi đáp trên paper
- [Best Embedding Models for RAG 2026](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/): BGE-M3, Qwen3-Embedding
- [Phoenix self-hosting](https://arize.com/docs/phoenix/self-hosting)

## Phụ lục: Thuật ngữ

| Thuật ngữ | Nghĩa trong tài liệu này |
| --- | --- |
| RAG | Tìm các đoạn liên quan trong kho paper, đưa chúng vào context, rồi để LLM trả lời dựa trên đó. LLM đọc và diễn đạt; kiến thức nằm ở paper. |
| Chunk | Một đoạn của paper (đoạn văn, bảng, caption) được index và trích dẫn như một đơn vị. |
| Embedding | Vector số biểu diễn nghĩa của một đoạn văn bản; hai đoạn gần nghĩa có vector gần nhau. |
| Dense retrieval | Tìm chunk có embedding gần embedding của câu hỏi nhất. |
| Sparse retrieval / BM25 | Tìm chunk theo từ trùng với câu hỏi, từ hiếm được trọng số cao hơn. |
| Hybrid search | Chạy cả dense và BM25 rồi gộp kết quả. |
| RRF | Cách gộp nhiều danh sách kết quả dựa trên thứ hạng của mỗi chunk trong từng danh sách. |
| Xếp hạng lại (rerank) | Bước đọc câu hỏi cùng các ứng viên để sắp lại theo độ liên quan. Ở đây do model nhanh của tài khoản làm. |
| Model nhanh / model trả lời | Hai vai trò LLM của một kết nối: model rẻ cho các bước phụ, model chính viết câu trả lời. |
| Collection | Trong giao diện và API: nhóm paper của một tài khoản để hỏi chung. Trong Qdrant: nơi chứa các point. Hai thứ không liên quan. |
| Ingestion | Quá trình biến một PDF thành chunk đã được index và sẵn sàng truy vấn. |
| Durable workflow | Workflow lưu kết quả từng bước, nên sau sự cố chạy tiếp được từ bước dở. |
| Bounding box | Toạ độ hình chữ nhật của một vùng trên trang PDF, dùng để tô sáng nguồn. |
| Marker | Nhãn `[S1]`, `[S2]`, … gắn cho từng chunk trong context để LLM dẫn nguồn. |
| Golden set | Bộ câu hỏi có sẵn chunk bằng chứng và câu trả lời tham chiếu, dùng để đo hệ thống. |
