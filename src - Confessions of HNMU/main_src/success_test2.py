from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.client_config import ClientConfig
from webdriver_manager.chrome import ChromeDriverManager
import re, os

from urllib.parse import urlparse, parse_qs, urlencode

import random
import json
import time

PAGE_URL = "https://www.facebook.com/profile.php?id=61555234277669"
OUTPUT_JSONL_FILE = "output/2_confessions_of_hnmu.jsonl"   # output chính (JSONL)
OUTPUT_JSON_FILE  = "output/2_confessions_of_hnmu.json"    # file JSON array sau khi convert
CHECKPOINT_FILE   = "output/2_checkpoint_hnmu.json"
COOKIES_FILE = "cookies.json"

# Số bài muốn crawl
crawl_post = 3000

def load_cookies(driver, cookies_file):
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)
        for cookie in cookies:
            c = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie.get("domain", ".facebook.com"),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", True),
                "httpOnly": cookie.get("httpOnly", False),
            }
            # EditThisCookie dùng 'expirationDate' (float giây). Selenium chấp nhận 'expiry' (int).
            if "expirationDate" in cookie:
                try:
                    c["expiry"] = int(float(cookie["expirationDate"]))
                except Exception:
                    pass
            try:
                driver.add_cookie(c)
            except Exception as e:
                print(f"⚠️ Không thêm được cookie {cookie.get('name')}: {e}")


def expand_all_see_more(driver, post):
    try:
        # Mở rộng caption
        see_more_btns = post.find_elements(
            By.XPATH,
            ".//div[@role='button' and (contains(.,'See more') or contains(.,'Xem thêm'))]"
        )
        for btn in see_more_btns:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.2)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.6)
            except Exception:
                continue

        # Mở rộng bản dịch / nguyên bản (nhiều bài nằm sau thao tác này)
        translate_btns = post.find_elements(
            By.XPATH,
            ".//div[@role='button' and (contains(.,'Xem bản dịch') or contains(.,'See translation') or contains(.,'Xem nguyên bản') or contains(.,'See original'))]"
        )
        for btn in translate_btns:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.2)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.6)
            except Exception:
                continue

    except Exception:
        pass

def pick_post_link(post):
    # 1. Ưu tiên: link chứa timestamp (thường là permalink gốc)
    try:
        ts_links = post.find_elements(
            By.XPATH,
            './/a[contains(@href,"permalink") or contains(@href,"story.php")]/span/time/..'
        )
        if ts_links:
            link = ts_links[0].get_attribute("href")
            print(">>> Picked link:", link)   # 👈 in ra để debug
            return link
    except Exception:
        pass

    # 2. Nếu không có timestamp thì fallback theo pattern cũ
    patterns = [
        'contains(@href,"/posts/")',
        'contains(@href,"story.php")',
        'contains(@href,"permalink")',
        'contains(@href,"photo.php")',
        'contains(@href,"/video")'
    ]
    for p in patterns:
        els = post.find_elements(By.XPATH, f'.//a[{p}]')
        if els:
            link = els[0].get_attribute("href")
            print(f">>> Picked link by pattern {p}:", link)
            return link

    # 3. Cuối cùng, fallback lấy bất kỳ link nào (ít dùng)
    any_a = post.find_elements(By.XPATH, './/a[@href]')
    return any_a[0].get_attribute('href') if any_a else None

def clean_post_url(url):
    if not url:
        return url
    p = urlparse(url)
    qs = parse_qs(p.query)
    for k in list(qs.keys()):
        if k.startswith("__cft__") or k in {"__tn__", "comment_id", "mibextid", "refid"}:
            qs.pop(k, None)
    q = urlencode(qs, doseq=True)
    return f"{p.scheme}://{p.netloc}{p.path}" + (f"?{q}" if q else "")

def save_checkpoint(processed, seen_urls):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"processed": int(processed), "seen_urls": list(seen_urls)}, f, ensure_ascii=False)

def load_checkpoint():
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return int(d.get("processed", 0)), set(d.get("seen_urls", []))
    except Exception:
        return 0, set()
    
