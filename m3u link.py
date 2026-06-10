import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import threading
import time
import sys
import os
import json
import re
import urllib.request
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# --- FIX LỖI UNICODE TRÊN WINDOWS TERMINAL TẠI GITHUB ACTIONS ---
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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
        
        if self.headless:
            self.current_path = "vn.m3u"
        else:
            self.current_path = self.settings.get("path", "D:\\Tool\\vn.m3u")
            if not self.current_path: 
                self.current_path = "D:\\Tool\\vn.m3u"

        if not self.headless:
            self.root = root
            self.root.title("VTVGo & TV360 IPTV - All In One Generator")
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

            self.log("=== ALL IN ONE IPTV TOOL ===")
            self.log("✅ Chế độ: Cơ chế Timeout 3 Lượt (60s/120s/240s), Chống trôi Proxy.")
            if USE_AUTO_VN_PROXY:
                self.log("✅ Chế độ Auto-Scrape Proxy VN đang BẬT.")

    def get_file_path(self):
        if self.headless:
            return "vn.m3u"
        path = self.file_entry.get().strip()
        return path if path else "vn.m3u"

    def log(self, message):
        now = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{now}] {message}"
        print(formatted_message) 
        
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
        settings = {"path": self.get_file_path()}
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
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

    def _create_driver(self, proxy_ip=None):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--log-level=3") 
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        if proxy_ip:
            chrome_options.add_argument(f'--proxy-server=http://{proxy_ip}')
        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def _reboot_driver(self, driver, proxy_ip=None):
        if driver:
            try:
                driver.execute_cdp_cmd('Network.clearBrowserCache', {})
                driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
                driver.quit()
            except: pass
        return self._create_driver(proxy_ip)

    # ========================================================
    # KIẾN TRÚC MỚI: QUÉT PROXY TỪ 8 NGUỒN (API + WEB) -> CHECK SINGLE THREAD
    # ========================================================
    def _find_best_proxy(self, target_name="vtv"):
        self.log(f"\n   [Proxy] 🔎 ĐANG CÀO VÀ TÌM PROXY TỐT NHẤT CHO {target_name.upper()}...")
        proxy_pool = []

        # --- NGUỒN 1: API ProxyScrape ---
        try:
            url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=VN&ssl=all&anonymity=all"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=10)
            data = res.read().decode('utf-8').strip()
            count = 0
            if data:
                for p in data.split('\r\n'):
                    if p.strip():
                        proxy_pool.append({'ip': p.strip(), 'source': 'API ProxyScrape'})
                        count += 1
            self.log(f"      [Scrape] Nguồn 1 (API ProxyScrape): {count} IPs.")
        except: pass

        # --- NGUỒN 2: API Geonode ---
        try:
            url = "https://proxylist.geonode.com/api/proxy-list?country=VN&protocols=http%2Chttps&limit=50&page=1&sort_by=lastChecked&sort_type=desc"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=10)
            data = json.loads(res.read().decode('utf-8'))
            count = 0
            for item in data.get('data', []):
                if item.get('ip') and item.get('port'):
                    proxy_pool.append({'ip': f"{item['ip']}:{item['port']}", 'source': 'API Geonode'})
                    count += 1
            self.log(f"      [Scrape] Nguồn 2 (API Geonode): {count} IPs.")
        except: pass

        # --- NGUỒN 3: API ProxyList.Download ---
        try:
            url = "https://www.proxy-list.download/api/v1/get?type=http&country=VN"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=10)
            data = res.read().decode('utf-8').strip()
            count = 0
            if data:
                for p in data.split('\r\n'):
                    if p.strip():
                        proxy_pool.append({'ip': p.strip(), 'source': 'API Proxy-List.download'})
                        count += 1
            self.log(f"      [Scrape] Nguồn 3 (API ProxyList.Download): {count} IPs.")
        except: pass

        # --- NGUỒN 4: API FateZero ---
        try:
            url = "https://raw.githubusercontent.com/fate0/proxylist/master/proxy.list"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=10)
            lines = res.read().decode('utf-8').strip().split('\n')
            count = 0
            for line in lines:
                try:
                    p_data = json.loads(line)
                    if p_data.get("country") == "VN" and p_data.get("type") == "http":
                        ip_port = f"{p_data['host']}:{p_data['port']}"
                        proxy_pool.append({'ip': ip_port, 'source': 'API FateZero'})
                        count += 1
                except: continue
            self.log(f"      [Scrape] Nguồn 4 (API FateZero): {count} IPs.")
        except: pass

        # --- NGUỒN 5: API Spys.me ---
        try:
            url = "https://spys.me/proxy.txt"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=10)
            data = res.read().decode('utf-8')
            count = 0
            for line in data.split('\n'):
                if 'VN' in line:
                    match = re.search(r'^(\d{1,3}(?:\.\d{1,3}){3}:\d+)', line)
                    if match:
                        proxy_pool.append({'ip': match.group(1), 'source': 'API Spys.me'})
                        count += 1
            self.log(f"      [Scrape] Nguồn 5 (API Spys.me): {count} IPs.")
        except: pass

        # --- NGUỒN 6,7,8: CÀO QUA WEB SELENIUM ---
        driver = None
        try:
            driver = self._create_driver() 
            
            # --- NGUỒN 6: Free-Proxy-List.net ---
            try:
                driver.get("https://free-proxy-list.net/")
                time.sleep(1)
                table_text = driver.find_element("tag name", "tbody").text
                count = 0
                for line in table_text.split('\n'):
                    if " VN " in line or "Vietnam" in line:
                        match = re.search(r'(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)(?!\d)', line)
                        if match:
                            proxy_pool.append({'ip': f"{match.group(1)}:{match.group(2)}", 'source': 'WEB FreeProxy'})
                            count += 1
                self.log(f"      [Scrape] Nguồn 6 (WEB FreeProxy): {count} IPs.")
            except: pass

            # --- NGUỒN 7: Spys.one ---
            try:
                driver.get("https://spys.one/free-proxy-list/VN/")
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "font.spy14")))
                js_extract = """
                    var results = [];
                    var elements = document.querySelectorAll('font.spy14');
                    for(var i=0; i<elements.length; i++) {
                        var txt = elements[i].innerText.trim();
                        if(/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$/.test(txt)) results.push(txt);
                    }
                    return results;
                """
                matches = driver.execute_script(js_extract)
                count = 0
                if matches:
                    for ip_port in matches:
                        proxy_pool.append({'ip': ip_port, 'source': 'WEB SpysOne'})
                        count += 1
                self.log(f"      [Scrape] Nguồn 7 (WEB SpysOne): {count} IPs.")
            except: pass

            # --- NGUỒN 8: ProxyNova ---
            try:
                driver.get("https://www.proxynova.com/proxy-server-list/country-vn/")
                time.sleep(3)
                js_extract_nova = """
                    var results = [];
                    var rows = document.querySelectorAll('#tbl_proxy_list tbody tr');
                    for(var i=0; i<rows.length; i++) {
                        if (!rows[i].hasAttribute('data-proxy-id')) continue;
                        var ipTd = rows[i].querySelector('td:nth-child(1)');
                        var portTd = rows[i].querySelector('td:nth-child(2)');
                        if(ipTd && portTd) {
                            var ipText = ipTd.innerText.replace(/[^0-9\.]/g, '').trim();
                            var portText = portTd.innerText.trim();
                            if(ipText && portText) results.push(ipText + ':' + portText);
                        }
                    }
                    return results;
                """
                matches = driver.execute_script(js_extract_nova)
                count = 0
                if matches:
                    for ip_port in matches:
                        proxy_pool.append({'ip': ip_port, 'source': 'WEB ProxyNova'})
                        count += 1
                self.log(f"      [Scrape] Nguồn 8 (WEB ProxyNova): {count} IPs.")
            except: pass

        except: pass
        finally:
            if driver: driver.quit()

        # Loại bỏ các IP trùng lặp
        unique_proxies = []
        seen = set()
        for p in proxy_pool:
            if p['ip'] not in seen:
                seen.add(p['ip'])
                unique_proxies.append(p)

        if not unique_proxies:
            self.log(f"   [Proxy] ❌ Không cào được danh sách Proxy thô nào.")
            return None

        # --- KIỂM TRA ĐƠN LUỒNG & CHỐT HẠ ---
        target_url = "https://vtvgo.vn" if target_name == "vtv" else "https://tv360.vn"
        self.log(f"   [Proxy] Đã gom {len(unique_proxies)} IPs. Bắt đầu Test (Timeout 10s)...")
        
        valid_proxies = []
        for p in unique_proxies:
            ip_port = p['ip']
            source = p['source']
            
            # 1. Ping Server Đích
            try:
                proxy_handler = urllib.request.ProxyHandler({'http': ip_port, 'https': ip_port})
                opener = urllib.request.build_opener(proxy_handler)
                req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
                start_time = time.time()
                opener.open(req, timeout=10)
                ping_time = time.time() - start_time
            except Exception:
                continue # Nếu sập hoặc quá 10s -> Bỏ qua

            # 2. Check Quốc Gia (Chỉ check những con Ping thành công để tiết kiệm thời gian)
            try:
                ip_only = ip_port.split(':')[0]
                url = f"https://get.geojs.io/v1/ip/country/{ip_only}.json"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=5) # Không dùng proxy đoạn này
                geo_data = json.loads(res.read().decode('utf-8'))
                if geo_data.get("country") != "VN":
                    continue
            except:
                continue

            # 3. Đánh giá và Chốt hạ
            self.log(f"      -> ✅ Sống: {ip_port} | Ping: {ping_time:.2f}s | Nguồn: {source}")
            valid_proxies.append((ping_time, ip_port, source))
            
            # EARLY EXIT: Nếu ping dưới 2s -> Dừng tìm kiếm, dùng luôn con này
            if ping_time < 2.0:
                self.log(f"   [Proxy] ⚡ Tìm thấy Proxy siêu tốc (< 2s). Bỏ qua các IP còn lại!")
                return ip_port

        if valid_proxies:
            # Sắp xếp theo ping từ thấp đến cao và lấy con đầu tiên
            valid_proxies.sort(key=lambda x: x[0])
            best = valid_proxies[0]
            self.log(f"   [Proxy] 🏆 Đã duyệt hết. CHỐT IP TỐT NHẤT: {best[1]} (Ping: {best[0]:.2f}s)")
            return best[1]
        
        self.log(f"   [Proxy] ❌ Mọi Proxy đều chết hoặc Timeout khi truy cập {target_name.upper()}.")
        return None

    def load_old_m3u_links(self):
        filepath = self.get_file_path()
        old_links = {}
        if not os.path.exists(filepath): return old_links
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            current_name, current_group = None, "Khác"
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    parts = line.split(',')
                    if len(parts) > 1: 
                        current_name = parts[-1].strip()
                        match_group = re.search(r'group-title="(.*?)"', line)
                        if match_group: current_group = match_group.group(1)
                elif line and not line.startswith("#") and current_name:
                    old_links[current_name] = {'url': line, 'group': current_group}
                    current_name, current_group = None, "Khác"
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

    # ========================================================
    # HÀM BẮT M3U8 (TRUYỀN THỜI GIAN CHỜ VÀO TỪ BÊN NGOÀI)
    # ========================================================
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

    def extract_all_data(self):
        self.save_settings() 
        old_links_dict = self.load_old_m3u_links()
        
        vtv_channels = []
        tv360_channels = []
        vtv_master_link = None 
        
        timeouts = [60, 120, 240] # Cấu hình 3 lượt Wait
        
        # ---------------------------------------------------------
        # CHU TRÌNH 1: VTVGO
        # ---------------------------------------------------------
        self.log("\n====== BẮT ĐẦU CHU TRÌNH VTV ======")
        vtv_p = self._find_best_proxy("vtv") if USE_AUTO_VN_PROXY else None
        
        if vtv_p or not USE_AUTO_VN_PROXY:
            self.log(f"▶ Mở trình duyệt (Proxy: {vtv_p})")
            driver = self._create_driver(vtv_p)
            
            # --- 1. LẤY DOM VTV ---
            dom_success = False
            for t in timeouts:
                self.log(f"   [VTV] Đang tải danh sách kênh (DOM) - Chờ tối đa {t}s...")
                try:
                    driver.set_page_load_timeout(t)
                    driver.get("https://vtvgo.vn/channel/vtv1-1,1.html")
                    time.sleep(3) 
                    
                    page_source = driver.page_source
                    match = re.search(r'<script id="__INITIAL_STATE__" type="application/json">(.*?)</script>', page_source)
                    if match:
                        state_json = json.loads(match.group(1))
                        groups = state_json.get('global', {}).get('dataList', {}).get('channel-by-catalog-all', {}).get('channels', [])
                        for group in groups:
                            gn_lower = group.get('name', 'Khác').lower()
                            if 'vtv' in gn_lower or 'sctv' in gn_lower or 'địa phương' in gn_lower or 'dia phuong' in gn_lower:
                                if 'vtvcab' in gn_lower: continue
                                src_type = 'vtvgo_dynamic' if ('địa phương' in gn_lower or 'dia phuong' in gn_lower) else 'vtvgo_static'
                                for c in group.get('channels', []):
                                    slug = self.create_slug(c.get('name')) if not c.get('slug') else c.get('slug')
                                    vtv_channels.append({
                                        'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                        'group_name': group.get('name', 'Khác'), 'source': src_type,
                                        'url': f"https://vtvgo.vn/channel/{slug}-1,{c.get('id')}.html",
                                        'm3u8_link': None, 'error_msg': None, 'skip': False
                                    })
                        if vtv_channels:
                            dom_success = True
                            self.log(f"      -> Thành công! Lấy được {len(vtv_channels)} kênh.")
                            break
                except: pass
                
                # Nếu fail, Reboot driver xoá cache
                self.log(f"      -> Lỗi/Timeout. Đang khởi động lại trình duyệt xoá Cache...")
                driver = self._reboot_driver(driver, vtv_p)

            # FALLBACK DOM VTV
            if not dom_success:
                self.log("   [VTV] ⚠️ DOM thất bại hoàn toàn 3 lượt. Đang khôi phục từ file M3U cũ...")
                for old_name, old_data in old_links_dict.items():
                    gn_lower = old_data.get('group', '').lower()
                    if 'vtv' in gn_lower or 'địa phương' in gn_lower or 'sctv' in gn_lower:
                        if 'vtvcab' in gn_lower: continue
                        vtv_channels.append({
                            'id': 'fallback', 'name': old_name, 'logo': '',
                            'group_name': old_data.get('group', 'Khác'), 'source': 'fallback_only',
                            'url': '', 'm3u8_link': old_data['url'], 'error_msg': None, 'skip': False
                        })
                self.log(f"      -> Đã khôi phục {len(vtv_channels)} kênh VTV từ file.")

            # --- 2. LẤY MASTER LINK (VTV1) ---
            if vtv_channels and vtv_channels[0]['source'] != 'fallback_only':
                for t in timeouts:
                    self.log(f"   [VTV] Tiến hành cào Link M3U8 gốc qua VTV1 (Chờ tối đa {t}s)...")
                    f_link, s_msg = self.catch_m3u8_vtvgo(driver, "https://vtvgo.vn/channel/vtv1-1,1.html", max_wait=t)
                    if f_link:
                        vtv_master_link = f_link
                        for ch in vtv_channels:
                            if ch['name'].upper() == "VTV1":
                                ch['m3u8_link'] = f_link
                                ch['skip'] = True 
                                break
                        self.log(f"      -> ✅ Bắt được Link Gốc VTV thành công.")
                        break
                    else:
                        self.log(f"      -> ❌ Lỗi ({s_msg}). Khởi động lại trình duyệt xoá Cache...")
                        driver = self._reboot_driver(driver, vtv_p)

            # --- 3. LẤY LINK DYNAMIC (ĐỊA PHƯƠNG) ---
            vtv_dynamic = [ch for ch in vtv_channels if ch['source'] == 'vtvgo_dynamic' and not ch.get('skip')]
            if vtv_dynamic:
                self.log(f"   [VTV] Tiến hành cào Link {len(vtv_dynamic)} Kênh Địa phương...")
                for idx, ch in enumerate(vtv_dynamic, 1):
                    for t in timeouts:
                        self.log(f"      [{idx}/{len(vtv_dynamic)}] {ch['name']} (Thử tối đa {t}s)...")
                        f_link, s_msg = self.catch_m3u8_vtvgo(driver, ch['url'], max_wait=t)
                        if f_link:
                            ch['m3u8_link'] = f_link
                            self.log(f"         -> ✅ OK")
                            break
                        else:
                            self.log(f"         -> ❌ Lỗi. Reboot trình duyệt...")
                            driver = self._reboot_driver(driver, vtv_p)
                    
                    # Nếu chạy hết 3 vòng timeout vẫn lỗi -> Fallback file
                    if not ch['m3u8_link']:
                        if ch['name'] in old_links_dict:
                            ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                            ch['source'] = 'fallback_only'
                            self.log(f"         -> ⚠️ Fallback khôi phục từ file cũ thành công.")
                        else:
                            ch['error_msg'] = "Lỗi toàn tập"
                            
            driver.quit()

        # ---------------------------------------------------------
        # CHU TRÌNH 2: TV360
        # ---------------------------------------------------------
        self.log("\n====== BẮT ĐẦU CHU TRÌNH TV360 ======")
        tv360_p = self._find_best_proxy("tv360") if USE_AUTO_VN_PROXY else None
        
        js_extractor_smart = """
            var results = [];
            var sections = document.querySelectorAll('.container-section');
            for (var i = 0; i < sections.length; i++) {
                var h2 = sections[i].querySelector('h2');
                if (!h2) continue;
                
                var exactGroupName = h2.innerText.trim();
                var gnLower = exactGroupName.toLowerCase();
                
                if (!gnLower.includes("vĩnh long") && !gnLower.includes("htv") && !gnLower.includes("vtv cab")) {
                    continue;
                }

                var links = sections[i].querySelectorAll('a');
                for (var j = 0; j < links.length; j++) {
                    var href = links[j].href;
                    if (href.includes('/tv/') && href.includes('ch=')) {
                        
                        // CƠ CHẾ LỌC VIP TẠI DOM 
                        if (links[j].querySelector('.css-1hssde8')) {
                            continue; 
                        }
                        var innerHTML = links[j].innerHTML.toLowerCase();
                        if (innerHTML.includes('cbac622c276c.png')) {
                            continue; 
                        }

                        var name = links[j].getAttribute('aria-label') || links[j].innerText.trim();
                        
                        // CƠ CHẾ LOGO TV360 GỐC
                        var img = links[j].querySelector('img');
                        var logo = img ? img.src : '';
                        
                        try {
                            var urlObj = new URL(href);
                            results.push({
                                id: urlObj.searchParams.get('ch'),
                                slug: urlObj.pathname.split('/').pop(),
                                name: name || urlObj.pathname.split('/').pop(),
                                logo: logo,
                                group_name: exactGroupName, 
                                link: href
                            });
                        } catch(e) {}
                    }
                }
            }
            var unique = [];
            var ids = new Set();
            for(var ch of results){
                if(ch.id && !ids.has(ch.id)){ ids.add(ch.id); unique.push(ch); }
            }
            return unique;
        """

        if tv360_p or not USE_AUTO_VN_PROXY:
            self.log(f"▶ Mở trình duyệt (Proxy: {tv360_p})")
            driver = self._create_driver(tv360_p)
            
            # --- 1. LẤY DOM TV360 ---
            dom_success = False
            for t in timeouts:
                self.log(f"   [TV360] Đang tải danh sách kênh (DOM) - Chờ tối đa {t}s...")
                try:
                    driver.set_page_load_timeout(t)
                    driver.get("https://tv360.vn/tv")
                    time.sleep(3) 
                    
                    dom_list = driver.execute_script(js_extractor_smart)
                    if dom_list:
                        for c in dom_list:
                            tv360_channels.append({
                                'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                'group_name': c.get('group_name'), 'source': 'tv360_dynamic',
                                'url': c.get('link'), 'm3u8_link': None, 'error_msg': None, 'skip': False
                            })
                        dom_success = True
                        self.log(f"      -> Thành công! Lấy được {len(tv360_channels)} kênh miễn phí.")
                        break
                except: pass
                
                # Reboot
                self.log(f"      -> Lỗi/Timeout. Đang khởi động lại trình duyệt xoá Cache...")
                driver = self._reboot_driver(driver, tv360_p)

            # FALLBACK DOM TV360
            if not dom_success:
                self.log("   [TV360] ⚠️ DOM thất bại hoàn toàn. Đang khôi phục từ file M3U cũ...")
                for old_name, old_data in old_links_dict.items():
                    gn_lower = old_data.get('group', '').lower()
                    if 'vĩnh long' in gn_lower or 'thvl' in gn_lower or 'htv' in gn_lower or 'vtv cab' in gn_lower or 'vtvcab' in gn_lower:
                        tv360_channels.append({
                            'id': 'fallback', 'name': old_name, 'logo': '',
                            'group_name': old_data.get('group', 'Khác'), 'source': 'fallback_only',
                            'url': '', 'm3u8_link': old_data['url'], 'error_msg': None, 'skip': False
                        })
                self.log(f"      -> Đã khôi phục {len(tv360_channels)} kênh TV360 từ file.")

            # --- 2. LẤY LINK DYNAMIC TV360 ---
            channels_to_scan = [ch for ch in tv360_channels if ch['source'] == 'tv360_dynamic']
            if channels_to_scan:
                self.log(f"   [TV360] Tiến hành cào Link {len(channels_to_scan)} Kênh TV360...")
                for idx, ch in enumerate(channels_to_scan, 1):
                    for t in timeouts:
                        self.log(f"      [{idx}/{len(channels_to_scan)}] {ch['name']} (Thử tối đa {t}s)...")
                        f_link, s_msg = self.catch_m3u8_tv360(driver, ch['url'], max_wait=t)
                        
                        if s_msg == "PREMIUM":
                            ch['skip'] = True
                            self.log(f"         -> 💰 Thu phí (Lọt lưới DOM). Bỏ qua.")
                            break
                        elif f_link:
                            ch['m3u8_link'] = f_link
                            self.log(f"         -> ✅ OK")
                            break
                        else:
                            self.log(f"         -> ❌ Lỗi ({s_msg}). Reboot trình duyệt...")
                            driver = self._reboot_driver(driver, tv360_p)
                    
                    if not ch['m3u8_link'] and not ch.get('skip'):
                        if ch['name'] in old_links_dict:
                            ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                            ch['source'] = 'fallback_only'
                            self.log(f"         -> ⚠️ Fallback khôi phục từ file cũ thành công.")
                        else:
                            ch['error_msg'] = "Lỗi toàn tập"
            
            driver.quit()

        # ---------------------------------------------------------
        # GOM DATA & XỬ LÝ FALLBACK STATIC CUỐI CÙNG
        # ---------------------------------------------------------
        self.log("\n🛡️ HOÀN TẤT. XỬ LÝ FILE M3U...")
        master_channels_list = vtv_channels + tv360_channels

        # Nếu VTV Static thất bại, phải khôi phục kênh tĩnh từ file cũ
        if not vtv_master_link:
            for ch in master_channels_list:
                if ch['source'] == 'vtvgo_static' and not ch.get('skip'):
                    if ch['name'] in old_links_dict:
                        ch['source'] = 'fallback_only'
                        ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                    else: ch['skip'] = True 

        # Đẩy nốt các kênh cũ vào nếu list mới quét không thấy
        current_channel_names = [ch['name'] for ch in master_channels_list]
        for old_name, old_data in old_links_dict.items():
            if old_name not in current_channel_names:
                master_channels_list.append({
                    'id': 'fallback_dom', 'name': old_name, 'logo': '',
                    'group_name': old_data.get('group', 'Khác'), 'source': 'fallback_only',
                    'url': '', 'm3u8_link': old_data['url'], 'error_msg': None, 'skip': False
                })

        return vtv_master_link, master_channels_list

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
            if 'sctv' in gn_lower: return 5
            if 'địa phương' in gn_lower or 'dia phuong' in gn_lower: return 6
            return 7 

        master_channels_list.sort(key=lambda x: get_group_priority(x['group_name']))

        m3u_content = "#EXTM3U\n"
        
        for ch in master_channels_list:
            if ch.get('skip') and not ch.get('m3u8_link'): continue 
            
            ch_id = ch['id']
            ch_name = ch['name']
            group_name = ch['group_name']
            
            m3u_content += f'#EXTINF:-1 tvg-id="{ch_name}" tvg-logo="{ch["logo"]}" group-title="{group_name}", {ch_name}\n'
            
            if ch.get('m3u8_link') and ch['source'] != 'fallback_only':
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
                    m3u_content += f"{new_link}\n"
                else:
                    new_link = re.sub(r'(/manifest/)[^/]+(/)', f'\\g<1>{ch_id}\\g<2>', vtv_master_link)
                    m3u_content += f"{new_link}\n"
                    
            elif ch['source'] in ('vtvgo_dynamic', 'tv360_dynamic'):
                error_info = ch.get('error_msg', 'Không rõ')
                m3u_content += f"# Lỗi: {error_info} | Link test: {ch['url']}\n"
            
            elif ch['source'] == 'fallback_only':
                m3u_content += f"{ch['m3u8_link']}\n"
            
        file_path = self.get_file_path()
        try:
            self.log(f"   [Debug] Đang tiến hành ghi file vào đường dẫn: {file_path}")
            
            dir_name = os.path.dirname(file_path)
            if dir_name: 
                os.makedirs(dir_name, exist_ok=True)
                
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