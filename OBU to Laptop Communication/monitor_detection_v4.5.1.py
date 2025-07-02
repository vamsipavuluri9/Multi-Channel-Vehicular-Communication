"""
monitor_detection_v4_5_1.py
=============================
Version: v4.5.1 (16-June-2025)

Overview:
---------
This version is the final stable and verified implementation for selectively transferring TX packets
from a moving OBU to a connected laptop **only during RX stalls** (i.e., when the OBU is out of RSU range).

Key Improvements Over Previous Versions:
----------------------------------------
1. Uses **packet indices** (instead of byte offsets) for precise slicing.
2. Preserves **original timestamps** using Scapy's `rdpcap` and `wrpcap` APIs.
3. Fixes the **duplicated timestamp issue** that appeared in v4.4 and v4.6.
4. Handles **edge case**: OBU never enters RSU range.
5. Fully automated: RX stall detection, TX pulling, and snapshot writing.

Folder Created:
---------------
`selective_tx_snapshots_v451/` with:
- `tx_clean_normal_*.pcap` (between RX stall/resume)
- `tx_clean_final_*.pcap` (final dump before OBU stops)
- `tx_pc5_full.pcap` (latest pulled full TX file from OBU)

"""

# ----------------------------
# Standard & External Imports
# ----------------------------
from __future__ import annotations
import time
from datetime import datetime
from pathlib import Path
import paramiko                       # SSH & SFTP communication with OBU
from scapy.all import rdpcap, wrpcap # PCAP parsing & writing with timestamp preservation

# ----------------------------
# SSH & PCAP File Configuration
# ----------------------------
OBU_IP = "192.168.52.79"
OBU_USER = "user"
OBU_PASS = "user"

RX_PCAP_PATH = "/mnt/rw/log/current/rx_pc5.pcap"   # Remote RX log file on OBU
TX_PCAP_PATH = "/mnt/rw/log/current/tx_pc5.pcap"   # Remote TX log file on OBU

# ----------------------------
# Monitoring & Snapshot Parameters
# ----------------------------
CHECK_INTERVAL = 5          # Seconds between RX/TX checks
STALL_THRESHOLD = 2         # How many times RX must stay constant to declare stall
STEADY_THRESHOLD = 4        # How many TX steady checks before final snapshot
RX_RESUME_THRESHOLD = 2     # RX must grow this many times to declare RSU re-entry

# ----------------------------
# Local Folder Setup
# ----------------------------
LOCAL_OUTPUT = Path("selective_tx_snapshots_v451")
LOCAL_TX_FULL = LOCAL_OUTPUT / "tx_pc5_full.pcap"

# ----------------------------
# SnapshotManager Class
# ----------------------------
class SnapshotManager:
    def __init__(self):
        self.cached_packets = []  # Stores full TX packet list after pulling

    def pull_tx_file(self, sftp: paramiko.SFTPClient) -> bool:
        """Pulls tx_pc5.pcap from OBU and loads it into memory."""
        LOCAL_OUTPUT.mkdir(exist_ok=True)
        try:
            sftp.get(TX_PCAP_PATH, str(LOCAL_TX_FULL))
            self.cached_packets = rdpcap(str(LOCAL_TX_FULL))  # Load packets into memory
            print(f"\U0001F4E6 Pulled full TX ({len(self.cached_packets)} packets) → {LOCAL_TX_FULL.name}")
            return True
        except Exception as e:
            print(f"❌ TX pull failed: {e}")
            return False

    def extract_snapshot(self, pkt_start: int, pkt_end: int, label: str):
        """Saves a slice of TX packets [start:end] with preserved timestamps."""
        ts = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        out_file = LOCAL_OUTPUT / f"tx_clean_{label}_{ts}.pcap"
        try:
            sliced = self.cached_packets[pkt_start:pkt_end]
            wrpcap(str(out_file), sliced)
            print(f"✅ Snapshot saved: {out_file.name} ({len(sliced)} packets)")
        except Exception as e:
            print(f"❌ Snapshot write failed: {e}")

    def count_packets(self) -> int:
        return len(self.cached_packets)

