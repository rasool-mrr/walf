# Windscribe Automatic Location Finder (WALF)

> 🌍 **[مطالعه به زبان فارسی (Farsi README)](README_FA.MD)**

[![Telegram Channel](https://img.shields.io/badge/Telegram-Channel-26A69A?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/CubicDreams)
[![Donate TRON](https://img.shields.io/badge/Donate-TRC20-red?style=for-the-badge&logo=tron&logoColor=white)](#-community--support)

**WALF** is an advanced, fully automated VPN benchmarking engine and exhaustive node discovery utility featuring a modern graphical user interface built with CustomTkinter. Operating as a high-powered automation wrapper for the native `windscribe-cli`, WALF completely eliminates the tedious process of manual server shifting by **systematically searching, scanning, and stress-testing every single server, city, and geographic location across Windscribe's global network.**

Instead of guessing which node works, WALF handles the heavy lifting through unattended network sweeping. It sequentially or randomly cycles through entire continents, countries, and individual server nodes back-to-back—testing them against various protocols and ports to pinpoint the exact paths that provide the highest performance.

Whether you are optimizing for ultra-low latency, benchmarking raw throughput, or trying to **completely bypass strict firewalls and heavy network censorship**, WALF automates the entire discovery pipeline and catalogs the real-time health of every location into a local database.

---

## 🚀 Key Features

* **Multi-Protocol & Multi-Port Sweeping:** Automatically tests connection combinations across WireGuard, IKEv2, UDP, TCP, Stealth, and WStunnel along with their corresponding default ports.
* **Granular Location Filtering:** Filter your execution queue by continent/region (including targeted US states), city, or specific server node using an accompanying data sheet.
* **Real-time Performance Benchmarking:** Seamlessly integrates with Speedtest APIs to fetch live network latency (Ping), download bandwidth, and upload speeds directly inside the application dashboard.
* **Advanced Execution Strategies:**
    * *Randomize Cities:* Shuffles your selected geographic locations while keeping your specified protocol order intact.
    * *Chaos Mode:* Shuffles the entire queue completely, testing arbitrary configurations of servers, ports, and protocols back-to-back.
    * *Stop on Success:* Instantly halts testing routines the moment a valid, functioning connection path is discovered—perfect for quick censorship-evasion setups.
* **Persistent Configuration & Profile Management:** Save custom testing parameter variations into discrete profiles to effortlessly load individual setups later.
* **Robust Logging & SQLite Storage:** Tracks every diagnostic test outcome locally inside an SQLite database file (`windscribe_results.db`) and offers a clean, filterable log interface alongside one-click CSV report exports.
* **Standalone Executable Support:** Fully compatible with compiled environments. The application handles headless stream redirections seamlessly when packaged as a standalone binary.

---

## 🛠️ Prerequisites

Before launching WALF, ensure your environment meets the following baseline criteria:

1. **Windscribe Desktop Client** must be installed with its Command Line Interface tools operational:
   * **Windows:** Installed at the default directory `C:\Program Files\Windscribe\windscribe-cli.exe`.
   * **Linux / macOS:** Ensure `windscribe-cli` is accessible globally within your user shell `$PATH` environments.
2. Ensure you have authenticated/logged into your Windscribe account through the native desktop app or terminal command line before executing automated loops.
3. *(Source Code Only)* **Python 3.8+** must be configured on your system environment paths if you choose to run the raw script instead of the pre-compiled executable.

---

## 📦 Download & Installation

### Option 1: Fast Setup (Recommended for Windows)
No Python installation or dependency configuration is required.
1. Head over to the **[GitHub Releases](../../releases)** page of this repository.
2. Download the latest `walf.zip` archive.
3. Extract the contents of `walf.zip` into your desired project folder.
4. Ensure your configuration asset (`cities_extended.csv`) is placed in that **same exact directory** alongside `walf.exe`.
5. Double-click `walf.exe` to launch the application immediately.

### Option 2: Running from Source Code
If you prefer running, modifying, or auditing the script manually, clone the repository and fetch the dependencies using the provided `requirements.txt`:

```bash
# Clone the repository
git clone [https://github.com/yourusername/walf.git](https://github.com/yourusername/walf.git)
cd walf

# Install python dependencies from requirements.txt
pip install -r requirements.txt
