<p align="center">
  <img src="banner.png" alt="SRJahir Tech Power Manager" width="700">
</p>

<h1 align="center">SRJahir Tech Power Manager v2.0</h1>

<p align="center">
  <strong>Smart PC Power Management — Auto Shutdown, Restart, Sleep after Downloads, Copies & Torrents</strong>
</p>

<p align="center">
  <a href="https://srjahir.in">Website</a> •
  <a href="#features">Features</a> •
  <a href="#installation">Install</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#build-exe">Build EXE</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/Made%20in-India%20%F0%9F%87%AE%F0%9F%87%B3-orange" alt="Made in India">
</p>

---

## The Problem

You start a big download (torrent, browser, file copy) and want your PC to shut down when it's done. But:

- **Network drops** pause your download — other tools see this as "complete" and shut down your PC mid-download!
- **Torrent seeding** starts after download — other tools keep waiting forever because the torrent client is still "active"
- No way to know if a browser download actually finished or just paused

## The Solution

**SRJahir Power Manager** is network-aware and smart:

- ✅ **Network drops?** Waits 10 minutes for reconnect — never false triggers
- ✅ **Torrent seeding?** Ignored — PC shuts down when download is done, seeding doesn't matter
- ✅ **Grace period** — re-verifies 3 times before taking any action
- ✅ **Cancel button** — 30-second countdown with one-click cancel

---

## Features

### 5 Monitors

| Monitor | What It Does |
|---------|-------------|
| 📥 **Browser Downloads** | Watches for `.crdownload`, `.part`, `.tmp` files — acts when all finish |
| 🌊 **Torrent Downloads** | Monitors µTorrent Web / qBittorrent — **seeding is ignored** |
| 📋 **File Copy/Move** | Watches any folder — acts when files stop changing |
| ⏱️ **Countdown Timer** | Simple timer — set minutes, done |
| 💤 **System Idle** | CPU + Network idle for N minutes → action |

### 5 Power Actions

| Action | Description |
|--------|-------------|
| ⏻ Shutdown | Clean Windows shutdown |
| 🔄 Restart | Restart PC |
| 😴 Sleep | Put PC to sleep |
| ❄️ Hibernate | Hibernate (saves state to disk) |
| 🔒 Lock Screen | Lock Windows |

### Smart Safety

| Feature | Detail |
|---------|--------|
| 🌐 **Network-Aware** | Pings Google/Cloudflare/OpenDNS before any action |
| ⏳ **10 Min Network Wait** | If network drops, waits 10 min for reconnect |
| 🔄 **Grace Period** | After detection, waits 2 min + re-verifies 3x |
| 🚫 **Seeding Ignored** | Torrent seeding ≠ downloading — PC shuts down |
| 🔔 **Warning Popup** | 30-second countdown with CANCEL button |
| 🔊 **Sound Alert** | Beep alert in last 10 seconds |
| 📋 **Activity Log** | All actions logged to file |

---

## Installation

### Quick Start (Recommended)

1. Make sure [Python 3.8+](https://www.python.org/downloads/) is installed
2. Double-click **`setup_and_run.bat`** — installs dependencies + launches app

### Manual Install

```bash
# Install dependencies
pip install customtkinter psutil

# Optional: qBittorrent API support
pip install qbittorrent-api

# Run
python power_manager.py
```

### Download EXE (No Python Required)

Check the [Releases](../../releases) page for pre-built `.exe` file.

---

## How It Works

### Torrent Download Flow (µTorrent Web)

```
Start Monitoring
    ↓
Detect torrent client (utorrentweb.exe)
    ↓
Found .!ut files? → YES → Download active, keep watching
    ↓
.!ut files gone? → Download done (seeding started)
    ↓
Check Network → DOWN? → Wait 10 minutes for reconnect
                         ↓ Network back → Wait 30s for resume → Re-check
    ↓
Network UP → Grace Period (2 min)
    ↓
Re-verify 3 times (every 15s)
    ↓
All checks pass → 30s Warning Popup
    ↓
No cancel → Execute Action (Shutdown/Restart/Sleep)
```

### Browser Download Flow

```
Start Monitoring → Watch Downloads folder
    ↓
.crdownload file appears → Download active
    ↓
.crdownload disappears → Check network
    ↓
Network DOWN? → Download PAUSED (not done!)
               → Wait 10 min for reconnect
               → Network back → Browser auto-resumes → Continue watching
    ↓
Network UP? → Grace period + 3x verify → Countdown → Action
```

### Why Seeding is Ignored

Most tools treat "torrent client active" as "still downloading". But after a torrent finishes downloading, it starts **seeding** (uploading to others). You don't need your PC on just for seeding.

Power Manager checks specifically for **downloading** state:
- `.!ut` / `.!bt` incomplete files = still downloading
- No incomplete files + client running = seeding (ignored)
- qBittorrent API: checks `downloading` state, ignores `uploading/stalledUP`

---

## Build EXE

```bash
# Install PyInstaller
pip install pyinstaller

# Build single .exe with icon
pyinstaller --onefile --windowed --icon=app_icon.ico --name="SRJahir-Power-Manager" power_manager.py
```

The `.exe` will be in the `dist/` folder. Ship it with `app_icon.ico` for the best experience.

Or use the included build script:

```bash
build_exe.bat
```

---

## µTorrent Web Setup

Power Manager auto-detects µTorrent Web through:
1. **Process detection** — looks for `utorrentweb.exe`
2. **Incomplete files** — checks Downloads folder for `.!ut` files

No extra setup needed! Just start the monitor and begin your torrent download.

### qBittorrent Setup (Optional)

If you use qBittorrent, enable Web UI:
1. qBittorrent → Tools → Options → Web UI
2. Enable "Web User Interface"
3. Set username/password
4. Enter credentials in Power Manager

---

## Configuration

Settings auto-save to `~/.srjahir_power_manager.json`

| Setting | Default | Description |
|---------|---------|-------------|
| Grace Period | 2 min | Wait time after detection before grace checks |
| Re-checks | 3 | Number of verification passes |
| Network Wait | 10 min | How long to wait if network drops |
| Warning | 30 sec | Countdown before executing action |

Logs saved to: `~/srjahir_power_manager_log.txt`

---

## Supported Torrent Clients

- ✅ µTorrent Web
- ✅ µTorrent Classic
- ✅ qBittorrent (with API)
- ✅ BitTorrent
- ✅ Deluge
- ✅ Transmission
- ✅ Tixati
- ✅ Vuze
- ✅ aria2

## Supported Browsers

- ✅ Google Chrome (`.crdownload`)
- ✅ Brave (`.crdownload`)
- ✅ Microsoft Edge (`.partial`)
- ✅ Firefox (`.part`)
- ✅ Opera (`.crdownload`)

---

## Tech Stack

- **Python 3.8+** — Core logic
- **CustomTkinter** — Modern dark UI
- **psutil** — Process & system monitoring
- **qbittorrent-api** — Optional qBittorrent integration

---

## Contributing

Pull requests welcome! Please:
1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing`)
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE)

---

<p align="center">
  <strong>Built with ❤️ by <a href="https://srjahir.in">SRJahir Tech</a></strong><br>
  <sub>Cloud & DevOps Engineer</sub>
</p>