# ----------------------------
# Copier Class: Main Monitor
# ----------------------------
class Copier:
    def __init__(self):
        self.prev_rx_size = -1
        self.prev_tx_size = -1
        self.rx_stalled_cnt = 0
        self.rx_growth_cnt = 0
        self.tx_steady_cnt = 0
        self.rx_stalled = False
        self.snapshot_start_idx = None
        self.final_snapshot_taken = False
        self.snapshot_mgr = SnapshotManager()

    def _get_size(self, ssh: paramiko.SSHClient, path: str) -> int:
        """Checks file size remotely over SSH."""
        for cmd in (f"stat -c %s {path}", f"wc -c < {path}"):
            try:
                _, out, _ = ssh.exec_command(cmd)
                val = out.read().decode().strip()
                if val.isdigit():
                    return int(val)
            except:
                pass
        return -1

    def run(self):
        while True:
            try:
                print("\U0001F50C Connecting …")
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(OBU_IP, username=OBU_USER, password=OBU_PASS, timeout=10)
                sftp = ssh.open_sftp()
                print(f"✅ Connected to {OBU_IP}")

                while True:
                    rx_sz = self._get_size(ssh, RX_PCAP_PATH)
                    tx_sz = self._get_size(ssh, TX_PCAP_PATH)

                    # RX STALL Detection
                    if rx_sz == self.prev_rx_size:
                        self.rx_stalled_cnt += 1
                        self.rx_growth_cnt = 0
                    else:
                        self.rx_growth_cnt += 1
                        # RSU Re-entry → copy snapshot
                        if self.rx_stalled and self.rx_growth_cnt >= RX_RESUME_THRESHOLD:
                            if self.snapshot_start_idx is not None:
                                print(f"\U0001F4C4 RX resumed. Saving TX snapshot (pkt {self.snapshot_start_idx} → …)")
                                if self.snapshot_mgr.pull_tx_file(sftp):
                                    pkt_end = self.snapshot_mgr.count_packets()
                                    self.snapshot_mgr.extract_snapshot(self.snapshot_start_idx, pkt_end, "normal")
                                    self.snapshot_start_idx = None
                                    self.final_snapshot_taken = False
                            self.rx_stalled_cnt = 0
                            self.tx_steady_cnt = 0

                    self.prev_rx_size = rx_sz
                    rx_stalled_now = self.rx_stalled_cnt >= STALL_THRESHOLD

                    if rx_stalled_now and self.snapshot_start_idx is None:
                        if self.snapshot_mgr.pull_tx_file(sftp):
                            pkt_count = self.snapshot_mgr.count_packets()
                            self.snapshot_start_idx = pkt_count
                            print(f"⚠️ RX stalled. TX pkt start = {pkt_count}")

                    self.rx_stalled = rx_stalled_now

                    # Final Snapshot: TX stopped + RX still stalled
                    if self.rx_stalled:
                        if tx_sz == self.prev_tx_size:
                            self.tx_steady_cnt += 1
                        else:
                            self.tx_steady_cnt = 0

                        if self.tx_steady_cnt >= STEADY_THRESHOLD and not self.final_snapshot_taken and self.snapshot_start_idx is not None:
                            print(f"\U0001F4C4 Final snapshot (pkt {self.snapshot_start_idx} → …)")
                            if self.snapshot_mgr.pull_tx_file(sftp):
                                pkt_end = self.snapshot_mgr.count_packets()
                                self.snapshot_mgr.extract_snapshot(self.snapshot_start_idx, pkt_end, "final")
                                self.final_snapshot_taken = True
                    else:
                        self.tx_steady_cnt = 0

                    self.prev_tx_size = tx_sz
                    print(f"📄 rx size = {rx_sz:,} | {'STALLED' if self.rx_stalled else 'growing'}")
                    time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                print("👋 Exiting …")
                break
            except Exception as e:
                print(f"❌ SSH error: {e} – reconnecting in 10s …")
                time.sleep(10)
            finally:
                try: sftp.close()
                except: pass
                try: ssh.close()
                except: pass

# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    print("\U0001F527 Running monitor_detection_v4_5_1 (timestamp-corrected slicing)\n")
    Copier().run()
