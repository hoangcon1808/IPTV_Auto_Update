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
            self.log("✅ Chế độ: NGUYÊN BẢN, 1 Luồng, Chờ 60s/Kênh, Cấu hình Windows.")
            if USE_AUTO_VN_PROXY:
                self.log("✅ Chế độ Auto-Scrape Proxy VN đang BẬT. Sẽ kiểm tra Speedtest tới Server VTV.")
            if is_in_startup():
                self.log("✅ Tool đang được đặt để khởi chạy ngầm cùng Windows.")

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

    # ========================================================
    # SỬA: TEST PING ĐỘC LẬP TỚI VTV VÀ TV360 TÁCH RIÊNG
    # ========================================================
    def _get_auto_vn_proxy(self):
        self.log("   [Proxy] Bắt đầu tổng hợp Proxy VN từ đa nguồn (API & Web Cào)...")
        proxy_pool = []

        try:
            self.log("      [Debug] Đang gọi API ProxyScrape...")
            url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=VN&ssl=all&anonymity=all"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=10)
            data = response.read().decode('utf-8').strip()
            if data:
                count = 0
                for p in data.split('\r\n'):
                    if p.strip():
                        proxy_pool.append({'ip': p.strip(), 'source': 'API_ProxyScrape'})
                        count += 1
                self.log(f"   [Proxy] Nguồn 1 (API ProxyScrape): Thu được {count} IPs.")
        except Exception as e:
            self.log(f"   [Proxy] Nguồn 1 Lỗi: {e}")

        try:
            self.log("      [Debug] Đang gọi API Geonode...")
            url = "https://proxylist.geonode.com/api/proxy-list?country=VN&protocols=http%2Chttps&limit=50&page=1&sort_by=lastChecked&sort_type=desc"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))
            count = 0
            for item in data.get('data', []):
                ip = item.get('ip')
                port = item.get('port')
                if ip and port:
                    proxy_pool.append({'ip': f"{ip}:{port}", 'source': 'API_Geonode'})
                    count += 1
            self.log(f"   [Proxy] Nguồn 4 (API Geonode): Thu được {count} IPs.")
        except Exception as e:
            self.log(f"   [Proxy] Nguồn 4 Lỗi: {e}")

        self.log("   [Proxy] Khởi động Selenium ngầm để quét thêm Proxy Web...")
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--log-level=3") 
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(15) 

            try:
                self.log("      [Debug] Đang mở trang Free-Proxy-List.net...")
                driver.get("https://free-proxy-list.net/")
                self.log("      [Debug] Đã load xong Free-Proxy-List, đang đọc DOM...")
                time.sleep(1)
                table_text = driver.find_element("tag name", "tbody").text
                count = 0
                for line in table_text.split('\n'):
                    if " VN " in line or "Vietnam" in line:
                        match = re.search(r'(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)(?!\d)', line)
                        if match:
                            proxy_pool.append({'ip': f"{match.group(1)}:{match.group(2)}", 'source': 'WEB_FreeProxy'})
                            count += 1
                self.log(f"   [Proxy] Nguồn 2 (Free-Proxy-List): Thu được {count} IPs.")
            except TimeoutException:
                self.log("   [Proxy] Nguồn 2 Lỗi: Trang web load quá thời gian 15s.")
            except Exception as e:
                self.log(f"   [Proxy] Nguồn 2 Lỗi: {e}")

            try:
                self.log("      [Debug] Đang mở trang Spys.one...")
                driver.get("https://spys.one/free-proxy-list/VN/")
                self.log("      [Debug] Đã load xong Spys.one, đang chờ JS giải mã...")
                
                try:
                    WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, "font.spy14")))
                    self.log("      [Debug] Đã tìm thấy dữ liệu Spys.one, tiến hành bóc tách...")
                    js_extract = """
                        var results = [];
                        var elements = document.querySelectorAll('font.spy14');
                        for(var i = 0; i < elements.length; i++) {
                            var txt = elements[i].innerText.trim();
                            if(/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$/.test(txt)) {
                                results.push(txt);
                            }
                        }
                        return results;
                    """
                    matches = driver.execute_script(js_extract)
                    
                    count = 0
                    if matches:
                        for ip_port in matches:
                            proxy_pool.append({'ip': ip_port, 'source': 'WEB_SpysOne'})
                            count += 1
                    self.log(f"   [Proxy] Nguồn 3 (Spys.one): Thu được {count} IPs.")
                except Exception:
                    self.log("   [Proxy] Nguồn 3 Lỗi: Bị chặn bởi Captcha/Cloudflare hoặc Timeout.")
            except TimeoutException:
                self.log("   [Proxy] Nguồn 3 Lỗi: Trang web load quá thời gian 15s.")
            except Exception as e:
                self.log(f"   [Proxy] Nguồn 3 Lỗi: {e}")

        except Exception as e:
            self.log(f"   [Proxy] Lỗi khởi tạo Selenium quét Web: {e}")
        finally:
            if driver: driver.quit()

        unique_proxies = {}
        for p in proxy_pool:
            if p['ip'] not in unique_proxies:
                unique_proxies[p['ip']] = p['source']

        if not unique_proxies:
            self.log("   [Proxy] ❌ Cào thất bại từ tất cả các nguồn (Không có Proxy nào).")
            return [], []

        self.log(f"   [Proxy] Đã lọc được {len(unique_proxies)} IP VN unique. Bắt đầu test PING tới VTVGo và TV360...")

        vtv_working = []
        tv360_working = []

        tested_count = 0
        for ip, source in unique_proxies.items():
            tested_count += 1
            try:
                proxy_handler = urllib.request.ProxyHandler({'http': ip, 'https': ip})
                opener = urllib.request.build_opener(proxy_handler)
                
                check_req = urllib.request.Request("http://ip-api.com/json/", headers={'User-Agent': 'Mozilla/5.0'})
                check_res = opener.open(check_req, timeout=3)
                geo_data = json.loads(check_res.read().decode('utf-8'))
                
                if geo_data.get("countryCode") == "VN":
                    # Test VTV
                    try:
                        start_time = time.time()
                        vtv_req = urllib.request.Request("https://vtvgo.vn", headers={'User-Agent': 'Mozilla/5.0'})
                        opener.open(vtv_req, timeout=4)
                        ping = time.time() - start_time
                        vtv_working.append((ping, ip, source))
                        self.log(f"      [Debug] [{source}] {ip} -> VTV PING: {ping:.2f}s")
                    except: pass

                    # Test TV360
                    try:
                        start_time = time.time()
                        tv360_req = urllib.request.Request("https://tv360.vn", headers={'User-Agent': 'Mozilla/5.0'})
                        opener.open(tv360_req, timeout=4)
                        ping = time.time() - start_time
                        tv360_working.append((ping, ip, source))
                        self.log(f"      [Debug] [{source}] {ip} -> TV360 PING: {ping:.2f}s")
                    except: pass
                else:
                    self.log(f"      [Debug] [{source}] {ip} -> LOẠI: Nằm ngoài lãnh thổ VN.")
            except Exception:
                pass 

        self.log(f"   [Proxy] Đã test xong {tested_count} IPs.")

        vtv_working.sort(key=lambda x: x[0])
        tv360_working.sort(key=lambda x: x[0])

        if vtv_working:
            self.log(f"   [Proxy] ✅ VTV Top 1: {vtv_working[0][1]} ({vtv_working[0][0]:.2f}s)")
        if tv360_working:
            self.log(f"   [Proxy] ✅ TV360 Top 1: {tv360_working[0][1]} ({tv360_working[0][0]:.2f}s)")

        return vtv_working, tv360_working

    def load_old_m3u_links(self):
        filepath = self.get_file_path()
        old_links = {}
        if not os.path.exists(filepath): 
            self.log(f"   [Debug] Không tìm thấy file cũ tại {filepath} để làm Fallback.")
            return old_links
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            current_name = None
            current_group = "Khác"
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
                    current_name = None
                    current_group = "Khác"
            self.log(f"   [Debug] Đã nạp {len(old_links)} link từ file cũ làm Fallback.")
        except Exception as e: 
            self.log(f"   [Debug] Lỗi đọc file cũ: {e}")
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

    def catch_m3u8_vtvgo(self, driver, url):
        try:
            self.log(f"      [Debug] Đang truy cập URL: {url}")
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

            for i in range(60): 
                logs = driver.get_log('performance')
                for entry in logs:
                    try:
                        log_data = json.loads(entry['message'])['message']
                        if 'Network.requestWillBeSent' in log_data['method']:
                            req_url = log_data['params']['request']['url']
                            vtv_keywords = ['vtv', 'cdn', 'stream', 'live', 'media', 'truyenhinhso', 'mediatech', 'playlist', 'index']
                            if '.m3u8' in req_url and any(kw in req_url.lower() for kw in vtv_keywords):
                                return req_url, "OK"
                    except: continue
                time.sleep(1)

            return None, "Timeout 60s"
        except Exception as e:
            return None, f"Lỗi System: {str(e)[:30]}"

    def catch_m3u8_tv360(self, driver, url):
        try:
            self.log(f"      [Debug] Đang truy cập URL: {url}")
            driver.get_log('performance') 
            driver.get(url)
            time.sleep(3) 
            
            is_premium = driver.execute_script("return document.body.innerText.includes('Nội dung có phí') || document.body.innerText.includes('Vui lòng đăng ký gói');")
            if is_premium:
                return None, "PREMIUM"
            
            try:
                driver.execute_script("var v=document.querySelector('video'); if(v) v.play();")
            except: pass

            for i in range(60): 
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

            return None, "Timeout 60s"
        except Exception as e:
            return None, f"Lỗi System: {str(e)[:30]}"

    # Helper tạo WebDriver để tránh lặp code
    def _create_driver(self, proxy_ip):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        if proxy_ip:
            chrome_options.add_argument(f'--proxy-server=http://{proxy_ip}')
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(90)
        return driver

    def extract_all_data(self):
        self.save_settings() 
        old_links_dict = self.load_old_m3u_links()
        
        master_channels_list = []
        
        try:
            vtv_proxies, tv360_proxies = [], []
            if USE_AUTO_VN_PROXY:
                vtv_proxies, tv360_proxies = self._get_auto_vn_proxy()
                if not vtv_proxies and not tv360_proxies:
                    self.log("❌ CRITICAL: Không tìm thấy Proxy VN hợp lệ nào. Hủy bỏ tiến trình để bảo vệ file M3U cũ!")
                    return None, None, None

            v_p1 = vtv_proxies[0][1] if len(vtv_proxies) > 0 else None
            v_p2 = vtv_proxies[1][1] if len(vtv_proxies) > 1 else None
            
            t_p1 = tv360_proxies[0][1] if len(tv360_proxies) > 0 else None
            t_p2 = tv360_proxies[1][1] if len(tv360_proxies) > 1 else None

            # ==========================================
            # PHASE 1: VTV PROCESSING
            # ==========================================
            vtv_token = None
            vtv_ts = None
            failed_vtv_dynamic = []
            
            if v_p1:
                self.log(f"▶ BẮT ĐẦU VTV PHASE (Lượt 1 - Proxy: {v_p1})...")
                driver = self._create_driver(v_p1)
                
                # 1.1 Lấy JSON Kênh VTV
                try:
                    driver.get("https://vtvgo.vn/channel/vtv1-1,1.html")
                    time.sleep(3) 
                    try:
                        driver.execute_script("""
                            var btns = document.getElementsByTagName('button');
                            for (var i=0; i<btns.length; i++) {
                                if(btns[i].innerText.includes('Đồng ý') || btns[i].innerText.includes('tiếp tục')) btns[i].click();
                            }
                            var vids = document.getElementsByTagName('video');
                            if(vids.length>0) vids[0].play();
                        """)
                    except: pass
                    time.sleep(2)

                    page_source = driver.page_source
                    match = re.search(r'<script id="__INITIAL_STATE__" type="application/json">(.*?)</script>', page_source)
                    if match:
                        state_json = json.loads(match.group(1))
                        groups = state_json.get('global', {}).get('dataList', {}).get('channel-by-catalog-all', {}).get('channels', [])
                        for group in groups:
                            group_name = group.get('name', 'Khác')
                            gn_lower = group_name.lower()
                            if 'vtv' in gn_lower or 'sctv' in gn_lower or 'địa phương' in gn_lower or 'dia phuong' in gn_lower:
                                if 'vtvcab' in gn_lower: continue
                                src_type = 'vtvgo_dynamic' if ('địa phương' in gn_lower or 'dia phuong' in gn_lower) else 'vtvgo_static'
                                for c in group.get('channels', []):
                                    slug = c.get('slug', '')
                                    if not slug: slug = self.create_slug(c.get('name'))
                                    master_channels_list.append({
                                        'id': str(c.get('id')),
                                        'name': c.get('name'),
                                        'logo': c.get('logo', ''),
                                        'group_name': group_name,
                                        'source': src_type,
                                        'url': f"https://vtvgo.vn/channel/{slug}-1,{c.get('id')}.html",
                                        'm3u8_link': None,
                                        'error_msg': None,
                                        'skip': False
                                    })
                except Exception as e:
                    self.log(f"   [VTV] Lỗi JSON VTVGo: {e}")

                # 1.2 Lấy VTV Token
                m3u8_url = None
                for i in range(30): 
                    logs = driver.get_log('performance')
                    for entry in logs:
                        try:
                            log_data = json.loads(entry['message'])['message']
                            if 'Network.requestWillBeSent' in log_data['method']:
                                req_url = log_data['params']['request']['url']
                                if '.m3u8' in req_url and 'vtvdigital.vn' in req_url and '/manifest/' in req_url:
                                    m3u8_url = req_url
                                    break
                        except: continue
                    if m3u8_url: break
                    time.sleep(1)

                if m3u8_url:
                    parts = m3u8_url.split('/')
                    vtv_token, vtv_ts = parts[3], parts[4]
                    self.log(f"   ✅ Bắt Token VTVGo thành công: {vtv_token[:8]}...")
                else:
                    self.log("   ❌ Lượt 1: Không bắt được Token VTVGo.")

                # 1.3 Cào VTV Dynamic
                vtv_dynamic_channels = [ch for ch in master_channels_list if ch['source'] == 'vtvgo_dynamic']
                if vtv_dynamic_channels:
                    self.log(f"⏳ Đang quét {len(vtv_dynamic_channels)} kênh địa phương VTVGo...")
                    for idx, ch in enumerate(vtv_dynamic_channels, 1):
                        found_link, status_msg = self.catch_m3u8_vtvgo(driver, ch['url'])
                        if found_link:
                            ch['m3u8_link'] = found_link
                            self.log(f"   [{idx}/{len(vtv_dynamic_channels)}] VTVGo: {ch['name']} -> ✅ OK")
                        else:
                            ch['error_msg'] = status_msg
                            self.log(f"   [{idx}/{len(vtv_dynamic_channels)}] VTVGo: {ch['name']} -> ❌ Lỗi: {status_msg}")
                            failed_vtv_dynamic.append(ch)

                driver.quit()

                # 1.4 LƯỢT 2 VTV (Nếu Lượt 1 xịt và có Proxy 2)
                if (not vtv_token or failed_vtv_dynamic) and v_p2:
                    self.log(f"🔄 VTV LƯỢT 2: Đổi Proxy sang {v_p2} để cứu hộ...")
                    driver2 = self._create_driver(v_p2)
                    
                    if not vtv_token:
                        driver2.get("https://vtvgo.vn/channel/vtv1-1,1.html")
                        time.sleep(3)
                        m3u8_url = None
                        for i in range(30): 
                            logs = driver2.get_log('performance')
                            for entry in logs:
                                try:
                                    log_data = json.loads(entry['message'])['message']
                                    if 'Network.requestWillBeSent' in log_data['method']:
                                        req_url = log_data['params']['request']['url']
                                        if '.m3u8' in req_url and 'vtvdigital.vn' in req_url and '/manifest/' in req_url:
                                            m3u8_url = req_url
                                            break
                                except: continue
                            if m3u8_url: break
                            time.sleep(1)

                        if m3u8_url:
                            parts = m3u8_url.split('/')
                            vtv_token, vtv_ts = parts[3], parts[4]
                            self.log(f"   ✅ Đã cứu Token VTVGo thành công: {vtv_token[:8]}...")
                        else:
                            self.log("   ❌ Cứu Token VTVGo thất bại.")

                    for ch in failed_vtv_dynamic:
                        found_link, status_msg = self.catch_m3u8_vtvgo(driver2, ch['url'])
                        if found_link:
                            ch['m3u8_link'] = found_link
                            ch['error_msg'] = None
                            self.log(f"   [Cứu] VTVGo: {ch['name']} -> ✅ OK")
                        else:
                            self.log(f"   [Cứu] VTVGo: {ch['name']} -> ❌ Vẫn Lỗi: {status_msg}")
                    
                    driver2.quit()

            # ==========================================
            # PHASE 2: TV360 PROCESSING
            # ==========================================
            tv360_dom_scraped = False
            failed_tv360_dynamic = []
            
            if t_p1:
                self.log(f"▶ BẮT ĐẦU TV360 PHASE (Lượt 1 - Proxy: {t_p1})...")
                driver = self._create_driver(t_p1)
                
                # 2.1 Lấy DOM TV360
                try:
                    driver.get("https://tv360.vn/tv")
                    for _ in range(8):
                        driver.execute_script("window.scrollBy(0, 800);")
                        time.sleep(1.5)
                        
                    js_extractor_smart = """
                        var results = [];
                        var sections = document.querySelectorAll('.container-section');
                        for (var i = 0; i < sections.length; i++) {
                            var h2 = sections[i].querySelector('h2');
                            if (!h2) continue;
                            var groupName = h2.innerText.trim();
                            var gnLower = groupName.toLowerCase();
                            var targetGroup = "";
                            if (gnLower.includes("vĩnh long")) targetGroup = "Vĩnh Long";
                            else if (gnLower.includes("htv")) targetGroup = "HTV";
                            else if (gnLower.includes("vtv cab")) targetGroup = "VTVCab";
                            if (!targetGroup) continue;
                            var links = sections[i].querySelectorAll('a');
                            for (var j = 0; j < links.length; j++) {
                                var href = links[j].href;
                                if (href.includes('/tv/') && href.includes('ch=')) {
                                    var name = links[j].getAttribute('aria-label') || links[j].innerText.trim();
                                    var img = links[j].querySelector('img');
                                    var logo = img ? img.src : '';
                                    try {
                                        var urlObj = new URL(href);
                                        var id = urlObj.searchParams.get('ch');
                                        var slug = urlObj.pathname.split('/').pop();
                                        results.push({
                                            id: id, slug: slug, name: name || slug, logo: logo,
                                            group_name: targetGroup, link: href
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
                    tv360_dom_list = driver.execute_script(js_extractor_smart)
                    if tv360_dom_list:
                        tv360_dom_scraped = True
                        for c in tv360_dom_list:
                            master_channels_list.append({
                                'id': str(c.get('id')),
                                'name': c.get('name'),
                                'logo': c.get('logo', ''),
                                'group_name': c.get('group_name'),
                                'source': 'tv360_dynamic',
                                'url': c.get('link'),
                                'm3u8_link': None,
                                'error_msg': None,
                                'skip': False
                            })
                        self.log(f"   -> Quét DOM TV360 thành công: Lấy {len(tv360_dom_list)} kênh chuẩn.")
                except Exception as e:
                    self.log(f"   [TV360] Lỗi khi cào DOM: {e}")

                # 2.2 Cào TV360 Dynamic
                tv360_dynamic_channels = [ch for ch in master_channels_list if ch['source'] == 'tv360_dynamic']
                if tv360_dynamic_channels:
                    self.log(f"⏳ Đang quét {len(tv360_dynamic_channels)} kênh TV360 Dynamic...")
                    for idx, ch in enumerate(tv360_dynamic_channels, 1):
                        found_link, status_msg = self.catch_m3u8_tv360(driver, ch['url'])
                        if status_msg == "PREMIUM":
                            ch['skip'] = True
                            self.log(f"   [{idx}/{len(tv360_dynamic_channels)}] TV360: {ch['name']} -> 💰 Bỏ qua (Thu phí)")
                        elif found_link:
                            ch['m3u8_link'] = found_link
                            self.log(f"   [{idx}/{len(tv360_dynamic_channels)}] TV360: {ch['name']} -> ✅ OK")
                        else:
                            ch['error_msg'] = status_msg
                            self.log(f"   [{idx}/{len(tv360_dynamic_channels)}] TV360: {ch['name']} -> ❌ Lỗi: {status_msg}")
                            failed_tv360_dynamic.append(ch)

                driver.quit()

                # 2.3 LƯỢT 2 TV360 (Nếu Lượt 1 xịt và có Proxy 2)
                if (not tv360_dom_scraped or failed_tv360_dynamic) and t_p2:
                    self.log(f"🔄 TV360 LƯỢT 2: Đổi Proxy sang {t_p2} để cứu hộ...")
                    driver2 = self._create_driver(t_p2)
                    
                    if not tv360_dom_scraped:
                        driver2.get("https://tv360.vn/tv")
                        for _ in range(8):
                            driver2.execute_script("window.scrollBy(0, 800);")
                            time.sleep(1.5)
                        tv360_dom_list_2 = driver2.execute_script(js_extractor_smart)
                        if tv360_dom_list_2:
                            new_channels_saved = []
                            for c in tv360_dom_list_2:
                                new_ch = {
                                    'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                    'group_name': c.get('group_name'), 'source': 'tv360_dynamic',
                                    'url': c.get('link'), 'm3u8_link': None, 'error_msg': None, 'skip': False
                                }
                                master_channels_list.append(new_ch)
                                new_channels_saved.append(new_ch)
                            self.log(f"   ✅ Cứu DOM TV360 thành công: Lấy {len(tv360_dom_list_2)} kênh chuẩn.")
                            
                            # Cào ngầm ngay cho các kênh vừa cứu được
                            for ch in new_channels_saved:
                                found_link, status_msg = self.catch_m3u8_tv360(driver2, ch['url'])
                                if status_msg == "PREMIUM": ch['skip'] = True
                                elif found_link: ch['m3u8_link'] = found_link
                                else: failed_tv360_dynamic.append(ch) # Đưa vào list để tí cứu tiếp nếu được

                    for ch in failed_tv360_dynamic:
                        if ch.get('skip'): continue
                        found_link, status_msg = self.catch_m3u8_tv360(driver2, ch['url'])
                        if found_link:
                            ch['m3u8_link'] = found_link
                            ch['error_msg'] = None
                            self.log(f"   [Cứu] TV360: {ch['name']} -> ✅ OK")
                        else:
                            self.log(f"   [Cứu] TV360: {ch['name']} -> ❌ Vẫn Lỗi: {status_msg}")
                    
                    driver2.quit()

            # ==========================================
            # PHASE 3: FALLBACK TOÀN TẬP (MEMORY)
            # ==========================================
            self.log("🛡️ KIỂM TRA LỚP BẢO VỆ FALLBACK CUỐI CÙNG...")
            
            # Fallback Token VTV
            if not vtv_token:
                self.log("   ⚠️ Cả 2 lượt đều không bắt được Token VTV. Kích hoạt FALLBACK cho VTV/SCTV Static...")
                for ch in master_channels_list:
                    if ch['source'] == 'vtvgo_static':
                        if ch['name'] in old_links_dict:
                            ch['source'] = 'fallback_only'
                            ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                        else:
                            ch['skip'] = True 

            # Fallback DOM Khuyết
            current_channel_names = [ch['name'] for ch in master_channels_list]
            fallback_dom_count = 0
            for old_name, old_data in old_links_dict.items():
                if old_name not in current_channel_names:
                    master_channels_list.append({
                        'id': 'fallback_dom',
                        'name': old_name,
                        'logo': '',
                        'group_name': old_data.get('group', 'Khác'),
                        'source': 'fallback_only',
                        'url': '',
                        'm3u8_link': old_data['url'],
                        'error_msg': None,
                        'skip': False
                    })
                    fallback_dom_count += 1
            if fallback_dom_count > 0:
                self.log(f"   -> Đã khôi phục {fallback_dom_count} kênh từ file cũ do Web bị lỗi hiển thị DOM.")

            # Fallback Kênh Dynamic Xịt
            fallback_dyn_count = 0
            for ch in master_channels_list:
                if ch['source'] in ('vtvgo_dynamic', 'tv360_dynamic') and not ch['m3u8_link'] and not ch.get('skip'):
                    if ch['name'] in old_links_dict:
                        ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                        fallback_dyn_count += 1
            if fallback_dyn_count > 0:
                self.log(f"   -> Đã khôi phục {fallback_dyn_count} link m3u8 cũ cho các kênh cào ngầm thất bại.")

            return vtv_token, vtv_ts, master_channels_list

        except Exception as e:
            self.log(f"❌ Lỗi Hệ thống Nghiêm trọng: {e}")
            return None, None, None

    def generate_m3u(self, vtv_token, vtv_ts, master_channels_list):
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
            if ch.get('skip'): continue 
            
            ch_id = ch['id']
            ch_name = ch['name']
            group_name = ch['group_name']
            
            m3u_content += f'#EXTINF:-1 tvg-id="{ch_name}" tvg-logo="{ch["logo"]}" group-title="{group_name}", {ch_name}\n'
            
            if ch['source'] == 'vtvgo_static':
                if not vtv_token: continue
                base_url = f"https://vtvgolive-ssaimh.vtvdigital.vn/{vtv_token}/{vtv_ts}/manifest"
                
                if 'vtv' in group_name.lower() and 'sctv' not in group_name.lower():
                    if ch_id == "13": folder_id = "vtv6tt"
                    elif not ch_id.isdigit(): folder_id = ch_id
                    else:
                        num = int(ch_id)
                        if num <= 6: folder_id = f"vtv{num}"
                        else: folder_id = self.get_vtv_acronym(ch_name)
                    m3u_content += f"{base_url}/{folder_id}/master.m3u8\n"
                else:
                    m3u_content += f"{base_url}/{ch_id}/master.m3u8\n"
                    
            elif ch['source'] in ('vtvgo_dynamic', 'tv360_dynamic'):
                if ch['m3u8_link']:
                    m3u_content += f"{ch['m3u8_link']}\n"
                else:
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
            
        tk_val, ts_val, channels_data = self.extract_all_data()
        if channels_data:
            self.generate_m3u(tk_val, ts_val, channels_data)
            
        if not self.headless:
            self.btn_manual.config(state="normal")

    def manual_update(self):
        threading.Thread(target=self.run_update_process, daemon=True).start()

    def run_update_process_headless(self):
        self.log("=== BẮT ĐẦU CHẠY NGẦM GITHUB (WIN MODE) ===")
        tk_val, ts_val, channels_data = self.extract_all_data()
        if channels_data:
            self.generate_m3u(tk_val, ts_val, channels_data)
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