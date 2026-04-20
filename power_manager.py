"""
+==============================================================+
|           SRJahir Tech Power Manager v2.0                    |
|           https://srjahir.in                                 |
|           GitHub: github.com/Srj0210/power-manager           |
|                                                              |
|  Smart PC Power Management after Downloads, Copies & More    |
|                                                              |
|  Features:                                                   |
|  - Network-aware (10min wait on disconnect)                  |
|  - Torrent seeding ignored (shutdown after download done)    |
|  - Grace period + multi-recheck before any action            |
|  - File copy/move completion detection                       |
|  - Browser download monitor (all major browsers)             |
|  - Countdown timer & System idle monitor                     |
+==============================================================+

Requirements: pip install customtkinter psutil
Optional:     pip install qbittorrent-api  (for qBittorrent API)
Run:          python power_manager.py
Build:        pyinstaller --onefile --windowed --icon=app_icon.ico power_manager.py
"""

import customtkinter as ctk
import threading
import time
import os
import sys
import json
import ctypes
import socket
from datetime import datetime
from pathlib import Path
import psutil

try:
    import qbittorrentapi
    QBIT_AVAILABLE = True
except ImportError:
    QBIT_AVAILABLE = False

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

# ── Paths ────────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".srjahir_power_manager.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), "srjahir_power_manager_log.txt")

DEFAULT_CONFIG = {
    "download_folder": str(Path.home() / "Downloads"),
    "monitor_folder": "",
    "qbit_host": "localhost",
    "qbit_port": 8080,
    "qbit_user": "admin",
    "qbit_pass": "adminadmin",
    "warning_seconds": 30,
    "idle_minutes": 10,
    "timer_minutes": 60,
    "check_interval": 5,
    "grace_period_minutes": 2,
    "recheck_count": 3,
    "network_wait_minutes": 10,
}

BRAND = {
    "bg_dark": "#0f0f1a",
    "bg_card": "#1a1a2e",
    "accent": "#00d4ff",
    "accent_hover": "#00b8e6",
    "accent2": "#7c3aed",
    "accent2_hover": "#6d28d9",
    "success": "#10b981",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "danger_hover": "#dc2626",
    "text": "#e2e8f0",
    "text_dim": "#94a3b8",
    "text_muted": "#64748b",
    "border": "#2d2d4a",
}


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            saved = json.load(f)
            config = DEFAULT_CONFIG.copy()
            config.update(saved)
            return config
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def log_action(message):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def play_alert():
    if SOUND_AVAILABLE:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


# ================================================================
#  NETWORK CHECKER
# ================================================================

class NetworkChecker:
    """Checks internet connectivity via DNS — core safety mechanism."""

    HOSTS = [("8.8.8.8", 53), ("1.1.1.1", 53), ("208.67.222.222", 53)]

    @staticmethod
    def is_online(timeout=3):
        for host, port in NetworkChecker.HOSTS:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                s.close()
                return True
            except (socket.timeout, socket.error, OSError):
                continue
        return False

    @staticmethod
    def wait_for_network(status_cb=None, max_wait_min=10, check_interval=15):
        """
        Waits up to max_wait_min minutes for network to come back.
        Returns True if online, False if timed out.
        """
        waited = 0
        max_wait = max_wait_min * 60
        while waited < max_wait:
            if NetworkChecker.is_online():
                return True
            remaining = (max_wait - waited) / 60
            if status_cb:
                status_cb(f"Network DOWN — waiting ({remaining:.1f} min left)...")
            time.sleep(check_interval)
            waited += check_interval
        return NetworkChecker.is_online()

    @staticmethod
    def get_download_speed_kbps(interval=3):
        net1 = psutil.net_io_counters()
        time.sleep(interval)
        net2 = psutil.net_io_counters()
        return (net2.bytes_recv - net1.bytes_recv) / interval / 1024


# ================================================================
#  MONITORS
# ================================================================

