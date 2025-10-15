import requests
import json
import sys
from datetime import datetime

OUTPUT_FILENAME = "sse_debug_log.txt"
BASE_URL = "http://localhost:8000"
ENDPOINT = "/chat/ask/sse"
STREAMING_URL = f"{BASE_URL}{ENDPOINT}"

PAYLOAD = {
    "message": {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "text": "Analyze the geopolitical impact of the latest G7 summit decisions on energy trading. Use deep research and provide complete citations for all claims.",
            }
        ],
        "metadata": {
            "conversation_id": "068ef452-0b6a-72bb-8000-2e23093ae04a",
            "kb_id": "068e7efb-fd5b-7523-8000-3e54cd74ff34",
            "user_id": "ha",
            "app_name": "ha",
        },
    },
    "agentic": True,
    "web_search": True,
}

print(f"--- Sending request to: {STREAMING_URL} (agentic=True) ---")
print("Connecting... Press Ctrl+C to stop.")
print("-" * 50)

try:
    # Use 'stream=True' to prevent downloading the entire response at once
    with requests.post(
        STREAMING_URL,
        json=PAYLOAD,
        stream=True,
        headers={"Accept": "text/event-stream"},  # Signal that we expect SSE format
    ) as response:
        # Check for HTTP errors before processing the stream
        response.raise_for_status()

        current_event = (
            "message"  # Default event type until an 'event:' line is received
        )

        # Open file for writing the output
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            # Write header information to the log file
            f.write(f"### SSE Debug Log Started: {datetime.now().isoformat()} ###\n")
            f.write(f"Request URL: {STREAMING_URL}\n")
            f.write(f"Request Payload:\n{json.dumps(PAYLOAD, indent=2)}\n\n")

            # Iterate over the response content line by line
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    trimmed_line = line.strip()

                    # Write the raw line to the file immediately (optional, useful for raw debugging)
                    f.write(f"RAW: {trimmed_line}\n")

                    if trimmed_line.startswith("event:"):
                        # 1. Capture the custom event type (e.g., 'thought', 'tool_call')
                        current_event = trimmed_line[len("event:") :].strip()

                    elif trimmed_line.startswith("data:"):
                        # 2. Extract and parse the JSON payload
                        data_str = trimmed_line[len("data:") :].strip()
                        try:
                            json_data = json.loads(data_str)

                            # 3. Format and write the structured event data
                            log_entry = f"\n--- [{current_event.upper()}] - Time: {datetime.now().strftime('%H:%M:%S.%f')[:-3]} ---\n"
                            log_entry += json.dumps(
                                json_data, indent=2, ensure_ascii=False
                            )
                            log_entry += f"\n{'-' * (len(current_event) + 30)}\n"

                            f.write(log_entry)

                            # Provide minimal terminal feedback
                            sys.stdout.write(f"-> Logged event: {current_event}\n")
                            sys.stdout.flush()

                        except json.JSONDecodeError:
                            # Fallback for unexpected or malformed data
                            f.write(
                                f"\n[ERROR] Failed to parse JSON for event type '{current_event}'. RAW DATA: {data_str}\n"
                            )
                            sys.stdout.write(
                                f"[ERROR] JSON Decode failed for {current_event}!\n"
                            )
                            sys.stdout.flush()

                    elif not trimmed_line.startswith(":"):
                        # Log any other unexpected line types
                        f.write(f"UNEXPECTED LINE: {trimmed_line}\n")

            f.write(f"\n### SSE Debug Log Ended: {datetime.now().isoformat()} ###\n")


except requests.exceptions.RequestException as e:
    print("\n--- An HTTP Request Error Occurred ---")
    print(f"Error: {e}")
    if hasattr(e.response, "text"):
        print(f"Response Body: {e.response.text[:250]}...")
    sys.exit(1)
except KeyboardInterrupt:
    print("\n--- Stream stopped by user (Ctrl+C) ---")
except Exception as e:
    print("\n--- An Unexpected Error Occurred ---")
    print(f"Error: {e}")

print("-" * 50)
print("Stream finished.")
