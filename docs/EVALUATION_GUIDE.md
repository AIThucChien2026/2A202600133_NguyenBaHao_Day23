# Hướng dẫn chạy và đánh giá toàn bộ dự án (Evaluation Guide)

Tài liệu này tổng hợp toàn bộ các lệnh mình đã sử dụng để setup, chạy kiểm thử, lấy điểm số và chạy giao diện UI cho dự án **LangGraph Agentic Orchestration**. Bạn có thể copy lần lượt từng lệnh dưới đây dán vào Terminal để tự mình nghiệm thu.

> [!IMPORTANT]
> **Lưu ý trước khi chạy:** Bạn phải đảm bảo đang đứng ở thư mục gốc của dự án (`b:\VInuni_lab\lab_23\phase2-track3-day8-langgraph-agent`) và **Docker Desktop** đang được bật trên máy (vì chúng ta đang dùng database Postgres bằng Docker).

---

## 1. Khởi động Database (Phase 2 - Persistence)

Hệ thống ghi nhớ (Checkpointer) của dự án sử dụng PostgreSQL. Chạy lệnh sau để bật database container:
```bash
docker-compose up -d
```
*Lệnh này sẽ chạy ngầm database ở cổng `5432`.*

---

## 2. Kiểm thử Unit Tests (Phase 1)

Lệnh này sẽ chạy các bài "smoke tests" kiểm tra xem sườn logic của các file `nodes.py`, `state.py`, `routing.py` và `graph.py` có bị lỗi cú pháp, vòng lặp vô hạn hay biên dịch lỗi không.
```bash
venv\Scripts\pytest.exe
```
**Kết quả mong đợi:** Tất cả các test đều pass 100% (màu xanh lá).

---

## 3. Chạy Kịch bản tự động và Chấm điểm (Phase 3)

### Bước 3.1: Chạy mô phỏng kịch bản (Run Scenarios)
Script này sẽ chạy toàn bộ 7 kịch bản giả lập (từ `S01` đến `S07`) đi xuyên qua LangGraph và ghi lại các kết quả định tuyến cũng như số vòng lặp `retry loop` vào file json.
```bash
venv\Scripts\python.exe -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json
```

### Bước 3.2: Tính điểm (Validate Metrics)
Script này đọc file JSON sinh ra ở Bước 3.1 để so sánh `actual_route` với `expected_route` và trả về tỷ lệ thành công.
```bash
venv\Scripts\python.exe -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```
**Kết quả mong đợi:** Màn hình in ra dòng chữ `Metrics valid. success_rate=100.00%`.

---

## 4. Trải nghiệm Giao diện và HITL thực tế (Phase 4 - Bonus)

Chúng ta đã dựng sẵn một giao diện người dùng chuyên nghiệp bằng Streamlit để test chức năng **Human-In-The-Loop** (Người duyệt can thiệp) bằng API `interrupt()`. 

Chạy lệnh sau để mở giao diện web:
```bash
venv\Scripts\python.exe -m streamlit run frontend/app.py
```

### Hướng dẫn test trên giao diện:
1. Trình duyệt sẽ tự động bật lên ở `http://localhost:8501`.
2. **Thử query an toàn:** Nhập *"Check my order status"* -> Agent sẽ trả lời bình thường.
3. **Thử query nguy hiểm (HITL):** Nhập *"Delete my customer account"* -> Đồ thị sẽ đóng băng, giao diện xuất hiện cảnh báo màu cam yêu cầu sự can thiệp của con người.
4. Bạn có thể bấm nút **✅ Approve Action** hoặc **❌ Reject Action** để thấy hệ thống tiếp nhận phản hồi từ con người và thay đổi luồng đi tiếp theo.

---

> [!TIP]
> Bạn có thể xem toàn bộ file báo cáo phân tích kiến trúc mà mình đã chuẩn bị theo yêu cầu chấm điểm của thầy cô tại: `reports/lab_report.md`.