class FolderMonitor:
    """
    Watches a folder for file copy/move operations.
    Triggers when all files stop changing for stable_seconds.
    Then runs grace period + re-checks to confirm.
    """

    def __init__(self, folder, stable_seconds=15, check_interval=3,
                 grace_minutes=2, recheck=3, net_wait_min=10):
        self.folder = folder
        self.stable_seconds = stable_seconds
        self.check_interval = check_interval
        self.grace_minutes = grace_minutes
        self.recheck = recheck
        self.net_wait_min = net_wait_min
        self.running = False
        self._thread = None
        self.status_cb = None

    def _snapshot(self):
        snap = {}
        try:
            for root, _, files in os.walk(self.folder):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        st = os.stat(fp)
                        snap[fp] = (st.st_size, st.st_mtime)
                    except Exception:
                        pass
        except Exception:
            pass
        return snap

    def start(self, callback, status_cb=None):
        self.running = True
        self.status_cb = status_cb
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def _status(self, msg):
        if self.status_cb:
            self.status_cb(msg)

    def _run(self, callback):
        prev = self._snapshot()
        stable_since = None
        self._status("Watching folder for changes...")

        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break

            curr = self._snapshot()
            if curr == prev:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= self.stable_seconds and len(curr) > 0:
                    self._status(f"Files stable! Grace: {self.grace_minutes}min verify...")
                    log_action(f"FOLDER: Stable, grace {self.grace_minutes}min")
                    if self._grace_verify():
                        callback("folder_stable")
                        return
                    stable_since = None
                    prev = self._snapshot()
            else:
                stable_since = None
                prev = curr
                self._status(f"Files changing... ({len(curr)} items)")

    def _grace_verify(self):
        time.sleep(self.grace_minutes * 60)
        snap = self._snapshot()
        for i in range(self.recheck):
            if not self.running:
                return False
            time.sleep(10)
            if self._snapshot() != snap:
                log_action(f"FOLDER: Verify {i+1} FAILED")
                return False
            self._status(f"Verify {i+1}/{self.recheck} OK")
        log_action("FOLDER: All checks PASSED")
        return True

    def stop(self):
        self.running = False


class DownloadMonitor:
    """
    Browser download monitor — detects temp files from all major browsers.
    Network-aware: waits 10min on disconnect before giving up.
    """

    TEMP_EXT = {".crdownload", ".part", ".tmp", ".download", ".partial", ".aria2"}

    def __init__(self, folder, check_interval=5, grace_minutes=2,
                 recheck=3, net_wait_min=10):
        self.folder = folder
        self.check_interval = check_interval
        self.grace_minutes = grace_minutes
        self.recheck = recheck
        self.net_wait_min = net_wait_min
        self.running = False
        self._thread = None
        self.status_cb = None

    def _temp_files(self):
        found = set()
        try:
            for f in os.listdir(self.folder):
                if os.path.splitext(f)[1].lower() in self.TEMP_EXT:
                    found.add(f)
        except Exception:
            pass
        return found

    def start(self, callback, status_cb=None):
        self.running = True
        self.status_cb = status_cb
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def _status(self, msg):
        if self.status_cb:
            self.status_cb(msg)

    def _run(self, callback):
        self._status("Waiting for browser download to start...")

        # Phase 1: Wait for download to start
        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break
            t = self._temp_files()
            if t:
                self._status(f"Download active: {len(t)} file(s)")
                log_action(f"DOWNLOAD: {len(t)} temp files detected")
                break
        else:
            return

        # Phase 2: Wait for completion
        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break

            t = self._temp_files()
            if t:
                self._status(f"Downloading: {len(t)} file(s)...")
                continue

            # Temp files gone — check network
            log_action("DOWNLOAD: Temp files gone, checking network")

            if not NetworkChecker.is_online():
                # NETWORK DOWN — likely just a pause!
                self._status("NETWORK DOWN — download paused, waiting 10min...")
                log_action("DOWNLOAD: Network DOWN — waiting for reconnect")

                online = NetworkChecker.wait_for_network(
                    status_cb=self._status,
                    max_wait_min=self.net_wait_min,
                )
                if online:
                    self._status("Network back! Giving browser 30s to resume...")
                    log_action("DOWNLOAD: Network restored, waiting for resume")
                    time.sleep(30)  # Let browser auto-resume
                    continue
                else:
                    # Network didn't come back in 10 min — still don't trigger
                    self._status("Network timeout, still waiting...")
                    continue

            # Network UP — maybe genuinely complete
            self._status(f"Network OK! Grace: {self.grace_minutes}min verify...")
            log_action(f"DOWNLOAD: Network UP, grace {self.grace_minutes}min")

            if self._grace_verify():
                callback("download_complete")
                return
            else:
                self._status("Download resumed during grace, watching...")
                continue

    def _grace_verify(self):
        time.sleep(self.grace_minutes * 60)
        for i in range(self.recheck):
            if not self.running:
                return False
            time.sleep(15)
            if self._temp_files():
                log_action(f"DOWNLOAD: Verify {i+1} FAILED — temp files back")
                return False
            if not NetworkChecker.is_online():
                log_action(f"DOWNLOAD: Verify {i+1} FAILED — network dropped")
                return False
            self._status(f"Verify {i+1}/{self.recheck} OK")
        log_action("DOWNLOAD: All checks PASSED")
        return True

    def stop(self):
        self.running = False


