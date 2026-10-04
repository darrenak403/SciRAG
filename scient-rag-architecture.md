# ScientRAG — Tài liệu kiến trúc

Cập nhật: 04/10/2026. Các số phiên bản trong tài liệu đã được đối chiếu với nguồn chính thức vào ngày này (xem [Nguồn](#16-nguồn)).

## 1. Mục tiêu và phạm vi

ScientRAG là hệ thống hỏi đáp trên bài báo khoa học do người dùng tải lên. Hệ thống phải làm được bốn việc:

1. Trả lời câu hỏi cụ thể trong một hoặc vài paper ("Bảng 3 báo cáo F1 bao nhiêu cho BERT-base trên SciERC?").
2. So sánh nhiều paper theo một tiêu chí (phương pháp, dataset, kết quả).
3. Tổng hợp trên cả một collection (literature review, research gap).
4. Mọi nhận định trong câu trả lời đều dẫn về đúng đoạn, đúng trang của paper nguồn.

Ngoài phạm vi của phiên bản đầu: tìm paper trên internet, hiểu nội dung hình ảnh, cộng tác thời gian thực, fine-tune model.

**Quy mô và ràng buộc đã chốt.**

- Người dùng là cá nhân hoặc nhóm nhỏ: vài trăm đến vài nghìn paper, dưới một triệu chunk, tối đa vài chục người dùng đồng thời.
- **CPU-first.** Giai đoạn đầu hệ thống chạy trên server hiện có, không có GPU. Parsing, ingestion và retrieval phải chạy được bằng CPU.
- Embedding và reranker được phép gọi qua API nếu tự host trên CPU quá chậm. Khi có GPU mới benchmark lại và cân nhắc chuyển về tự host.

Mọi lựa chọn "nhẹ" bên dưới dựa trên các ràng buộc này; [mục 14](#14-đường-nâng-cấp) ghi rõ khi nào cần đổi sang phương án nặng hơn.

**Nguyên tắc thiết kế.**

- PostgreSQL là nguồn dữ liệu gốc. Qdrant là index dẫn xuất, xoá đi dựng lại được từ PostgreSQL.
- Mỗi thành phần hay thay đổi (parser, embedding, reranker, LLM, object storage) nằm sau một interface riêng.
- Lõi RAG tự viết, không phụ thuộc framework như LangChain, để kiểm soát và đo được từng bước.
- Không thêm service nào khi chưa có nhu cầu đo được.

## 2. Tổng quan kiến trúc

```text
                      ┌──────────────────────┐
                      │  Next.js Research UI │
                      └──────────┬───────────┘
                                 │ HTTP / SSE
                                 ▼
                      ┌──────────────────────┐
                      │       FastAPI        │
                      │ Auth · Papers · Chat │
                      │ Collections · Search │
                      │      RAG Engine      │
                      └──┬─────┬─────┬────┬──┘
        ghi/đọc business │     │     │    │ gọi model
        + enqueue job    │     │     │    └───────────────┐
                         ▼     │     ▼                    ▼
              ┌──────────────┐ │ ┌──────────┐   ┌───────────────────┐
              │ PostgreSQL 18│ │ │  Qdrant  │   │  Model providers  │
              │ business data│ │ │ dense +  │   │ Embedding         │
              │ chunks (gốc) │ │ │ BM25     │   │ Reranker          │
              │ job state    │ │ │ hybrid   │   │ LLM               │
              └──────▲───────┘ │ └────▲─────┘   └─────────▲─────────┘
                     │         │      │                   │
       dequeue job,  │         │      │ upsert / delete   │ embed
       ghi chunks    │         ▼      │                   │
              ┌──────┴────────────────┴───────────────────┴─────────┐
              │              Ingestion worker (DBOS)                │
              │ parse → metadata → chunk → embed → index → validate │
              └───────────────────────┬─────────────────────────────┘
                                      │ PDF, DoclingDocument JSON
                                      ▼
                           ┌─────────────────────┐
                           │ S3-compatible store │
                           └─────────────────────┘

      FastAPI và worker gửi trace qua OpenTelemetry → Phoenix
```

API process không bao giờ parse PDF hay tính embedding hàng loạt. Nó chỉ ghi bản ghi `papers`, đưa job vào hàng đợi và trả về ngay. Worker là một process riêng chạy cùng codebase.

## 3. Stack

| Thành phần | Lựa chọn | Lý do |
| --- | --- | --- |
| Ngôn ngữ | Python 3.14 (hiện là 3.14.8) | Nhánh bugfix hiện hành. Python 3.15 vẫn ở trạng thái pre-release trên python.org. Docling, PyTorch, DBOS đều đã khai báo hỗ trợ 3.14. |
| Quản lý package | uv (`pyproject.toml` + `uv.lock`) | Một công cụ cho Python version, dependency, lockfile. |
| API | FastAPI 0.142 + Pydantic v2 | Async, streaming SSE, schema rõ ràng. |
| ORM / migration | SQLAlchemy 2.1 + Alembic | 2.1.3 là bản stable trên PyPI; project mới nên bắt đầu từ 2.1. |
| CSDL chính | PostgreSQL 18 (hiện là 18.6) | PostgreSQL 19 mới ở Beta 4. |
| Vector search | Qdrant 1.19 | Hybrid dense + sparse, RRF, BM25 phía server, gom nhóm theo paper và lọc theo tenant đều có sẵn trong một Query API. |
| Parser PDF | Docling 2.x, sau interface `Parser` | Cho ra cấu trúc tài liệu kèm trang và bounding box, chạy được trên CPU, giấy phép MIT. Xem cảnh báo ở [mục 6](#6-parsing-và-chunking). |
| Chunking | Docling `HybridChunker` + `ScientificChunker` tự viết | Giữ ranh giới heading, bảng, caption. |
| Background job | DBOS Transact 3.x | Durable workflow lưu trạng thái ngay trong PostgreSQL, không cần thêm service. |
| Object storage | Interface theo S3 API | Dev: Garage hoặc thư mục local. Production: S3 / Cloudflare R2. Không dùng MinIO: repo cộng đồng đã bị archive ngày 25/04/2026. |
| Embedding | `EmbeddingProvider`; hai ứng viên: BGE-M3 tự host trên CPU, hoặc một model qua API | BGE-M3 có giấy phép MIT, context 8.192 token. Chọn bên nào do benchmark CPU ở [mục 13](#13-quyết-định-còn-mở) quyết định. |
| Sparse | BM25 phía server của Qdrant (`Qdrant/bm25`) | Không cần thêm model; bắt tốt thuật ngữ, tên dataset, số liệu. |
| Reranker | `Reranker`; hai ứng viên: `bge-reranker-v2-m3` tự host trên CPU, hoặc reranker qua API | Đây là bước dễ vượt ngân sách độ trễ nhất khi không có GPU, nên nhiều khả năng bắt đầu bằng API. ColBERT để lại làm thí nghiệm. |
| LLM | `LLMProvider`; mặc định Claude | Sonnet 5.5 cho bước sinh câu trả lời, Haiku 4.5 cho các bước rẻ (phân loại query, tóm tắt bằng chứng). Có adapter cho OpenAI, Gemini và model local qua API tương thích OpenAI. |
| Evaluation | Ragas 0.4 + metric retrieval tự viết | Xem [mục 9](#9-evaluation). |
| Tracing | OpenTelemetry → Arize Phoenix | Xem được từng bước retrieve, rerank, gọi LLM. Miễn phí khi tự host. |
| Frontend | Next.js + TypeScript + Tailwind + shadcn/ui | |
| Triển khai | Docker Compose | Sáu container: `web`, `api`, `worker`, `postgres`, `qdrant`, `phoenix`. |

**Những thứ cố ý không đưa vào phiên bản đầu:**

- **pgvector thay cho Qdrant.** Làm được ở quy mô này, nhưng hybrid search phải tự ghép: full-text search có sẵn của PostgreSQL không xếp hạng theo BM25, còn fusion và gom nhóm theo paper phải tự viết bằng SQL. Qdrant cho cả ba trong một lời gọi.
- **Temporal.** Cần chạy thêm một cụm server và kho lưu trữ riêng. DBOS cho cùng khả năng resume workflow mà chỉ cần PostgreSQL sẵn có.
- **Redis.** Hàng đợi đã nằm trong PostgreSQL. Rate limit và cache ở quy mô này làm được trong process hoặc trong PostgreSQL.
- **Prometheus + Grafana, Kubernetes.** Chưa có nhu cầu vận hành tương ứng.

## 4. Mô hình dữ liệu

### 4.1 PostgreSQL

```text
users
papers                 owner_id, title, doi, file_sha256, storage_key,
                       status, parser_version, error
authors, paper_authors
collections, collection_papers
collection_members     collection_id, user_id, role

paper_sections         paper_id, parent_id, heading, level, order
chunks                 id, paper_id, section_id, chunk_index, kind,
                       text, token_count, page_start, page_end, bboxes,
                       section_path, chunking_version
paper_summaries        paper_id, summary, model, created_at

chat_sessions, chat_messages
message_sources        message_id, chunk_id, marker, quote

ingestion_runs         paper_id, workflow_id, step, status, started_at
```

Ghi chú:

- `chunks` là nguồn gốc của mọi thứ trong Qdrant và là đích của citation. `kind` nhận một trong các giá trị `text`, `table`, `figure_caption`, `equation`, `reference`.
- `bboxes` lưu toạ độ từng vùng trên trang để giao diện tô sáng đúng đoạn trong PDF.
- `papers.file_sha256` có ràng buộc unique theo `owner_id` để chặn tải trùng.
- `papers.status` đi theo thứ tự `UPLOADED → PARSING → CHUNKING → EMBEDDING → INDEXING → READY`, hoặc `FAILED` kèm `error`.

### 4.2 Qdrant

Hai collection:

| Collection | Một point là | Vector |
| --- | --- | --- |
| `chunks__<embedding>__v<n>` | một chunk | `dense` (1.024 chiều với BGE-M3), `bm25` (sparse, bật IDF modifier) |
| `papers__<embedding>__v<n>` | một paper (tiêu đề + abstract + tóm tắt) | `dense`, `bm25` |

Hai collection ứng với hai tầng tìm kiếm. Vector cấp chunk dùng để tìm đúng đoạn bằng chứng. Vector cấp paper dùng để chọn paper nào đáng đọc cho câu hỏi tổng hợp ([mục 7.4](#74-synthesis-tổng-hợp-trên-nhiều-paper)); nó không thay được vector cấp chunk, vì một vector không đại diện nổi cho mọi phần của paper.

Tìm kiếm dense trong Qdrant là tìm gần đúng qua index HNSW, không so câu hỏi với từng vector. Kết quả có thể thiếu một vài điểm gần nhất thật sự; ở quy mô của dự án sai lệch này nhỏ và được đo gộp trong Recall@k.

Quy ước:

- **Point ID tất định.** `uuid5(NAMESPACE, f"{paper_id}:{chunk_index}:{chunking_version}")`. Chạy lại ingestion sẽ ghi đè, không tạo bản trùng.
- **Version theo tên collection.** Đổi embedding model hoặc cách chunk thì dựng collection mới, kiểm tra bằng eval, rồi trỏ alias `chunks_current` / `papers_current` sang. Code chỉ truy vấn qua alias.
- **Payload** của mỗi chunk: `owner_id`, `paper_id`, `chunk_id`, `kind`, `section_path`, `page_start`, `year`. Text của chunk đọc từ PostgreSQL theo `chunk_id`, không lưu bản thứ hai trong Qdrant.
- **Payload index:** `owner_id` (keyword, `is_tenant: true`), `paper_id` (keyword), `kind` (keyword), `year` (integer).

### 4.3 Giữ PostgreSQL và Qdrant đồng bộ

- **Ghi:** ghi `chunks` vào PostgreSQL trước, upsert Qdrant sau, cuối cùng mới đặt `papers.status = READY`. Truy vấn chỉ lấy paper ở trạng thái `READY`.
- **Xoá:** đánh dấu paper là đã xoá trong PostgreSQL, xoá point theo filter `paper_id`, rồi mới xoá hẳn bản ghi.
- **Đối soát:** một job định kỳ so số chunk của từng paper giữa hai bên và index lại paper bị lệch.

## 5. Ingestion pipeline

Một paper là một DBOS workflow; mỗi bước là một step được lưu kết quả. Worker chết giữa chừng thì khi khởi động lại, các step đã xong không chạy lại; step đang dở chạy lại từ đầu step đó. Vì vậy paper không bị parse lại từ đầu, nhưng mỗi step phải chịu được việc chạy hai lần.

DBOS là thư viện chạy ngay trong process worker, không phải một service điều phối riêng.

Ingestion chạy nền vì nó chậm. Bài so sánh parser dẫn ở [mục 6.1](#61-parser) ghi Docling khoảng 2 trang mỗi giây, tức một paper 100 trang mất gần một phút chỉ riêng bước parse, chưa kể bước tóm tắt gọi LLM và bước embedding. Con số thật trên máy của dự án cần đo lại.

```text
upload (API)
  └─ lưu PDF vào object storage, tạo papers(status=UPLOADED), enqueue workflow

workflow ingest_paper(paper_id)
  1. parse       PDF → DoclingDocument, lưu JSON vào object storage
  2. metadata    tiêu đề, tác giả, năm, DOI; bổ sung qua tra cứu DOI nếu có
  3. chunk       DoclingDocument → paper_sections + chunks (PostgreSQL)
  4. summarize   sinh tóm tắt paper → paper_summaries
  5. embed       dense embedding theo lô cho chunks và cho paper
  6. index       upsert vào Qdrant (dense + văn bản cho BM25)
  7. validate    số point khớp số chunk → status=READY
```

Quy tắc khi viết step:

- **Idempotent.** Mỗi step xoá-rồi-ghi theo `paper_id` hoặc upsert theo ID tất định.
- **Step chỉ trả về tham chiếu.** Kết quả step được lưu vào PostgreSQL, nên step trả về `storage_key` hoặc danh sách ID, không trả về cả tài liệu đã parse.
- **Giới hạn song song.** Hàng đợi `ingest` đặt `worker_concurrency` thấp (1–2) vì Docling ngốn CPU và RAM. Lời gọi embedding và LLM qua API dùng `limiter` để không vượt rate limit của nhà cung cấp.
- **Retry có giới hạn** cho lỗi tạm thời (mạng, rate limit). Lỗi do nội dung file (PDF hỏng, bị khoá) chuyển thẳng sang `FAILED` kèm thông báo cho người dùng.

## 6. Parsing và chunking

### 6.1 Parser

Docling là lựa chọn mặc định vì nó trả về cây tài liệu (heading, đoạn, bảng, caption, công thức) kèm số trang và bounding box cho từng phần tử, đúng thứ citation cần. Docling không dùng LLM, nhưng vẫn chạy các model nhận diện layout và bảng; đó là lý do worker cần nhiều CPU và RAM.

Cảnh báo cần biết: trên olmOCR-Bench, một bài so sánh tháng 7/2026 ghi Docling 2.116 đạt 50,3 điểm, so với 76,0 của Marker 2 (chế độ balanced, cần GPU) và 72,7 của MinerU 3.4. Chỉ tính PDF born-digital thì khoảng cách là 64,0 so với 83,5 và 83,3. Bài đó cũng khuyên dùng MinerU cho paper nhiều công thức vì nó chuyển công thức sang LaTeX. Các con số này lấy từ một bài blog, chưa được kiểm tra lại trên dữ liệu của dự án.

Với ràng buộc CPU-first, đối thủ thực tế của Docling là Marker 2 ở chế độ fast: cùng bài đó ghi nó chạy được trên CPU và đạt 66,6 điểm. MinerU và Marker balanced cần GPU nên để lại cho giai đoạn sau. Trước khi so sánh cần kiểm tra Marker có trả về bounding box đủ dùng cho citation hay không; nếu không thì nó bị loại bất kể điểm số.

Vì vậy parser nằm sau interface, và so sánh parser là thí nghiệm đầu tiên cần làm ([mục 13](#13-quyết-định-còn-mở)):

```python
class Parser(Protocol):
    def parse(self, pdf: bytes) -> ScientificDocument: ...
```

`ScientificDocument` là mô hình nội bộ (section, block, bảng, công thức, vị trí trên trang). Mọi phần phía sau chỉ biết mô hình này, nên đổi parser không ảnh hưởng tới chunking hay retrieval.

### 6.2 Chunking

`ScientificChunker` bắt đầu từ kết quả của `HybridChunker` (chia theo cấu trúc, cắt chunk quá dài và gộp chunk quá ngắn theo tokenizer của embedding model) rồi áp thêm quy tắc riêng cho paper:

- Không gộp qua ranh giới heading hoặc subheading.
- Bảng là chunk riêng, kèm caption; bảng dài thì lặp lại hàng tiêu đề ở mỗi phần.
- Caption của hình là chunk riêng, loại `figure_caption`.
- Công thức đi cùng đoạn văn giải thích nó.
- Phần References được đánh dấu `reference` và mặc định bị loại khỏi retrieval.
- Văn bản đem embedding được ghép thêm tiêu đề paper và đường dẫn section ("Experiments > Evaluation") ở đầu. Văn bản lưu trong `chunks.text` giữ nguyên bản gốc để trích dẫn.

Kích thước chunk là tham số cấu hình, giá trị chốt lấy từ eval.

## 7. Retrieval và generation

### 7.1 Định tuyến câu hỏi

`QueryAnalyzer` (một lời gọi LLM rẻ, trả về JSON) xác định:

- **loại câu hỏi:** `factual`, `comparison` hoặc `synthesis`;
- **phạm vi:** paper hoặc collection nào, suy từ ngữ cảnh chat và lựa chọn trên giao diện;
- **câu truy vấn đã viết lại:** tự đứng được mà không cần lịch sử hội thoại.

Ba loại câu hỏi đi ba đường khác nhau.

### 7.2 Factual: tìm đúng đoạn

```text
query
 ├─ dense  (top 50) ─┐
 └─ BM25   (top 50) ─┴─ RRF → 30 ứng viên → cross-encoder → 8 chunk → LLM
```

Hai nhánh prefetch và bước RRF chạy trong một lời gọi Query API của Qdrant. Reranker chạy ở tầng ứng dụng. Các con số 50 / 30 / 8 là giá trị khởi điểm, chốt bằng eval.

Vai trò của từng bước:

- **Dense** tìm theo nghĩa: bắt được cách diễn đạt khác và từ đồng nghĩa, nhưng dễ trượt tên riêng và ký hiệu.
- **BM25** tìm theo từ, và cho từ hiếm trọng số cao hơn từ phổ biến. "SciERC" hay "BERT-base" vì thế rất có giá trị; "Table 3" gần như không, vì paper nào cũng có.
- **RRF** gộp hai danh sách theo thứ hạng, không theo điểm số, nên không phải lo hai thang điểm khác nhau.
- **Cross-encoder** đọc câu hỏi và chunk cùng lúc, nên đánh giá chính xác hơn bước retrieve (vốn embed hai bên riêng rẽ). Đổi lại nó chậm, chỉ chạy được trên vài chục ứng viên.

### 7.3 Comparison: mỗi paper đều phải có mặt

Dùng API gom nhóm của Qdrant với `group_by="paper_id"` và `group_size` khoảng 3, để mỗi paper trong phạm vi đóng góp các chunk tốt nhất của nó thay vì một paper chiếm hết top-k. Rerank trong từng nhóm, rồi dựng context theo từng paper. LLM được yêu cầu trả lời theo cấu trúc so sánh và nói rõ khi một paper không đề cập tới tiêu chí được hỏi.

### 7.4 Synthesis: tổng hợp trên nhiều paper

Một lượt top-k không đủ cho literature review. Đường này làm theo hướng của PaperQA2 (tìm paper, gom bằng chứng, tóm tắt có ngữ cảnh, rồi mới tổng hợp):

```text
1. Chọn paper      hybrid search trên papers_current → tối đa N paper (N ≈ 20)
2. Gom bằng chứng  với mỗi paper: lấy vài chunk liên quan nhất tới câu hỏi
3. Chấm và tóm tắt LLM rẻ chấm độ liên quan từng chunk và tóm tắt nó theo câu hỏi;
                   bỏ chunk dưới ngưỡng
4. Tổng hợp        LLM chính viết câu trả lời từ các tóm tắt, kèm marker nguồn
```

Bước 2 và 3 chạy song song theo paper. Số paper và số chunk mỗi paper có trần cứng để kiểm soát chi phí và độ trễ.

### 7.5 Citation

- Mỗi chunk đưa vào context mang một marker (`[S1]`, `[S2]`, …). LLM được yêu cầu gắn marker sau từng nhận định.
- `CitationValidator` kiểm tra mọi marker trong câu trả lời đều tồn tại trong context, và loại bỏ marker bịa.
- Mỗi marker hợp lệ được lưu vào `message_sources` cùng `chunk_id`. Giao diện mở PDF tại đúng trang và tô sáng theo `bboxes`.
- Khi context không đủ để trả lời, hệ thống nói rõ là không tìm thấy trong các paper đã chọn, không suy đoán.

Giới hạn cần biết: validator chỉ bảo đảm marker trỏ tới một chunk có thật trong context. Nó không bảo đảm chunk đó chứng minh được câu mang marker; LLM vẫn có thể gắn một marker hợp lệ vào một nhận định sai. Phần này được đo ở evaluation ([mục 9](#9-evaluation)), không bị chặn lúc chạy. Thêm một bước kiểm tra lúc chạy (LLM rẻ đối chiếu từng câu với chunk được dẫn) là một lựa chọn ở [mục 13](#13-quyết-định-còn-mở).

### 7.6 Giao diện của lõi RAG

```python
result = await rag.query(question, scope=Scope(collection_id=...), user=user)
```

```text
RAGEngine
  QueryAnalyzer → Retriever → Reranker → ContextBuilder → Generator → CitationValidator
```

Câu trả lời được stream về client qua SSE; danh sách nguồn gửi trước, văn bản gửi sau.

## 8. Xác thực và phân quyền

- **Xác thực:** email và mật khẩu (băm bằng Argon2), phiên đăng nhập lưu trong cookie httpOnly. Đăng nhập qua Google là tuỳ chọn về sau.
- **Quyền:** paper thuộc về người tải lên. Collection có thành viên với vai trò `owner`, `editor` hoặc `viewer`.
- **Áp quyền khi retrieve:** API tự tính danh sách `paper_id` người dùng được đọc từ PostgreSQL, rồi đưa vào filter của Qdrant. Filter không bao giờ lấy từ dữ liệu client gửi lên. Mọi truy vấn Qdrant đều đi qua một hàm duy nhất bắt buộc có filter này.

## 9. Evaluation

Dựng bộ đánh giá trước khi tối ưu bất kỳ thứ gì.

**Dữ liệu.**

- **QASPER** (5.049 câu hỏi trên 1.585 paper NLP, có đánh dấu đoạn bằng chứng) để đo retrieval và chất lượng câu trả lời trên paper thật.
- **Bộ golden tự xây:** 50–100 câu hỏi trên chính corpus của dự án, gồm cả ba loại câu hỏi, mỗi câu có chunk bằng chứng và câu trả lời tham chiếu. Đây là bộ quyết định khi hai nguồn mâu thuẫn.

**Metric.**

| Tầng | Metric |
| --- | --- |
| Retrieval | Recall@k, MRR, nDCG@k (tự viết, so với chunk bằng chứng) |
| Context | context precision, context recall (Ragas) |
| Câu trả lời | faithfulness, answer relevance (Ragas) |
| Citation | tỉ lệ marker hợp lệ; tỉ lệ nhận định có nguồn thực sự chứng minh nó |
| Vận hành | độ trễ từng bước, số token, chi phí mỗi câu hỏi |

Định nghĩa các metric retrieval, tính trên từng câu hỏi rồi lấy trung bình cả bộ:

- **Recall@k:** tỉ lệ chunk bằng chứng xuất hiện trong k kết quả đầu. Một câu hỏi có ba chunk bằng chứng mà tìm được hai thì Recall@k là 2/3.
- **MRR:** 1 chia cho thứ hạng của chunk bằng chứng đầu tiên tìm được. Chunk đúng đứng thứ ba thì được 1/3.
- **nDCG@k:** chất lượng thứ tự của cả k kết quả; chunk đúng càng ở trên điểm càng cao.

**Cách dùng.** Mỗi thay đổi về parser, chunk, embedding, sparse, reranker hay prompt chạy lại bộ đánh giá và ghi kết quả kèm cấu hình. Thay đổi làm giảm metric chính thì không được gộp.

## 10. Observability

FastAPI và worker phát trace bằng OpenTelemetry và gửi tới Phoenix. Mỗi câu hỏi là một trace, mỗi bước là một span, ghi:

- loại câu hỏi và phạm vi;
- ID và điểm của các chunk sau retrieve và sau rerank;
- model, số token, độ trễ của từng lời gọi embedding, rerank và LLM;
- kết quả kiểm tra citation.

Log ứng dụng ở dạng JSON có `trace_id`. Nội dung paper và câu hỏi của người dùng không ghi vào log ứng dụng; chúng chỉ xuất hiện trong trace, và Phoenix chỉ mở trong mạng nội bộ.

## 11. Cấu trúc mã nguồn

```text
scientrag/
├── apps/
│   ├── api/            FastAPI: routers, auth, schemas
│   ├── worker/         điểm khởi động worker DBOS
│   └── web/            Next.js
├── src/scientrag/
│   ├── db/             SQLAlchemy models, repositories, migrations
│   ├── storage/        ObjectStorage + adapter S3 / local
│   ├── parsing/        Parser + adapter Docling
│   ├── chunking/       ScientificChunker
│   ├── providers/      EmbeddingProvider, Reranker, LLMProvider + adapter
│   ├── index/          Qdrant: collection, upsert, truy vấn có filter quyền
│   ├── ingestion/      workflow và các step
│   ├── rag/            analyzer, retriever, context, generator, citation
│   └── evaluation/     dataset, metric, runner
├── tests/
├── compose.yaml
└── pyproject.toml
```

`requires-python = ">=3.14,<3.15"`.

## 12. Triển khai

Docker Compose với sáu service: `web`, `api`, `worker`, `postgres`, `qdrant`, `phoenix`. Thêm `garage` nếu muốn dev giống production về object storage.

- `api` và `worker` dùng chung một image, khác lệnh khởi động.
- `worker` cần nhiều RAM hơn `api` vì Docling và model embedding chạy trong đó.
- Không service nào yêu cầu GPU. Model tự host (nếu benchmark cho thấy đủ nhanh) nạp một lần khi worker hoặc API khởi động.
- Embedding và reranker có thể chạy tự host hoặc qua API, chọn bằng cấu hình. Hai điều cần nhớ khi dùng API: nội dung paper và câu hỏi được gửi tới bên thứ ba, và câu hỏi phải được embed bằng đúng model đã dùng để index.
- Sao lưu: chỉ cần PostgreSQL và object storage. Qdrant dựng lại được.

## 13. Quyết định còn mở

Các điểm sau chốt bằng eval, không chốt bằng cảm giác:

| Câu hỏi | Phương án so sánh | Cần biết trước |
| --- | --- | --- |
| Parser | Docling so với Marker 2 fast, trên CPU, khoảng 20 paper mẫu có bảng và công thức | Marker có trả bounding box hay không |
| Embedding | BGE-M3 trên CPU so với một model qua API | Ngân sách API; paper có được phép gửi ra ngoài hay không |
| Reranker | `bge-reranker-v2-m3` trên CPU so với reranker qua API | Ngân sách độ trễ bên dưới |
| Kích thước chunk | Khoảng 400 so với 800 token | |
| Fusion | RRF so với DBSF | |
| ColBERT | Thêm bước rescoring đa vector trong Qdrant | Chỉ thử khi cross-encoder chưa đủ |
| Kiểm tra citation lúc chạy | Có hay không bước LLM đối chiếu từng câu với chunk được dẫn | Tỉ lệ citation sai đo được, độ trễ và chi phí chấp nhận được |

**Benchmark CPU.** Ba hàng đầu được quyết bằng cách đo trên chính server sẽ triển khai, cùng lúc với chất lượng:

| Đo gì | Ngưỡng đề xuất để giữ tự host |
| --- | --- |
| Parse một paper 12 trang | Dưới 1 phút |
| Embed toàn bộ chunk của một paper khi ingest | Dưới 1 phút |
| Embed một câu hỏi lúc truy vấn | Dưới 200 ms |
| Rerank 30 ứng viên lúc truy vấn | Dưới 1,5 giây |

Các ngưỡng này là đề xuất để có điểm xuất phát, nhóm chỉnh theo trải nghiệm mong muốn. Bước nào vượt ngưỡng thì chuyển sang API. Với reranker, trước khi chuyển có thể thử giảm số ứng viên từ 30 xuống 15–20 và đo lại cả độ trễ lẫn chất lượng.

**Hệ quả khi đổi embedding model.** Vector của hai model khác nhau không so được với nhau, nên chuyển từ API sang tự host (hoặc ngược lại) nghĩa là embed lại toàn bộ corpus vào một collection mới rồi đổi alias ([mục 4.2](#42-qdrant)). Kiến trúc đã tính sẵn việc này; chi phí là thời gian chạy lại, không phải sửa code. Đổi reranker thì không cần index lại.

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

Chạy song song với bước 1: vài notebook thử embedding, hybrid search và rerank trên một ít paper thật. Chúng vừa để nhóm nắm khái niệm, vừa thành khung cho các thí nghiệm ở bước 4.

1. **Nền tảng.** Schema, auth, upload, object storage, Docker Compose.
2. **Ingestion.** Workflow đủ bảy bước cho một paper, có resume và trạng thái hiển thị trên giao diện.
3. **Factual RAG.** Hybrid search, rerank, sinh câu trả lời có citation, stream qua SSE.
4. **Evaluation.** QASPER và bộ golden; chạy các thí nghiệm ở mục 13 và chốt cấu hình.
5. **Nhiều paper.** Đường comparison, rồi đường synthesis.
6. **Hoàn thiện.** Tô sáng nguồn trong PDF, chia sẻ collection, đối soát index.

## 16. Nguồn

Phiên bản:

- [Python downloads](https://www.python.org/downloads/): 3.14.8 phát hành 30/09/2026, 3.15 còn pre-release
- [PostgreSQL](https://www.postgresql.org/): 18.6 phát hành 13/08/2026, 19 Beta 4 ngày 24/09/2026
- [SQLAlchemy trên PyPI](https://pypi.org/project/SQLAlchemy/): 2.1.3
- [Docling trên PyPI](https://pypi.org/project/docling/): 2.133.0, hỗ trợ Python 3.10–3.14
- [Qdrant releases](https://github.com/qdrant/qdrant/releases): 1.19.1
- [DBOS trên PyPI](https://pypi.org/project/dbos/): 3.2.0, MIT
- [FastAPI trên PyPI](https://pypi.org/project/fastapi/): 0.142.2
- [Ragas trên PyPI](https://pypi.org/project/ragas/): 0.4.3
- [Redis releases](https://github.com/redis/redis/releases): 8.10.2
- [MinIO repository](https://github.com/minio/minio): archive ngày 25/04/2026

Thiết kế:

- [Qdrant: Hybrid Search](https://qdrant.tech/documentation/search-tuning/hybrid-search/): prefetch, RRF, DBSF, BM25 phía server
- [Qdrant: Hybrid Queries](https://qdrant.tech/documentation/concepts/hybrid-queries/): truy vấn nhiều tầng, gom nhóm
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
| Reranker / cross-encoder | Model đọc câu hỏi và một chunk cùng lúc để chấm lại độ liên quan của các ứng viên. |
| Ingestion | Quá trình biến một PDF thành chunk đã được index và sẵn sàng truy vấn. |
| Durable workflow | Workflow lưu kết quả từng bước, nên sau sự cố chạy tiếp được từ bước dở. |
| Bounding box | Toạ độ hình chữ nhật của một vùng trên trang PDF, dùng để tô sáng nguồn. |
| Marker | Nhãn `[S1]`, `[S2]`, … gắn cho từng chunk trong context để LLM dẫn nguồn. |
| Golden set | Bộ câu hỏi có sẵn chunk bằng chứng và câu trả lời tham chiếu, dùng để đo hệ thống. |
