# 0003 — Cấu hình hỏi trên nhiều paper

- Ngày đo: 2026-10-05, code ở commit `6d466bf` cộng các thay đổi của phần nhiều paper.
- Trạng thái: đủ để giữ các giá trị mặc định. Phần chấm bằng giám khảo (faithfulness, citation support) **chưa đo**: khóa Gemini hết hạn mức embedding trong ngày. Lệnh chạy lại ở cuối tài liệu.

## Cấu hình chốt

Không giá trị mặc định nào trong `config.py` phải đổi.

| Tham số | Giá trị | Quyết định | Căn cứ |
|---|---|---|---|
| `multi_paper_max_papers` | `20` | Giữ, chưa chạm trần | Bộ đo chỉ có 12 paper. Đường cắt bớt paper khi vượt trần chỉ mới kiểm bằng test, chưa đo trên dữ liệu thật. |
| `multi_paper_chunks` | `3` | Giữ | Ở 3 đoạn mỗi paper, 12/15 câu so sánh trích đủ mọi paper; một câu tổng hợp trên 12 paper tốn khoảng 85 nghìn token vào cho model nhanh. Tăng lên thì chi phí tăng tuyến tính. |
| `evidence_min_relevance` | `4` | Giữ, căn cứ yếu | Model miễn phí chấm rộng tay: gần như mọi đoạn đều qua ngưỡng, nên ngưỡng chưa lọc được gì. Cần đo lại bằng model tốt hơn trước khi nâng. |
| `multi_paper_parallel_calls` | `4` | Giữ | Trung vị 56 giây cho 36 lời gọi; không gặp giới hạn tốc độ. |
| `multi_paper_answer_tokens` | `4096` | Giữ | Gấp đôi trần của câu factual (2048). Ở 4096 vẫn có 1/9 bài tổng hợp bị cắt (model suy luận tiêu token đầu ra vào phần suy luận); chưa đo mức cao hơn. |
| Phân loại câu hỏi | mặc định `factual` | Giữ | Đúng 75/76 câu; không câu factual nào bị đẩy nhầm sang tổng hợp. |

## Dữ liệu đo

Bộ golden của dự án trên 12 paper arXiv (`eval/golden/`):

| File | Câu hỏi | Phạm vi |
|---|---:|---|
| `factual.jsonl` | 53 | Một paper (một câu hai paper). Có từ phase 5. |
| `comparison.jsonl` | 15 | 2–4 paper nêu tên trong câu hỏi; mong đợi trích đủ các paper đó. |
| `synthesis.jsonl` | 10 | Cả 12 paper; mỗi câu ghi các paper mong đợi có mặt trong nguồn. |

Kế hoạch nêu collection khoảng 15 paper; bộ có sẵn là 12 và đã đi qua parser thật, nên dùng luôn.

## Kết quả

### Phân loại câu hỏi

Model nhanh của kết nối Gemini, cấu hình `golden-classify`, kết quả ở `eval-results/golden-classify-20261004T173411.json`. 78 câu, 2 câu lỗi giới hạn tốc độ.

| Loại câu hỏi | Đúng | Số câu |
|---|---:|---:|
| factual | 0,980 | 51 |
| comparison | 1,000 | 15 |
| synthesis | 1,000 | 10 |
| Tất cả | 0,987 | 76 |

Câu sai duy nhất: "What is the difference between RAG-Sequence and RAG-Token?" bị xếp là comparison. Câu này hỏi trên một paper, và phạm vi một paper luôn được trả lời như câu factual, nên người dùng không thấy khác biệt.

### So sánh và tổng hợp

Đo qua đúng API trình duyệt gọi (`POST /chats/{id}/messages`), trên tài khoản dùng 9router: model trả lời và model nhanh đều là `nvidia/nemotron-3-super-120b-a12b:free` (model suy luận, miễn phí, thất thường), embedding `baai/bge-m3`. Loại câu hỏi được chỉ định sẵn, không qua phân loại.

| Chỉ số | So sánh (15 câu) | Tổng hợp (10 câu) |
|---|---:|---:|
| Trả lời được | 15 | 9 |
| Độ phủ paper (paper mong đợi được trích dẫn) | 0,928 | 0,857 |
| Câu trích đủ mọi paper mong đợi | 12 | 6 / 9 |
| Thời gian, trung vị / lớn nhất | 24 s / 143 s | 56 s / 74 s |
| Token model nhanh, vào / ra (trung bình) | 0 | 85 119 / 8 077 |
| Token model trả lời, vào / ra (trung bình) | 5 479 / 3 372 | 5 607 / 3 496 |

