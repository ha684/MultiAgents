import httpx


async def regenerate_refresh_token():
    """
    Script để generate refresh token mới
    Run this when refresh token expires
    """
    print("=== Google OAuth2 Refresh Token Generator ===")
    print("1. Go to: https://console.cloud.google.com/")
    print("2. Select your project")
    print("3. Go to APIs & Services > Credentials")
    print("4. Find your OAuth 2.0 Client ID")
    print("5. Note down Client ID and Client Secret")
    print()

    client_id = input("Enter Client ID: ")
    client_secret = input("Enter Client Secret: ")
    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri=urn:ietf:wg:oauth:2.0:oob&"
        f"scope=https://www.googleapis.com/auth/gmail.send&"
        f"response_type=code&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    print(f"\n6. Open this URL in browser:\n{auth_url}")
    print("\n7. Authorize the application")
    print("8. Copy the authorization code")

    auth_code = input("\nEnter authorization code: ")

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)

        if response.status_code == 200:
            tokens = response.json()
            print("\n=== SUCCESS! ===")
            print(f"Refresh Token: {tokens.get('refresh_token')}")
            print(f"Access Token: {tokens.get('access_token')}")
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
