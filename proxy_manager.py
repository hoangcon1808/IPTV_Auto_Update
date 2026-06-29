import time
import requests

def check_local_ip_is_vn(logger):
    logger("\n[INIT] 🔎 Đang kiểm tra IP gốc của máy...")
    try:
        res = requests.get("http://ip-api.com/json/", timeout=5).json()
        if res.get("countryCode") == "VN":
            logger(f"   -> 🇻🇳 IP gốc của bạn là Việt Nam ({res.get('query')}). BỎ QUA VPN/PROXY để chạy tốc độ tối đa!")
            return True
        else:
            logger(f"   -> 🌍 IP gốc là {res.get('countryCode')} ({res.get('query')}). Sẽ kích hoạt cào Proxy Việt Nam.")
            return False
    except Exception as e:
        logger(f"   -> ⚠️ Lỗi check IP: {e}. Mặc định sẽ sử dụng Proxy.")
        return False

def test_proxy_ping(ip_port, target_url, protocol="http"):
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

def test_cached_proxies(settings, logger):
    logger("\n[GIAI ĐOẠN 0] 🔎 KIỂM TRA PROXY CŨ ĐÃ LƯU TRONG CONFIG...")
    alive_proxies = {"vtv": None, "tv360": None}
    
    for platform in ["vtv", "tv360"]:
        cache_str = settings.get(f"{platform}_proxy")
        if cache_str:
            logger(f"   -> Test {platform.upper()} Proxy cũ: {cache_str}")
            
            if "://" in cache_str:
                protocol, ip_port = cache_str.split("://")
            else:
                protocol, ip_port = "http", cache_str
                
            target = "https://vtvgo.vn" if platform == "vtv" else "https://tv360.vn"
            ping = test_proxy_ping(ip_port, target, protocol)
            
            if ping is not None:
                logger(f"      ✅ Sống (Ping: {ping:.2f}s)")
                alive_proxies[platform] = {"ip": ip_port, "protocol": protocol}
            else:
                logger("      ❌ Đã chết.")
                
    return alive_proxies

def prepare_global_proxies(logger):
    logger("\n[GIAI ĐOẠN 1] 🔎 TẢI DANH SÁCH PROXY TỪ PROXYSCRAPE (ĐÃ LỌC SẴN IP VIỆT NAM)...")
    
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
                logger(f"      [Tải File] ProxyScrape {protocol.upper()}: Lấy được {count} IPs.")
        except Exception as e: 
            logger(f"      [Lỗi] Không tải được file {protocol}: {e}")

    unique_proxies = {}
    for p in raw_pool:
        if p['ip'] not in unique_proxies:
            unique_proxies[p['ip']] = p['protocol']

    vn_proxies = [{'ip': ip, 'protocol': protocol} for ip, protocol in unique_proxies.items()]
    logger(f"   [Hoàn tất Tiền Xử Lý] Kho đạn có {len(vn_proxies)} IP chuẩn Việt Nam (Bỏ qua bước quét Geo do API đã lọc chuẩn).")
    return vn_proxies

def get_best_proxy_for_target(vn_proxies, target_platform, exclude_set, logger):
    if not vn_proxies:
        return None, "http"

    target_url = "https://vtvgo.vn" if target_platform == "vtv" else "https://tv360.vn"
    logger(f"\n   [Ping Server] Đang kiểm tra từng Proxy vào {target_url} (Timeout 5s)...")
    
    best_ip = None
    best_protocol = "http"
    best_ping = 999
    
    for proxy_data in vn_proxies:
        ip_port = proxy_data['ip']
        protocol = proxy_data['protocol']
        
        if ip_port in exclude_set:
            continue
            
        ping_time = test_proxy_ping(ip_port, target_url, protocol)
        if ping_time is not None:
            logger(f"      -> ✅ Sống: {ip_port} | Giao thức: {protocol.upper()} | Ping: {ping_time:.2f}s")
            if ping_time < best_ping:
                best_ping = ping_time
                best_ip = ip_port
                best_protocol = protocol
                
            if ping_time < 2.0:
                logger(f"   ⚡ Tốc độ ánh sáng (< 2s). Chọn ngay {ip_port} ({protocol.upper()})!")
                return best_ip, best_protocol
            
    if best_ip:
        logger(f"   🏆 Quét xong. Chốt IP tốt nhất: {best_ip} ({best_protocol.upper()}) (Ping: {best_ping:.2f}s)")
        return best_ip, best_protocol
        
    logger(f"   ❌ Toàn bộ kho IP Việt Nam đều không ping được tới {target_url}.")
    return None, "http"