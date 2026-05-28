import os
import sys

# PyInstaller --noconsole stream redirect fix
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import sqlite3
import csv
import subprocess
import time
import datetime
import threading
import platform
import os
import sys
import json
import speedtest
import random

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DEFAULT_PROTOCOLS = {
    "wireguard": [443, 80, 53, 123, 1194, 65142],
    "ikev2": [500],
    "udp": [443, 80, 53, 123, 1194, 54783],
    "tcp": [443, 587, 21, 22, 80, 123, 143, 3306, 8080, 54783, 1194],
    "stealth": [443, 587, 21, 22, 80, 123, 143, 3306, 8080, 54783, 8443],
    "wstunnel": [443]
}

if getattr(sys, 'frozen', False):
    APP_PATH = os.path.dirname(sys.executable)
else:
    APP_PATH = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(APP_PATH, "windscribe_results.db")
CONFIG_FILE = os.path.join(APP_PATH, "config.json")
CSV_FILE = os.path.join(APP_PATH, "cities_extended.csv")


# --- Config Manager ---
class ConfigManager:
    @staticmethod
    def load_config():
        default_data = {
            "saved_profiles": {},
            "last_settings": {
                "timeout": "25",
                "speed_wait": "5",
                "test_ping": False,
                "test_down": False,
                "test_up": False,
                "filter_continent": "All",
                "filter_city": "All",
                "filter_location": "All",
                "random_cities": False,
                "chaos_mode": False,
                "stop_on_success": False,
                "priority_order": list(DEFAULT_PROTOCOLS.keys()),
                "protocols": {}
            }
        }
        for proto, ports in DEFAULT_PROTOCOLS.items():
            default_data["last_settings"]["protocols"][proto] = {"enabled": True,
                                                                 "ports": {str(p): True for p in ports}}

        if not os.path.exists(CONFIG_FILE):
            return default_data

        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                if "saved_profiles" not in loaded: loaded["saved_profiles"] = {}
                if "last_settings" not in loaded: loaded["last_settings"] = default_data["last_settings"]
                # Ensure new keys exist
                ls = loaded["last_settings"]
                if "filter_location" not in ls: ls["filter_location"] = "All"
                if "random_cities" not in ls: ls["random_cities"] = False
                if "chaos_mode" not in ls: ls["chaos_mode"] = False
                if "stop_on_success" not in ls: ls["stop_on_success"] = False
                return loaded
        except Exception as e:
            print(f"Config Load Error: {e}")
            return default_data

    @staticmethod
    def save_config(data):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Config Save Error: {e}")


