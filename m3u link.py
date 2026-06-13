import sys
import os

# --- ÉP XUẤT LOG NGAY LẬP TỨC ĐỂ DEBUG GITHUB ACTIONS ---
print("👉 [DEBUG] Đã nạp file script thành công. Chuẩn bị import thư viện...", flush=True)

import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import threading
import time
import json
import re
import urllib.request
import requests
import concurrent.futures
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# =========================================================
# CẤU HÌNH TỰ ĐỘNG CÀO PROXY VIỆT NAM
# =========================================================
USE_AUTO_VN_PROXY = True 
# =========================================================

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
        return win32api.RegOpenKeyEx(
            win32con.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            win32con.KEY_ALL_ACCESS
        )
    except Exception: return None

def add_to_startup():
    key = get_startup_registry_key()
    if not key: return False
    try:
        main_program_path = os.path.abspath(sys.argv[0])
        if main_program_path.lower().endswith('.exe'):
            command = f'"{main_program_path}" --startup'
        else:
            python_interpreter_path = sys.executable
            command = f'"{python_interpreter_path}" "{main_program_path}" --startup'
            
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
        
        global USE_AUTO_VN_PROXY
        if USE_AUTO_VN_PROXY:
            if self._check_local_ip_is_vn():
                USE_AUTO_VN_PROXY = False
        
        if self.headless:
            self.current_path = "vn.m3u"
            self.vtvprime_cookie = self.settings.get("vtvprime_cookie", "")
        else:
            self.current_path = self.settings.get("path", "D:\\Tool\\vn.m3u")
            if not self.current_path: 
                self.current_path = "D:\\Tool\\vn.m3u"

        if not self.headless:
            self.root = root
            self.root.title("VTVGo, TV360 & VTVPrime IPTV - All In One Generator")
            self.root.geometry("850x550")

            # M3U Path Entry
            tk.Label(root, text="Lưu file M3U tại:").grid(row=0, column=0, sticky="e", padx=5, pady=10)
            self.file_entry = tk.Entry(root, width=65)
            self.file_entry.grid(row=0, column=1, sticky="w", padx=5, pady=10)
            self.file_entry.insert(0, self.current_path)
            tk.Button(root, text="Chọn Thư Mục", command=self.browse_file).grid(row=0, column=1, sticky="e", padx=10)

            # VTV Prime Cookie Entry
            tk.Label(root, text="Cookie VTV Prime (Tùy chọn):").grid(row=1, column=0, sticky="e", padx=5, pady=5)
            self.cookie_entry = tk.Entry(root, width=65)
            self.cookie_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)
            self.cookie_entry.insert(0, self.settings.get("vtvprime_cookie", ""))

            btn_frame = tk.Frame(root)
            btn_frame.grid(row=2, column=0, columnspan=2, pady=5)
            
            self.btn_manual = tk.Button(btn_frame, text="▶ BẮT ĐẦU QUÉT DATA & XUẤT FILE M3U", command=self.manual_update, bg="#87CEFA", font=("Arial", 11, "bold"), height=2, width=40)
            self.btn_manual.pack(pady=5)

            self.startup_var = tk.BooleanVar(value=is_in_startup())
            self.chk_startup = tk.Checkbutton(btn_frame, text="Khởi động cùng Windows (Tự động cập nhật ngầm)", variable=self.startup_var, command=self.toggle_startup)
            self.chk_startup.pack(pady=5)
            if not WIN32API_AVAILABLE:
                self.chk_startup.config(state="disabled", text="Khởi động cùng Windows (Cần cài pywin32)")

            tk.Label(root, text="Nhật ký hoạt động:").grid(row=3, column=0, sticky="w", padx=10)
            self.log_area = scrolledtext.ScrolledText(root, width=100, height=15, state='disabled', bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
            self.log_area.grid(row=4, column=0, columnspan=2, padx=10, pady=5)

            self.log("=== ALL IN ONE IPTV TOOL ===")
            self.log("✅ Chế độ: Đảo Proxy Vô hạn (Infinite Proxy Rotation) & Lùi 3 Bước.")
            self.log("✅ Chế độ: Timeout leo thang (60s -> 120s -> 240s) cho kênh cũ.")
            self.log("✅ Chế độ: Nhớ Proxy tốt nhất (Smart Caching Proxy) đang bật.")
            if USE_AUTO_VN_PROXY:
                self.log("✅ Chế độ Auto-Scrape Proxy Đa Giao Thức từ ProxyScrape đang BẬT.")
            else:
                self.log("✅ Chế độ Auto-Proxy đang TẮT (IP Gốc là Việt Nam).")

    def _check_local_ip_is_vn(self):
        print("\n[INIT] 🔎 Đang kiểm tra IP gốc của máy...", flush=True)
        try:
            res = requests.get("http://ip-api.com/json/", timeout=5).json()
            if res.get("countryCode") == "VN":
                print(f"   -> 🇻🇳 IP gốc của bạn là Việt Nam ({res.get('query')}). BỎ QUA VPN/PROXY để chạy tốc độ tối đa!", flush=True)
                return True
            else:
                print(f"   -> 🌍 IP gốc là {res.get('countryCode')} ({res.get('query')}). Sẽ kích hoạt cào Proxy Việt Nam.", flush=True)
                return False
        except Exception as e:
            print(f"   -> ⚠️ Lỗi check IP: {e}. Mặc định sẽ sử dụng Proxy.", flush=True)
            return False

    def get_file_path(self):
        if self.headless:
            return "vn.m3u"
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
        if not self.headless:
            self.settings["vtvprime_cookie"] = self.cookie_entry.get().strip()
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

    def _create_driver(self, proxy_ip=None, protocol="http"):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--log-level=3") 
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        if proxy_ip:
            chrome_options.add_argument(f'--proxy-server={protocol}://{proxy_ip}')
                
        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def _reboot_driver(self, driver, proxy_ip=None, protocol="http"):
        if driver:
            try:
                driver.execute_cdp_cmd('Network.clearBrowserCache', {})
                driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
                driver.quit()
            except: pass
        return self._create_driver(proxy_ip, protocol)

    def _add_cookies_to_driver(self, driver, cookie_string, domain):
        if not cookie_string: return
        for item in cookie_string.split(';'):
            if '=' in item:
                name, value = item.strip().split('=', 1)
                try:
                    driver.add_cookie({'name': name, 'value': value, 'domain': domain})
                except: pass

    def _test_proxy_ping(self, ip_port, target_url, protocol="http"):
        try:
            proxies = {
                "http": f"{protocol}://{ip_port}",
                "https": f"{protocol}://{ip_port}"
            }
            start_time = time.time()
            req = requests.get(target_url, proxies=proxies, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            if req.status_code == 200:
                return time.time() - start_time
            return None
        except requests.exceptions.InvalidSchema:
            return None
        except Exception:
            return None

    def _test_cached_proxies(self):
        self.log("\n[GIAI ĐOẠN 0] 🔎 KIỂM TRA PROXY CŨ ĐÃ LƯU TRONG CONFIG...")
        alive_proxies = {"vtv": None, "tv360": None, "vtvprime": None}
        
        for platform in ["vtv", "tv360", "vtvprime"]:
            cache_str = self.settings.get(f"{platform}_proxy")
            if cache_str:
                self.log(f"   -> Test {platform.upper()} Proxy cũ: {cache_str}")
                
                if "://" in cache_str:
                    protocol, ip_port = cache_str.split("://")
                else:
                    protocol, ip_port = "http", cache_str
                    
                target = "https://vtvgo.vn" if platform == "vtv" else ("https://tv360.vn" if platform == "tv360" else "https://vtvprime.vn")
                ping = self._test_proxy_ping(ip_port, target, protocol)
                
                if ping is not None:
                    self.log(f"      ✅ Sống (Ping: {ping:.2f}s)")
                    alive_proxies[platform] = {"ip": ip_port, "protocol": protocol}
                else:
                    self.log("      ❌ Đã chết.")
                    
        return alive_proxies

    def _prepare_global_proxies(self):
        if not USE_AUTO_VN_PROXY: return
        self.log("\n[GIAI ĐOẠN 1] 🔎 TẢI DANH SÁCH PROXY TỪ PROXYSCRAPE (ĐÃ LỌC SẴN IP VIỆT NAM)...")
        
        raw_pool = []
        sources = [
            ("http", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=ipport&format=text&protocol=http&anonymity=elite&country=vn&timeout=10000"),
            ("socks5", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=ipport&format=text&protocol=socks5&anonymity=elite&country=vn&timeout=10000"),
            ("socks4", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=ipport&format=text&protocol=socks4&anonymity=elite&country=vn&timeout=10000")
        ]
        
        for protocol, url in sources:
            try:
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if res.status_code == 200:
                    data = res.text
                    count = 0
                    for line in data.split('\n'):
                        ip_port = line.strip()
                        if ip_port:
                            raw_pool.append({'ip': ip_port, 'protocol': protocol})
                            count += 1
                    self.log(f"      [Tải File] ProxyScrape {protocol.upper()}: Lấy được {count} IPs.")
            except Exception as e: 
                self.log(f"      [Lỗi] Không tải được file {protocol}: {e}")

        unique_proxies = {}
        for p in raw_pool:
            if p['ip'] not in unique_proxies:
                unique_proxies[p['ip']] = p['protocol']

        self.vn_proxies = [{'ip': ip, 'protocol': protocol} for ip, protocol in unique_proxies.items()]
        self.log(f"   [Hoàn tất Tiền Xử Lý] Kho đạn có {len(self.vn_proxies)} IP chuẩn Việt Nam (Bỏ qua bước quét Geo do API đã lọc chuẩn).")
        self.global_proxies_prepared = True

    def _get_best_proxy_for_target(self, target_platform, exclude_set):
        if not self.global_proxies_prepared and USE_AUTO_VN_PROXY:
            self._prepare_global_proxies()

        target_url = "https://vtvgo.vn" if target_platform == "vtv" else ("https://tv360.vn" if target_platform == "tv360" else "https://vtvprime.vn")
        self.log(f"\n   [Ping Server] Đang kiểm tra từng Proxy vào {target_url} (Timeout 5s)...")
        
        best_ip = None
        best_protocol = "http"
        best_ping = 999
        
        for proxy_data in self.vn_proxies:
            ip_port = proxy_data['ip']
            protocol = proxy_data['protocol']
            
            if ip_port in exclude_set:
                continue
                
            ping_time = self._test_proxy_ping(ip_port, target_url, protocol)
            if ping_time is not None:
                self.log(f"      -> ✅ Sống: {ip_port} | Giao thức: {protocol.upper()} | Ping: {ping_time:.2f}s")
                if ping_time < best_ping:
                    best_ping = ping_time
                    best_ip = ip_port
                    best_protocol = protocol
                    
                if ping_time < 2.0:
                    self.log(f"   ⚡ Tốc độ ánh sáng (< 2s). Chọn ngay {ip_port} ({protocol.upper()})!")
                    return best_ip, best_protocol
                
        if best_ip:
            self.log(f"   🏆 Quét xong. Chốt IP tốt nhất: {best_ip} ({best_protocol.upper()}) (Ping: {best_ping:.2f}s)")
            return best_ip, best_protocol
            
        self.log(f"   ❌ Toàn bộ kho IP Việt Nam đều không ping được tới {target_url}.")
        return None, "http"

    def _scan_channels_with_rotation(self, driver, channels, platform, old_links_dict, exclude_set, current_proxy_ip, current_protocol, proxy_stats):
        i = 0
        consecutive_fails = 0

        while i < len(channels):
            ch = channels[i]

            if ch.get('skip'):
                i += 1
                continue

            f_link = None
            s_msg = ""
            
            has_old_link = ch['name'] in old_links_dict and old_links_dict[ch['name']]['url']
            
            if not ch.get('url'):
                if has_old_link:
                    ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                    if ch['source'] != 'vtvprime_drm': 
                        ch['source'] = 'fallback_only'
                    self.log(f"         [{i+1}/{len(channels)}] Kênh {ch['name']}: ⚠️ DOM Fallback không có URL web. Áp dụng Link Fallback thành công.")
                else:
                    ch['error_msg'] = "Không có URL để quét"
                    self.log(f"         [{i+1}/{len(channels)}] Kênh {ch['name']}: ❌ Thất bại (Không có URL web, không có link cũ).")
                i += 1
                continue

            if has_old_link:
                timeouts = [60, 120, 240] 
            else:
                timeouts = [60] 

            for t in timeouts:
                self.log(f"      [{i+1}/{len(channels)}] Cào kênh {ch['name']} (Chờ tối đa {t}s)...")
                
                if platform == 'vtvprime':
                    self.log(f"         [DEBUG SCTV] Đang truy cập trực tiếp URL kênh: {ch['url']}")
                    f_link, s_msg, lic_url = self.catch_drm_vtvprime(driver, ch['url'], max_wait=t)
                    if f_link and s_msg != "PREMIUM" and s_msg != "ERROR":
                        ch['drm_token'] = s_msg
                        ch['drm_license_url'] = lic_url
                        s_msg = "OK"
                elif platform == 'vtv':
                    f_link, s_msg = self.catch_m3u8_vtvgo(driver, ch['url'], max_wait=t)
                else:
                    f_link, s_msg = self.catch_m3u8_tv360(driver, ch['url'], max_wait=t)

                if platform == 'vtvprime':
                    self.log(f"         [DEBUG SCTV] Trả về -> Link: {f_link} | Msg: {s_msg}")

                if s_msg == "PREMIUM":
                    ch['skip'] = True
                    break 
                if f_link:
                    break 

                if has_old_link and t != timeouts[-1]:
                    self.log(f"         -> ❌ Timeout. Xoá Cache & Khởi động lại trình duyệt...")
                    driver = self._reboot_driver(driver, current_proxy_ip, current_protocol)
                    if platform == 'vtvprime':
                        driver.get("https://vtvprime.vn")
                        self._add_cookies_to_driver(driver, self.settings.get("vtvprime_cookie", ""), ".vtvprime.vn")

            if f_link:
                ch['m3u8_link'] = f_link
                consecutive_fails = 0
                if current_proxy_ip:
                    proxy_key = f"{current_protocol}://{current_proxy_ip}"
                    proxy_stats[proxy_key] = proxy_stats.get(proxy_key, 0) + 1 
                self.log(f"         -> ✅ Lấy Link Thành Công")
                i += 1
            elif ch.get('skip'):
                self.log(f"         -> 💰 Kênh Thu Phí. Bỏ qua.")
                consecutive_fails = 0
                i += 1
            else:
                consecutive_fails += 1
                
                if has_old_link:
                    ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                    if ch['source'] != 'vtvprime_drm':
                        ch['source'] = 'fallback_only'
                    else:
                        ch['drm_token'] = old_links_dict[ch['name']].get('drm_token', '')
                        ch['drm_license_url'] = old_links_dict[ch['name']].get('drm_license_url', 'https://vtvcab.ondrm.vn/license-api/v1/drm/licenses/widevine')
                        
                    self.log(f"         -> ⚠️ Thất bại. Link Fallback lấy từ file cũ thành công.")
                else:
                    ch['error_msg'] = "Lỗi toàn tập"
                    self.log(f"         -> ❌ Thất bại hoàn toàn (Không có file cũ).")

                if consecutive_fails >= 3:
                    self.log(f"   [CẢNH BÁO] 3 kênh liên tiếp thất bại. Cần đổi IP!")
                    if current_proxy_ip:
                        exclude_set.add(current_proxy_ip) 
                    
                    self.log(f"   🔄 ĐANG TÌM PROXY MỚI THAY THẾ...")
                    new_proxy_ip, new_protocol = self._get_best_proxy_for_target(platform, exclude_set)

                    if new_proxy_ip:
                        self.log(f"   🔄 ĐỔI IP THÀNH CÔNG: {new_proxy_ip}. Đang quay lui 3 bước để cào lại...")
                        current_proxy_ip = new_proxy_ip
                        current_protocol = new_protocol
                        driver = self._reboot_driver(driver, current_proxy_ip, current_protocol)
                        
                        if platform == 'vtvprime':
                            driver.get("https://vtvprime.vn")
                            self._add_cookies_to_driver(driver, self.settings.get("vtvprime_cookie", ""), ".vtvprime.vn")
                            
                        consecutive_fails = 0

                        back_steps = 3
                        start_rewind = max(0, i - back_steps + 1)

                        for rewind_idx in range(start_rewind, i + 1):
                            channels[rewind_idx]['m3u8_link'] = None
                            channels[rewind_idx]['source'] = channels[rewind_idx]['original_source']
                            channels[rewind_idx]['error_msg'] = None
                            if platform == 'vtvprime':
                                channels[rewind_idx].pop('drm_token', None)
                                channels[rewind_idx].pop('drm_license_url', None)
                            
                        i = start_rewind 
                    else:
                        self.log(f"   ❌ Kho IP đã cạn kiệt (Hoặc đang tắt tự xoay IP). Chấp nhận số phận, tiếp tục cào bằng Fallback...")
                        consecutive_fails = 0 
                        i += 1
                else:
                    i += 1

        return driver

    def load_old_m3u_links(self):
        filepath = self.get_file_path()
        old_links = {}
        if not os.path.exists(filepath): return old_links
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            current_name, current_group, current_logo = None, "Khác", ""
            current_drm_token = ""
            current_drm_lic = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    parts = line.split(',')
                    if len(parts) > 1: 
                        current_name = parts[-1].strip()
                        match_group = re.search(r'group-title="(.*?)"', line)
                        if match_group: current_group = match_group.group(1)
                        match_logo = re.search(r'tvg-logo="(.*?)"', line)
                        if match_logo: current_logo = match_logo.group(1)
                elif line.startswith("#KODIPROP:inputstream.adaptive.license_key="):
                    val = line.replace("#KODIPROP:inputstream.adaptive.license_key=", "")
                    if "|" in val:
                        parts = val.split("|")
                        current_drm_lic = parts[0]
                        for p in parts[1:]:
                            if "Token=" in p:
                                current_drm_token = p.split("Token=")[1].split("&")[0].replace("|R{SSM}", "")
                            elif "token=" in p.lower():
                                current_drm_token = p.split("oken=")[1]
                        
                        # Fix fallback for proxy URL
                        if "WORKER_DRM_PROXY_URL" in current_drm_lic and "?url=" in current_drm_lic:
                            current_drm_lic = current_drm_lic.split("?url=")[1]

                elif line and not line.startswith("#") and current_name:
                    old_links[current_name] = {
                        'url': line, 'group': current_group, 'logo': current_logo,
                        'drm_token': current_drm_token, 'drm_license_url': current_drm_lic
                    }
                    current_name, current_group, current_logo = None, "Khác", ""
                    current_drm_token, current_drm_lic = "", ""
        except: pass
        return old_links

    def remove_accents(self, input_str):
        s1 = u'ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúýĂăĐđĨĩŨũƠơƯưẠạẢảẤấẦầẨẩẪẫẬậẮắẰằẲẳẴẵẶặẸẹẺẻẼẽẾếỀềỂểỄễỆệỈỉỊịỌọỎỏỐốỒồỔổỖỗỘộỚớỜờỞởỠỡỢợỤụỦủỨứỪừỬửỮữỰựỲỳỴỵỶỷỸỹ'
        s0 = u'AAAAEEEIIOOOOUUYaaaaeeeiioooouuyAaDdIiUuOoUuAaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEeEeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuYyYyYyYy'
        s = ''
        for c in input_str:
            if c in s1: s += s0[s1.index(c)]
            else: s += c
        return s

    def get_vtv_acronym(self, ch_name):
        clean_name = self.remove_accents(ch_name).lower()
        words = clean_name.split()
        if not words: return ""
        res = words[0] 
        for w in words[1:]:
            if w: res += w[0] 
        return res
        
    def create_slug(self, ch_name):
        text = self.remove_accents(ch_name).lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'\s+', '-', text).strip('-')
        return text

    def catch_m3u8_vtvgo(self, driver, url, max_wait=60):
        try:
            driver.set_page_load_timeout(max_wait)
            driver.get_log('performance') 
            driver.get(url)
            time.sleep(2) 
            try:
                driver.execute_script("""
                    var btns = document.getElementsByTagName('button');
                    for (var i=0; i<btns.length; i++) {
                        if(btns[i].innerText.includes('Đồng ý') || btns[i].innerText.includes('tiếp tục')) btns[i].click();
                    }
                    var vids = document.getElementsByTagName('video');
                    if (vids.length > 0) vids[0].play();
                """)
            except: pass

            for i in range(max_wait):  
                logs = driver.get_log('performance')
                for entry in logs:
                    try:
                        log_data = json.loads(entry['message'])['message']
                        if 'Network.requestWillBeSent' in log_data['method']:
                            req_url = log_data['params']['request']['url']
                            vtv_keywords = ['vtv', 'cdn', 'stream', 'live', 'media', 'truyenhinhso', 'mediatech', 'playlist', 'manifest']
                            if '.m3u8' in req_url and any(kw in req_url.lower() for kw in vtv_keywords):
                                return req_url, "OK"
                    except: continue
                time.sleep(1)
            return None, f"Timeout {max_wait}s"
        except Exception as e:
            return None, f"Lỗi System: {str(e)[:30]}"

    def catch_m3u8_tv360(self, driver, url, max_wait=60):
        try:
            driver.set_page_load_timeout(max_wait)
            driver.get_log('performance') 
            driver.get(url)
            time.sleep(3) 
            is_premium = driver.execute_script("return document.body.innerText.includes('Nội dung có phí') || document.body.innerText.includes('Vui lòng đăng ký gói');")
            if is_premium: return None, "PREMIUM"
            try: driver.execute_script("var v=document.querySelector('video'); if(v) v.play();")
            except: pass

            for i in range(max_wait): 
                logs = driver.get_log('performance')
                for entry in logs:
                    try:
                        log_data = json.loads(entry['message'])['message']
                        if 'Network.requestWillBeSent' in log_data['method']:
                            req_url = log_data['params']['request']['url']
                            if '.m3u8' in req_url and 'uid=' in req_url:
                                return req_url, "OK"
                    except: continue
                time.sleep(1)
            return None, f"Timeout {max_wait}s"
        except Exception as e:
            return None, f"Lỗi System: {str(e)[:30]}"

    def catch_drm_vtvprime(self, driver, url, max_wait=60):
        try:
            driver.set_page_load_timeout(max_wait)
            driver.get_log('performance') 
            driver.get(url)
            time.sleep(2) 
            
            mpd_link = None
            drm_token = None
            license_url = None

            for i in range(max_wait): 
                logs = driver.get_log('performance')
                for entry in logs:
                    try:
                        log_msg = json.loads(entry['message'])['message']
                        method = log_msg['method']
                        
                        if method == 'Network.responseReceived':
                            resp_url = log_msg['params']['response']['url']
                            if 'graphql.vtvprime.vn' in resp_url:
                                req_id = log_msg['params']['requestId']
                                try:
                                    body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                                    json_body = json.loads(body['body'])
                                    if 'data' in json_body and 'channel' in json_body['data']:
                                        vid_data = json_body['data']['channel'].get('video', {})
                                        drm_prov = vid_data.get('drmProvider', {})
                                        
                                        token_found = drm_prov.get('drmLicenseToken') or vid_data.get('drmLicenseToken')
                                        if token_found:
                                            drm_token = token_found
                                            self.log(f"         [DEBUG SCTV] Đã chụp được DRM Token.")
                                except: pass
                                
                        if method == 'Network.requestWillBeSent':
                            req_url = log_msg['params']['request']['url']
                            if '.mpd' in req_url:
                                mpd_link = req_url
                                self.log(f"         [DEBUG SCTV] Đã chụp được luồng .mpd")
                            if 'license-api/v1/drm/licenses/widevine' in req_url:
                                license_url = req_url
                                self.log(f"         [DEBUG SCTV] Đã chụp được License Server URL")
                                
                    except: continue
                    
                if mpd_link and drm_token and license_url:
                    return mpd_link, drm_token, license_url
                    
                time.sleep(1)
                
            return None, "Timeout", None
        except Exception as e:
            return None, "ERROR", None

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
        # KHỞI TẠO BIẾN DRIVER ĐỂ TRÁNH LỖI UNBOUND LOCAL ERROR
        driver = None
        
        alive_cached = self._test_cached_proxies() if USE_AUTO_VN_PROXY else {"vtv": None, "tv360": None, "vtvprime": None}
            
        self.save_settings() 
        old_links_dict = self.load_old_m3u_links()
        
        vtv_channels = []
        tv360_channels = []
        vtvprime_channels = []
        vtv_master_link = None 
        
        exclude_proxies = set()
        vtv_proxy_stats = {}
        tv360_proxy_stats = {}
        vtvprime_proxy_stats = {}
        
        # ==========================================
        # CHU TRÌNH VTV PRIME ĐẦU TIÊN (DÀNH CHO SCTV)
        # ==========================================
        cookie_prime = self.settings.get("vtvprime_cookie", "")
        
        if cookie_prime:
            self.log("\n====== BẮT ĐẦU CHU TRÌNH VTV PRIME (SCTV) ======")
            vprime_ip, vprime_proto = None, "http"
            dom_success = False
            no_proxy_attempts = 0

            while True:
                if USE_AUTO_VN_PROXY and not vprime_ip:
                    if alive_cached["vtvprime"] and alive_cached["vtvprime"]["ip"] not in exclude_proxies:
                        vprime_ip, vprime_proto = alive_cached["vtvprime"]["ip"], alive_cached["vtvprime"]["protocol"]
                    else:
                        vprime_ip, vprime_proto = self._get_best_proxy_for_target("vtvprime", exclude_proxies)
                    
                if not vprime_ip and USE_AUTO_VN_PROXY: break
                if not USE_AUTO_VN_PROXY:
                    if no_proxy_attempts >= 3: break
                    no_proxy_attempts += 1

                self.log(f"▶ Mở trình duyệt DOM VTV Prime (Proxy: {vprime_ip} - Giao thức: {vprime_proto.upper()})")
                driver = self._reboot_driver(driver, vprime_ip, vprime_proto)
                
                for t in [60, 120, 240]:
                    self.log(f"   [VTV Prime] Tiêm Cookie và bắt gói tin Danh sách kênh (DOM) - Chờ tối đa {t}s...")
                    try:
                        driver.set_page_load_timeout(t)
                        
                        # 1. Truy cập trang chủ để tiêm Cookie hợp lệ
                        driver.get("https://vtvprime.vn")
                        self._add_cookies_to_driver(driver, cookie_prime, ".vtvprime.vn")
                        
                        # 2. Xóa log cũ, tải kênh SCTV1 Hài để kích hoạt API lấy List Kênh
                        driver.get_log('performance')
                        driver.get("https://vtvprime.vn/content/channel/1a8afdc2-181a-4c48-8e41-61411a81ce64")
                        time.sleep(5)
                        
                        # 3. Quét log tìm GraphQL
                        for wait_sec in range(t):
                            logs = driver.get_log('performance')
                            for entry in logs:
                                try:
                                    log_msg = json.loads(entry['message'])['message']
                                    if log_msg['method'] == 'Network.responseReceived':
                                        resp_url = log_msg['params']['response']['url']
                                        if 'graphql.vtvprime.vn' in resp_url:
                                            req_id = log_msg['params']['requestId']
                                            try:
                                                body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                                                json_body = json.loads(body['body'])
                                                
                                                # Cấu trúc API VTV Prime: data -> channels -> channels
                                                if 'data' in json_body and 'channels' in json_body['data']:
                                                    ch_list = json_body['data']['channels'].get('channels', [])
                                                    sctv_count = 0
                                                    for c in ch_list:
                                                        title_lower = c.get('title', '').lower()
                                                        if 'sctv' in title_lower:
                                                            ch_id = c.get('id')
                                                            if ch_id:
                                                                vtvprime_channels.append({
                                                                    'id': ch_id, 'name': c.get('title'), 'logo': c.get('logoURL', ''),
                                                                    'group_name': 'SCTV (VTV Prime)', 
                                                                    'source': 'vtvprime_drm', 'original_source': 'vtvprime_drm',
                                                                    'url': f"https://vtvprime.vn/content/channel/{ch_id}",
                                                                    'm3u8_link': None, 'error_msg': None, 'skip': False
                                                                })
                                                                sctv_count += 1
                                                    
                                                    if vtvprime_channels:
                                                        dom_success = True
                                                        self.log(f"      -> Thành công! Bắt được {sctv_count} kênh SCTV từ API GraphQL.")
                                                        break
                                            except: pass
                                except: continue
                                
                            if dom_success: break
                            time.sleep(1)
                            
                        if dom_success: break
                        
                    except Exception as e: 
                        self.log(f"      [DEBUG VTV Prime] Lỗi cào DOM: {e}")
                    
                    self.log(f"      -> Lỗi/Timeout. Đang khởi động lại trình duyệt xoá Cache...")
                    driver = self._reboot_driver(driver, vprime_ip, vprime_proto)
                    
                if dom_success: break
                if vprime_ip:
                    exclude_proxies.add(vprime_ip)
                    vprime_ip = None

            if not dom_success:
                self.log("   [VTV Prime] ⚠️ DOM thất bại hoàn toàn. Khôi phục từ file M3U cũ...")
                for old_name, old_data in old_links_dict.items():
                    if 'sctv (vtv prime)' in old_data.get('group', '').lower() or 'sctv' in old_name.lower():
                        vtvprime_channels.append({
                            'id': 'fallback', 'name': old_name, 'logo': old_data.get('logo', ''),
                            'group_name': old_data.get('group', 'SCTV (VTV Prime)'), 
                            'source': 'vtvprime_drm', 'original_source': 'vtvprime_drm',
                            'url': '', 'm3u8_link': None, 'error_msg': None, 'skip': False
                        })

            if driver and vtvprime_channels and vtvprime_channels[0]['source'] != 'fallback_only':
                self.log(f"   [VTV Prime] Bắt đầu duyệt ngầm {len(vtvprime_channels)} Kênh SCTV (Đảo Proxy nếu Fail)...")
                driver = self._scan_channels_with_rotation(driver, vtvprime_channels, 'vtvprime', old_links_dict, exclude_proxies, vprime_ip, vprime_proto, vtvprime_proxy_stats)
                
            self.save_best_proxy("vtvprime", vtvprime_proxy_stats)
        else:
            self.log("\n[!] Bỏ qua VTV Prime do không có thông tin cấu hình Cookie.")


        # ==========================================
        # CHU TRÌNH VTV (BỎ QUA SCTV VÌ ĐÃ CÓ VTV PRIME LÀM)
        # ==========================================
        self.log("\n====== BẮT ĐẦU CHU TRÌNH VTV ======")
        vtv_ip, vtv_proto = None, "http"
        dom_success = False
        no_proxy_attempts = 0

        while True: 
            if USE_AUTO_VN_PROXY and not vtv_ip:
                if alive_cached["vtv"] and alive_cached["vtv"]["ip"] not in exclude_proxies:
                    vtv_ip, vtv_proto = alive_cached["vtv"]["ip"], alive_cached["vtv"]["protocol"]
                else:
                    vtv_ip, vtv_proto = self._get_best_proxy_for_target("vtv", exclude_proxies)
            
            if not vtv_ip and USE_AUTO_VN_PROXY: break 
            if not USE_AUTO_VN_PROXY:
                if no_proxy_attempts >= 3: break
                no_proxy_attempts += 1

            self.log(f"▶ Mở trình duyệt VTV (Proxy: {vtv_ip} - Giao thức: {vtv_proto.upper()})")
            driver = self._reboot_driver(driver, vtv_ip, vtv_proto)
            
            for t in [60, 120, 240]:
                self.log(f"   [VTV] Đang truy cập VTV1 để GỘP bước lấy Danh sách kênh (DOM) & Link Gốc - Chờ tối đa {t}s...")
                try:
                    driver.set_page_load_timeout(t)
                    driver.get_log('performance') 
                    driver.get("https://vtvgo.vn/channel/vtv1-1,1.html")
                    time.sleep(2) 
                    try:
                        driver.execute_script("""
                            var btns = document.getElementsByTagName('button');
                            for (var i=0; i<btns.length; i++) { if(btns[i].innerText.includes('Đồng ý')) btns[i].click(); }
                            var vids = document.getElementsByTagName('video');
                            if (vids.length > 0) vids[0].play();
                        """)
                    except: pass
                    
                    api_json_data = None
                    captured_api_json = None
                    api_auth_headers = None
                    temp_vtv_master_link = None
                    vtv_keywords = ['vtv', 'cdn', 'stream', 'live', 'media', 'truyenhinhso', 'mediatech', 'playlist', 'manifest']
                    
                    for wait_sec in range(t):
                        logs = driver.get_log('performance')
                        for entry in logs:
                            try:
                                log_msg = json.loads(entry['message'])['message']
                                method = log_msg['method']
                                
                                if not api_auth_headers and method == 'Network.requestWillBeSent':
                                    req_params = log_msg['params']['request']
                                    req_url = req_params['url']
                                    req_method = req_params.get('method', '').upper()
                                    if 'live-channel/api/v1/channels/byCatalog' in req_url and req_method != 'OPTIONS':
                                        temp_headers = req_params.get('headers', {})
                                        if any(k.lower() == 'authorization' for k in temp_headers.keys()):
                                            api_auth_headers = temp_headers
                                            
                                if not captured_api_json and method == 'Network.responseReceived':
                                    resp_url = log_msg['params']['response']['url']
                                    if 'live-channel/api/v1/channels/byCatalog' in resp_url:
                                        req_id = log_msg['params']['requestId']
                                        try:
                                            body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                                            captured_api_json = json.loads(body['body'])
                                        except: pass

                                if not temp_vtv_master_link and method == 'Network.requestWillBeSent':
                                    req_url = log_msg['params']['request']['url']
                                    if '.m3u8' in req_url and any(kw in req_url.lower() for kw in vtv_keywords):
                                        temp_vtv_master_link = req_url
                            except Exception: continue
                            
                        if api_auth_headers and temp_vtv_master_link: break
                        time.sleep(1)
                        
                    if api_auth_headers:
                        clean_headers = {k: v for k, v in api_auth_headers.items() if not k.startswith(':')}
                        js_fetch = f"""
                        var callback = arguments[arguments.length - 1];
                        fetch("https://web-api-vtvgo.vtvdigital.vn/live-channel/api/v1/channels/byCatalog?page=1&limit=500", {{
                            method: "GET", headers: {json.dumps(clean_headers)}
                        }}).then(res => res.json()).then(data => callback({{success: true, data: data}}))
                        .catch(err => callback({{success: false, error: err.toString()}}));
                        """
                        try:
                            driver.set_script_timeout(15) 
                            res = driver.execute_async_script(js_fetch)
                            if res and res.get('success'): api_json_data = res.get('data')
                        except: pass

                    if not api_json_data and captured_api_json:
                        api_json_data = captured_api_json

                    if api_json_data and 'data' in api_json_data:
                        groups = api_json_data['data'].get('channels', [])
                        for item in groups:
                            if 'channels' in item:
                                gn_name = item.get('name', 'Khác')
                                ch_list = item.get('channels', [])
                            else:
                                gn_name = 'Khác'
                                ch_list = [item]

                            for c in ch_list:
                                gn_lower = gn_name.lower()
                                ch_name_lower = c.get('name', '').lower()
                                
                                if any(kw in gn_lower or kw in ch_name_lower for kw in ['vtv', 'sctv', 'địa phương', 'dia phuong', 'trong nước', 'thiết yếu']):
                                    if 'vtvcab' in gn_lower or 'vtvcab' in ch_name_lower: continue
                                    # LOẠI BỎ SCTV KHỎI VTV NẾU VTV PRIME ĐÃ LÀM
                                    if cookie_prime and ('sctv' in gn_lower or 'sctv' in ch_name_lower): continue

                                    src_type = 'vtvgo_dynamic' if any(kw in gn_lower or kw in ch_name_lower for kw in ['địa phương', 'dia phuong', 'trong nước', 'thiết yếu', 'sctv']) else 'vtvgo_static'
                                    slug = self.create_slug(c.get('name')) if not c.get('slug') else c.get('slug')
                                    vtv_channels.append({
                                        'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                        'group_name': gn_name if gn_name != 'Khác' else 'Địa phương', 
                                        'source': src_type, 'original_source': src_type, 
                                        'url': f"https://vtvgo.vn/channel/{slug}-1,{c.get('id')}.html",
                                        'm3u8_link': None, 'error_msg': None, 'skip': False
                                    })
                        if vtv_channels: dom_success = True
                    else:
                        page_source = driver.page_source
                        match = re.search(r'<script id="__INITIAL_STATE__" type="application/json">(.*?)</script>', page_source)
                        if match:
                            state_json = json.loads(match.group(1))
                            groups = state_json.get('global', {}).get('dataList', {}).get('channel-by-catalog-all', {}).get('channels', [])
                            for group in groups:
                                gn_name = group.get('name', 'Khác')
                                gn_lower = gn_name.lower()
                                if any(kw in gn_lower for kw in ['vtv', 'sctv', 'địa phương', 'dia phuong', 'trong nước', 'thiết yếu']):
                                    if 'vtvcab' in gn_lower: continue
                                    if cookie_prime and 'sctv' in gn_lower: continue
                                    src_type = 'vtvgo_dynamic' if any(kw in gn_lower for kw in ['địa phương', 'dia phuong', 'trong nước', 'thiết yếu', 'sctv']) else 'vtvgo_static'
                                    for c in group.get('channels', []):
                                        slug = self.create_slug(c.get('name')) if not c.get('slug') else c.get('slug')
                                        vtv_channels.append({
                                            'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                            'group_name': gn_name, 'source': src_type, 'original_source': src_type, 
                                            'url': f"https://vtvgo.vn/channel/{slug}-1,{c.get('id')}.html",
                                            'm3u8_link': None, 'error_msg': None, 'skip': False
                                        })
                            if vtv_channels: dom_success = True
                            
                    if temp_vtv_master_link:
                        vtv_master_link = temp_vtv_master_link
                        if vtv_ip: 
                            proxy_key = f"{vtv_proto}://{vtv_ip}"
                            vtv_proxy_stats[proxy_key] = vtv_proxy_stats.get(proxy_key, 0) + 1
                            
                    if dom_success and vtv_master_link:
                        for ch in vtv_channels:
                            if ch['name'].upper() == "VTV1":
                                ch['m3u8_link'] = vtv_master_link
                                ch['skip'] = True 
                                break

                    if dom_success and vtv_master_link: break 
                    elif dom_success:
                        if t == 240: break
                        else:
                            vtv_channels.clear()
                            dom_success = False
                except Exception: pass
                
                if not dom_success or not vtv_master_link:
                    driver = self._reboot_driver(driver, vtv_ip, vtv_proto)

            if dom_success: break
            if vtv_ip:
                exclude_proxies.add(vtv_ip)
                vtv_ip = None 

        if not dom_success:
            self.log("   [VTV] ⚠️ DOM thất bại hoàn toàn. Đang khôi phục DOM từ file M3U cũ...")
            for old_name, old_data in old_links_dict.items():
                gn_lower = old_data.get('group', '').lower()
                if 'vtv' in gn_lower or 'địa phương' in gn_lower or ('sctv' in gn_lower and not cookie_prime):
                    if 'vtvcab' in gn_lower: continue
                    src_type = 'vtvgo_static' if 'vtv' in gn_lower and 'sctv' not in gn_lower else 'vtvgo_dynamic'
                    vtv_channels.append({
                        'id': 'fallback', 'name': old_name, 'logo': old_data.get('logo', ''),
                        'group_name': old_data.get('group', 'Khác'), 
                        'source': src_type, 'original_source': src_type,
                        'url': '', 'm3u8_link': None, 'error_msg': None, 'skip': False
                    })

        if driver and vtv_channels and vtv_channels[0]['source'] != 'fallback_only':
            vtv_dynamic = [ch for ch in vtv_channels if ch['source'] == 'vtvgo_dynamic' and not ch.get('skip')]
            if vtv_dynamic:
                self.log(f"   [VTV] Bắt đầu duyệt ngầm Kênh Địa phương (Đảo Proxy nếu Fail)...")
                driver = self._scan_channels_with_rotation(driver, vtv_dynamic, 'vtv', old_links_dict, exclude_proxies, vtv_ip, vtv_proto, vtv_proxy_stats)
                        
        self.save_best_proxy("vtv", vtv_proxy_stats)

        # ==========================================
        # CHU TRÌNH TV360
        # ==========================================
        self.log("\n====== BẮT ĐẦU CHU TRÌNH TV360 ======")
        tv360_ip, tv360_proto = None, "http"
        
        js_extractor_smart = """
            var results = [];
            var sections = document.querySelectorAll('.container-section');
            for (var i = 0; i < sections.length; i++) {
                var h2 = sections[i].querySelector('h2');
                if (!h2) continue;
                var exactGroupName = h2.innerText.trim();
                var gnLower = exactGroupName.toLowerCase();
                if (!gnLower.includes("vĩnh long") && !gnLower.includes("htv") && !gnLower.includes("vtv cab")) continue;

                var links = sections[i].querySelectorAll('a');
                for (var j = 0; j < links.length; j++) {
                    var href = links[j].href;
                    if (href.includes('/tv/') && href.includes('ch=')) {
                        if (links[j].querySelector('.css-1hssde8')) continue; 
                        var name = links[j].getAttribute('aria-label') || links[j].innerText.trim();
                        var img = links[j].querySelector('img');
                        var logo = '';
                        if (img) {
                            logo = img.getAttribute('src') || '';
                            if (logo.includes('data:image') || logo === '') {
                                var dataSrc = img.getAttribute('data-src') || img.getAttribute('lazy-src');
                                if (dataSrc) logo = dataSrc;
                                else if (img.hasAttribute('srcset')) {
                                    var firstUrl = img.getAttribute('srcset').split(',')[0].trim().split(' ')[0];
                                    if (firstUrl && !firstUrl.includes('data:image')) logo = firstUrl;
                                }
                            }
                        }
                        try {
                            var urlObj = new URL(href);
                            results.push({id: urlObj.searchParams.get('ch'), slug: urlObj.pathname.split('/').pop(), name: name || urlObj.pathname.split('/').pop(), logo: logo, group_name: exactGroupName, link: href});
                        } catch(e) {}
                    }
                }
            }
            var unique = [];
            var ids = new Set();
            for(var ch of results){ if(ch.id && !ids.has(ch.id)){ ids.add(ch.id); unique.push(ch); } }
            return unique;
        """

        dom_success = False
        no_proxy_attempts = 0
        while True:
            if USE_AUTO_VN_PROXY and not tv360_ip:
                if alive_cached["tv360"] and alive_cached["tv360"]["ip"] not in exclude_proxies:
                    tv360_ip, tv360_proto = alive_cached["tv360"]["ip"], alive_cached["tv360"]["protocol"]
                else:
                    tv360_ip, tv360_proto = self._get_best_proxy_for_target("tv360", exclude_proxies)
                
            if not tv360_ip and USE_AUTO_VN_PROXY: break
            if not USE_AUTO_VN_PROXY:
                if no_proxy_attempts >= 3: break
                no_proxy_attempts += 1

            self.log(f"▶ Mở trình duyệt DOM TV360 (Proxy: {tv360_ip} - Giao thức: {tv360_proto.upper()})")
            driver = self._reboot_driver(driver, tv360_ip, tv360_proto)
            
            for t in [60, 120, 240]:
                self.log(f"   [TV360] Đang tải danh sách kênh (DOM) - Chờ tối đa {t}s...")
                try:
                    driver.set_page_load_timeout(t)
                    driver.get("https://tv360.vn/tv")
                    time.sleep(3) 
                    driver.execute_script("""
                        var totalHeight = 0; var distance = 600;
                        var timer = setInterval(() => { window.scrollBy(0, distance); totalHeight += distance; if(totalHeight >= document.body.scrollHeight) clearInterval(timer); }, 250);
                    """)
                    time.sleep(4) 
                    
                    dom_list = driver.execute_script(js_extractor_smart)
                    if dom_list:
                        for c in dom_list:
                            tv360_channels.append({
                                'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                'group_name': c.get('group_name'), 
                                'source': 'tv360_dynamic', 'original_source': 'tv360_dynamic',
                                'url': c.get('link'), 'm3u8_link': None, 'error_msg': None, 'skip': False
                            })
                        dom_success = True
                        self.log(f"      -> Thành công! Lấy được {len(tv360_channels)} kênh miễn phí.")
                        break
                except: pass
                
                driver = self._reboot_driver(driver, tv360_ip, tv360_proto)
                
            if dom_success: break
            if tv360_ip:
                exclude_proxies.add(tv360_ip)
                tv360_ip = None

        if not dom_success:
            self.log("   [TV360] ⚠️ DOM thất bại hoàn toàn. Đang khôi phục DOM từ file M3U cũ...")
            for old_name, old_data in old_links_dict.items():
                gn_lower = old_data.get('group', '').lower()
                if 'vĩnh long' in gn_lower or 'thvl' in gn_lower or 'htv' in gn_lower or 'vtv cab' in gn_lower or 'vtvcab' in gn_lower:
                    tv360_channels.append({
                        'id': 'fallback', 'name': old_name, 'logo': old_data.get('logo', ''),
                        'group_name': old_data.get('group', 'Khác'), 
                        'source': 'tv360_dynamic', 'original_source': 'tv360_dynamic',
                        'url': '', 'm3u8_link': None, 'error_msg': None, 'skip': False
                    })
        else:
            for c in tv360_channels:
                if c['logo'].startswith('data:image') or not c['logo']:
                    if c['name'] in old_links_dict and old_links_dict[c['name']].get('logo'):
                        c['logo'] = old_links_dict[c['name']]['logo']

        if driver and tv360_channels and tv360_channels[0]['source'] != 'fallback_only':
            channels_to_scan = [ch for ch in tv360_channels if ch['source'] == 'tv360_dynamic']
            if channels_to_scan:
                self.log(f"   [TV360] Bắt đầu duyệt ngầm {len(channels_to_scan)} Kênh TV360...")
                driver = self._scan_channels_with_rotation(driver, channels_to_scan, 'tv360', old_links_dict, exclude_proxies, tv360_ip, tv360_proto, tv360_proxy_stats)
            
        if driver: driver.quit()
        self.save_best_proxy("tv360", tv360_proxy_stats)

        self.log("\n🛡️ HOÀN TẤT. XỬ LÝ FILE M3U...")
        master_channels_list = vtv_channels + vtvprime_channels + tv360_channels

        if not vtv_master_link:
            for ch in master_channels_list:
                if ch['source'] == 'vtvgo_static' and not ch.get('skip'):
                    if ch['name'] in old_links_dict:
                        ch['source'] = 'fallback_only'
                        ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                        if not ch['logo'] and old_links_dict[ch['name']].get('logo'):
                            ch['logo'] = old_links_dict[ch['name']]['logo']
                    else: ch['skip'] = True 

        current_channel_names = [ch['name'] for ch in master_channels_list]
        for old_name, old_data in old_links_dict.items():
            if old_name not in current_channel_names:
                master_channels_list.append({
                    'id': 'fallback_dom', 'name': old_name, 'logo': old_data.get('logo', ''),
                    'group_name': old_data.get('group', 'Khác'), 'source': 'fallback_only',
                    'url': '', 'm3u8_link': old_data['url'], 'error_msg': None, 'skip': False,
                    'drm_token': old_data.get('drm_token', ''), 'drm_license_url': old_data.get('drm_license_url', '')
                })

        return vtv_master_link, master_channels_list

    def check_link_is_alive(self, url):
        headers = {"User-Agent": "VLC/3.0.16 LibVLC/3.0.16"}
        try:
            response = requests.get(url, headers=headers, timeout=3, stream=True)
            return response.status_code == 200
        except Exception:
            return False

    def generate_m3u(self, vtv_master_link, master_channels_list):
        official_vtv_group = "Kênh VTV" 
        for ch in master_channels_list:
            if ch['name'].upper() == "VTV1":
                official_vtv_group = ch['group_name']
                break

        for ch in master_channels_list:
            ch_name_lower = ch['name'].lower()
            if any(keyword in ch_name_lower for keyword in ['an ninh', 'antv', 'quốc phòng', 'qptv', 'công an nhân dân', 'cand']):
                ch['group_name'] = official_vtv_group

        def get_group_priority(group_name):
            gn_lower = group_name.lower()
            if 'vtv cab' in gn_lower or 'vtvcab' in gn_lower: return 2
            if 'vtv' in gn_lower: return 1
            if 'htv' in gn_lower: return 3
            if 'vĩnh long' in gn_lower or 'thvl' in gn_lower or 'ttvl' in gn_lower: return 4
            if 'địa phương' in gn_lower or 'dia phuong' in gn_lower: return 5
            if 'sctv' in gn_lower: return 99 
            return 6 

        master_channels_list.sort(key=lambda x: get_group_priority(x['group_name']))

        m3u_content = "#EXTM3U\n"
        
        for ch in master_channels_list:
            if ch.get('skip') and not ch.get('m3u8_link'): continue 
            
            ch_id = ch['id']
            ch_name = ch['name']
            group_name = ch['group_name']
            
            extinf_line = f'#EXTINF:-1 tvg-id="{ch_name}" tvg-logo="{ch["logo"]}" group-title="{group_name}", {ch_name}\n'
            
            # XỬ LÝ VTV PRIME DRM WIDEVINE KODI CHUẨN
            if ch['source'] == 'vtvprime_drm' and ch.get('m3u8_link'):
                m3u_content += extinf_line
                m3u_content += '#KODIPROP:inputstream.adaptive.manifest_type=mpd\n'
                m3u_content += '#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n'
                lic_url = ch.get('drm_license_url', 'https://vtvcab.ondrm.vn/license-api/v1/drm/licenses/widevine')
                token = ch.get('drm_token', '')
                # SỬ DỤNG PLACEHOLDER CHO PROXY WORKER
                m3u_content += f'#KODIPROP:inputstream.adaptive.license_key=WORKER_DRM_PROXY_URL?url={lic_url}|Token={token}\n'
                m3u_content += f"{ch['m3u8_link']}\n"
                continue
            
            if ch.get('m3u8_link') and ch['source'] != 'fallback_only':
                 m3u_content += extinf_line
                 m3u_content += f"{ch['m3u8_link']}\n"
                 continue

            if ch['source'] == 'vtvgo_static':
                if not vtv_master_link: continue
                
                if 'vtv' in group_name.lower() and 'sctv' not in group_name.lower():
                    if ch_id == "13": folder_id = "vtv6tt"
                    elif not ch_id.isdigit(): folder_id = ch_id
                    else:
                        num = int(ch_id)
                        if num <= 6: folder_id = f"vtv{num}"
                        else: folder_id = self.get_vtv_acronym(ch_name)
                    
                    new_link = re.sub(r'(/manifest/)[^/]+(/)', f'\\g<1>{folder_id}\\g<2>', vtv_master_link)
                    m3u_content += extinf_line
                    m3u_content += f"{new_link}\n"
                else:
                    new_link = re.sub(r'(/manifest/)[^/]+(/)', f'\\g<1>{ch_id}\\g<2>', vtv_master_link)
                    is_sctv = 'sctv' in group_name.lower() or 'sctv' in ch_name.lower()
                    if is_sctv:
                        self.log(f"   [Kiểm tra SCTV Nội suy] Đang ping HTTP kênh {ch_name}...")
                        if self.check_link_is_alive(new_link):
                            m3u_content += extinf_line
                            m3u_content += f"{new_link}\n"
                        else:
                            self.log(f"      -> ❌ Link {ch_name} trả về HTTP Lỗi (Đã chết). Đã loại bỏ.")
                    else:
                        m3u_content += extinf_line
                        m3u_content += f"{new_link}\n"
                    
            elif ch['source'] in ('vtvgo_dynamic', 'tv360_dynamic'):
                error_info = ch.get('error_msg', 'Không rõ')
                m3u_content += extinf_line
                m3u_content += f"# Lỗi: {error_info} | Link test: {ch['url']}\n"
            
            elif ch['source'] == 'fallback_only':
                if 'sctv (vtv prime)' in group_name.lower():
                    m3u_content += extinf_line
                    m3u_content += '#KODIPROP:inputstream.adaptive.manifest_type=mpd\n'
                    m3u_content += '#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n'
                    lic_url = ch.get('drm_license_url', 'https://vtvcab.ondrm.vn/license-api/v1/drm/licenses/widevine')
                    token = ch.get('drm_token', '')
                    # SỬ DỤNG PLACEHOLDER CHO PROXY WORKER
                    m3u_content += f'#KODIPROP:inputstream.adaptive.license_key=WORKER_DRM_PROXY_URL?url={lic_url}|Token={token}\n'
                    m3u_content += f"{ch['m3u8_link']}\n"
                else:
                    is_sctv = 'sctv' in group_name.lower() or 'sctv' in ch_name.lower()
                    if is_sctv:
                        self.log(f"   [Kiểm tra Fallback SCTV] Đang test link cũ kênh {ch_name}...")
                        if self.check_link_is_alive(ch['m3u8_link']):
                            m3u_content += extinf_line
                            m3u_content += f"{ch['m3u8_link']}\n"
                        else:
                            self.log(f"      -> ❌ Link {ch_name} (từ file M3U cũ) đã chết. Đã loại bỏ.")
                    else:
                        m3u_content += extinf_line
                        m3u_content += f"{ch['m3u8_link']}\n"
            
        file_path = self.get_file_path()
        try:
            self.log(f"   [Debug] Đang tiến hành ghi file vào đường dẫn: {file_path}")
            
            dir_name = os.path.dirname(file_path)
            if dir_name: os.makedirs(dir_name, exist_ok=True)
                
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(m3u_content)
            self.log(f"🎉 HOÀN TẤT! Đã xuất file M3U Hỗn hợp thành công.")
        except Exception as e:
            self.log(f"❌ LỖI Ghi file: {e}")

    def run_update_process(self):
        if not self.headless:
            self.btn_manual.config(state="disabled")
            
        vtv_master, channels_data = self.extract_all_data()
        if channels_data:
            self.generate_m3u(vtv_master, channels_data)
            
        if not self.headless:
            self.btn_manual.config(state="normal")

    def manual_update(self):
        threading.Thread(target=self.run_update_process, daemon=True).start()

    def run_update_process_headless(self):
        self.log("=== BẮT ĐẦU CHẠY NGẦM GITHUB (WIN MODE) ===")
        vtv_master, channels_data = self.extract_all_data()
        if channels_data:
            self.generate_m3u(vtv_master, channels_data)
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