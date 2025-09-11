# Hướng Dẫn API Đại Lý Du Lịch

## Tổng Quan

Hướng dẫn này mô tả cách sử dụng hệ thống API Đại Lý Du Lịch, bao gồm hai thành phần chính:

* **Host Agent**: Đại lý chính điều phối các cuộc trò chuyện và phối hợp với các đại lý từ xa
* **Trip Agent**: Một đại lý từ xa chuyên biệt xử lý các nhiệm vụ lập kế hoạch du lịch

## Kiến Trúc Hệ Thống

Hệ thống sử dụng kiến trúc phân tán, trong đó:

1. Đại lý Host đóng vai trò điều phối chính
2. Các đại lý từ xa (như Trip Agent) có thể được đăng ký để xử lý các tác vụ cụ thể
3. Giao tiếp diễn ra qua các điểm cuối REST API

## Cài Đặt và Khởi Tạo

### Bước 1: Khởi Động Trip Agent (Tùy Chọn)

Nếu bạn muốn sử dụng Trip Agent để có khả năng lập kế hoạch du lịch nâng cao:

```bash
# Di chuyển đến thư mục trip_agent và chạy
python main.py
```

Điều này sẽ khởi động dịch vụ Trip Agent, thường chạy trên một cổng khác với Host Agent.

### Bước 2: Khởi Động Host Agent

```bash
# Di chuyển đến thư mục app và chạy
python main.py
```

Điều này sẽ khởi động dịch vụ Host Agent chính (cổng mặc định: 12000).

### Bước 3: Khởi Tạo hoặc Đăng Ký Các Đại Lý

#### Lựa Chọn A: Với Trip Agent

Nếu bạn đang chạy Trip Agent, đăng ký nó với Host Agent:

```http
POST /agent/register
Content-Type: application/json

{
    "path": "http://localhost:[TRIP_AGENT_PORT]",
    "app_name": "trip_agent"
}
```

#### Lựa Chọn B: Không Có Trip Agent (Chế Độ Độc Lập)

Nếu chạy mà không có Trip Agent, khởi tạo Host Agent ở chế độ độc lập:

```http
POST /agent/initialize
Content-Type: application/json

{
    "app_name": "your_app_name"
}
```

## Quy Trình API

### 1. Tạo Một Cuộc Trò Chuyện

Trước khi gửi bất kỳ tin nhắn nào, bạn cần tạo một cuộc trò chuyện:

```http
POST /conversation/create
Content-Type: application/json

{
    "app_name": "your_app_name",
    "user_id": "unique_user_id"
}
```

**Phản Hồi:**

```json
{
    "result": {
        "conversation_id": "36d460c5-1a81-4ee3-bd9f-0b01770ad858",
        "name": "",
        "is_active": true
    }
}
```

Hãy lưu lại `conversation_id` - bạn sẽ cần nó cho tất cả các yêu cầu tiếp theo.

### 2. Gửi Tin Nhắn Lập Kế Hoạch Du Lịch

Sử dụng điểm cuối `/message/send/fixed` cho các yêu cầu lập kế hoạch du lịch có cấu trúc:

```http
POST /message/send/fixed
Content-Type: application/json

{
    "role": "user",
    "parts": [
        {
            "type": "text",
            "text": "Tôi muốn lên kế hoạch du lịch từ Hà Nội đến Nhật Bản vào khoảng từ 10-6-2025 đến 17-6-2025 với 2 người bạn, ngân sách 3000 USD mỗi người"
        }
    ],
    "metadata": {
        "conversation_id": "36d460c5-1a81-4ee3-bd9f-0b01770ad858",
        "conversation_name": "",
        "context_id": "unique_context_id",
        "user_id": "your_user_id",
        "app_name": "your_app_name",
        "departure_city": "Hà Nội",
        "destination_city": "Nhật Bản",
        "start_date": "2025-06-10",
        "end_date": "2025-06-17",
        "number_of_travelers": 3,
        "budget": 3000,
        "preferences": "ẩm thực, văn hóa, lịch sử"
    }
}
```

**Các Trường Metadata Bắt Buộc:**

* `departure_city`: Thành phố khởi hành
* `destination_city`: Thành phố đến
* `start_date`: Ngày bắt đầu chuyến đi (định dạng YYYY-MM-DD)
* `end_date`: Ngày kết thúc chuyến đi (định dạng YYYY-MM-DD)
* `number_of_travelers`: Số người tham gia chuyến đi (tối thiểu 1)
* `budget`: Ngân sách mỗi người (USD)
* `preferences`: Danh sách sở thích du lịch (cách nhau bởi dấu phẩy)

**Phản Hồi:**

```json
{
    "result": {
        "message_id": "generated_message_id",
        "status": "processing"
    }
}
```

### 3. Lấy Kết Quả

Kết quả lập kế hoạch du lịch được phân thành 4 danh mục:

