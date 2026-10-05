# 0002 — Kết quả đo chất lượng và cấu hình chốt

- Ngày đo: 2026-10-04, code ở commit `ac9def2` cộng các thay đổi của bộ đo.
- Lệnh: `python -m scirag.evaluation.run --config eval/configs/<tên>.toml` (xem README, mục "Đo chất lượng"). File kết quả nằm trong `eval-results/` (không commit).
- Model: Gemini, `gemini-3.5-flash` (trả lời và giám khảo), `gemini-3.5-flash-lite` (rerank), `gemini-embedding-2` (embedding).
- Trạng thái: đủ để chốt cấu hình. Một số thí nghiệm bị cắt bớt vì key hết hạn mức giữa chừng; liệt kê ở mục "Chưa đo".

## Cấu hình chốt

Không giá trị mặc định nào trong `config.py` phải đổi.

| Tham số | Giá trị | Quyết định | Căn cứ |
|---|---|---|---|
| `rerank_enabled` | `true` | Giữ | recall@1 từ 0,366 lên 0,532; đổi lại khoảng 1,1 giây mỗi câu hỏi. |
| `search_fusion` | `rrf` | Giữ, căn cứ yếu | Nhỉnh hơn DBSF ở recall@5 và @8. Trên QASPER không rerank thì kém tìm theo nghĩa đơn thuần; phép so khi có rerank và khi tìm trên nhiều paper chưa đo (xem dưới). |
| `chunk_max_tokens` | `400` | Giữ | Chunk 800 có recall@k cao hơn ở cùng k nhưng thấp hơn ở cùng lượng token đưa vào model. |
| `rerank_candidates` | `30` | Giữ, mẫu nhỏ | Trên 50 câu, 15 ứng viên chỉ nhanh hơn khoảng 80 ms và mất đoạn bằng chứng ở một số câu. |
| `context_chunks` | `8` | Giữ | recall@8 là 0,919 so với recall@5 là 0,844. |
| Kiểm tra citation lúc chạy | không có | Không thêm | Marker hợp lệ 100%; giám khảo chấm 95–99% câu có trích dẫn là được nguồn chứng minh. |

## Dữ liệu đo

| Bộ | Paper | Câu hỏi | Ghi chú |
|---|---:|---:|---|
| QASPER (dev, seed 7) | 100 | 314 | Paper ở dạng văn bản: đo chunking, tìm kiếm, trả lời; không đo parser. Mỗi câu hỏi tìm trong paper của nó. |
| Golden (`eval/golden/`) | 12 | 53 | PDF arXiv công khai đi qua parser thật. 48 câu có bằng chứng chép nguyên văn (2 câu về bảng, 1 câu cần hai paper), 5 câu paper không trả lời được. |

**Ánh xạ bằng chứng sang chunk.** Một chunk được tính là chứa đoạn bằng chứng khi nó có ít nhất 40% các cụm 4 từ liên tiếp của đoạn đó. Kiểm trên toàn bộ 505 đoạn bằng chứng của QASPER: 475 nằm nguyên văn trong một chunk, 8 bị cắt qua hai chunk (cả hai đều được tính), 22 không tìm thấy vì bằng chứng là một tiêu đề mục (bỏ qua). Trên golden, cả 48 câu đều ánh xạ được.

**Recall** tính theo từng đoạn bằng chứng: một đoạn được coi là tìm thấy khi có chunk chứa nó nằm trong k chunk đầu.

## Kết quả tìm kiếm trên QASPER

314 câu hỏi. Thời gian là p50 / p95 từ lúc nhận câu hỏi tới lúc có danh sách đoạn văn đưa vào model.

