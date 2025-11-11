"""
Script để test Google OAuth flow
Chạy: python test_oauth.py
"""

import requests
import webbrowser
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

# ===== CẤU HÌNH =====
BACKEND_URL = "http://localhost:8000"  # Thay bằng URL backend của bạn
CALLBACK_PORT = 8888  # Port để nhận callback
FRONTEND_REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# Biến global để lưu code
captured_code = None
captured_error = None
server_should_stop = False


class CallbackHandler(BaseHTTPRequestHandler):
    """Handler để bắt callback từ backend"""

    def do_GET(self):
        global captured_code, captured_error, server_should_stop

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            captured_code = params["code"][0]
            message = f"✅ Nhận được code: {captured_code[:20]}..."
            print(f"\n{message}")
        elif "error" in params:
            captured_error = params["error"][0]
            message = f"❌ Lỗi: {captured_error}"
            print(f"\n{message}")
        else:
            message = "⚠️ Không nhận được code hoặc error"

        html = f"""<!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>OAuth Callback</title>
    </head>
    <body style="font-family: Arial; padding: 50px; text-align: center;">
    <h2>{message}</h2>
    <p>Bạn có thể đóng tab này.</p>
    <script>setTimeout(() => window.close(), 2000);</script>
    </body>
    </html>
    """

        body = html.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        server_should_stop = True

    def log_message(self, format, *args):
        """Tắt log mặc định"""
        pass


def start_callback_server():
    """Khởi động HTTP server để nhận callback"""
    global server_should_stop
    server_should_stop = False

    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    print(f"🔧 Callback server đang chạy tại http://localhost:{CALLBACK_PORT}")

    # Chạy server cho đến khi nhận được callback
    while not server_should_stop:
        server.handle_request()

    print("🔧 Callback server đã dừng")


def test_oauth_flow():
    """Test toàn bộ OAuth flow"""

    print("=" * 60)
    print("🚀 BẮT ĐẦU TEST GOOGLE OAUTH FLOW")
    print("=" * 60)

    # Bước 1: Khởi động callback server trong thread riêng
    print("\n📍 Bước 1: Khởi động callback server...")
    server_thread = threading.Thread(target=start_callback_server, daemon=True)
    server_thread.start()
    time.sleep(1)  # Đợi server khởi động

    # Bước 2: Gọi endpoint login
    print("\n📍 Bước 2: Gọi endpoint /google/login...")
    login_url = f"{BACKEND_URL}/auth/google/login?redirect_uri={FRONTEND_REDIRECT_URI}"
    print(f"   URL: {login_url}")

    try:
        response = requests.get(login_url, allow_redirects=False)

        if response.status_code in [301, 302, 303, 307, 308]:
            google_oauth_url = response.headers.get("Location")
            print(f"   ✅ Redirect đến Google OAuth: {google_oauth_url[:80]}...")

            # Bước 3: Mở browser để user login
            print("\n📍 Bước 3: Mở browser để đăng nhập Google...")
            print("   ⚠️ Vui lòng đăng nhập và cho phép quyền truy cập")
            webbrowser.open(google_oauth_url)

            # Đợi callback
            print("\n📍 Bước 4: Đợi callback từ backend...")
            print("   (Timeout sau 120 giây)")

            timeout = 120
            start_time = time.time()
            while captured_code is None and captured_error is None:
                if time.time() - start_time > timeout:
                    print("\n❌ Timeout! Không nhận được callback")
                    return
                time.sleep(0.5)

            if captured_error:
                print(f"\n❌ OAuth thất bại: {captured_error}")
                return

            # Bước 5: Exchange code lấy tokens
            print("\n📍 Bước 5: Exchange code lấy tokens...")
            exchange_url = f"{BACKEND_URL}/auth/exchange-code"
            exchange_response = requests.post(
                exchange_url, json={"code": captured_code}
            )

            if exchange_response.status_code == 200:
                tokens = exchange_response.json()
                print("\n" + "=" * 60)
                print("✅ THÀNH CÔNG! NHẬN ĐƯỢC TOKENS")
                print("=" * 60)
                print(f"Tokens: {tokens}")
                print(
                    f"\n📦 Access Token: {tokens['data'].get('access_token')[:50]}..."
                )
                print(
                    f"📦 Refresh Token: {tokens['data'].get('refresh_token')[:50]}..."
                )
                print(f"📦 Token Type: {tokens['data'].get('token_type')}")
                if "user_id" in tokens["data"]:
                    print(f"👤 User ID: {tokens['data'].get('user_id')}")

                # Test access token
                print("\n📍 Bước 6: Test access token...")
                test_token(tokens["data"].get("access_token"))

            else:
                print("\n❌ Exchange code thất bại!")
                print(f"   Status: {exchange_response.status_code}")
                print(f"   Response: {exchange_response.text}")

        else:
            print("\n❌ Không nhận được redirect!")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Lỗi kết nối: {e}")
        print(f"   Đảm bảo backend đang chạy tại {BACKEND_URL}")

    print("\n" + "=" * 60)
    print("🏁 HOÀN THÀNH TEST")
    print("=" * 60)


def test_token(access_token):
    """Test access token bằng cách gọi endpoint cần auth"""

    # Thử gọi một endpoint protected (thay đổi URL tùy backend của bạn)
    test_endpoints = [
        f"{BACKEND_URL}/auth/me",
        f"{BACKEND_URL}/auth/profile",
    ]

    headers = {"Authorization": f"Bearer {access_token}"}

    for endpoint in test_endpoints:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            print(f"   ✅ Token hoạt động! Endpoint: {endpoint}")
            print(f"   📄 User data: {response.json()}")
            return
        elif response.status_code == 404:
            continue  # Thử endpoint khác
        else:
            print(f"   ⚠️ Response: {response.status_code}")

    print("   ⚠️ Không tìm thấy endpoint để test token")
    print("   💡 Thử tự gọi endpoint protected của bạn với header:")
    print(f"      Authorization: Bearer {access_token[:30]}...")


if __name__ == "__main__":
    try:
        test_oauth_flow()
    except KeyboardInterrupt:
        print("\n\n⚠️ Đã hủy bởi user")
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
        import traceback

        traceback.print_exc()
