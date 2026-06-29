import time
import json
import re
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from proxy_manager import get_best_proxy_for_target
from m3u_generator import create_slug

def create_driver(proxy_ip=None, protocol="http"):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--log-level=3") 
    chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
    
    # FIX: Vượt tường lửa WAF của VTV/Kong API (Block dấu hiệu Webdriver & Headless khi dùng IP Datacenter)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--ignore-certificate-errors")
    
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    if proxy_ip:
        chrome_options.add_argument(f'--proxy-server={protocol}://{proxy_ip}')
            
    driver = webdriver.Chrome(options=chrome_options)
    
    # WORKAROUND: Tiêm Javascript xoá cờ navigator.webdriver ngay khi khởi tạo trang trắng
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })
    return driver

def reboot_driver(driver, proxy_ip=None, protocol="http"):
    if driver:
        try:
            driver.execute_cdp_cmd('Network.clearBrowserCache', {})
            driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
            driver.quit()
        except: pass
    return create_driver(proxy_ip, protocol)

def catch_m3u8_vtvgo(driver, url, max_wait=60):
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

def catch_m3u8_tv360(driver, url, max_wait=60):
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

def scan_channels_with_rotation(driver, channels, platform, old_links_dict, exclude_set, current_proxy_ip, current_protocol, proxy_stats, vn_proxies, use_auto_proxy, logger):
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
                ch['source'] = 'fallback_only'
                logger(f"         [{i+1}/{len(channels)}] Kênh {ch['name']}: ⚠️ DOM Fallback không có URL web. Áp dụng Link Fallback thành công.")
            else:
                ch['error_msg'] = "Không có URL để quét"
                logger(f"         [{i+1}/{len(channels)}] Kênh {ch['name']}: ❌ Thất bại (Không có URL web, không có link cũ).")
            i += 1
            continue

        timeouts = [60, 120, 240] if has_old_link else [60]

        for t in timeouts:
            logger(f"      [{i+1}/{len(channels)}] Cào kênh {ch['name']} (Chờ tối đa {t}s)...")
            
            if platform == 'vtv':
                f_link, s_msg = catch_m3u8_vtvgo(driver, ch['url'], max_wait=t)
            else:
                f_link, s_msg = catch_m3u8_tv360(driver, ch['url'], max_wait=t)

            if s_msg == "PREMIUM":
                ch['skip'] = True
                break 
            if f_link:
                break 

            if has_old_link and t != timeouts[-1]:
                logger(f"         -> ❌ Timeout. Xoá Cache & Khởi động lại trình duyệt...")
                driver = reboot_driver(driver, current_proxy_ip, current_protocol)

        if f_link:
            ch['m3u8_link'] = f_link
            consecutive_fails = 0
            if current_proxy_ip:
                proxy_key = f"{current_protocol}://{current_proxy_ip}"
                proxy_stats[proxy_key] = proxy_stats.get(proxy_key, 0) + 1 
            logger(f"         -> ✅ Lấy Link Thành Công")
            i += 1
        elif ch.get('skip'):
            logger(f"         -> 💰 Kênh Thu Phí. Bỏ qua.")
            consecutive_fails = 0
            i += 1
        else:
            consecutive_fails += 1
            if has_old_link:
                ch['m3u8_link'] = old_links_dict[ch['name']]['url']
                ch['source'] = 'fallback_only'
                logger(f"         -> ⚠️ Thất bại. Link Fallback lấy từ file cũ thành công.")
            else:
                ch['error_msg'] = "Lỗi toàn tập"
                logger(f"         -> ❌ Thất bại hoàn toàn (Không có file cũ).")

            if consecutive_fails >= 3:
                logger(f"   [CẢNH BÁO] 3 kênh liên tiếp thất bại. Cần đổi IP!")
                if current_proxy_ip:
                    exclude_set.add(current_proxy_ip) 
                
                logger(f"   🔄 ĐANG TÌM PROXY MỚI THAY THẾ...")
                new_proxy_ip, new_protocol = get_best_proxy_for_target(vn_proxies, platform, exclude_set, logger)

                if new_proxy_ip:
                    logger(f"   🔄 ĐỔI IP THÀNH CÔNG: {new_proxy_ip}. Đang quay lui 3 bước để cào lại...")
                    current_proxy_ip = new_proxy_ip
                    current_protocol = new_protocol
                    driver = reboot_driver(driver, current_proxy_ip, current_protocol)
                    consecutive_fails = 0

                    back_steps = 3
                    start_rewind = max(0, i - back_steps + 1)
                    for rewind_idx in range(start_rewind, i + 1):
                        channels[rewind_idx]['m3u8_link'] = None
                        channels[rewind_idx]['source'] = channels[rewind_idx]['original_source']
                        channels[rewind_idx]['error_msg'] = None
                    i = start_rewind 
                else:
                    logger(f"   ❌ Kho IP đã cạn kiệt (Hoặc đang tắt tự xoay IP). Chấp nhận số phận, tiếp tục cào bằng Fallback...")
                    consecutive_fails = 0 
                    i += 1
            else:
                i += 1
    return driver

