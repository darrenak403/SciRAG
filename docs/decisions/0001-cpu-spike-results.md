# 0001 — Kết quả spike kiểm chứng stack trên CPU

- Ngày đo: 2026-10-04
- Code: `spikes/cpu-validation/` (chạy bằng `docker compose run --rm spike` và `docker compose run --rm spike python dbos_resume_check.py`)
- Trạng thái: đã đo đủ các bước. Các bảng số lấy từ **một lượt chạy** (lượt cuối) trên 3 paper và 5 câu hỏi, không phải trung bình. Spike đã chạy 5 lượt; chỗ nào các lượt lệch nhau đáng kể thì ghi kèm khoảng dao động.

## Máy đo

Laptop dev, không phải server. Mọi con số bên dưới chỉ để tham khảo; đo lại ở phase 8.

| | |
|---|---|
| Máy | Apple M2, 8 core, 16 GB RAM |
| Docker Desktop | 8 CPU, 7,7 GB RAM cấp cho Docker; container `linux/arm64` |
| Phiên bản (xem trong image lúc đo; spike không có lockfile) | Python 3.14.8, Docling 2.133.0, PyTorch 2.14.1+cpu, qdrant-client 1.19.1, Qdrant 1.19.0, DBOS 3.2.0, PostgreSQL 18 |

## Quyết định

| Việc | Quyết định | Căn cứ |
|---|---|---|
| Phiên bản Python | **3.14** | Cả bộ `docling torch qdrant-client dbos sqlalchemy psycopg[binary]` cài được trên `python:3.14-slim` (arm64), không gói nào thiếu wheel. |
| Parser | **Docling**, tắt OCR, bật nhận diện bảng | Mọi phần tử đều có số trang và bbox; bbox khớp đúng cột. Marker không đo (đã bỏ khỏi spike). |
| Citation | Tô sáng theo bbox của chunk | bbox đủ tốt. Thứ tự đọc có lỗi ở một trang (xem dưới) nhưng không ảnh hưởng vị trí tô sáng. |
| BM25 | **Phía server** (`models.Document(model="Qdrant/bm25")`) | Chạy được trên Qdrant 1.19.0 tự host, không cần `fastembed` ở client. |
| DBOS | Dùng như kiến trúc mô tả | Resume đúng: step đã xong không chạy lại, step dở chạy lại từ đầu. |
| LLM và embedding | **Gemini, free tier, một key.** LLM: Gemini Flash. Embedding: `gemini-embedding-2`, 768 chiều | Không tốn tiền; người làm đã có key. Embed một câu hỏi 0,6–0,8 giây. |
| Reranker | **Không dùng API rerank trả phí.** Nền là thứ tự RRF; thêm bước LLM chọn đoạn (Gemini Flash-Lite), tắt được | Gemini không có API rerank. Giữ hay bỏ bước LLM do eval ở phase 5 quyết định. |

## Số đo

### Dung lượng đĩa (ngân sách 8 GB)

| Thành phần | Dung lượng |
|---|---|
| Image `spike` (Python + Docling + PyTorch CPU) | 2,36 GB |
| Model Docling (layout + bảng) và tokenizer, trong volume | 0,53 GB |
| Image `postgres:18` | 0,67 GB |
| Image `qdrant/qdrant:v1.19.0` | 0,29 GB |
| **Tổng image + model** | **≈ 3,9 GB** |
| Build cache sau hai lần build (đo lúc dọn dẹp bằng `docker builder prune`) | 4,2 GB |

Tính cả build cache thì đỉnh khoảng 8,1 GB, sát ngân sách 8 GB. Build cache là phần lớn nhất và xoá được ngay sau mỗi lần build. Sau bước dọn dẹp, `docker system df` báo 0 B ở mọi mục.

Image slim thiếu thư viện hệ thống cho OpenCV: phải cài `libgl1 libglib2.0-0 libxcb1`, nếu không model bảng của Docling không import được. Image `worker` ở phase 3 cần đúng ba gói này.

### Parse (Docling, `do_ocr=False`, `do_table_structure=True`)

| Paper | Trang | Giây | Giây/trang | Phần tử | Có trang + bbox | Bảng | Công thức |
|---|---|---|---|---|---|---|---|
| ResNet (hai cột, nhiều bảng) | 12 | 33,0 | 2,75 | 214 | 214 | 15 | 2 |
| BERT (hai cột) | 16 | 34,4 | 2,15 | 258 | 258 | 8 | 0 |
| Adam (một cột, nhiều công thức) | 15 | 13,2 | 0,88 | 163 | 163 | 0 | 36 |

