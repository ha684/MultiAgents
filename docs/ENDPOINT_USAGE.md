# 📡 Conversation Server - Tài liệu API

> **Môi trường phát triển:** Python 3.12

> Nếu bạn chưa rõ cách sử dụng API, vui lòng xem thư mục `sample_use` để tham khảo các ví dụ cụ thể.

---

## 🔗 Base URL

```
http://localhost:12000/api/v1 (Có thể tùy chỉnh dựa vào .env)
```

---

## 🧭 Tổng Quan

Conversation Server là backend hỗ trợ giao tiếp giữa người dùng và các agents trong hệ thống. Hệ thống hỗ trợ đa phiên trò chuyện, gửi tin nhắn, đính kèm file, quản lý agent, và xử lý các tác vụ.

---

## 📁 Danh sách Endpoints

### 1. 📞 Quản lý Cuộc Hội Thoại

#### `POST /conversation/create`

* **Mô tả:** Tạo cuộc hội thoại mới.
* **Tham số:**

  ```json
  {
    "params": "user_id"
  }
  ```
* **Phản hồi:**
  `conversation_id` được tạo mới.

#### `POST /conversation/list`

* **Mô tả:** Trả về danh sách tất cả các cuộc hội thoại.
* **Tham số:** `{}` (body rỗng)

---

### 2. 💬 Quản lý Tin nhắn

#### `POST /message/send`

* **Mô tả:** Gửi tin nhắn trong cuộc hội thoại.
* **Tham số:**

  ```json
  {
    "params": {
      "role": "user | assistant",
      "parts": [
        { "text": "..." } hoặc { "file": { "bytes": "...", "mimeType": "..." } }
      ],
      "metadata": {
        "conversation_id": "string",
        "user_id": "string",
        "context_id": "string",
        "message_id": "string"
      }
    }
  }
  ```
* **Phản hồi:** Kết quả trả về nội dung và ID tin nhắn.

#### `POST /message/list`

* **Mô tả:** Lấy danh sách tin nhắn theo `conversation_id`.
* **Tham số:**

  ```json
  {
    "params": "conversation_id"
  }
  ```

#### `POST /message/pending`

* **Mô tả:** Lấy danh sách tin nhắn đang chờ xử lý.
* **Tham số:** `{}` (body rỗng)

#### `GET /message/file/{file_id}`

* **Mô tả:** Tải file đính kèm trong tin nhắn bằng `file_id`.

---

### 3. 🤖 Quản lý Agent

#### `POST /agent/register`

* **Mô tả:** Đăng ký một agent từ một URL cụ thể.
* **Tham số:**

  ```json
  {
    "params": "http://<agent-host>:<port>"
  }
  ```

#### `POST /agent/list`

* **Mô tả:** Trả về danh sách các agent đã được đăng ký.

---

### 4. 📆 Sự kiện & Tác vụ

#### `POST /events/get`

* **Mô tả:** Trả về danh sách các sự kiện nội bộ của hệ thống.

#### `POST /task/list`

* **Mô tả:** Trả về danh sách các tác vụ đang chạy hoặc đã hoàn thành.

---

### 5. 🔐 Cập nhật cấu hình API Key

#### `POST /api_key/update`

* **Mô tả:** Cập nhật `API Key` cho hệ thống xử lý agent.
* **Tham số:**

  ```json
  {
    "api_key": "string"
  }
  ```

---

## 🧠 Kiến trúc tổng quan

* `ConversationServer` là lớp chính định nghĩa các API sử dụng FastAPI `router`
* Tất cả các thao tác như xử lý tin nhắn, agent, và event được quản lý qua lớp `ADKHostManager`
* File đính kèm được cache tạm thời và truy cập qua endpoint `/message/file/{file_id}`


## Cách dùng

* Đầu tiên là chạy host agent bằng cách chạy API trong folder `app`
* Sau đó chạy file `__main__.py` trong folder `trip_agent_server`
* Sau đó kết nối với APIs exposed bởi host agent và tương tác, xem folder `sample_use` để biết rõ hơn về cách sử dụng, pipeline sẽ là regist agent (sẽ có URL sau khi khởi tạo trip_agent_server) -> tạo conversation (lưu lại id) -> gửi message (cần có `conversation_id` và `user_id`) -> lấy kết quả
