from __future__ import annotations
import time
from datetime import datetime
from pathlib import Path
import paramiko
from scapy.all import rdpcap, wrpcap

# OBU Connection Details
OBU_IP = "192.168.52.79"
OBU_USER = "user"
OBU_PASS = "user"

# Remote Paths on OBU
RX_PCAP_PATH = "/mnt/rw/log/current/rx_pc5.pcap"
TX_PCAP_PATH = "/mnt/rw/log/current/tx_pc5.pcap"

# Monitoring Parameters
CHECK_INTERVAL = 10
STALL_THRESHOLD = 2
STEADY_THRESHOLD = 4
RX_RESUME_THRESHOLD = 2
TX_STALL_THRESHOLD = 4

# Local Paths
LOCAL_OUTPUT = Path("selective_tx_snapshots_v451")
LOCAL_TX_FULL = LOCAL_OUTPUT / "tx_pc5_full.pcap"
OBU_HALT_FLAG = Path("obu_halted.flag")

# Cleanup old halt flag if present
OBU_HALT_FLAG.unlink(missing_ok=True)


class SnapshotManager:
    def __init__(self):
        self.cached_packets = []

    def pull_tx_file(self, sftp: paramiko.SFTPClient) -> bool:
        LOCAL_OUTPUT.mkdir(exist_ok=True)
        try:
            sftp.get(TX_PCAP_PATH, str(LOCAL_TX_FULL))
            self.cached_packets = rdpcap(str(LOCAL_TX_FULL))
            print(f"Pulled full TX ({len(self.cached_packets)} packets) → {LOCAL_TX_FULL.name}")
            return True
        except Exception as e:
            print(f"TX pull failed: {e}")
            return False

    def extract_snapshot(self, pkt_start: int, pkt_end: int, label: str):
        ts = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        out_file = LOCAL_OUTPUT / f"tx_clean_{label}_{ts}.pcap"
        try:
            sliced = self.cached_packets[pkt_start:pkt_end]
            wrpcap(str(out_file), sliced)
            print(f"Snapshot saved: {out_file.name} ({len(sliced)} packets)")
        except Exception as e:
            print(f"Snapshot write failed: {e}")

    def count_packets(self) -> int:
        return len(self.cached_packets)


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
        self.rsu_detected = False

    def _get_size(self, ssh: paramiko.SSHClient, path: str) -> int:
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
        try:
            while True:
                try:
                    print("Connecting to OBU…")
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(OBU_IP, username=OBU_USER, password=OBU_PASS, timeout=10)
                    sftp = ssh.open_sftp()
                    print(f"Connected to {OBU_IP}")

                    while True:
                        rx_sz = self._get_size(ssh, RX_PCAP_PATH)
                        tx_sz = self._get_size(ssh, TX_PCAP_PATH)

                        # RX Zone Detection
                        if rx_sz > 0 and rx_sz > self.prev_rx_size:
                            self.rx_growth_cnt += 1
                            self.rsu_detected = True
                        else:
                            self.rx_growth_cnt = 0

                        # RX Stall Detection
                        if rx_sz == self.prev_rx_size:
                            self.rx_stalled_cnt += 1
                        else:
                            if self.rx_stalled and self.rx_growth_cnt >= RX_RESUME_THRESHOLD:
                                if self.snapshot_start_idx is not None:
                                    print("RX resumed. Saving normal TX snapshot…")
                                    if self.snapshot_mgr.pull_tx_file(sftp):
                                        pkt_end = self.snapshot_mgr.count_packets()
                                        self.snapshot_mgr.extract_snapshot(self.snapshot_start_idx, pkt_end, "normal")
                                        self.snapshot_start_idx = None
                                        self.final_snapshot_taken = False
                                    Path("rx_stalled.flag").unlink(missing_ok=True)
                                self.rx_stalled_cnt = 0
                                self.tx_steady_cnt = 0

                        self.rx_stalled = self.rx_stalled_cnt >= STALL_THRESHOLD

                        # Snapshot during Stall
                        if self.rx_stalled and self.snapshot_start_idx is None:
                            if self.snapshot_mgr.pull_tx_file(sftp):
                                pkt_count = self.snapshot_mgr.count_packets()
                                self.snapshot_start_idx = pkt_count
                                print(f"RX stalled. TX pkt start = {pkt_count}")
                                Path("rx_stalled.flag").write_text("1")

                        # TX Steady Detection for OBU halt (independent of RX stall)
                        if tx_sz == self.prev_tx_size:
                            self.tx_steady_cnt += 1
                        else:
                            self.tx_steady_cnt = 0

                        if self.tx_steady_cnt >= TX_STALL_THRESHOLD:
                            print("OBU has halted based on TX file. Saving final snapshot and stopping monitoring…")
                            if self.snapshot_start_idx is not None:
                                if self.snapshot_mgr.pull_tx_file(sftp):
                                    pkt_end = self.snapshot_mgr.count_packets()
                                    self.snapshot_mgr.extract_snapshot(self.snapshot_start_idx, pkt_end, "final")

                            OBU_HALT_FLAG.write_text("1")
                            return  # Exit monitoring

                        self.prev_rx_size = rx_sz
                        self.prev_tx_size = tx_sz

                        status = "STALLED" if self.rx_stalled else ("growing" if self.rsu_detected else "no RSU zone yet")
                        print(f"rx size = {rx_sz:,} | {status}")

                        time.sleep(CHECK_INTERVAL)

                except Exception as e:
                    print(f"SSH error: {e} – reconnecting in 10s…")
                    time.sleep(10)
                finally:
                    try: sftp.close()
                    except: pass
                    try: ssh.close()
                    except: pass

        except KeyboardInterrupt:
            print("User manually stopped the OBU monitoring code.")


if __name__ == "__main__":
    print("Running monitor_detection_v4.5.1…")
    Copier().run()