| Cấu hình | recall@1 | recall@3 | recall@5 | recall@8 | MRR | Thời gian (ms) |
|---|---:|---:|---:|---:|---:|---:|
| **baseline**: RRF, rerank 30, chunk 400 | 0,532 | 0,779 | 0,844 | 0,919 | 0,717 | 1821 / 2093 |
| không rerank | 0,366 | 0,606 | 0,778 | 0,891 | 0,573 | 689 / 1604 |
| không rerank, chỉ tìm theo nghĩa | 0,408 | 0,705 | 0,810 | 0,891 | 0,619 | 732 / 990 |
| không rerank, DBSF | 0,363 | 0,623 | 0,750 | 0,865 | 0,564 | 728 / 870 |
| không rerank, chunk 800 | 0,386 | 0,682 | 0,828 | 0,936 | 0,601 | 687 / 895 |

Rerank 15 ứng viên, so với baseline trên cùng 50 câu hỏi (100 câu chọn theo seed, 50 câu chạy được trước khi key hết quota):

| Cấu hình | recall@1 | recall@3 | recall@5 | recall@8 | Đoạn bằng chứng có trong ứng viên | Thời gian p50 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| rerank 30 | 0,627 | 0,868 | 0,933 | 0,993 | 1,000 | 1854 |
| rerank 15 | 0,620 | 0,848 | 0,933 | 0,953 | 0,980 | 1776 |

### Kết luận từng thí nghiệm

- **Có rerank hay không: giữ rerank.** Đây là thay đổi có tác dụng lớn nhất: đoạn bằng chứng lên vị trí đầu ở 53% câu hỏi thay vì 37%. Chi phí là một lời gọi model nhanh, khoảng 1,1 giây và 5–6 nghìn token vào mỗi câu hỏi. Ai cần nhanh và rẻ hơn có thể đặt `RERANK_ENABLED=false`.
- **Hybrid hay chỉ tìm theo nghĩa: giữ hybrid (RRF), nhưng số liệu không ủng hộ.** Khi không rerank, tìm theo nghĩa đơn thuần xếp hạng tốt hơn hybrid ở recall@1, @3 và @5 (recall@1 0,408 so với 0,366) và ngang nhau ở recall@8. Dự đoán, chưa đo: khi có rerank thì khác biệt này mất đi, vì paper QASPER ngắn, 30 ứng viên chứa gần như mọi đoạn bằng chứng ở cả hai cách (99,9–100%), và model rerank xếp lại toàn bộ. Tìm theo từ khoá được giữ cho trường hợp QASPER không đo: tìm trên nhiều paper cùng lúc và câu hỏi chứa tên riêng, ký hiệu, con số. Trường hợp đó chưa có số so sánh (xem "Chưa đo"); nếu sau này đo thấy không có lợi thì đặt `SEARCH_FUSION=none`.
- **RRF hay DBSF: giữ RRF.** DBSF thấp hơn 0,03 ở recall@5 và recall@8, nhưng cao hơn 0,02 ở recall@3. Chênh lệch nhỏ và không có khoảng tin cậy, nên giữ giá trị đang dùng.
- **Chunk 400 hay 800: giữ 400.** Ở cùng k, chunk 800 có recall cao hơn vì mỗi chunk chứa nhiều văn bản hơn. So ở cùng lượng văn bản đưa vào model thì ngược lại: 8 chunk 400 token (3.200 token) đạt 0,891, trong khi 5 chunk 800 token (4.000 token) chỉ đạt 0,828; 5 chunk 400 (2.000 token) đạt 0,778, hơn 3 chunk 800 (2.400 token, 0,682). Tám chunk 800 token còn vượt `context_max_tokens = 6000`, nên recall@8 của chunk 800 có khi chỉ tính trên 7 đoạn. Chunk nhỏ cũng cho trích dẫn chỉ vào đoạn hẹp hơn. Phép so này đo ở chế độ không rerank.
- **Rerank 30 hay 15 ứng viên: giữ 30, căn cứ yếu.** 15 ứng viên chỉ nhanh hơn khoảng 80 ms và làm mất đoạn bằng chứng khỏi danh sách ở 2% trường hợp. Mẫu chỉ 50 câu, và hai lượt chạy với số câu hỏi đồng thời khác nhau (2 so với 4) nên thời gian không so được chặt. Lợi ích chưa tính của 15 ứng viên: lượng token vào model nhanh, khoản lớn nhất mỗi câu hỏi, giảm khoảng một nửa. Đáng đo lại trên đủ câu hỏi nếu chi phí là ưu tiên.
- **Đưa 8 hay 5 đoạn vào model: giữ 8.** Đọc từ lượt baseline: 8 đoạn chứa bằng chứng ở 91,9% trường hợp, 5 đoạn ở 84,4%. Giảm xuống 5 tiết kiệm khoảng 900 token vào mỗi câu hỏi.

