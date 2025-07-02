import os
import time
import requests
from pathlib import Path

WATCH_FOLDER = Path(r"C:\Users\Admin\OneDrive\Desktop\selective_tx_snapshots_v451")
CENTRAL_SERVER_URL = "http://127.0.0.1:5000/upload_pcap"
LAPTOP_ID = "Laptop001"

uploaded_files = set()

print(f"Monitoring {WATCH_FOLDER} folder for completed TX snapshots to upload to the central server…")

try:
    while True:
        try:
            for file in WATCH_FOLDER.glob("tx_clean_*.pcap"):
                if file.name not in uploaded_files:
                    try:
                        with open(file, "rb") as f:
                            files = {'pcap_file': f}
                            data = {'laptop_id': LAPTOP_ID}
                            response = requests.post(CENTRAL_SERVER_URL, files=files, data=data)
                            if response.status_code == 200:
                                print(f"Uploaded {file.name}")
                                uploaded_files.add(file.name)
                            else:
                                print(f"Failed to upload {file.name}: {response.text}")
                    except Exception as e:
                        print(f"Error uploading {file.name}: {e}")

            time.sleep(5)
        
        except KeyboardInterrupt:
            raise  # Re-raise to be caught by outer except block

except KeyboardInterrupt:
    print("\n[INFO] Server side uploading script stopped manually (Ctrl+c) by the admin...")
