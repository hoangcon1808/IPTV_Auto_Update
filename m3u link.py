import sys
import os

# --- ÉP XUẤT LOG NGAY LẬP TỨC ĐỂ DEBUG GITHUB ACTIONS ---
print("👉 [DEBUG] Đã nạp file script thành công. Chuẩn bị khởi chạy Modular System...", flush=True)

import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import threading
import json
from datetime import datetime

# --- FIX LỖI UNICODE TRÊN WINDOWS TERMINAL TẠI GITHUB ACTIONS ---
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- IMPORT MODULES ĐÃ ĐƯỢC TÁCH ---
from proxy_manager import check_local_ip_is_vn, test_cached_proxies, prepare_global_proxies
from core_scrapers import process_vtv_pipeline, process_tv360_pipeline
from m3u_generator import load_old_m3u_links, generate_m3u

# --- IMPORT CHO CHỨC NĂNG KHỞI ĐỘNG CÙNG WINDOWS ---
WIN32API_AVAILABLE = False
try:
    import win32api
    import win32con
    WIN32API_AVAILABLE = True
except ImportError:
    pass

CONFIG_FILE = "iptv_tool_config.json"
APP_NAME = "IPTV_AIO_Generator"

# --- CÁC HÀM QUẢN LÝ REGISTRY (KHỞI ĐỘNG CÙNG WIN) ---
def get_startup_registry_key():
    if not WIN32API_AVAILABLE: return None
    try:
        return win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, win32con.KEY_ALL_ACCESS)
    except Exception: return None

def add_to_startup():
    key = get_startup_registry_key()
    if not key: return False
    try:
        main_program_path = os.path.abspath(sys.argv[0])
        if main_program_path.lower().endswith('.exe'): command = f'"{main_program_path}" --startup'
        else: command = f'"{sys.executable}" "{main_program_path}" --startup'
            
        win32api.RegSetValueEx(key, APP_NAME, 0, win32con.REG_SZ, command)
        win32api.RegCloseKey(key)
        return True
    except Exception:
        if key: win32api.RegCloseKey(key)
        return False

def remove_from_startup():
    key = get_startup_registry_key()
    if not key: return False
    try:
        win32api.RegDeleteValue(key, APP_NAME)
        win32api.RegCloseKey(key)
        return True
    except FileNotFoundError:
        if key: win32api.RegCloseKey(key)
        return True
    except Exception:
        if key: win32api.RegCloseKey(key)
        return False

def is_in_startup():
    key = get_startup_registry_key()
    if not key: return False
    try:
        win32api.RegQueryValueEx(key, APP_NAME)
        win32api.RegCloseKey(key)
        return True
    except Exception:
        if key: win32api.RegCloseKey(key)
        return False