## Kết quả trên bộ golden

48 câu có bằng chứng, cấu hình baseline.

| Phạm vi tìm | recall@1 | recall@3 | recall@5 | recall@8 | MRR |
|---|---:|---:|---:|---:|---:|
| Paper của câu hỏi | 0,719 | 0,917 | 0,979 | 1,000 | 0,835 |
| Cả 12 paper | 0,719 | 0,917 | 0,979 | 0,979 | 0,827 |

Văn bản do parser tạo ra đủ tốt để cả 48 đoạn bằng chứng, kể cả hai dòng trong bảng, được tìm thấy nguyên văn trong chunk.

## Chất lượng câu trả lời

Cấu hình baseline, giám khảo là `gemini-3.5-flash`. Lượt QASPER dừng ở 33 trên 50 câu vì key hết hạn mức; số câu được chấm ở từng dòng ít hơn một chút vì một số lời gọi giám khảo cũng lỗi.

| Chỉ số | Golden (53 câu) | QASPER (33 câu) |
|---|---:|---:|
| Trả lời khi có bằng chứng, từ chối khi không có | 0,981 | 0,879 |
| Marker trỏ tới nguồn có thật | 1,000 | 1,000 |
| Faithfulness: ý trong câu trả lời có trong các đoạn đã đưa vào | 1,000 | 0,964 |
| Answer relevance | 0,922 | 0,808 |
| Context precision | 0,927 | 0,849 |
| Context recall | 1,000 | 0,840 |
| Câu có trích dẫn được nguồn chứng minh | 0,988 | 0,948 |
| F1 theo từ so với đáp án tham chiếu | 0,337 | 0,190 |

- F1 thấp vì câu trả lời của hệ thống dài và có giải thích, còn đáp án tham chiếu là một cụm ngắn. Không dùng chỉ số này để quyết định.
- Trong 5 câu golden không có đáp án, 4 câu được từ chối đúng. Câu còn lại hệ thống nói không tìm thấy rồi nêu thêm thông tin liên quan có trong paper, và bị tính là đã trả lời.

**Giám khảo trích dẫn đáng tin tới đâu.** Kiểm tay 20 phán quyết trên golden (cả 4 câu bị chấm "không chứng minh" và 16 câu chọn ngẫu nhiên trong số được chấm "có chứng minh"), đối chiếu với văn bản paper:

| Giám khảo chấm | Số câu | Đúng khi kiểm tay |
|---|---:|---:|
| Có chứng minh | 16 | 16 |
| Không chứng minh | 4 | 0 |

Cả 4 câu bị chấm sai đều là một dòng trong danh sách gạch đầu dòng, lấy số từ bảng; giám khảo đọc dòng đó tách khỏi câu dẫn phía trên nên không thấy đủ ngữ cảnh. Trên mẫu này giám khảo sai về phía khắt khe. Mẫu nhỏ: 16 trên 16 câu "có chứng minh" đúng chưa loại trừ được việc giám khảo đôi khi chấm dễ (tỉ lệ đó có thể tới khoảng 17% ở độ tin cậy 95%). Con số trong bảng là trung bình của tỉ lệ từng câu hỏi, không phải tỉ lệ trên tổng số câu.