So sánh:

- 14/15 câu ra bảng, và bảng nào cũng có đúng một hàng cho mỗi paper trong phạm vi. Một câu (c02) hỏng bảng hai lần rồi lùi về văn bản: ba lời gọi model, 143 giây.
- Ba câu thiếu paper trong trích dẫn (c10, c14, c15): hàng của paper đó vẫn có, các ô ghi "Not stated in the passages found". c15 hỏi về hạn chế tác giả tự nêu, thứ mà hai paper thật sự không viết.

Tổng hợp:

- Nguồn đến từ ít nhất 5 paper ở 5/9 câu (12, 6, 6, 5, 5 paper). Bốn câu còn lại có chủ đề hẹp (dịch máy, attention, ví dụ âm): 2–4 paper.
- 8/9 bài đủ bốn phần. Bài còn lại (s05) dùng hết 4096 token đầu ra và dừng sau phần đầu.
- Mỗi câu gửi 36 đoạn cho model nhanh; 0–5 đoạn không chấm được (model trả rỗng).
- Câu s01 hỏng cả ba lần thử: model trả lời không viết gì (`provider_rejected`).
- Câu s07 (benchmark và dataset) chỉ trích 3/8 paper mong đợi: 3 đoạn mỗi paper tìm theo câu hỏi chung chung không chạm tới phần thí nghiệm của nhiều paper. Đây là giới hạn của cách tìm, không phải của ngưỡng.

### Chi phí một câu tổng hợp

Trên 12 paper: 36 lời gọi model nhanh (khoảng 85 nghìn token vào, 8 nghìn ra) và một lời gọi model trả lời (5,6 nghìn vào, 3,5 nghìn ra). Model nhanh chiếm hơn 90% số token. Ở trần 20 paper con số này vào khoảng 140 nghìn token vào. Hệ thống chỉ ghi token, không quy ra tiền (mỗi tài khoản dùng khóa và bảng giá riêng).

Một câu so sánh rẻ hơn khoảng 10 lần: một lời gọi model trả lời, không dùng model nhanh.

## Sửa trong lúc đo và sau review

- Model viết marker dạng `(S1)` thay cho `[S1]` nên không trích dẫn nào được nhận. Bộ kiểm tra nay nhận ngoặc tròn, nhưng chỉ khi cả câu trả lời không có marker ngoặc vuông nào và ngoặc không đứng sát sau chữ hay số (`P(S1)` là công thức).
- Sau 8 đoạn liên tiếp không chấm được thì thôi không gửi nữa và viết từ các đoạn tìm được. Trước đó một model nhanh hỏng hẳn vẫn bị gọi đủ cho mọi đoạn.
- Còn đoạn chưa chấm được mà không đoạn nào qua ngưỡng thì không báo "không tìm thấy" nữa, vì đó là đoán.
- Phần nhận xét của bảng so sánh không còn lộ mã nội bộ của paper ("Adam (P1)").

## Chưa đo

- **Faithfulness và citation support** của câu so sánh và tổng hợp. Rủi ro cần con số này nhất: bản tóm tắt bằng chứng làm méo nội dung, marker trỏ đúng đoạn nhưng nhận định sai.
- **Cùng bộ câu hỏi trên Gemini**, để so được với số liệu phase 5 và để chỉnh `evidence_min_relevance` bằng một model chấm nghiêm hơn.
- **Phạm vi vượt trần 20 paper.**

Chạy lại khi khóa có hạn mức (paper golden đã index sẵn trong tài khoản đo):

```bash
docker compose run --rm -e GIT_COMMIT=$(git rev-parse --short HEAD) worker \
  python -m scientrag.evaluation.run --config \
  eval/configs/golden-classify.toml eval/configs/golden-comparison.toml eval/configs/golden-synthesis.toml
```

## Giới hạn đã biết

- Câu trả lời bị cắt vì chạm trần token đầu ra không được phát hiện: người đọc nhận bài thiếu phần mà không có thông báo.
- So sánh nhiều paper với nhiều cột có thể vượt 4096 token đầu ra; khi đó bảng hỏng, thử lại vẫn hỏng, rồi lùi về văn bản: ba lời gọi cho một kết quả kém hơn. Chưa gặp ở 4 paper; chưa thử ở 15–20 paper.
- Câu hỏi tiếp theo về một ô của bảng: lịch sử trò chuyện chỉ giữ phần nhận xét, không giữ bảng.
