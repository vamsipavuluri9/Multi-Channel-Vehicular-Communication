import socket
import time
from datetime import datetime
from pathlib import Path

# Target OBU Details
UDP_IP = "192.168.52.79"
UDP_PORT = 12345

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("[INFO] Monitoring RX stall status and sending packets every 10s during stalls...")

try:
    while True:
        if Path("rx_stalled.flag").exists():
            # Compose dynamic message with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Hello from Laptop! You are currently out of RSU zone. Timestamp: {timestamp}"
            sock.sendto(message.encode(), (UDP_IP, UDP_PORT))
            print(f"[{timestamp}] RX stalled → Message sent to OBU.")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] RX growing → No packet sent.")
        
        time.sleep(10)  # 10s interval

except KeyboardInterrupt:
    print("\n[INFO] Script stopped by user.")

finally:
    sock.close()
