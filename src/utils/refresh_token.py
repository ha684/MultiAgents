import httpx
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the authorization code from callback URL
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if "code" in query_params:
            self.server.auth_code = query_params["code"][0]
            # Send success response
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html><body>
            <h2>Authorization successful!</h2>
            <p>You can close this window and return to the application.</p>
            </body></html>
            """)
        else:
            # Handle error
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html><body>
            <h2>Authorization failed!</h2>
            <p>No authorization code received.</p>
            </body></html>
            """)

    def log_message(self, format, *args):
        # Suppress server logs
        return


async def regenerate_refresh_token():
    """
    Script để generate refresh token mới sử dụng localhost redirect
    Run this when refresh token expires
    """
    print("=== Google OAuth2 Refresh Token Generator ===")
    print("1. Go to: https://console.cloud.google.com/")
    print("2. Select your project")
    print("3. Go to APIs & Services > Credentials")
    print("4. Find your OAuth 2.0 Client ID")
    print("5. Add 'http://localhost:8080' to Authorized redirect URIs")
    print("6. Note down Client ID and Client Secret")
    print()

    client_id = input("Enter Client ID: ")
    client_secret = input("Enter Client Secret: ")

    # Use localhost instead of OOB
    redirect_uri = "http://localhost:8000"
    port = 8000

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope=https://www.googleapis.com/auth/gmail.send&"
        f"response_type=code&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    print(f"\n7. Starting local server on port {port}...")

    # Start local HTTP server to handle callback
    server = HTTPServer(("localhost", port), CallbackHandler)
    server.auth_code = None
    server.timeout = 60  # 1 minute timeout

    # Start server in a separate thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    print("8. Opening browser for authorization...")
    webbrowser.open(auth_url)
    print(f"   If browser doesn't open automatically, go to:\n   {auth_url}")
    print("\n9. Complete the authorization in your browser...")

    # Wait for authorization code
    start_time = time.time()
    while server.auth_code is None and (time.time() - start_time) < 60:
        time.sleep(1)

    server.shutdown()

    if server.auth_code is None:
        print("\nTIMEOUT: No authorization code received within 60 seconds")
        return

    print("\n10. Got authorization code, exchanging for tokens...")

    # Exchange authorization code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": server.auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)

        if response.status_code == 200:
            tokens = response.json()
            print("\n=== SUCCESS! ===")
            print(f"Refresh Token: {tokens.get('refresh_token')}")
            print(f"Access Token: {tokens.get('access_token')}")
            print(f"Expires in: {tokens.get('expires_in')} seconds")
            print("\nAdd this to your .env file:")
            print(f"GMAIL_CLIENT_ID={client_id}")
            print(f"GMAIL_CLIENT_SECRET={client_secret}")
            print(f"GMAIL_REFRESH_TOKEN={tokens.get('refresh_token')}")
        else:
            print(f"\nERROR: {response.status_code}")
            print(response.text)


if __name__ == "__main__":
    import asyncio

    asyncio.run(regenerate_refresh_token())