class TorrentMonitor:
    """
    Torrent monitor — supports uTorrent Web, qBittorrent, and others.
    
    KEY BEHAVIOR:
    - Seeding is IGNORED — only downloading matters
    - Network drop = wait 10 min, don't trigger
    - Detects .!ut/.!bt incomplete files (uTorrent)
    - Uses qBittorrent API if available
    - Falls back to process + file detection
    """

    TORRENT_PROCS = {
        "utorrent.exe", "utorrentweb.exe", "bittorrent.exe",
        "qbittorrent.exe", "deluge.exe", "transmission-qt.exe",
        "aria2c.exe", "tixati.exe", "vuze.exe",
    }

    def __init__(self, host="localhost", port=8080, user="admin", password="adminadmin",
                 check_interval=10, grace_minutes=2, recheck=3, net_wait_min=10):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.check_interval = check_interval
        self.grace_minutes = grace_minutes
        self.recheck = recheck
        self.net_wait_min = net_wait_min
        self.running = False
        self._thread = None
        self.status_cb = None

    def _get_procs(self):
        found = set()
        for proc in psutil.process_iter(['name']):
            try:
                n = proc.info['name']
                if n and n.lower() in self.TORRENT_PROCS:
                    found.add(n.lower())
            except Exception:
                pass
        return found

    def _qbit_downloading_count(self):
        """Returns number of DOWNLOADING (not seeding) torrents, or None if API unavailable."""
        if not QBIT_AVAILABLE:
            return None
        try:
            c = qbittorrentapi.Client(
                host=self.host, port=self.port,
                username=self.user, password=self.password,
            )
            c.auth_log_in()
            downloading_states = {
                "downloading", "stalledDL", "metaDL", "queuedDL",
                "forcedDL", "allocating", "checkingDL",
            }
            # Seeding states are NOT counted: uploading, stalledUP, queuedUP, forcedUP, checkingUP
            torrents = c.torrents_info()
            dl_count = sum(1 for t in torrents if t.state in downloading_states)
            seed_count = sum(1 for t in torrents if "UP" in t.state or t.state == "uploading")
            return (dl_count, seed_count, len(torrents))
        except Exception:
            return None

    def _has_incomplete_files(self):
        """Check for uTorrent incomplete files (.!ut, .!bt) in Downloads."""
        dl_folder = str(Path.home() / "Downloads")
        try:
            for f in os.listdir(dl_folder):
                if f.endswith(".!ut") or f.endswith(".!bt"):
                    return True
        except Exception:
            pass
        return False

    def _is_downloading(self):
        """
        Returns (is_downloading, detail_string).
        SEEDING IS NOT DOWNLOADING — we only care about actual downloads.
        """
        # Method 1: qBittorrent API (most accurate)
        qbit = self._qbit_downloading_count()
        if qbit is not None:
            dl, seed, total = qbit
            if dl > 0:
                return True, f"qBit: {dl} downloading, {seed} seeding / {total} total"
            else:
                return False, f"qBit: 0 downloading, {seed} seeding (ignored)"

        # Method 2: Incomplete file detection (uTorrent Web)
        procs = self._get_procs()
        if procs:
            if self._has_incomplete_files():
                return True, f"{', '.join(procs)} — incomplete files found"
            else:
                # Process running but no incomplete files = seeding or idle
                # SEEDING IS NOT DOWNLOADING — return False
                return False, f"{', '.join(procs)} — no incomplete files (seeding/idle)"

        return False, "No torrent client detected"

    def start(self, callback, status_cb=None):
        self.running = True
        self.status_cb = status_cb
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def _status(self, msg):
        if self.status_cb:
            self.status_cb(msg)

    def _run(self, callback):
        self._status("Waiting for torrent download...")
        had_download = False

        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break

            is_dl, detail = self._is_downloading()

            if is_dl:
                had_download = True
                self._status(detail)
                continue

            if not had_download:
                # Check if there's at least a torrent client running
                procs = self._get_procs()
                if procs:
                    self._status(f"Client running: {', '.join(procs)} — waiting for download...")
                else:
                    self._status("Waiting for torrent client to start...")
                continue

            # HAD downloads, now no active downloads (seeding doesn't count!)
            self._status(f"Downloads done! {detail}")
            log_action(f"TORRENT: Downloads complete. {detail}")

            # Network check
            if not NetworkChecker.is_online():
                self._status("NETWORK DOWN — torrent likely paused, waiting 10min...")
                log_action("TORRENT: Network DOWN — waiting for reconnect")

                online = NetworkChecker.wait_for_network(
                    status_cb=self._status,
                    max_wait_min=self.net_wait_min,
                )
                if online:
                    self._status("Network back! Giving torrent 30s to resume...")
                    log_action("TORRENT: Network restored")
                    time.sleep(30)
                    had_download = False  # Re-detect
                    continue
                else:
                    self._status("Network timeout, still waiting...")
                    continue

            # Network UP — grace period
            self._status(f"Network OK! Grace: {self.grace_minutes}min verify...")
            log_action(f"TORRENT: Network UP, grace {self.grace_minutes}min")

            if self._grace_verify():
                callback("torrent_complete")
                return
            else:
                self._status("Download resumed during grace, watching...")
                had_download = True
                continue

    def _grace_verify(self):
        time.sleep(self.grace_minutes * 60)
        for i in range(self.recheck):
            if not self.running:
                return False
            time.sleep(15)

            if not NetworkChecker.is_online():
                log_action(f"TORRENT: Verify {i+1} FAILED — network dropped")
                return False

            is_dl, _ = self._is_downloading()
            if is_dl:
                log_action(f"TORRENT: Verify {i+1} FAILED — downloads active again")
                return False

            speed = NetworkChecker.get_download_speed_kbps(interval=3)
            if speed > 2000:  # >2 MBps = likely downloading again
                log_action(f"TORRENT: Verify {i+1} FAILED — high speed {speed:.0f} KBps")
                return False

            self._status(f"Verify {i+1}/{self.recheck} OK (net: {speed:.0f} KBps)")

        log_action("TORRENT: All checks PASSED — seeding ignored, download confirmed done")
        return True

    def stop(self):
        self.running = False