# --- Database Manager ---
class DatabaseManager:
    def __init__(self, app=None):
        self.app = app
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT,
                city TEXT,
                country TEXT,
                protocol TEXT,
                port INTEGER,
                status TEXT,
                duration REAL,
                ping REAL,
                download REAL,
                upload REAL,
                profile_name TEXT,
                timestamp TEXT,
                UNIQUE(location, city, country, protocol, port)
            )
        ''')
        self.conn.commit()

        try:
            self.cursor.execute("SELECT profile_name FROM tests LIMIT 1")
        except:
            if self.app: self.app.log_message("[DB] Migrating table columns...", "WARN")
            try:
                self.cursor.execute("ALTER TABLE tests ADD COLUMN profile_name TEXT")
            except:
                pass
            try:
                self.cursor.execute("ALTER TABLE tests RENAME COLUMN location_nickname TO location")
            except:
                pass
            try:
                self.cursor.execute("ALTER TABLE tests RENAME COLUMN region TO country")
            except:
                pass
            self.conn.commit()

    def record_result(self, location, city, country, proto, port, status, duration, ping, down, up, profile_name):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            duration = round(duration, 2)
            self.cursor.execute('''
                INSERT OR REPLACE INTO tests 
                (location, city, country, protocol, port, status, duration, ping, download, upload, profile_name, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (location, city, country, proto, port, status, duration, ping, down, up, profile_name, timestamp))
            self.conn.commit()
            return True
        except Exception as e:
            if self.app: self.app.log_message(f"DB ERROR: {e}", "FAILURE")
            return False

    def get_row_count(self):
        try:
            self.cursor.execute("SELECT COUNT(*) FROM tests")
            return self.cursor.fetchone()[0]
        except:
            return 0

    def is_tested(self, location, city, country, proto, port):
        self.cursor.execute(
            "SELECT 1 FROM tests WHERE location=? AND city=? AND country=? AND protocol=? AND port=?",
            (location, city, country, proto, port))
        return self.cursor.fetchone() is not None

    def export_to_csv(self, current_profile_name="Manual"):
        reports_dir = os.path.join(APP_PATH, "reports")
        if not os.path.exists(reports_dir):
            try:
                os.makedirs(reports_dir)
            except OSError as e:
                return -1, f"Failed to create directory: {e}"

        existing_files = os.listdir(reports_dir)
        max_id = 0
        for f in existing_files:
            if f.endswith(".csv"):
                parts = f.split('_')
                if parts and parts[0].isdigit():
                    try:
                        val = int(parts[0])
                        if val > max_id: max_id = val
                    except:
                        pass
        new_id = max_id + 1

        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_profile = "".join(
            [c for c in current_profile_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        if not safe_profile: safe_profile = "Manual"

        filename = f"{new_id}_{safe_profile}_{ts}.csv"
        csv_file = os.path.join(reports_dir, filename)

        self.cursor.execute("SELECT * FROM tests")
        rows = self.cursor.fetchall()
        headers = [description[0] for description in self.cursor.description]

        try:
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            return len(rows), csv_file
        except PermissionError:
            return -1, "File Open Error - Close the file if open."

    def clear_db(self):
        self.cursor.execute("DELETE FROM tests")
        self.conn.commit()


# --- Logic Worker ---
class WindscribeWorker:
    def __init__(self, app_instance):
        self.app = app_instance
        self.db = DatabaseManager(app=app_instance)
        self.stop_event = threading.Event()
        if platform.system() == "Windows":
            self.cli_cmd = r"C:\Program Files\Windscribe\windscribe-cli.exe"
        else:
            self.cli_cmd = "windscribe-cli"

    def log(self, msg, tag="INFO"):
        self.app.log_message(msg, tag)

    def update_dashboard(self, ping="-", down="-", up="-", status="Idle", progress=0.0):
        count = self.db.get_row_count()
        self.app.update_live_dashboard(ping, down, up, status, progress, count)

    def run_cli(self, args):
        cmd = [self.cli_cmd] + args
        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    startupinfo=startupinfo)
            return result.returncode, result.stdout
        except Exception as e:
            self.log(f"CLI Error: {e}", "FAILURE")
            return -1, ""

    def ensure_disconnected(self):
        # IMPROVED DISCONNECT LOGIC
        max_retries = 5
        for i in range(max_retries):
            code, out = self.run_cli(["status"])
            if "DISCONNECTED" in out.upper():
                return True

            # Attempt to force firewall off and disconnect
            self.run_cli(["firewall", "off"])
            self.run_cli(["disconnect"])
            time.sleep(3)  # Wait for CLI to process

        # Final Check
        code, out = self.run_cli(["status"])
        return "DISCONNECTED" in out.upper()

    def wait_for_connection(self, start_time, timeout):
        while time.time() - start_time < timeout:
            code, out = self.run_cli(["status"])
            if "CONNECTED" in out.upper() and "DISCONNECTED" not in out.upper():
                if "CONNECTING" not in out.upper():
                    duration = time.time() - start_time
                    return True, duration
            time.sleep(1)
            if self.stop_event.is_set(): return False, 0.0
        return False, 0.0

    def start(self, work_plan, resume, timeout, speed_wait, do_ping, do_down, do_up, filter_cont, filter_city,
              filter_location, random_cities, chaos_mode, stop_on_success, profile_name):
        self.stop_event.clear()
        threading.Thread(target=self._run,
                         args=(
                         work_plan, resume, timeout, speed_wait, do_ping, do_down, do_up, filter_cont, filter_city,
                         filter_location, random_cities, chaos_mode, stop_on_success, profile_name)).start()

    def stop(self):
        self.stop_event.set()
        self.log("Stopping...", "WARN")

    def _run(self, work_plan, resume, conn_timeout, speed_wait, do_ping, do_down, do_up, filter_cont, filter_city,
             filter_location, random_cities, chaos_mode, stop_on_success, profile_name):
        try:
            if not os.path.exists(CSV_FILE):
                self.log(f"{CSV_FILE} missing! Run convert_csv.py first.", "FAILURE")
                self.app.on_job_finish()
                return

            if not resume: self.db.clear_db()

            raw_locations = []
            with open(CSV_FILE, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, skipinitialspace=True)
                for row in reader:
                    if "City" in row:
                        raw_locations.append({
                            "city": row["City"].strip(),
                            "location": row.get("Location", "").strip(),
                            "country": row.get("Region", "").strip(),
                            "continent": row.get("Continent", "Unknown").strip()
                        })

            # --- 1. FILTERING ---
            locations = []
            skipped_count = 0

            for loc in raw_locations:
                # Region
                if filter_cont == "USA":
                    if "US " not in loc["country"]:
                        skipped_count += 1
                        continue
                elif filter_cont != "All":
                    if filter_cont != loc["continent"]:
                        skipped_count += 1
                        continue

                # City
                if filter_city != "All" and filter_city != loc["city"]:
                    skipped_count += 1
                    continue

                # Location
                if filter_location != "All" and filter_location != loc["location"]:
                    skipped_count += 1
                    continue

                locations.append(loc)

            # --- 2. RANDOMIZE CITIES (Normal Random) ---
            if random_cities:
                self.log("Randomizing CITY order...", "INFO")
                random.shuffle(locations)

            self.log(f"Queued {len(locations)} locations (Skipped {skipped_count})", "HEADER")

            # --- 3. BUILD ALL TASKS ---
            all_tasks = []
            for loc in locations:
                for proto, ports in work_plan.items():
                    for port in ports:
                        all_tasks.append((loc, proto, port))

            # --- 4. CHAOS MODE (Override Normal Random) ---
            if chaos_mode:
                self.log("CHAOS MODE: Randomizing ALL individual tests...", "WARN")
                random.shuffle(all_tasks)
            else:
                self.log(f"Sequential Mode (City Grouped): {len(all_tasks)} tests queued.", "INFO")

            # --- 5. EXECUTE ---
            for i, task in enumerate(all_tasks):
                if self.stop_event.is_set(): break

                loc_data, proto, port = task
                target_city = loc_data['city']
                location_name = loc_data['location']
                country = loc_data['country']

                # Resume Check
                if resume:
                    if self.db.is_tested(location_name, target_city, country, proto, port):
                        continue

                self.log("-" * 40, "INFO")
                self.log(f"Test {i + 1}/{len(all_tasks)}: {location_name} ({country}) -> {proto}:{port}", "HEADER")

                # *** CRITICAL: Ensure we are disconnected first ***
                if not self.ensure_disconnected():
                    self.log("ERROR: Could not disconnect. Skipping...", "FAILURE")
                    continue

                target_arg = f"{proto}:{port}"
                self.update_dashboard("-", "-", "-", f"Conn {target_city}...", 0.2)

                start_ts = time.time()
                self.run_cli(["connect", "-n", target_city, target_arg])

                # Small buffer for CLI to update
                time.sleep(1)

                _, status_out = self.run_cli(["status"])
                print(f"\n[DEBUG] {target_city} ({target_arg}):")
                print(status_out)
                print("-" * 40)

                # Skip Logic
                if "Location does not exist" in status_out or "is disabled" in status_out:
                    self.log(f"SKIPPING: {location_name} unavailable.", "FAILURE")
                    self.db.record_result(location_name, target_city, country, proto, port, "INVALID_LOC", 0, 0, 0, 0,
                                          "N/A")
                    continue

                connected, duration = self.wait_for_connection(start_ts, conn_timeout)
                ping, down, up, isp = 0, 0, 0, "N/A"
                status_str = "FAILURE"

                if connected:
                    status_str = "SUCCESS"
                    self.log(f"Connected in {duration:.2f}s", "SUCCESS")
                    self.app.add_success(f"{location_name} - {target_city} ({country}) | {proto}:{port}")

                    try:
                        self.update_dashboard("-", "-", "-", "Fetch ISP...", 0.3)
                        st = speedtest.Speedtest()
                        client_info = st.results.client
                        isp = client_info.get("isp", "Unknown")
                        self.log(f"ISP: {isp}", "INFO")
                    except:
                        isp = "Unknown"

                    if do_ping or do_down or do_up:
                        self.log(f"Waiting {speed_wait}s...", "INFO")
                        time.sleep(speed_wait)
                        if not self.stop_event.is_set():
                            try:
                                self.update_dashboard("-", "-", "-", "Finding Server...", 0.4)
                                st.get_best_server()
                                if do_ping:
                                    ping = st.results.ping
                                    self.update_dashboard(f"{ping:.0f}", "-", "-", "Ping...", 0.6)
                                if do_down:
                                    down = st.download() / 1_000_000
                                    self.update_dashboard(f"{ping:.0f}", f"{down:.1f}", "-", "Down...", 0.7)
                                if do_up:
                                    up = st.upload() / 1_000_000
                                    self.update_dashboard(f"{ping:.0f}", f"{down:.1f}", f"{up:.1f}", "Up...", 0.9)
                                self.log(f"P:{ping:.0f} D:{down:.1f} U:{up:.1f}", "INFO")
                            except Exception as ex:
                                self.log(f"Speedtest Error: {ex}", "WARN")
                else:
                    self.log(f"Timeout on {target_arg}", "FAILURE")

                self.db.record_result(location_name, target_city, country, proto, port, status_str, duration, ping,
                                      down, up, profile_name)
                self.update_dashboard(f"{ping:.0f}" if ping else "-", f"{down:.1f}" if down else "-",
                                      f"{up:.1f}" if up else "-", "Saved", 0)

                # Disconnect after job
                self.run_cli(["disconnect"])
                time.sleep(3)

                if connected and stop_on_success:
                    self.log("STOP ON SUCCESS ENABLED. Stopping job.", "WARN")
                    self.stop_event.set()
                    break

        except Exception as e:
            self.log(f"Critical Error: {e}", "FAILURE")
        finally:
            self.app.on_job_finish()


# --- Main App ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Windscribe Ultra Tester")
        self.geometry("1100x950")

        self.protocol_vars = {}
        self.port_vars = {}
        self.protocol_labels = {}
        self.config_data = ConfigManager.load_config()
        self.last_settings = self.config_data.get("last_settings", {})
        self.saved_profiles = self.config_data.get("saved_profiles", {})
        self.priority_order = self.last_settings.get("priority_order", list(DEFAULT_PROTOCOLS.keys()))

        self.is_log_fullscreen = False
        self.current_profile_name = "Manual"
        self.all_cities_list = ["All"]
        self.all_locations_list = ["All"]

        self.load_csv_data()
        self.init_vars()
        self.setup_ui()
        self.worker = WindscribeWorker(self)
        self.apply_config_to_ui()

    def load_csv_data(self):
        if os.path.exists(CSV_FILE):
            try:
                cities = set()
                locations = set()
                with open(CSV_FILE, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f, skipinitialspace=True)
                    for row in reader:
                        if "City" in row: cities.add(row["City"].strip())
                        if "Location" in row: locations.add(row["Location"].strip())
                self.all_cities_list = ["All"] + sorted(list(cities))
                self.all_locations_list = ["All"] + sorted(list(locations))
            except:
                self.all_cities_list = ["All", "Error"]
                self.all_locations_list = ["All", "Error"]
        else:
            self.all_cities_list = ["All", "CSV Missing"]
            self.all_locations_list = ["All", "CSV Missing"]

    def init_vars(self):
        saved_protocols = self.last_settings.get("protocols", {})
        for proto, ports in DEFAULT_PROTOCOLS.items():
            is_proto_enabled = saved_protocols.get(proto, {}).get("enabled", True)
            self.protocol_vars[proto] = ctk.BooleanVar(value=is_proto_enabled)
            self.port_vars[proto] = {}
            saved_ports = saved_protocols.get(proto, {}).get("ports", {})
            for port in ports:
                is_port_enabled = saved_ports.get(str(port), True)
                self.port_vars[proto][port] = ctk.BooleanVar(value=is_port_enabled)

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. Dashboard
        self.frame_dashboard = ctk.CTkFrame(self, fg_color="#1a1a1a", corner_radius=15)
        self.frame_dashboard.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        self.frame_dashboard.columnconfigure((0, 1, 2, 3), weight=1)

        self.lbl_ping_val = self.create_tile(self.frame_dashboard, 0, "PING (ms)", "-", "white")
        self.lbl_down_val = self.create_tile(self.frame_dashboard, 1, "DOWN (Mbps)", "-", "#3b8ed0")
        self.lbl_up_val = self.create_tile(self.frame_dashboard, 2, "UP (Mbps)", "-", "#a45ee5")
        self.lbl_count_val = self.create_tile(self.frame_dashboard, 3, "RESULTS", "0", "gray")

        self.lbl_status = ctk.CTkLabel(self.frame_dashboard, text="Ready", font=("Arial", 14))
        self.lbl_status.grid(row=2, column=0, columnspan=4, pady=5)
        self.progress_bar = ctk.CTkProgressBar(self.frame_dashboard)
        self.progress_bar.grid(row=3, column=0, columnspan=4, padx=20, pady=(0, 15), sticky="ew")
        self.progress_bar.set(0)

        # 2. Settings
        self.frame_settings = ctk.CTkFrame(self)
        self.frame_settings.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        # Config Row
        config_frame = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        config_frame.pack(side="top", fill="x", pady=5)
        ctk.CTkLabel(config_frame, text="Profile:", font=("Arial", 12)).pack(side="left", padx=10)

        self.combo_profiles = ctk.CTkComboBox(config_frame, values=list(self.saved_profiles.keys()), width=150,
                                              command=self.load_profile)
        self.combo_profiles.pack(side="left", padx=5)

        ctk.CTkButton(config_frame, text="Delete", command=self.delete_profile, width=60, fg_color="#800000").pack(
            side="left", padx=2)

        self.entry_save_name = ctk.CTkEntry(config_frame, placeholder_text="Profile Name", width=120)
        self.entry_save_name.pack(side="right", padx=5)
        ctk.CTkButton(config_frame, text="Save Config", command=self.save_current_profile, width=80).pack(side="right",
                                                                                                          padx=5)

        # Filters Row
        filter_frame = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        filter_frame.pack(side="top", fill="x", pady=5)

        # Region
        ctk.CTkLabel(filter_frame, text="Region:", font=("Arial", 12, "bold")).pack(side="left", padx=10)
        self.combo_continent = ctk.CTkComboBox(filter_frame,
                                               values=["All", "USA", "North America", "South America", "Europe", "Asia",
                                                       "Oceania", "Africa"],
                                               width=150)
        self.combo_continent.pack(side="left", padx=5)

        # City
        ctk.CTkLabel(filter_frame, text="City:", font=("Arial", 12, "bold")).pack(side="left", padx=10)
        self.combo_city = ctk.CTkComboBox(filter_frame, values=self.all_cities_list, width=150)
        self.combo_city.pack(side="left", padx=5)

        # Location
        ctk.CTkLabel(filter_frame, text="Location:", font=("Arial", 12, "bold")).pack(side="left", padx=10)
        self.combo_location = ctk.CTkComboBox(filter_frame, values=self.all_locations_list, width=150)
        self.combo_location.pack(side="left", padx=5)

        # Options Row
        options_frame = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        options_frame.pack(side="top", fill="x", pady=5)

        # TWO RANDOM OPTIONS
        self.chk_random_cities = ctk.CTkCheckBox(options_frame, text="Randomize Cities (Keep Protocol Order)")
        self.chk_random_cities.pack(side="left", padx=20)

        self.chk_random = ctk.CTkCheckBox(options_frame, text="Chaos Mode (Randomize All)")
        self.chk_random.pack(side="left", padx=20)

        self.chk_stop_success = ctk.CTkCheckBox(options_frame, text="Stop on Success")
        self.chk_stop_success.pack(side="left", padx=20)

        self.btn_clear_log = ctk.CTkButton(options_frame, text="Clear Log", command=self.clear_logs, fg_color="#444444",
                                           width=80)
        self.btn_clear_log.pack(side="right", padx=20)

        # Params Row
        param_frame = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        param_frame.pack(side="top", fill="x", pady=5)
        ctk.CTkLabel(param_frame, text="Timeout (s):", font=("Arial", 12, "bold")).pack(side="left", padx=10)
        self.entry_timeout = ctk.CTkEntry(param_frame, width=50)
        self.entry_timeout.pack(side="left")
        ctk.CTkLabel(param_frame, text="Wait (s):", font=("Arial", 12, "bold")).pack(side="left", padx=10)
        self.entry_speed_wait = ctk.CTkEntry(param_frame, width=50)
        self.entry_speed_wait.pack(side="left")
        self.chk_ping = ctk.CTkCheckBox(param_frame, text="Ping")
        self.chk_ping.pack(side="right", padx=10)
        self.chk_up = ctk.CTkCheckBox(param_frame, text="Upload")
        self.chk_up.pack(side="right", padx=10)
        self.chk_down = ctk.CTkCheckBox(param_frame, text="Download")
        self.chk_down.pack(side="right", padx=10)

        # 3. Config Tabs
        self.tab_config = ctk.CTkTabview(self, height=200)
        self.tab_config.grid(row=2, column=0, padx=20, pady=5, sticky="nsew")
        self.tab_config.add("Configuration")
        self.tab_config.add("Priority Order")
        self.setup_config_tab(self.tab_config.tab("Configuration"))
        self.setup_priority_tab(self.tab_config.tab("Priority Order"))

        # 4. LOGS AREA (Tabs)
        self.frame_logs_container = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_logs_container.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")

        self.btn_maximize = ctk.CTkButton(self.frame_logs_container, text="⛶ Maximize Logs",
                                          command=self.toggle_log_fullscreen,
                                          fg_color="#2b2b2b", hover_color="#444", height=24, width=120)
        self.btn_maximize.pack(side="top", anchor="e", pady=(0, 2))

        self.log_tabview = ctk.CTkTabview(self.frame_logs_container)
        self.log_tabview.pack(fill="both", expand=True)
        self.log_tabview.add("All Logs")
        self.log_tabview.add("Success List")

        self.log_box = tk.Text(self.log_tabview.tab("All Logs"), bg="#2b2b2b", fg="white", font=("Consolas", 10),
                               relief="flat")
        self.log_box.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_box.tag_config("SUCCESS", foreground="#2cc985")
        self.log_box.tag_config("FAILURE", foreground="#ff4d4d")
        self.log_box.tag_config("WARN", foreground="orange")
        self.log_box.tag_config("HEADER", foreground="#3b8ed0", font=("Consolas", 10, "bold"))
        self.log_box.tag_config("INFO", foreground="#dce4ee")

        self.txt_success = tk.Text(self.log_tabview.tab("Success List"), bg="#2b2b2b", fg="#2cc985",
                                   font=("Consolas", 11), relief="flat")
        self.txt_success.pack(fill="both", expand=True, padx=5, pady=5)

        # 5. Buttons
        self.frame_actions = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_actions.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.btn_fresh = ctk.CTkButton(self.frame_actions, text="Start FRESH", command=self.start_fresh,
                                       fg_color="green", height=40)
        self.btn_fresh.pack(side="left", padx=5, expand=True, fill="x")
        self.btn_continue = ctk.CTkButton(self.frame_actions, text="CONTINUE", command=self.start_continue,
                                          fg_color="#1f6aa5", height=40)
        self.btn_continue.pack(side="left", padx=5, expand=True, fill="x")
        self.btn_stop = ctk.CTkButton(self.frame_actions, text="STOP", command=self.stop_job, fg_color="red",
                                      state="disabled", height=40)
        self.btn_stop.pack(side="left", padx=5, expand=True, fill="x")
        self.btn_export = ctk.CTkButton(self.frame_actions, text="Export CSV", command=self.export_csv, fg_color="gray",
                                        height=40)
        self.btn_export.pack(side="left", padx=5, expand=True, fill="x")

    def toggle_log_fullscreen(self):
        if not self.is_log_fullscreen:
            self.frame_dashboard.grid_remove()
            self.frame_settings.grid_remove()
            self.tab_config.grid_remove()
            self.frame_actions.grid_remove()
            self.btn_maximize.configure(text="⬇ Restore View", fg_color="green")
            self.is_log_fullscreen = True
        else:
            self.frame_dashboard.grid()
            self.frame_settings.grid()
            self.tab_config.grid()
            self.frame_actions.grid()
            self.btn_maximize.configure(text="⛶ Maximize Logs", fg_color="#2b2b2b")
            self.is_log_fullscreen = False

    def apply_config_to_ui(self):
        self.entry_timeout.delete(0, "end")
        self.entry_timeout.insert(0, str(self.last_settings.get("timeout", "25")))
        self.entry_speed_wait.delete(0, "end")
        self.entry_speed_wait.insert(0, str(self.last_settings.get("speed_wait", "5")))

        if self.last_settings.get("test_ping", False):
            self.chk_ping.select()
        else:
            self.chk_ping.deselect()
        if self.last_settings.get("test_down", False):
            self.chk_down.select()
        else:
            self.chk_down.deselect()
        if self.last_settings.get("test_up", False):
            self.chk_up.select()
        else:
            self.chk_up.deselect()

        if self.last_settings.get("random_cities", False):
            self.chk_random_cities.select()
        else:
            self.chk_random_cities.deselect()
        if self.last_settings.get("chaos_mode", False):
            self.chk_random.select()
        else:
            self.chk_random.deselect()
        if self.last_settings.get("stop_on_success", False):
            self.chk_stop_success.select()
        else:
            self.chk_stop_success.deselect()

        self.combo_continent.set(self.last_settings.get("filter_continent", "All"))
        self.combo_city.set(self.last_settings.get("filter_city", "All"))
        self.combo_location.set(self.last_settings.get("filter_location", "All"))

    def gather_config_data(self):
        data = {
            "timeout": self.entry_timeout.get(),
            "speed_wait": self.entry_speed_wait.get(),
            "test_ping": bool(self.chk_ping.get()),
            "test_down": bool(self.chk_down.get()),
            "test_up": bool(self.chk_up.get()),
            "filter_continent": self.combo_continent.get(),
            "filter_city": self.combo_city.get(),
            "filter_location": self.combo_location.get(),
            "random_cities": bool(self.chk_random_cities.get()),
            "chaos_mode": bool(self.chk_random.get()),
            "stop_on_success": bool(self.chk_stop_success.get()),
            "priority_order": self.priority_order,
            "protocols": {}
        }
        for proto, p_var in self.protocol_vars.items():
            ports_data = {str(p): bool(v.get()) for p, v in self.port_vars[proto].items()}
            data["protocols"][proto] = {"enabled": bool(p_var.get()), "ports": ports_data}
        return data

    def save_current_profile(self):
        name = self.entry_save_name.get().strip()
        if not name:
            name = self.combo_profiles.get().strip()

        if not name:
            tk.messagebox.showerror("Error", "Please enter a profile name.")
            return

        current_settings = self.gather_config_data()
        self.saved_profiles[name] = current_settings
        self.config_data["saved_profiles"] = self.saved_profiles
        self.config_data["last_settings"] = current_settings
        ConfigManager.save_config(self.config_data)

        self.combo_profiles.configure(values=list(self.saved_profiles.keys()))
        self.combo_profiles.set(name)
        self.current_profile_name = name
        tk.messagebox.showinfo("Saved", f"Profile '{name}' saved.")

    def load_profile(self, choice=None):
        name = choice if choice else self.combo_profiles.get()
        if name in self.saved_profiles:
            profile = self.saved_profiles[name]
            self.last_settings = profile
            self.apply_config_to_ui()
            self.current_profile_name = name

            for proto, settings in profile.get("protocols", {}).items():
                if proto in self.protocol_vars:
                    self.protocol_vars[proto].set(settings.get("enabled", True))
                    for port, enabled in settings.get("ports", {}).items():
                        if port in self.port_vars[proto]:
                            self.port_vars[proto][port].set(enabled)

            self.priority_order = profile.get("priority_order", list(DEFAULT_PROTOCOLS.keys()))
            self.refresh_priority_list()
            self.log_message(f"Loaded profile: {name}", "INFO")

    def delete_profile(self):
        name = self.combo_profiles.get()
        if name in self.saved_profiles:
            if tk.messagebox.askyesno("Delete", f"Delete profile '{name}'?"):
                del self.saved_profiles[name]
                self.config_data["saved_profiles"] = self.saved_profiles
                ConfigManager.save_config(self.config_data)

                profiles = list(self.saved_profiles.keys())
                self.combo_profiles.configure(values=profiles)
                if profiles:
                    self.combo_profiles.set(profiles[0])
                else:
                    self.combo_profiles.set("")
                self.log_message(f"Deleted profile: {name}", "WARN")

    def create_tile(self, parent, col, title, initial, color):
        ctk.CTkLabel(parent, text=title, font=("Arial", 12, "bold"), text_color="gray").grid(row=0, column=col,
                                                                                             pady=(10, 0))
        lbl = ctk.CTkLabel(parent, text=initial, font=("Arial", 30, "bold"), text_color=color)
        lbl.grid(row=1, column=col, pady=(0, 10))
        return lbl

    def update_live_dashboard(self, ping, down, up, status, progress, count):
        self.lbl_ping_val.configure(text=str(ping))
        self.lbl_down_val.configure(text=str(down))
        self.lbl_up_val.configure(text=str(up))
        self.lbl_count_val.configure(text=str(count))
        self.lbl_status.configure(text=status)
        self.progress_bar.set(progress)
        if ping != "-" and str(ping).replace('.', '').isdigit():
            p = float(ping)
            if p < 50:
                self.lbl_ping_val.configure(text_color="#2cc985")
            elif p < 100:
                self.lbl_ping_val.configure(text_color="orange")
            else:
                self.lbl_ping_val.configure(text_color="#ff4d4d")

    def add_success(self, msg):
        ts = datetime.datetime.now().strftime("[%H:%M] ")
        self.txt_success.configure(state="normal")
        self.txt_success.insert("end", ts + msg + "\n")
        self.txt_success.see("end")
        self.txt_success.configure(state="disabled")

    def setup_config_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True)
        row = 0
        for proto in DEFAULT_PROTOCOLS.keys():
            chk = ctk.CTkCheckBox(scroll, text=proto.upper(), variable=self.protocol_vars[proto])
            chk.grid(row=row, column=0, padx=10, pady=5, sticky="w")
            btn = ctk.CTkButton(scroll, text="Select Ports", width=100,
                                command=lambda p=proto: self.open_port_dialog(p))
            btn.grid(row=row, column=1, padx=20, pady=5, sticky="e")
            self.update_summary(proto)
            row += 1

    def setup_priority_tab(self, parent):
        self.priority_container = ctk.CTkScrollableFrame(parent)
        self.priority_container.pack(fill="both", expand=True)
        self.refresh_priority_list()

    def refresh_priority_list(self):
        for widget in self.priority_container.winfo_children(): widget.destroy()
        for i, proto in enumerate(self.priority_order):
            f = ctk.CTkFrame(self.priority_container, fg_color="transparent")
            f.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(f, text=f"{i + 1}. {proto.upper()}", font=("Arial", 12, "bold"), width=150, anchor="w").pack(
                side="left", padx=10)
            if i < len(self.priority_order) - 1:
                ctk.CTkButton(f, text="⬇", width=30, command=lambda p=proto: self.move_down(p)).pack(side="right",
                                                                                                     padx=2)
            if i > 0:
                ctk.CTkButton(f, text="⬆", width=30, command=lambda p=proto: self.move_up(p)).pack(side="right", padx=2)

    def move_up(self, proto):
        idx = self.priority_order.index(proto)
        if idx > 0:
            self.priority_order[idx], self.priority_order[idx - 1] = self.priority_order[idx - 1], self.priority_order[
                idx]
            self.refresh_priority_list()

    def move_down(self, proto):
        idx = self.priority_order.index(proto)
        if idx < len(self.priority_order) - 1:
            self.priority_order[idx], self.priority_order[idx + 1] = self.priority_order[idx + 1], self.priority_order[
                idx]
            self.refresh_priority_list()

    def open_port_dialog(self, proto):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"{proto.upper()} Ports")
        dialog.geometry("300x400")
        dialog.attributes("-topmost", True)
        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        for port, var in self.port_vars[proto].items():
            cb = ctk.CTkCheckBox(scroll, text=str(port), variable=var)
            cb.pack(anchor="w", pady=2)
        ctk.CTkButton(dialog, text="Done", command=lambda: [self.update_summary(proto), dialog.destroy()]).pack(pady=10)

    def update_summary(self, proto):
        active = sum(1 for v in self.port_vars[proto].values() if v.get())
        total = len(self.port_vars[proto])
        txt = "All ports selected" if active == total else f"{active} ports selected" if active > 0 else "None selected"
        if proto in self.protocol_labels: self.protocol_labels[proto].configure(text=txt)

    def log_message(self, msg, tag):
        ts = datetime.datetime.now().strftime("[%H:%M:%S] ")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", ts + msg + "\n", tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.txt_success.configure(state="normal")
        self.txt_success.delete("1.0", "end")
        self.txt_success.configure(state="disabled")

    def get_plan(self):
        plan = {}
        for proto in self.priority_order:
            if self.protocol_vars[proto].get():
                ports = [p for p, v in self.port_vars[proto].items() if v.get()]
                if ports: plan[proto] = ports
        return plan

    def start_fresh(self):
        self.start_job(False)

    def start_continue(self):
        self.start_job(True)

    def start_job(self, resume):
        plan = self.get_plan()
        if not plan: return
        try:
            to, sw = int(self.entry_timeout.get()), int(self.entry_speed_wait.get())
        except:
            to, sw = 20, 5

        current_settings = self.gather_config_data()
        self.config_data["last_settings"] = current_settings
        ConfigManager.save_config(self.config_data)

        self.btn_fresh.configure(state="disabled")
        self.btn_continue.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        profile_name = self.entry_save_name.get().strip() or self.combo_profiles.get().strip() or "Manual"

        self.worker.start(plan, resume, to, sw,
                          self.chk_ping.get(),
                          self.chk_down.get(),
                          self.chk_up.get(),
                          self.combo_continent.get(),
                          self.combo_city.get(),
                          self.combo_location.get(),
                          bool(self.chk_random_cities.get()),
                          bool(self.chk_random.get()),
                          bool(self.chk_stop_success.get()),
                          profile_name)

    def stop_job(self):
        self.worker.stop()
        self.btn_stop.configure(state="disabled")

    def on_job_finish(self):
        self.after(0, self._reset_btns)

    def _reset_btns(self):
        self.btn_fresh.configure(state="normal")
        self.btn_continue.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.log_message("Job Finished.", "HEADER")
        self.update_live_dashboard("-", "-", "-", "Ready", 0, self.worker.db.get_row_count())

    def export_csv(self):
        count, path = self.worker.db.export_to_csv(self.current_profile_name)
        if count == -1:
            tk.messagebox.showerror("Error", f"Could not save CSV.\n{path}")
        else:
            tk.messagebox.showinfo("Export", f"Exported {count} rows.\nSaved to:\n{path}")


if __name__ == "__main__":
    app = App()
    app.mainloop()