NOISE_WORDS = {
    "like", "reply", "share", "comment", "send", "follow",
    "thích", "trả lời", "chia sẻ", "bình luận", "gửi", "theo dõi", "phản hồi"
}
TIME_RE = re.compile(r"^\d+\s*(s|m|h|d|w|y)$", re.I)

def _is_noise(t: str) -> bool:
    s = t.strip()
    if not s:
        return True
    if TIME_RE.match(s):
        return True          # 1d, 3h, 15m...
    if s.isdigit():
        return True               # “45”, “2” (đếm)
    low = s.lower()
    if low in NOISE_WORDS:
        return True        # Like/Reply/Share...
    # dòng rất ngắn và trùng từ hành động → coi như rác
    if len(s) <= 2:
        return True
    return False

def _extract_message_container_text(post):
    msg_nodes = post.find_elements(By.CSS_SELECTOR, 'div[data-ad-preview="message"], div[data-ad-comet-preview="message"]')
    if msg_nodes:
        t = (msg_nodes[0].get_attribute("textContent") or "").strip()
        return t

    msg_nodes2 = post.find_elements(By.CSS_SELECTOR, 'div[data-ad-rendering-role="story_message"]')
    if msg_nodes2:
        t = (msg_nodes2[0].get_attribute("textContent") or "").strip()
        return t

    return ""

def extract_post_text_segments(driver, post):
    expand_all_see_more(driver, post)

    segs = []
    selectors = [
        "div.xdj266r.x14z9mp.xat24cr.x1lziwak.x1vvkbs.x126k92a",    # dòng đầu
        "div.x14z9mp.xat24cr.x1lziwak.x1vvkbs.xtlvy1s.x126k92a"     # các dòng sau
    ]

    print(">>> Đang lấy text cho post...")
    for sel in selectors:
        els = post.find_elements(By.CSS_SELECTOR, sel)
        print(f"Selector {sel} tìm thấy {len(els)} elements")
        for el in els:
            print("----", (el.text or '').strip()[:80])

    # ====== Logic cũ giữ nguyên ======
    for sel in selectors:
        for el in post.find_elements(By.CSS_SELECTOR, sel):
            try:
                t = (el.get_attribute("textContent") or "").strip()
                if t and not _is_noise(t):
                    segs.append(t)
            except Exception:
                continue

    # =========================
    # ADDED: fallback bền vững hơn (container message)
    # Nếu selector class không bắt được, vẫn lấy được caption
    # =========================
    if not segs:
        t = _extract_message_container_text(post)
        if t:
            # Tách theo dòng để tương thích output segments
            lines = [x.strip() for x in t.split("\n") if x.strip()]
            for ln in lines:
                if ln and not _is_noise(ln):
                    segs.append(ln)

    # =========================
    # ADDED: fallback cuối (dir="auto" trong message container) để hạn chế miss do split node
    # =========================
    if not segs:
        msg_nodes = post.find_elements(By.CSS_SELECTOR, 'div[data-ad-preview="message"], div[data-ad-comet-preview="message"], div[data-ad-rendering-role="story_message"]')
        if msg_nodes:
            container = msg_nodes[0]
            for el in container.find_elements(By.CSS_SELECTOR, 'div[dir="auto"]'):
                try:
                    t = (el.get_attribute("textContent") or "").strip()
                    if t and not _is_noise(t):
                        segs.append(t)
                except Exception:
                    continue

    # Khử trùng lặp
    seen, uniq = set(), []
    for s in segs:
        s = " ".join(s.split())  # ADDED: normalize whitespace để giảm duplicate do khoảng trắng
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq

def build_driver():
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Giảm tải: tắt ảnh, hạn chế autoplay
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "autoplay-policy": "document-user-activation-required",
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--disable-gpu")

    # Tăng timeout command Selenium ↔ ChromeDriver (Selenium 4.38)
    client_config = ClientConfig(timeout=300)

    driver = webdriver.Chrome(
        service=Service("../../chromedriver-win64/chromedriver.exe"),
        options=options,
        client_config=client_config
    )

    driver.get("https://www.facebook.com")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    load_cookies(driver, COOKIES_FILE)
    driver.refresh()
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    driver.get(PAGE_URL)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed'], div[role='main']"))
    )
    return driver