class IdleMonitor:
    """Triggers when CPU + Network idle for N minutes."""

    def __init__(self, idle_minutes=10, cpu_threshold=5,
                 net_threshold_kbps=50, check_interval=30):
        self.idle_minutes = idle_minutes
        self.cpu_threshold = cpu_threshold
        self.net_threshold = net_threshold_kbps * 1024
        self.check_interval = check_interval
        self.running = False
        self._thread = None
        self.status_cb = None

    def start(self, callback, status_cb=None):
        self.running = True
        self.status_cb = status_cb
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def _status(self, msg):
        if self.status_cb:
            self.status_cb(msg)

    def _run(self, callback):
        idle_start = None
        while self.running:
            cpu = psutil.cpu_percent(interval=2)
            net1 = psutil.net_io_counters()
            time.sleep(self.check_interval)
            if not self.running:
                break
            net2 = psutil.net_io_counters()
            net_speed = (net2.bytes_recv - net1.bytes_recv) / self.check_interval

            if cpu < self.cpu_threshold and net_speed < self.net_threshold:
                if idle_start is None:
                    idle_start = time.time()
                elapsed = time.time() - idle_start
                self._status(f"Idle: {elapsed/60:.1f} / {self.idle_minutes} min")
                if elapsed >= self.idle_minutes * 60:
                    callback("system_idle")
                    break
            else:
                if idle_start:
                    self._status("Activity detected, reset!")
                idle_start = None

    def stop(self):
        self.running = False


class TimerMonitor:
    """Simple countdown timer."""

    def __init__(self, minutes=60):
        self.total = minutes * 60
        self.remaining = self.total
        self.running = False

    def start(self, callback, tick_cb=None, status_cb=None):
        self.running = True
        self.remaining = self.total
        threading.Thread(target=self._run, args=(callback, tick_cb), daemon=True).start()

    def _run(self, callback, tick_cb):
        while self.running and self.remaining > 0:
            time.sleep(1)
            if not self.running:
                break
            self.remaining -= 1
            if tick_cb:
                tick_cb(self.remaining)
        if self.running and self.remaining <= 0:
            callback("timer_done")

    def stop(self):
        self.running = False


# ================================================================
#  POWER ACTIONS
# ================================================================

def do_shutdown():
    log_action("ACTION: Shutdown")
    os.system('shutdown /s /t 5 /c "SRJahir Power Manager: Shutting down..."')

def do_restart():
    log_action("ACTION: Restart")
    os.system('shutdown /r /t 5 /c "SRJahir Power Manager: Restarting..."')

def do_sleep():
    log_action("ACTION: Sleep")
    ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)

def do_hibernate():
    log_action("ACTION: Hibernate")
    os.system("shutdown /h")

def do_lock():
    log_action("ACTION: Lock Screen")
    ctypes.windll.user32.LockWorkStation()

def cancel_shutdown():
    os.system("shutdown /a")