- Dao động giữa các lượt: ResNet 33–35 giây, BERT 34–39 giây, Adam 13–21 giây.
- Nạp model: 2,3 giây (model đã có trong volume). Lần chạy đầu tải thêm khoảng 0,5 GB.
- RAM đỉnh của container: **2,14 GB** ở lượt này, 2,1–2,5 GB qua các lượt. Con số đọc từ `memory.peak` của cgroup nên gồm cả page cache, và script giữ cả ba tài liệu đã parse trong bộ nhớ; nó là cận trên thô, không phải nhu cầu cho một paper.
- Paper 12 trang: **33 giây**. Chậm hơn nhiều so với con số "2 trang/giây" của bài blog dẫn trong kiến trúc; một paper 100 trang hai cột sẽ mất khoảng 4–5 phút riêng bước parse. Paper đầu tiên trong lượt chạy gánh cả phần khởi động.

Nhận xét khi xem JSON bằng mắt:

- **bbox:** chính xác. Cột trái và cột phải có toạ độ ngang tách bạch (ResNet: 0,08–0,47 và 0,51–0,89 sau khi chuẩn hoá). Chuẩn hoá về tỉ lệ 0–1 gốc trên-trái làm được bằng `bbox.to_top_left_origin(page_height)` rồi chia cho kích thước trang.
- **Thứ tự đọc:** đúng ở BERT và ở trang 2 trở đi của ResNet. Sai ở trang 1 của ResNet: cột phải (hình 1 và ba đoạn văn) đứng trước Abstract và cột trái. Hệ quả: chunk ở trang đầu có thể ghép đoạn không liền mạch.
- **Bảng:** cấu trúc hàng/cột đọc được (bảng 1 của ResNet: 8 × 8, ô tiêu đề đúng).
- **Công thức:** Docling nhận ra vùng công thức nhưng để `text` rỗng; nội dung nằm ở trường `orig` dưới dạng chữ dàn phẳng, không phải LaTeX (ví dụ `vt = (1 - β2) t∑ i=1 βt-i 2 · g2 i (1)`). Số thứ tự công thức có chỗ bị đảo. Muốn có LaTeX phải bật `do_formula_enrichment`, tức tải thêm model và chậm hơn; chưa đo.
- Dấu watermark arXiv ở lề trái bị nhận thành `picture`.

### Chunk (`HybridChunker` mặc định)

| Paper | Chunk | Token nhỏ nhất | Trung vị | p95 | Lớn nhất |
|---|---|---|---|---|---|
| ResNet | 95 | 33 | 201 | 261 | 266 |
| BERT | 97 | 19 | 205 | 264 | 265 |
| Adam | 58 | 18 | 181 | 251 | 255 |

Thời gian chunk dưới 0,4 giây mỗi paper. Mặc định `HybridChunker` đếm token bằng tokenizer `all-MiniLM-L6-v2` với trần 256 token, nên chunk khá nhỏ: 4–8 chunk mỗi trang, khoảng 1 150 token mỗi trang. Bảng trên đếm token của văn bản đã ghép thêm heading (thứ sẽ đem đi embed), vì vậy giá trị lớn nhất nhỉnh hơn 256.

### BM25 phía server

- Tạo collection với sparse vector `bm25` (IDF modifier), upsert 250 point bằng `models.Document(text=..., model="Qdrant/bm25")`: 0,03 giây, server nhận.
- Truy vấn chỉ BM25: 1 ms mỗi câu (11 ms cho câu đầu tiên). Câu có tên riêng và ký hiệu (`ResNet`, `top-5`, `β1`, `β2`) trả về đúng paper và đúng mục.
- Câu tiếng Việt ("BERT-Large có bao nhiêu tham số?") chỉ khớp được nhờ từ `BERT-Large`; top 3 không có đoạn nêu số tham số. Đúng như dự kiến: BM25 không bắc cầu được giữa hai ngôn ngữ, phần này phụ thuộc vào nhánh dense.

### DBOS resume

Workflow 3 step, mỗi step ghi một dòng vào PostgreSQL. Process bị `SIGKILL` giữa step 2, rồi khởi động lại.