#### A. Ghi Chú/Tóm Tắt Chung

Đây được bao gồm trong phản hồi tin nhắn từ `/message/send/fixed`.

#### B. Thông Tin Chuyến Bay

```http
GET /trip/flights?conversation_id=36d460c5-1a81-4ee3-bd9f-0b01770ad858
```

**Phản Hồi:**

```json
{
    "result": [
        {
            "flight_number": "JL792",
            "airline": "Japan Airlines",
            "departure": "HAN",
            "arrival": "NRT",
            "departure_time": "2025-06-10T09:00:00",
            "arrival_time": "2025-06-10T16:30:00",
            "price": 450,
            "duration": "5h 30m"
        }
    ]
}
```

#### C. Thông Tin Khách Sạn

```http
GET /trip/hotels?conversation_id=36d460c5-1a81-4ee3-bd9f-0b01770ad858
```

**Phản Hồi:**

```json
{
    "result": [
        {
            "hotel_name": "Hotel Sunroute Plaza Shinjuku",
            "location": "Tokyo, Shinjuku",
            "check_in": "2025-06-10",
            "check_out": "2025-06-14",
            "price_per_night": 120,
            "total_price": 480,
            "rating": 4.2,
            "amenities": ["WiFi", "Breakfast", "Gym"]
        }
    ]
}
```

#### D. Hoạt Động

```http
GET /trip/activities?conversation_id=36d460c5-1a81-4ee3-bd9f-0b01770ad858
```

**Phản Hồi:**

```json
{
    "result": [
        {
            "activity_name": "Tham quan Tokyo Skytree",
            "date": "2025-06-11",
            "time": "10:00 AM",
            "duration": "2 giờ",
            "price_per_person": 20,
            "description": "Tham quan công trình cao nhất Tokyo với các đài quan sát",
            "category": "Tham quan"
        }
    ]
}
```

## Các Điểm Cuối API Bổ Sung

### Danh Sách Các Cuộc Trò Chuyện

```http
GET /conversation/list?app_name=your_app_name&user_id=your_user_id
```

### Danh Sách Tin Nhắn Trong Một Cuộc Trò Chuyện

```http
GET /message/list?conversation_id=36d460c5-1a81-4ee3-bd9f-0b01770ad858
```

### Kiểm Tra Trạng Thái Xử Lý

```http
GET /message/pending
```

### Xóa Một Cuộc Trò Chuyện

```http
DELETE /conversation/delete?conversation_id=36d460c5-1a81-4ee3-bd9f-0b01770ad858
```

## Xử Lý Lỗi

Các phản hồi lỗi thường gặp:

### Thiếu Các Trường Bắt Buộc

```json
{
    "detail": "Thiếu các trường bắt buộc: departure_city, budget"
}
```

### Khoảng Thời Gian Ngày Không Hợp Lý

```json
{
    "detail": "Ngày bắt đầu phải trước ngày kết thúc"
}
```

### Ngân Sách Không Hợp Lý

```json
{
    "detail": "Ngân sách phải lớn hơn 0"
}
```

## Các Thực Hành Tốt Nhất

1. **Luôn lưu lại `conversation_id`** sau khi tạo cuộc trò chuyện
2. **Xác minh ngày tháng** trước khi gửi - đảm bảo ngày bắt đầu < ngày kết thúc và ngày tháng phải ở tương lai
3. **Bao gồm tất cả các trường metadata bắt buộc** khi sử dụng `/message/send/fixed`
4. **Chờ và kiểm tra kết quả** - Sau khi gửi tin nhắn, đợi một lát trước khi lấy dữ liệu chuyến bay/khách sạn/hoạt động
5. **Xử lý lỗi một cách thận trọng** - Kiểm tra mã trạng thái và thông báo lỗi

## Ví Dụ Luồng Frontend

```javascript
// 1. Tạo cuộc trò chuyện
const conversation = await createConversation(appName, userId);
const conversationId = conversation.result.conversation_id;

// 2. Gửi yêu cầu du lịch
const messageData = {
    role: "user",
    parts: [{
        type: "text",
        text: userInput
    }],
    metadata: {
        conversation_id: conversationId,
        departure_city: "Hà Nội",
        destination_city: "Nhật Bản",
        start_date: "2025-06-10",
        end_date: "2025-06-17",
        number_of_travelers: 3,
        budget: 3000,
        preferences: "ẩm thực, văn hóa, lịch sử"
        // ... các trường khác
    }
};

await sendMessage(messageData);

// 3. Chờ và lấy kết quả
setTimeout(async () => {
    const flights = await getFlights(conversationId);
    const hotels = await getHotels(conversationId);
    const activities = await getActivities(conversationId);
    
    // Hiển thị kết quả cho người dùng
}, 5000); // Chờ 5 giây cho việc xử lý
```