def process_vtv_pipeline(old_links_dict, alive_cached, exclude_proxies, vn_proxies, use_auto_proxy, logger):
    vtv_channels = []
    vtv_master_link = None
    vtv_proxy_stats = {}
    
    logger("\n====== BẮT ĐẦU CHU TRÌNH VTV ======")
    vtv_ip, vtv_proto = None, "http"
    driver = None
    dom_success = False
    no_proxy_attempts = 0

    while True: 
        if use_auto_proxy and not vtv_ip:
            if alive_cached["vtv"] and alive_cached["vtv"]["ip"] not in exclude_proxies:
                vtv_ip, vtv_proto = alive_cached["vtv"]["ip"], alive_cached["vtv"]["protocol"]
            else:
                vtv_ip, vtv_proto = get_best_proxy_for_target(vn_proxies, "vtv", exclude_proxies, logger)
        
        if not vtv_ip and use_auto_proxy: 
            break 

        if not use_auto_proxy:
            if no_proxy_attempts >= 3:
                break
            no_proxy_attempts += 1

        logger(f"▶ Mở trình duyệt VTV (Proxy: {vtv_ip} - Giao thức: {vtv_proto.upper()})")
        driver = reboot_driver(driver, vtv_ip, vtv_proto)
        
        for t in [60, 120, 240]:
            logger(f"   [VTV] Đang truy cập VTV1 để GỘP bước lấy Danh sách kênh (DOM) & Link Gốc - Chờ tối đa {t}s...")
            try:
                driver.set_page_load_timeout(t)
                driver.get_log('performance') 
                
                logger(f"      [DEBUG VTV] Truy cập vtv1-1,1.html...")
                driver.get("https://vtvgo.vn/channel/vtv1-1,1.html")
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
                
                api_json_data = None
                captured_api_json = None
                api_auth_headers = None
                temp_vtv_master_link = None
                vtv_keywords = ['vtv', 'cdn', 'stream', 'live', 'media', 'truyenhinhso', 'mediatech', 'playlist', 'manifest']
                
                logger(f"      [DEBUG VTV] Đang chờ và quét Network Logs (CDP) tìm API Header và M3U8...")
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
                                        logger(f"      [DEBUG VTV] 🔑 Đã trộm thành công Headers/Token API từ: {req_url.split('?')[0]}")
                                        
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
                                    logger(f"      [DEBUG VTV] 🚨 Bắt được Link Gốc M3U8: {req_url.split('?')[0]}")
                                    
                        except Exception: continue
                        
                    if api_auth_headers and temp_vtv_master_link:
                        logger(f"      [DEBUG VTV] 🎯 Đã có đủ Token & Link M3U8 (sau {wait_sec+1}s). Chuẩn bị Request API Thủ Công!")
                        break
                    time.sleep(1)
                    
                if api_auth_headers:
                    logger("      [DEBUG VTV] 🚀 Gửi Fetch Request (bằng JS trong trình duyệt) để ép lấy FULL 500 KÊNH...")
                    clean_headers = {k: v for k, v in api_auth_headers.items() if not k.startswith(':')}
                    js_fetch = f"""
                    var callback = arguments[arguments.length - 1];
                    fetch("https://web-api-vtvgo.vtvdigital.vn/live-channel/api/v1/channels/byCatalog?page=1&limit=500", {{
                        method: "GET",
                        headers: {json.dumps(clean_headers)}
                    }})
                    .then(res => res.json())
                    .then(data => callback({{success: true, data: data}}))
                    .catch(err => callback({{success: false, error: err.toString()}}));
                    """
                    try:
                        driver.set_script_timeout(15) 
                        res = driver.execute_async_script(js_fetch)
                        if res and res.get('success'):
                            api_json_data = res.get('data')
                            logger("      [DEBUG VTV] ✅ Fetch JS thủ công THÀNH CÔNG! Đã qua mặt bộ lọc trang VTV.")
                        else:
                            logger(f"      [DEBUG VTV] ⚠️ Fetch JS lỗi: {res.get('error')}")
                    except Exception as req_err:
                        logger(f"      [DEBUG VTV] ❌ Ngoại lệ gọi Fetch JS: {req_err}")

                if not api_json_data and captured_api_json:
                    logger("      [DEBUG VTV] ⚠️ Fallback sử dụng dữ liệu JSON bị giới hạn bắt được từ trình duyệt.")
                    api_json_data = captured_api_json

                if api_json_data and 'data' in api_json_data:
                    groups = api_json_data['data'].get('channels', [])
                    count_channels = 0
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
                                
                                src_type = 'vtvgo_dynamic' if any(kw in gn_lower or kw in ch_name_lower for kw in ['địa phương', 'dia phuong', 'trong nước', 'thiết yếu']) else 'vtvgo_static'
                                slug = create_slug(c.get('name')) if not c.get('slug') else c.get('slug')
                                vtv_channels.append({
                                    'id': str(c.get('id')), 'name': c.get('name'), 'logo': c.get('logo', ''),
                                    'group_name': gn_name if gn_name != 'Khác' else 'Địa phương', 
                                    'source': src_type, 'original_source': src_type, 
                                    'url': f"https://vtvgo.vn/channel/{slug}-1,{c.get('id')}.html",
                                    'm3u8_link': None, 'error_msg': None, 'skip': False
                                })
                                count_channels += 1

                    if vtv_channels:
                        dom_success = True
                        logger(f"      -> Thành công! Phân tích được tổng cộng {count_channels} kênh VTV/SCTV/Địa Phương.")
                else:
                    logger("      [DEBUG VTV] ⚠️ Không lấy được JSON. Thử Fallback Cổ Điển DOM __INITIAL_STATE__...")
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
                                src_type = 'vtvgo_dynamic' if any(kw in gn_lower for kw in ['địa phương', 'dia phuong', 'trong nước', 'thiết yếu']) else 'vtvgo_static'
                                for c in group.get('channels', []):
                                    slug = create_slug(c.get('name')) if not c.get('slug') else c.get('slug')
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

                if dom_success and vtv_master_link:
                    break 
                elif dom_success:
                    if t == 240:
                        logger("      ⚠️ Cố gắng cuối cùng chỉ được DOM, KHÔNG CÓ Link Gốc VTV1. Chấp nhận và đi tiếp.")
                        break
                    else:
                        logger("      ⚠️ Lấy được DOM nhưng mất Link Gốc VTV1. Đang thử lại mức Timeout cao hơn...")
                        vtv_channels.clear()
                        dom_success = False

            except Exception as ex: 
                logger(f"      [DEBUG VTV] ❌ Ngoại lệ hệ thống khi cào DOM VTV: {ex}")
            
            if not dom_success or not vtv_master_link:
                # FIX: BẮT ĐẦU DEBUG PAGE SOURCE & SCREENSHOT TRƯỚC KHI REBOOT 
                try:
                    logger(f"      [DEBUG VTV CHUYÊN SÂU] Tiêu đề trang hiện tại: {driver.title}")
                    page_src = driver.page_source
                    clean_html = re.sub(r'\s+', ' ', page_src[:1000])
                    logger(f"      [DEBUG VTV CHUYÊN SÂU] 1000 ký tự HTML đầu tiên:\n{clean_html}")
                    screenshot_path = os.path.join(os.getcwd(), f"debug_vtv_proxy_{int(time.time())}.png")
                    driver.save_screenshot(screenshot_path)
                    logger(f"      [DEBUG VTV CHUYÊN SÂU] 📸 Đã lưu ảnh chụp màn hình tại: {screenshot_path}")
                    
                    # FIX: DỪNG KHẨN CẤP NGAY SAU KHI LẤY ĐƯỢC ẢNH ĐẦU TIÊN
                    logger(f"      [DEBUG VTV CHUYÊN SÂU] 🛑 Ép buộc dừng chương trình ngay lập tức để tiết kiệm thời gian chờ của bạn!")
                    driver.quit()
                    sys.exit(1)

                except Exception as debug_err:
                    logger(f"      [DEBUG VTV CHUYÊN SÂU] ⚠️ Lỗi khi cố trích xuất thông tin debug: {debug_err}")
                    driver.quit()
                    sys.exit(1)
                # --- KẾT THÚC DEBUG ---

        if dom_success: break
        
        if vtv_ip:
            logger(f"   [VTV] ⚠️ IP {vtv_ip} thất bại. Loại bỏ và tìm IP khác...")
            exclude_proxies.add(vtv_ip)
            vtv_ip = None 

    if not dom_success:
        logger("   [VTV] ⚠️ DOM thất bại hoàn toàn. Đang khôi phục DOM từ file M3U cũ...")
        for old_name, old_data in old_links_dict.items():
            gn_lower = old_data.get('group', '').lower()
            if 'vtv' in gn_lower or 'địa phương' in gn_lower or 'sctv' in gn_lower:
                if 'vtvcab' in gn_lower: continue
                src_type = 'vtvgo_static' if ('vtv' in gn_lower or 'sctv' in gn_lower) else 'vtvgo_dynamic'
                vtv_channels.append({
                    'id': 'fallback', 'name': old_name, 'logo': old_data.get('logo', ''),
                    'group_name': old_data.get('group', 'Khác'), 
                    'source': src_type, 'original_source': src_type,
                    'url': '', 'm3u8_link': None, 'error_msg': None, 'skip': False
                })
        logger(f"      -> Đã khôi phục DOM {len(vtv_channels)} kênh VTV từ file.")

    if driver and vtv_channels and vtv_channels[0]['source'] != 'fallback_only':
        vtv_dynamic = [ch for ch in vtv_channels if ch['source'] == 'vtvgo_dynamic' and not ch.get('skip')]
        if vtv_dynamic:
            logger(f"   [VTV] Bắt đầu duyệt ngầm {len(vtv_dynamic)} Kênh Địa phương (Đảo Proxy nếu Fail 3 kênh)...")
            driver = scan_channels_with_rotation(driver, vtv_dynamic, 'vtv', old_links_dict, exclude_proxies, vtv_ip, vtv_proto, vtv_proxy_stats, vn_proxies, use_auto_proxy, logger)
                    
    if driver: driver.quit()
    
    return vtv_master_link, vtv_channels, vtv_proxy_stats