| Step | Số lần chạy |
|---|---|
| 1 | 1 |
| 2 | 2 |
| 3 | 1 |

Số lần chạy khớp với mô tả của kiến trúc: kết quả step 1 được lưu lại, step 2 chạy lại từ đầu. Giới hạn của phép thử: ở lần khởi động lại, script vừa để DBOS tự khôi phục vừa gọi lại workflow bằng cùng ID, nên con số trên chứng minh việc lưu kết quả từng step, chưa tách riêng được cơ chế tự khôi phục lúc khởi động.

Một điều thấy trong log, **chưa thử**: lúc khởi động DBOS ghi `Recovering 1 workflows from application version <mã băm>`, tức việc khôi phục gắn với application version, mặc định là mã băm của code. Nếu đúng vậy thì sửa code rồi khởi động lại worker sẽ không tự chạy tiếp workflow dở của bản cũ. Phase 3 cần thử điều này trước khi quyết định đặt `application_version` cố định hay làm lệnh quản trị chạy lại paper kẹt ở `PROCESSING`.

### Embedding, hybrid search, rerank qua Gemini

Model: `gemini-embedding-2` ở 768 chiều; rerank bằng `gemini-3.5-flash-lite`. Free tier, gọi từ Việt Nam.

| Phép đo | Kết quả |
|---|---|
| Embed một paper (95 chunk, 2 lô) | 4,0 giây |
| Embed một câu hỏi | 0,50–0,60 giây |
| Số chiều vector trả về | 768 |
| Upsert 250 point (dense + BM25) | 0,11 giây |
| Truy vấn hybrid (2 prefetch + RRF, lấy 30) | 18–29 ms |
| Rerank bằng LLM, 30 ứng viên | trung vị 1,34 giây (1,17–1,64) |
| Rerank bằng LLM, 15 ứng viên | trung vị 1,09 giây (1,05–1,41) |
| Số lần phải gọi lại vì 429 / 5xx (6 lô embed, 5 câu hỏi, 10 lời gọi LLM) | 0 |

- Các lời gọi dùng chung một kết nối HTTP, nên số trên không gồm thời gian bắt tay TLS. Lần 30 ứng viên luôn chạy trước lần 15.
- Rerank bằng LLM nằm quanh ngưỡng 1,5 giây của mục 13 kiến trúc: trung vị thấp hơn, nhưng một trong năm câu vượt (1,64 giây). Ở một lượt chạy trước có một lời gọi mất 5,0 giây; lượt đó chưa đếm số lần gọi lại nên không biết nguyên nhân. Giảm xuống 15 ứng viên nhanh hơn khoảng 0,25 giây ở lượt này; với năm câu hỏi thì chênh lệch đó chưa chắc chắn.
- Câu hỏi tiếng Việt ("BERT-Large có bao nhiêu tham số?"): hybrid đưa đoạn "Model Architecture" của BERT (đoạn nêu số tham số) lên hạng 2; bước LLM đưa nó lên hạng 1. Khi chỉ dùng BM25 đoạn này không vào top 3. Nhánh dense bắc cầu được giữa tiếng Việt và tiếng Anh.
- Bốn câu tiếng Anh: top 1 của RRF đã nằm đúng paper và đúng mục; bước LLM giữ nguyên top 1 ở ba câu, đổi ở một câu sang một đoạn cũng liên quan. Năm câu hỏi là quá ít để kết luận LLM rerank có giúp hay không; phase 5 đo.
- Embedding không phải nút cổ chai của ingestion (4 giây so với 33 giây parse cho cùng paper). Chưa biết hạn mức theo ngày của free tier.

## Model qua API: Gemini

Thông tin lấy từ tài liệu Gemini API ngày 2026-10-04.