def crawl_fanpage():
    processed, seen_urls = load_checkpoint()
    driver = build_driver()

    # Cuộn để tải bài và chờ “ổn định”
    max_wait = 5
    stagnant = 0

    os.makedirs(os.path.dirname(OUTPUT_JSONL_FILE), exist_ok=True)

    mode = "a" if (processed > 0 and os.path.exists(OUTPUT_JSONL_FILE)) else "w"
    with open(OUTPUT_JSONL_FILE, mode, encoding="utf-8") as f:
        print(f"📜 Bắt đầu cuộn và xử lý đến khi đủ {crawl_post} bài... (resume={processed})")

        while processed < crawl_post:
            # --- TIMEOUT SELF-HEAL: nếu find_elements bị Read timed out thì restart ---
            try:
                posts = driver.find_elements(By.CSS_SELECTOR, "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z")
            except Exception as e:
                msg = str(e).lower()
                if "read timed out" in msg or "httppool" in msg:
                    print("⚠️ ChromeDriver timeout. Restart và resume...")
                    save_checkpoint(processed, seen_urls)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
                    driver = build_driver()
                    continue
                raise

            cur = len(posts)
            print(f"🔽 Đang thấy {cur} post trên DOM | đã lưu {processed}")

            if cur <= processed:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3 + random.random())

                posts2 = driver.find_elements(By.CSS_SELECTOR, "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z")
                cur2 = len(posts2)
                if cur2 <= cur:
                    stagnant += 1
                    if stagnant >= max_wait:
                        print("⚠️ Không thấy post mới, dừng.")
                        break
                else:
                    stagnant = 0
                continue

            for i in range(processed, min(cur, crawl_post)):
                try:
                    # refetch theo index để giảm stale
                    posts = driver.find_elements(By.CSS_SELECTOR, "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z")
                    if i >= len(posts):
                        break
                    post = posts[i]

                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", post)
                    time.sleep(0.7)

                    permalink = clean_post_url(pick_post_link(post)) or "N/A"

                    # chống trùng do FB re-render
                    if permalink != "N/A" and permalink in seen_urls:
                        processed += 1
                        continue
                    if permalink != "N/A":
                        seen_urls.add(permalink)

                    segs = extract_post_text_segments(driver, post)
                    if not segs:
                        print("⚠️ Không tìm thấy text... vẫn lưu post_text=''")

                    data = {
                        "index": processed + 1,
                        "page_url": PAGE_URL,
                        "post_url": permalink,
                        "segments": segs,
                        "post_text": "\n".join(segs) if segs else ""
                    }

                    # --- JSONL: mỗi dòng 1 JSON object ---
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
                    f.flush()

                    # --- dọn DOM để giảm RAM/đơ ---
                    try:
                        driver.execute_script("arguments[0].remove();", post)
                    except Exception:
                        pass

                    processed += 1

                    # checkpoint mỗi 10 bài
                    if processed % 10 == 0:
                        save_checkpoint(processed, seen_urls)
                        try:
                            f.flush()
                            os.fsync(f.fileno())
                        except Exception:
                            pass

                except Exception as e:
                    print("⚠️ Lỗi xử lý một bài:", e)
                    data = {
                        "index": processed + 1,
                        "page_url": PAGE_URL,
                        "post_url": "N/A",
                        "segments": [],
                        "post_text": ""
                    }
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
                    f.flush()

                    processed += 1
                    if processed % 10 == 0:
                        save_checkpoint(processed, seen_urls)
                        try:
                            f.flush()
                            os.fsync(f.fileno())
                        except Exception:
                            pass
                    continue

        save_checkpoint(processed, seen_urls)
        print(f"✅ Đã lưu {processed} bài viết vào {OUTPUT_JSONL_FILE}")


    driver.quit()

def jsonl_to_json(jsonl_path=OUTPUT_JSONL_FILE, json_path=OUTPUT_JSON_FILE):
    items = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=4)

    print(f"✅ Convert xong: {len(items)} records -> {json_path}")

if __name__ == "__main__":
    crawl_fanpage()
    jsonl_to_json()