def process_tv360_pipeline(old_links_dict, alive_cached, exclude_proxies, vn_proxies, use_auto_proxy, logger):
    tv360_channels = []
    tv360_proxy_stats = {}
    
    logger("\n====== BẮT ĐẦU CHU TRÌNH TV360 ======")
    tv360_ip, tv360_proto = None, "http"
    driver = None
    
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
                            if (dataSrc) {
                                logo = dataSrc;
                            } else if (img.hasAttribute('srcset')) {
                                var srcsetStr = img.getAttribute('srcset');
                                var firstUrl = srcsetStr.split(',')[0].trim().split(' ')[0];
                                if (firstUrl && !firstUrl.includes('data:image')) logo = firstUrl;
                            }
                        }
                    }
                    try {
                        var urlObj = new URL(href);
                        results.push({
                            id: urlObj.searchParams.get('ch'), slug: urlObj.pathname.split('/').pop(),
                            name: name || urlObj.pathname.split('/').pop(), logo: logo,
                            group_name: exactGroupName, link: href
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

    dom_success = False
    no_proxy_attempts = 0
    while True:
        if use_auto_proxy and not tv360_ip:
            if alive_cached["tv360"] and alive_cached["tv360"]["ip"] not in exclude_proxies:
                tv360_ip, tv360_proto = alive_cached["tv360"]["ip"], alive_cached["tv360"]["protocol"]
            else:
                tv360_ip, tv360_proto = get_best_proxy_for_target(vn_proxies, "tv360", exclude_proxies, logger)
            
        if not tv360_ip and use_auto_proxy:
            break
            
        if not use_auto_proxy:
            if no_proxy_attempts >= 3: break
            no_proxy_attempts += 1

        logger(f"▶ Mở trình duyệt DOM TV360 (Proxy: {tv360_ip} - Giao thức: {tv360_proto.upper()})")
        driver = reboot_driver(driver, tv360_ip, tv360_proto)
        
        for t in [60, 120, 240]:
            logger(f"   [TV360] Đang tải danh sách kênh (DOM) - Chờ tối đa {t}s...")
            try:
                driver.set_page_load_timeout(t)
                driver.get("https://tv360.vn/tv")
                time.sleep(3) 
                
                driver.execute_script("""
                    var totalHeight = 0; var distance = 600;
                    var timer = setInterval(() => {
                        var scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if(totalHeight >= scrollHeight) clearInterval(timer);
                    }, 250);
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
                    logger(f"      -> Thành công! Lấy được {len(tv360_channels)} kênh miễn phí.")
                    break
            except: pass
            
            logger(f"      -> Lỗi/Timeout. Đang khởi động lại trình duyệt xoá Cache...")
            driver = reboot_driver(driver, tv360_ip, tv360_proto)
            
        if dom_success: break
        
        if tv360_ip:
            logger(f"   [TV360] ⚠️ IP {tv360_ip} thất bại DOM. Loại bỏ và tìm IP khác...")
            exclude_proxies.add(tv360_ip)
            tv360_ip = None

    if not dom_success:
        logger("   [TV360] ⚠️ DOM thất bại hoàn toàn. Đang khôi phục DOM từ file M3U cũ...")
        for old_name, old_data in old_links_dict.items():
            gn_lower = old_data.get('group', '').lower()
            if 'vĩnh long' in gn_lower or 'thvl' in gn_lower or 'htv' in gn_lower or 'vtv cab' in gn_lower or 'vtvcab' in gn_lower:
                tv360_channels.append({
                    'id': 'fallback', 'name': old_name, 'logo': old_data.get('logo', ''),
                    'group_name': old_data.get('group', 'Khác'), 
                    'source': 'tv360_dynamic', 'original_source': 'tv360_dynamic',
                    'url': '', 'm3u8_link': None, 'error_msg': None, 'skip': False
                })
        logger(f"      -> Đã khôi phục DOM {len(tv360_channels)} kênh TV360 từ file.")
    else:
        for c in tv360_channels:
            if c['logo'].startswith('data:image') or not c['logo']:
                if c['name'] in old_links_dict and old_links_dict[c['name']].get('logo'):
                    c['logo'] = old_links_dict[c['name']]['logo']

    if driver and tv360_channels and tv360_channels[0]['source'] != 'fallback_only':
        channels_to_scan = [ch for ch in tv360_channels if ch['source'] == 'tv360_dynamic']
        if channels_to_scan:
            logger(f"   [TV360] Bắt đầu duyệt ngầm {len(channels_to_scan)} Kênh TV360 (Đảo Proxy nếu Fail 3 kênh)...")
            driver = scan_channels_with_rotation(driver, channels_to_scan, 'tv360', old_links_dict, exclude_proxies, tv360_ip, tv360_proto, tv360_proxy_stats, vn_proxies, use_auto_proxy, logger)
        
    if driver: driver.quit()
    return tv360_channels, tv360_proxy_stats