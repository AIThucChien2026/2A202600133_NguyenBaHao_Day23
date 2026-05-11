# Implementation Plan: LangGraph Agentic Orchestration

Dựa trên yêu cầu của bài lab, quá trình phát triển sẽ được chia thành 4 Phase. Chúng ta sẽ thực hiện tuần tự từng Phase một:

## Phase 1: Core graph (0–75 min) - Trọng số: 45 điểm
Mục tiêu: Xây dựng bộ khung logic cốt lõi và hệ thống định tuyến (routing) cho LangGraph.

- [ ] **`state.py`**:
  - Xác nhận các trường sử dụng reducer `Annotated[list, add]` (append-only).
  - Thêm trường `evaluation_result` vào `AgentState` để kiểm soát vòng lặp retry.
- [ ] **`nodes.py`**: Cài đặt các hàm logic cho node:
  - `classify_node`: Phân loại query dựa trên từ khóa ưu tiên (Risky > Tool > Missing Info > Error > Simple).
  - `evaluate_node`: Kiểm tra kết quả trả về từ tool, gán `evaluation_result` là `"needs_retry"` hoặc `"success"`.
  - `dead_letter_node`: Ghi nhận lỗi khi đã vượt quá số lần retry tối đa.
  - `approval_node`: Trả về `approved=True` cho kịch bản mock HITL.
- [ ] **`routing.py`**: Cài đặt logic định tuyến:
  - `route_after_classify`: Mapping kết quả phân loại sang tên node tiếp theo.
  - `route_after_evaluate`: Nếu `"needs_retry"` -> chuyển sang `"retry"`, ngược lại -> chuyển sang `"answer"`.
  - `route_after_retry`: Nếu `attempt < max_attempts` -> quay lại `tool`, nếu không -> chuyển sang `"dead_letter"`.
- [ ] **`graph.py`**: Kết nối các nodes và edges để hình thành Graph hoàn chỉnh theo kiến trúc sau:
  ```text
  START → intake → classify → [conditional routing]
    simple       → answer → finalize → END
    tool         → tool → evaluate → answer → finalize → END
    missing_info → clarify → finalize → END
    risky        → risky_action → approval → tool → evaluate → answer → finalize → END
    error        → retry → tool → evaluate → [retry loop or answer]
    max retry    → dead_letter → finalize → END
  ```
- [ ] **Verify**: Chạy `make test` và `make run-scenarios`.

---

## Phase 2: Persistence (75–120 min) - Trọng số: 15 điểm
Mục tiêu: Cài đặt khả năng ghi nhớ trạng thái (Checkpointing) bằng Database thực tế (PostgreSQL via Docker).

- [x] **`docker-compose.yml`**: Khởi chạy container `postgres:16-alpine`.
- [x] **`configs/lab.yaml`**: Cập nhật cấu hình sang dùng `checkpointer: postgres` và `database_url`.
- [x] **`persistence.py`**: Cài đặt factory `get_checkpointer`:
  - Trả về `MemorySaver()` khi mode là `"memory"`.
  - Khởi tạo kết nối tới database thông qua `psycopg.connect(..., autocommit=True)` để tránh lỗi transaction blocks.
  - Sử dụng `PostgresSaver(conn)` và gọi `checkpointer.setup()` để tự động tạo schema.
- [x] Đảm bảo cơ chế phân luồng `thread_id` hoạt động trên mỗi kịch bản (run) để thể hiện khả năng lưu lịch sử (state history) bằng PostgreSQL.

---

## Phase 3: Metrics & report (120–180 min) - Trọng số: 35 điểm
Mục tiêu: Thu thập chỉ số đánh giá, kiểm thử tổng thể và báo cáo.

- [ ] Chạy lệnh `make run-scenarios` trên toàn bộ tập kịch bản mẫu để sinh ra file `outputs/metrics.json`.
- [ ] Validate lại cấu trúc của file json vừa sinh ra bằng lệnh `make grade-local`.
- [ ] Soạn thảo báo cáo tại `reports/lab_report.md`:
  - Giải thích thiết kế và kiến trúc.
  - Phân tích chi tiết các chỉ số metrics.
  - Đánh giá các trường hợp lỗi (failures) và đề xuất phương án cải thiện.

---

## Phase 4: Bonus extensions (180+ min) - Trọng số: 10+ điểm
Mục tiêu: Đạt điểm xuất sắc (90+) thông qua các tính năng nâng cao. Chọn triển khai ít nhất 1 trong các tính năng sau:

- [ ] **Parallel fan-out**: Sử dụng `Send()` chạy song song hai tools, tổng hợp kết quả qua reducer `add`.
- [ ] **Real HITL**: Kích hoạt `LANGGRAPH_INTERRUPT=true` và sử dụng `interrupt()` tại node `approval_node`.
- [ ] **Streamlit UI**: Thiết kế giao diện tương tác approve/reject trực quan.
- [ ] **Time travel**: Tái tạo lại state từ một checkpoint trước đó bằng `get_state_history()`.
- [ ] **Crash recovery**: Chứng minh SQLite có thể phục hồi dữ liệu khi tiến trình bị kill và khởi động lại.
- [ ] **Graph diagram**: Xuất sơ đồ Mermaid qua hàm `graph.get_graph().draw_mermaid()`.