| | |
|---|---|
| Embedding | `gemini-embedding-2`: đa ngôn ngữ (hơn 100 ngôn ngữ), context 8 192 token, 128–3 072 chiều (khuyến nghị 768 / 1 536 / 3 072), vector cắt ngắn được tự chuẩn hoá |
| Số chiều chọn | **768**: nhỏ nhất trong các mức khuyến nghị, tiết kiệm RAM của Qdrant khi chưa biết cấu hình server. Là tham số config; đổi thì index lại |
| Cách phân biệt câu hỏi / tài liệu | Tiền tố trong văn bản: `task: search result \| query: …` và `title: none \| text: …` |
| LLM | Gemini Flash (free tier có `gemini-3.8-flash` … `gemini-3.5-flash-lite`) |
| Giá free tier | 0 USD cho cả embedding và Flash |
| Giá nếu trả tiền | Embedding 0,20 USD / 1M token → khoảng 3–7 USD cho 1 000 paper (17–35M token, ước từ 1 150 token/trang) |
| Giới hạn tần suất free tier | Google không công bố con số; xem trong AI Studio của tài khoản. Lượt chạy spike (21 lời gọi trong chưa đầy một phút) không phải gọi lại lần nào; hạn mức theo ngày chưa biết |
| Dữ liệu | Free tier: nội dung được Google dùng để cải thiện sản phẩm. Gói trả tiền: không |

Đã loại: Voyage, Jina, Cohere (thêm tài khoản và key, có thể phát sinh chi phí); reranker tự host (ngốn đĩa và RAM, đã bỏ khỏi spike).

### Reranker: thay bằng gì

Gemini không có API rerank. Hai lớp thay thế, đều không tốn tiền:

1. **RRF** (đã có trong lời gọi hybrid của Qdrant): thuật toán gộp thứ hạng của nhánh dense và nhánh BM25, không cần model. Đây là thứ tự mặc định.
2. **LLM chọn đoạn (listwise):** một lời gọi Gemini Flash-Lite nhận câu hỏi và 30 ứng viên, trả về chỉ số các đoạn hữu ích nhất. Nằm sau interface `Reranker`, tắt được bằng config; lỗi hoặc quá thời gian chờ thì lùi về thứ tự RRF.

Đánh đổi của lớp 2: thêm một lời gọi LLM vào mỗi câu hỏi (khoảng 1,1–1,6 giây, từng có lần 5 giây; tốn hạn mức free tier), và LLM chỉ trả thứ tự, không trả điểm. Phase 5 so có / không có lớp 2 trên bộ eval rồi mới chốt.

## Việc chuyển sang các phase sau

- **Phase 2:** `requires-python = ">=3.14,<3.15"`; image nền `python:3.14-slim`.
- **Phase 3:**
  - Image `worker` cài `libgl1 libglib2.0-0 libxcb1`; PyTorch lấy từ index CPU của PyTorch.
  - Cấp cho worker ít nhất 4 GB RAM (đỉnh đo được 2,1–2,5 GB khi parse lần lượt ba paper trong cùng một process); `worker_concurrency = 1`.
  - Đặt tokenizer và `max_tokens` của `HybridChunker` theo model embedding đã chọn thay vì mặc định 256 token của MiniLM.
  - Chunk công thức lấy nội dung từ `orig`, vì `text` rỗng.
  - Thử việc khôi phục workflow sau khi đổi code, rồi quyết định cách đặt `application_version` của DBOS.
  - Ngân sách thời gian parse: tính theo 2–3 giây/trang, không phải 0,5.
- **Phase 3:** adapter `embedding_gemini.py` và `llm_gemini.py`; `limiter` của hàng đợi đặt theo giới hạn free tier đo được.
- **Phase 4:** BM25 phía server, không thêm `fastembed`. `Reranker` trả về thứ tự chỉ số; adapter là LLM chọn đoạn.
- **Phase 5:** đưa vào bộ eval ít nhất một paper có trang đầu hai cột kèm hình, để đo ảnh hưởng của lỗi thứ tự đọc; và câu hỏi tiếng Việt, để đo nhánh dense.
- **Phase 6:** tô sáng theo bbox tỉ lệ 0–1, gốc trên-trái.
- **Phase 8:** đo lại parse và RAM trên server thật.

## Câu hỏi còn mở

1. Hạn mức theo ngày của free tier Gemini có đủ để index vài trăm paper không.
2. Bước rerank bằng LLM có cải thiện chất lượng đủ để đáng 1,3 giây mỗi câu hỏi không (phase 5).
3. Có bật `do_formula_enrichment` để lấy LaTeX không. Chưa đo chi phí thời gian và dung lượng model.
4. Paper chưa công bố có được gửi qua free tier không (Google dùng nội dung để cải thiện sản phẩm).

## Nguồn

- [Gemini API: Embeddings](https://ai.google.dev/gemini-api/docs/embeddings), [Pricing](https://ai.google.dev/gemini-api/docs/pricing), [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [Models](https://ai.google.dev/gemini-api/docs/models)
