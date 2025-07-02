import socket
import time
import requests
from datetime import datetime
from pathlib import Path

# Target OBU Details
UDP_IP = "192.168.52.79"
UDP_PORT = 12345

# Central Server Details
CENTRAL_SERVER_URL = "http://127.0.0.1:5000/get_dummy_message"
LAPTOP_ID = "Laptop001"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("[INFO] Monitoring RX stall status and polling Central Server for dummy messages...")

try:
    while True:
        if Path("obu_halted.flag").exists():
            print("[INFO] OBU halt detected based on TX file. Stopping polling...\n")
            break

        if Path("rx_stalled.flag").exists():
            try:
                response = requests.get(CENTRAL_SERVER_URL, params={"laptop_id": LAPTOP_ID})
                if response.status_code == 200:
                    msg = response.json().get("message")
                    if msg:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sock.sendto(msg.encode(), (UDP_IP, UDP_PORT))
                        print(f"\nReceived message from the central server and it has been sent to OBU.\n The actual message from the central server is:\n{msg}")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] No message from server.")
                else:
                    print(f"[ERROR] Server response error: {response.text}")

            except Exception as e:
                print(f"[ERROR] {e}")

        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] RX growing → No packet sent.")

        time.sleep(10)

except KeyboardInterrupt:
    print("\n[INFO] Script stopped by user.")

finally:
    sock.close()