class AllInOneIPTVTool:
    def __init__(self, root, headless=False):
        self.headless = headless
        self.settings = self.load_settings()
        
        self.vn_proxies = [] 
        self.global_proxies_prepared = False
        
        # BIẾN THAY THẾ GLOBAL: Dùng biến instance để quản lý luồng Proxy
        self.use_auto_proxy = True
        if self.use_auto_proxy:
            if check_local_ip_is_vn(self.log):
                self.use_auto_proxy = False
        
        if self.headless:
            self.current_path = "vn.m3u"
        else:
            self.current_path = self.settings.get("path", "D:\\Tool\\vn.m3u")
            if not self.current_path: 
                self.current_path = "D:\\Tool\\vn.m3u"

        if not self.headless:
            self.root = root
            self.root.title("VTVGo & TV360 IPTV - All In One Generator (Modular)")
            self.root.geometry("850x500")

            tk.Label(root, text="Lưu file M3U tại:").grid(row=0, column=0, sticky="e", padx=5, pady=20)
            self.file_entry = tk.Entry(root, width=65)
            self.file_entry.grid(row=0, column=1, sticky="w", padx=5, pady=20)
            self.file_entry.insert(0, self.current_path)
            
            tk.Button(root, text="Chọn Thư Mục", command=self.browse_file).grid(row=0, column=1, sticky="e", padx=10)

            btn_frame = tk.Frame(root)
            btn_frame.grid(row=1, column=0, columnspan=2, pady=5)
            
            self.btn_manual = tk.Button(btn_frame, text="▶ BẮT ĐẦU QUÉT DATA & XUẤT FILE M3U", command=self.manual_update, bg="#87CEFA", font=("Arial", 11, "bold"), height=2, width=40)
            self.btn_manual.pack(pady=5)

            self.startup_var = tk.BooleanVar(value=is_in_startup())
            self.chk_startup = tk.Checkbutton(btn_frame, text="Khởi động cùng Windows (Tự động cập nhật ngầm)", variable=self.startup_var, command=self.toggle_startup)
            self.chk_startup.pack(pady=5)
            if not WIN32API_AVAILABLE:
                self.chk_startup.config(state="disabled", text="Khởi động cùng Windows (Cần cài pywin32)")

            tk.Label(root, text="Nhật ký hoạt động:").grid(row=2, column=0, sticky="w", padx=10)
            self.log_area = scrolledtext.ScrolledText(root, width=100, height=16, state='disabled', bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
            self.log_area.grid(row=3, column=0, columnspan=2, padx=10, pady=5)

            self.log("=== ALL IN ONE IPTV TOOL (MODULAR ARCHITECTURE) ===")
            self.log("✅ Chế độ: Đảo Proxy Vô hạn (Infinite Proxy Rotation) & Lùi 3 Bước.")
            self.log("✅ Chế độ: Timeout leo thang (60s -> 120s -> 240s) cho kênh cũ.")
            self.log("✅ Chế độ: Nhớ Proxy tốt nhất (Smart Caching Proxy) đang bật.")
            if self.use_auto_proxy:
                self.log("✅ Chế độ Auto-Scrape Proxy Đa Giao Thức từ ProxyScrape đang BẬT.")
            else:
                self.log("✅ Chế độ Auto-Proxy đang TẮT (IP Gốc là Việt Nam).")

    def get_file_path(self):
        if self.headless: return "vn.m3u"
        path = self.file_entry.get().strip()
        return path if path else "vn.m3u"

    def log(self, message):
        now = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{now}] {message}"
        print(formatted_message, flush=True) 
        if not self.headless and hasattr(self, 'log_area'):
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, formatted_message + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')

    def load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def save_settings(self):
        self.settings["path"] = self.get_file_path()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception: pass

    def browse_file(self):
        filename = filedialog.asksaveasfilename(defaultextension=".m3u", filetypes=[("M3U Playlist", "*.m3u")])
        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)
            self.save_settings() 

    def toggle_startup(self):
        if self.startup_var.get():
            if add_to_startup():
                messagebox.showinfo("Thành công", "Đã bật chức năng tự động chạy ngầm cập nhật M3U khi mở máy.")
                self.log("Đã BẬT Khởi động cùng Windows.")
            else:
                self.startup_var.set(False)
                messagebox.showerror("Lỗi", "Không thể thêm vào Registry. Hãy thử mở Tool bằng Run as Administrator.")
        else:
            if remove_from_startup():
                self.log("Đã TẮT Khởi động cùng Windows.")
            else:
                self.startup_var.set(True)

    def save_best_proxy(self, platform, proxy_stats):
        if proxy_stats:
            best_proxy_key = max(proxy_stats, key=proxy_stats.get)
            if proxy_stats[best_proxy_key] > 0:
                self.settings[f"{platform}_proxy"] = best_proxy_key
                self.save_settings()
                self.log(f"   💾 Tự động LƯU IP Tốt Nhất cho {platform.upper()}: {best_proxy_key} (Bắt thành công {proxy_stats[best_proxy_key]} link).")
                return
        self.settings[f"{platform}_proxy"] = ""
        self.save_settings()
        self.log(f"   🗑️ Không có IP nào bắt được link cho {platform.upper()}. Đã xoá Cache Proxy để lần sau làm mới toàn bộ.")

    def extract_all_data(self):
        alive_cached = test_cached_proxies(self.settings, self.log) if self.use_auto_proxy else {"vtv": None, "tv360": None}
            
        self.save_settings() 
        old_links_dict = load_old_m3u_links(self.get_file_path())
        exclude_proxies = set()
        
        # Chuẩn bị kho Proxy một lần duy nhất nếu cần
        if self.use_auto_proxy and not self.global_proxies_prepared:
            self.vn_proxies = prepare_global_proxies(self.log)
            self.global_proxies_prepared = True
        
        # Pipeline 1: VTV
        vtv_master, vtv_channels, vtv_proxy_stats = process_vtv_pipeline(old_links_dict, alive_cached, exclude_proxies, self.vn_proxies, self.use_auto_proxy, self.log)
        self.save_best_proxy("vtv", vtv_proxy_stats)
        
        # Pipeline 2: TV360
        tv360_channels, tv360_proxy_stats = process_tv360_pipeline(old_links_dict, alive_cached, exclude_proxies, self.vn_proxies, self.use_auto_proxy, self.log)
        self.save_best_proxy("tv360", tv360_proxy_stats)

        self.log("\n🛡️ HOÀN TẤT. XỬ LÝ FILE M3U...")
        master_channels_list = vtv_channels + tv360_channels

        # Xử lý Logic Fallback M3U cho kênh VTV nếu không lấy được Master Link
        if not vtv_master:
            for ch in master_channels_list:
                if ch['source'] == 'vtvgo_static' and not ch.get('skip'):
                    if ch['name'] in old_links_dict:
                        ch['source'] = 'fallback_only'
                        ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                        if not ch['logo'] and old_links_dict[ch['name']].get('logo'):
                            ch['logo'] = old_links_dict[ch['name']]['logo']
                    else: ch['skip'] = True 

        # Xử lý Logic chèn bù các kênh có trong M3U cũ nhưng không xuất hiện ở DOM mới
        current_channel_names = [ch['name'] for ch in master_channels_list]
        for old_name, old_data in old_links_dict.items():
            if old_name not in current_channel_names:
                master_channels_list.append({
                    'id': 'fallback_dom', 'name': old_name, 'logo': old_data.get('logo', ''),
                    'group_name': old_data.get('group', 'Khác'), 'source': 'fallback_only',
                    'url': '', 'm3u8_link': old_data['url'], 'error_msg': None, 'skip': False
                })

        return vtv_master, master_channels_list

    def run_update_process(self):
        if not self.headless: self.btn_manual.config(state="disabled")
        vtv_master, channels_data = self.extract_all_data()
        if channels_data:
            generate_m3u(vtv_master, channels_data, self.get_file_path(), self.vn_proxies, self.use_auto_proxy, self.log)
        if not self.headless: self.btn_manual.config(state="normal")

    def manual_update(self):
        threading.Thread(target=self.run_update_process, daemon=True).start()

    def run_update_process_headless(self):
        self.log("=== BẮT ĐẦU CHẠY NGẦM GITHUB (WIN MODE) ===")
        vtv_master, channels_data = self.extract_all_data()
        if channels_data:
            generate_m3u(vtv_master, channels_data, self.get_file_path(), self.vn_proxies, self.use_auto_proxy, self.log)
        self.log("=== KẾT THÚC CHẠY NGẦM ===")

print(f"👉 [DEBUG] Cờ startup truyền vào: {'--startup' in sys.argv}", flush=True)

if __name__ == "__main__":
    is_startup_mode = "--startup" in sys.argv
    if is_startup_mode:
        app = AllInOneIPTVTool(None, headless=True)
        app.run_update_process_headless()
        sys.exit(0)
    else:
        root = tk.Tk()
        app = AllInOneIPTVTool(root, headless=False)
        root.mainloop()