ACTIONS = {
    "Shutdown": do_shutdown,
    "Restart": do_restart,
    "Sleep": do_sleep,
    "Hibernate": do_hibernate,
    "Lock Screen": do_lock,
}


# ================================================================
#  GUI
# ================================================================

class PowerManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config = load_config()

        self.title("SRJahir Tech Power Manager v2.0")
        self.geometry("540x880")
        self.minsize(500, 750)
        self.configure(fg_color=BRAND["bg_dark"])

        # Set icon if available
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.active_monitor = None
        self.monitor_name = ""
        self.is_monitoring = False
        self.countdown_active = False
        self.countdown_remaining = 0
        self.selected_action = ctk.StringVar(value="Shutdown")
        self.status_text = ctk.StringVar(value="Ready")
        self.detail_text = ctk.StringVar(value="")
        self.network_text = ctk.StringVar(value="")
        self.timer_display = ctk.StringVar(value="")

        self._build_ui()
        self._start_network_indicator()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_network_indicator(self):
        def loop():
            while True:
                ok = NetworkChecker.is_online()
                self.after(0, lambda o=ok: self._net_ui(o))
                time.sleep(10)
        threading.Thread(target=loop, daemon=True).start()

    def _net_ui(self, online):
        if online:
            self.network_text.set("Online")
            self.net_label.configure(text_color=BRAND["success"])
        else:
            self.network_text.set("Offline")
            self.net_label.configure(text_color=BRAND["danger"])

    def _build_ui(self):
        mf = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BRAND["border"],
            scrollbar_button_hover_color=BRAND["accent"],
        )
        mf.pack(fill="both", expand=True, padx=12, pady=12)
        self.mf = mf

        # Header
        hdr = ctk.CTkFrame(mf, fg_color=BRAND["bg_card"], corner_radius=12)
        hdr.pack(fill="x", pady=(0, 12))

        ht = ctk.CTkFrame(hdr, fg_color="transparent")
        ht.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(ht, text="SRJahir Tech", font=ctk.CTkFont(size=14, weight="bold"),
                      text_color=BRAND["accent"]).pack(side="left")
        self.net_label = ctk.CTkLabel(ht, textvariable=self.network_text,
                                       font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color=BRAND["success"])
        self.net_label.pack(side="right")

        ctk.CTkLabel(hdr, text="Power Manager v2.0",
                      font=ctk.CTkFont(size=26, weight="bold"),
                      text_color=BRAND["text"]).pack(anchor="w", padx=16, pady=(2, 2))
        ctk.CTkLabel(hdr, text="Network-Aware  |  Seeding Ignored  |  Smart Grace Periods",
                      font=ctk.CTkFont(size=11),
                      text_color=BRAND["text_dim"]).pack(anchor="w", padx=16, pady=(0, 4))

        sf = ctk.CTkFrame(hdr, fg_color="#1a2e1a", corner_radius=6)
        sf.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(sf, text="SAFE: Network drop = 10min wait | Seeding = still shuts down",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=BRAND["success"]).pack(padx=10, pady=6)

        # Action Selector
        ac = self._card("Power Action")
        af = ctk.CTkFrame(ac, fg_color="transparent")
        af.pack(fill="x", padx=16, pady=(0, 14))
        for a in ACTIONS:
            ctk.CTkRadioButton(
                af, text=a, variable=self.selected_action, value=a,
                font=ctk.CTkFont(size=13), text_color=BRAND["text"],
                fg_color=BRAND["accent"], hover_color=BRAND["accent_hover"],
                border_color=BRAND["border"],
            ).pack(anchor="w", pady=3)

        # Safety Settings
        gc = self._card("Safety Settings")
        gf = ctk.CTkFrame(gc, fg_color="transparent")
        gf.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(gf, text="Grace (min):", text_color=BRAND["text_dim"],
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.grace_entry = self._small_entry(gf, 50, str(self.config["grace_period_minutes"]))

        ctk.CTkLabel(gf, text="Re-checks:", text_color=BRAND["text_dim"],
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self.recheck_entry = self._small_entry(gf, 40, str(self.config["recheck_count"]))

        ctk.CTkLabel(gf, text="Net wait (min):", text_color=BRAND["text_dim"],
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self.net_wait_entry = self._small_entry(gf, 40, str(self.config["network_wait_minutes"]))

        ctk.CTkLabel(gc, text="Grace: wait after detection before acting. Net wait: how long to wait if network drops.\nSeeding is always ignored — only active downloads prevent shutdown.",
                      font=ctk.CTkFont(size=10), text_color=BRAND["text_muted"],
                      justify="left").pack(anchor="w", padx=16, pady=(4, 12))

        # Download Monitor
        dc = self._card("Browser Download Monitor")
        self._sub(dc, "Chrome | Brave | Edge | Firefox — network-pause safe")
        self.dl_entry = self._folder_row(dc, self.config["download_folder"])
        self._btn(dc, "Start Download Monitor", self._start_download)

        # File Copy/Move Monitor
        cc = self._card("File Copy / Move Monitor")
        self._sub(cc, "Watch any folder — acts when all files stop changing")
        self.cp_entry = self._folder_row(cc, self.config["monitor_folder"])
        self._btn(cc, "Start Copy/Move Monitor", self._start_copy)

        # Torrent Monitor
        tc = self._card("Torrent Monitor (uTorrent / qBittorrent)")
        self._sub(tc, "Seeding IGNORED — shuts down after downloads complete")

        if QBIT_AVAILABLE:
            qf = ctk.CTkFrame(tc, fg_color="transparent")
            qf.pack(fill="x", padx=16, pady=(0, 4))
            self.qh_entry = self._small_entry(qf, 140,
                f"{self.config['qbit_host']}:{self.config['qbit_port']}", "Host:Port")
            self.qu_entry = self._small_entry(qf, 80, self.config["qbit_user"], "User")
            self.qp_entry = self._small_entry(qf, 80, self.config["qbit_pass"], "Pass", show="*")

        self._btn(tc, "Start Torrent Monitor", self._start_torrent)

        # Timer
        tmc = self._card("Countdown Timer")
        self._sub(tmc, "Acts after set time — not network dependent")
        tmf = ctk.CTkFrame(tmc, fg_color="transparent")
        tmf.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(tmf, text="Minutes:", text_color=BRAND["text_dim"],
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        self.tm_entry = self._small_entry(tmf, 80, str(self.config["timer_minutes"]))
        ctk.CTkLabel(tmf, textvariable=self.timer_display,
                      font=ctk.CTkFont(size=18, weight="bold"),
                      text_color=BRAND["accent"]).pack(side="right", padx=8)
        self._btn(tmc, "Start Timer", self._start_timer)

        # Idle Monitor
        ic = self._card("System Idle Monitor")
        self._sub(ic, "CPU + Network idle for N minutes = action")
        idf = ctk.CTkFrame(ic, fg_color="transparent")
        idf.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(idf, text="Idle minutes:", text_color=BRAND["text_dim"],
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        self.idle_entry = self._small_entry(idf, 80, str(self.config["idle_minutes"]))
        self._btn(ic, "Start Idle Monitor", self._start_idle)

        # Status Bar
        sc = ctk.CTkFrame(mf, fg_color=BRAND["bg_card"], corner_radius=12)
        sc.pack(fill="x", pady=(4, 0))
        si = ctk.CTkFrame(sc, fg_color="transparent")
        si.pack(fill="x", padx=16, pady=10)
        sl = ctk.CTkFrame(si, fg_color="transparent")
        sl.pack(side="left", fill="x", expand=True)

        self.status_label = ctk.CTkLabel(sl, textvariable=self.status_text,
                                          font=ctk.CTkFont(size=13, weight="bold"),
                                          text_color=BRAND["success"])
        self.status_label.pack(anchor="w")
        self.detail_label = ctk.CTkLabel(sl, textvariable=self.detail_text,
                                          font=ctk.CTkFont(size=11),
                                          text_color=BRAND["text_dim"])
        self.detail_label.pack(anchor="w")

        self.stop_btn = ctk.CTkButton(
            si, text="STOP", width=90,
            fg_color=BRAND["danger"], hover_color=BRAND["danger_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._stop_all, state="disabled",
        )
        self.stop_btn.pack(side="right")

        ctk.CTkLabel(mf, text="2026 SRJahir Tech  |  srjahir.in  |  Made in India",
                      font=ctk.CTkFont(size=10),
                      text_color=BRAND["text_muted"]).pack(pady=(10, 4))

    # ── UI Helpers ────────────────────────────────

    def _card(self, title):
        c = ctk.CTkFrame(self.mf, fg_color=BRAND["bg_card"], corner_radius=12)
        c.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                      text_color=BRAND["text"]).pack(anchor="w", padx=16, pady=(12, 4))
        return c

    def _sub(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=11),
                      text_color=BRAND["text_dim"]).pack(anchor="w", padx=16, pady=(0, 8))

    def _small_entry(self, parent, width, default="", placeholder="", show=None):
        kw = {}
        if show:
            kw["show"] = show
        if placeholder:
            kw["placeholder_text"] = placeholder
        e = ctk.CTkEntry(parent, width=width, fg_color=BRAND["bg_dark"],
                          border_color=BRAND["border"], text_color=BRAND["text"],
                          font=ctk.CTkFont(size=12), **kw)
        e.pack(side="left", padx=(0, 6))
        if default:
            e.insert(0, default)
        return e

    def _folder_row(self, parent, default=""):
        fr = ctk.CTkFrame(parent, fg_color="transparent")
        fr.pack(fill="x", padx=16, pady=(0, 4))
        e = ctk.CTkEntry(fr, placeholder_text="Folder path",
                          fg_color=BRAND["bg_dark"], border_color=BRAND["border"],
                          text_color=BRAND["text"], font=ctk.CTkFont(size=12))
        e.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if default:
            e.insert(0, default)
        ctk.CTkButton(fr, text="Browse", width=60,
                       fg_color=BRAND["accent2"], hover_color=BRAND["accent2_hover"],
                       command=lambda: self._browse(e)).pack(side="right")
        return e

    def _btn(self, parent, text, cmd):
        ctk.CTkButton(parent, text=text, fg_color=BRAND["accent"],
                       hover_color=BRAND["accent_hover"],
                       font=ctk.CTkFont(size=13, weight="bold"),
                       height=36, corner_radius=8, command=cmd
                       ).pack(fill="x", padx=16, pady=(8, 14))

    def _browse(self, entry):
        from tkinter import filedialog
        f = filedialog.askdirectory()
        if f:
            entry.delete(0, "end")
            entry.insert(0, f)

    def _get_settings(self):
        try: grace = int(self.grace_entry.get().strip())
        except: grace = 2
        try: recheck = int(self.recheck_entry.get().strip())
        except: recheck = 3
        try: net_wait = int(self.net_wait_entry.get().strip())
        except: net_wait = 10
        self.config["grace_period_minutes"] = grace
        self.config["recheck_count"] = recheck
        self.config["network_wait_minutes"] = net_wait
        save_config(self.config)
        return grace, recheck, net_wait

    # ── Monitor Starters ─────────────────────────

    def _busy(self):
        if self.is_monitoring:
            self._set_status(f"Already monitoring: {self.monitor_name}", BRAND["warning"])
            return True
        return False

    def _set_status(self, t, c=None):
        self.status_text.set(t)
        self.status_label.configure(text_color=c or BRAND["success"])

    def _set_detail(self, t):
        self.detail_text.set(t)

    def _mon_cb(self, msg):
        self.after(0, lambda: self._set_detail(msg))

    def _activate(self, name):
        self.is_monitoring = True
        self.monitor_name = name
        self.stop_btn.configure(state="normal")
        self._set_status(f"Monitoring: {name}", BRAND["accent"])
        log_action(f"STARTED: {name} — Action: {self.selected_action.get()}")

    def _start_download(self):
        if self._busy(): return
        folder = self.dl_entry.get().strip()
        if not folder or not os.path.isdir(folder):
            self._set_status("Invalid Downloads folder!", BRAND["danger"]); return
        self.config["download_folder"] = folder
        save_config(self.config)
        g, r, n = self._get_settings()
        self.active_monitor = DownloadMonitor(folder, grace_minutes=g, recheck=r, net_wait_min=n)
        self.active_monitor.start(self._on_trigger, self._mon_cb)
        self._activate("Browser Downloads")

    def _start_copy(self):
        if self._busy(): return
        folder = self.cp_entry.get().strip()
        if not folder or not os.path.isdir(folder):
            self._set_status("Invalid folder!", BRAND["danger"]); return
        self.config["monitor_folder"] = folder
        save_config(self.config)
        g, r, n = self._get_settings()
        self.active_monitor = FolderMonitor(folder, grace_minutes=g, recheck=r, net_wait_min=n)
        self.active_monitor.start(self._on_trigger, self._mon_cb)
        self._activate("File Copy/Move")

    def _start_torrent(self):
        if self._busy(): return
        g, r, n = self._get_settings()
        kw = {"grace_minutes": g, "recheck": r, "net_wait_min": n}
        if QBIT_AVAILABLE:
            hp = self.qh_entry.get().strip()
            if ":" in hp:
                h, p = hp.rsplit(":", 1); p = int(p)
            else:
                h, p = hp, 8080
            kw.update(host=h, port=p, user=self.qu_entry.get().strip(),
                      password=self.qp_entry.get().strip())
        self.active_monitor = TorrentMonitor(**kw)
        self.active_monitor.start(self._on_trigger, self._mon_cb)
        self._activate("Torrent Downloads")

    def _start_timer(self):
        if self._busy(): return
        try: mins = int(self.tm_entry.get().strip())
        except: self._set_status("Enter valid minutes!", BRAND["danger"]); return
        self.config["timer_minutes"] = mins; save_config(self.config)
        self.active_monitor = TimerMonitor(mins)
        self.active_monitor.start(self._on_trigger, self._timer_tick)
        self._activate(f"Timer ({mins} min)")

    def _start_idle(self):
        if self._busy(): return
        try: mins = int(self.idle_entry.get().strip())
        except: self._set_status("Enter valid minutes!", BRAND["danger"]); return
        self.config["idle_minutes"] = mins; save_config(self.config)
        self.active_monitor = IdleMonitor(idle_minutes=mins)
        self.active_monitor.start(self._on_trigger, self._mon_cb)
        self._activate(f"System Idle ({mins} min)")

    # ── Callbacks ─────────────────────────────────

    def _on_trigger(self, reason):
        log_action(f"TRIGGERED: {reason}")
        self.after(0, self._countdown_start)

    def _timer_tick(self, rem):
        m, s = divmod(rem, 60)
        h, m = divmod(m, 60)
        d = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self.after(0, lambda: self.timer_display.set(d))

    def _countdown_start(self):
        self.countdown_active = True
        self.countdown_remaining = self.config["warning_seconds"]
        play_alert()
        self._set_status(f"{self.selected_action.get()} in {self.countdown_remaining}s — STOP to cancel!", BRAND["danger"])
        self._show_cd()

    def _show_cd(self):
        self.cdw = ctk.CTkToplevel(self)
        self.cdw.title("Action Incoming!")
        self.cdw.geometry("420x270")
        self.cdw.configure(fg_color=BRAND["bg_dark"])
        self.cdw.attributes("-topmost", True)
        self.cdw.resizable(False, False)

        ctk.CTkLabel(self.cdw, text="SRJahir Power Manager",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      text_color=BRAND["accent"]).pack(pady=(18, 6))
        ctk.CTkLabel(self.cdw, text=self.selected_action.get(),
                      font=ctk.CTkFont(size=24, weight="bold"),
                      text_color=BRAND["text"]).pack(pady=(0, 4))
        self.cd_label = ctk.CTkLabel(self.cdw,
                                      text=f"in {self.countdown_remaining} seconds...",
                                      font=ctk.CTkFont(size=18),
                                      text_color=BRAND["danger"])
        self.cd_label.pack(pady=(0, 6))
        ctk.CTkLabel(self.cdw, text="Network verified | All grace checks passed",
                      font=ctk.CTkFont(size=11),
                      text_color=BRAND["success"]).pack(pady=(0, 12))
        ctk.CTkButton(self.cdw, text="CANCEL — Keep PC ON",
                       fg_color=BRAND["danger"], hover_color=BRAND["danger_hover"],
                       font=ctk.CTkFont(size=15, weight="bold"),
                       height=44, width=280, command=self._cd_cancel).pack()
        self._cd_tick()

    def _cd_tick(self):
        if not self.countdown_active: return
        self.countdown_remaining -= 1
        if self.countdown_remaining <= 0:
            self._execute()
            try: self.cdw.destroy()
            except: pass
            return
        if self.countdown_remaining <= 10:
            play_alert()
        try: self.cd_label.configure(text=f"in {self.countdown_remaining} seconds...")
        except: pass
        self._set_status(f"{self.selected_action.get()} in {self.countdown_remaining}s — STOP!", BRAND["danger"])
        self.after(1000, self._cd_tick)

    def _cd_cancel(self):
        self.countdown_active = False
        cancel_shutdown()
        try: self.cdw.destroy()
        except: pass
        self._stop_all()
        self._set_status("Cancelled! PC is safe.", BRAND["success"])
        self._set_detail("")
        log_action("CANCELLED by user")

    def _execute(self):
        name = self.selected_action.get()
        fn = ACTIONS.get(name)
        self.countdown_active = False
        self.is_monitoring = False
        if fn:
            self._set_status(f"Executing: {name}...", BRAND["success"])
            log_action(f"EXECUTED: {name}")
            self.after(500, fn)

    def _stop_all(self):
        self.countdown_active = False
        self.is_monitoring = False
        self.timer_display.set("")
        if self.active_monitor:
            self.active_monitor.stop()
            self.active_monitor = None
        cancel_shutdown()
        self.stop_btn.configure(state="disabled")
        self._set_status("Stopped", BRAND["text_dim"])
        self._set_detail("")
        log_action("STOPPED by user")

    def _on_close(self):
        self._stop_all()
        self.destroy()


if __name__ == "__main__":
    app = PowerManagerApp()
    app.mainloop()