**Kiểm tra citation lúc chạy: không thêm.** Marker luôn hợp lệ nhờ bước kiểm sẵn có trong `rag/citation.py`. Tỉ lệ câu được nguồn chứng minh theo giám khảo là 95–99%; thêm một lời gọi model cho mỗi câu trả lời để bắt vài phần trăm còn lại, bằng một giám khảo có sai số cùng cỡ, không đáng độ trễ và chi phí.

## Độ trễ và chi phí của cấu hình chốt

Đo trên laptop dev (Apple M2), model qua API; lượt golden có giám khảo, 53 câu hỏi.

| Bước | p50 (ms) | p95 (ms) |
|---|---:|---:|
| Embed câu hỏi và tìm kiếm | 754 | 1057 |
| Tới khi rerank xong | 1887 | 2261 |
| Tới chữ đầu tiên của câu trả lời | 4552 | 6574 |
| Toàn bộ | 4814 | 7725 |

| Token mỗi câu hỏi | Vào | Ra |
|---|---:|---:|
| Model trả lời | 2.325 | 473 |
| Model nhanh (rerank) | 5.957 | 11 |
| Embedding | 17 | 0 |

Chữ đầu tiên tới sau 4,6 giây trong khi cả câu trả lời xong ở 4,8 giây: phần lớn thời gian trôi qua trước khi model bắt đầu viết. Chưa tìm hiểu nguyên nhân (model suy nghĩ trước khi viết, hay provider trả chữ theo cụm lớn).

## Tính lặp lại

Hai lượt cùng cấu hình ban đầu cho thứ hạng khác nhau ở 85 trên 314 câu hỏi. Nguyên nhân: trộn theo thứ hạng (RRF) hay cho điểm bằng nhau, và Qdrant trả các đoạn bằng điểm theo thứ tự thay đổi giữa các lần gọi (16 trên 40 paper khi lặp lại cùng một truy vấn). `index/search.py` giờ sắp các đoạn bằng điểm theo id. Sau khi sửa, hai lượt `no-rerank` cho thứ hạng giống hệt ở 313 trên 313 câu chạy được.

Lượt có rerank phụ thuộc vào model nên không bảo đảm giống hệt; chưa đo mức dao động.

## Chưa đo

Key trả tiền chạm hạn mức chi tiêu và key miễn phí hết quota ngày trước khi chạy hết. Các config vẫn nằm trong `eval/configs/` để chạy lại khi có quota:

- `dense-only`, `dbsf`: hai kiểu trộn khi có rerank. Dự đoán không khác baseline, vì lý do nêu ở trên.
- `chunk-800`: chunk 800 khi có rerank.
- `answer-top-5`: chất lượng câu trả lời khi chỉ đưa 5 đoạn vào model.
- `rerank-15` trên đủ 100 câu, và lượt `baseline` lặp lại để biết dao động do model rerank.
- So ba kiểu trộn khi tìm trên cả 12 paper golden. Đây là phép đo có thể đổi quyết định về hybrid.

## Giới hạn của kết quả

- Golden chỉ có 53 câu, mỗi câu một hoặc hai đoạn bằng chứng do người viết chọn. Một đoạn khác của paper cũng trả lời được thì không được tính, nên recall@1 trên golden là cận dưới.
- QASPER tìm trong một paper ngắn (vài chục chunk). Kết quả không nói gì về tìm kiếm trên thư viện vài trăm paper.
- Mọi con số gắn với ba model Gemini nêu ở đầu. Đổi model embedding hay model rerank thì phải đo lại.
- Độ trễ đo trên laptop với API ở xa, 4 câu hỏi chạy đồng thời (2 ở lượt `rerank-15` và `chunk-800-no-rerank`), và gồm cả thời gian chờ thử lại khi bị giới hạn tốc độ. Đo lại trên server triển khai.
- Các lượt trong tài liệu này chạy trước khi bộ đo biết loại câu hỏi có rerank thất bại. Đã kiểm lại trên file kết quả: lượt baseline và ba lượt golden rerank bằng model ở mọi câu; lượt `rerank-15` có 11 câu rerank thất bại, đã loại khỏi bảng (còn 50 câu).
