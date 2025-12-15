from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import re

from urllib.parse import urlparse, parse_qs, urlencode

import random
import json
import time

PAGE_URL = "https://www.facebook.com/profile.php?id=61555234277669"
OUTPUT_FILE = "hnmu_posts_2.json"
COOKIES_FILE = "cookies.json"

# Số bài muốn crawl
crawl_post = 5

# Map đúng expiry từ EditThisCookie (có trường 'expirationDate')
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
        see_more_btns = post.find_elements(
            By.XPATH,
            ".//div[@role='button' and (contains(text(),'See more') or contains(text(),'Xem thêm'))]"
        )
        for btn in see_more_btns:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            try:
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.6)
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
        if k.startswith("__cft__") or k in {"__tn__","comment_id","mibextid","refid"}:
            qs.pop(k, None)
    q = urlencode(qs, doseq=True)
    return f"{p.scheme}://{p.netloc}{p.path}" + (f"?{q}" if q else "")

NOISE_WORDS = {
    "like","reply","share","comment","send","follow",
    "thích","trả lời","chia sẻ","bình luận","gửi","theo dõi","phản hồi"
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

def extract_post_text_segments(driver, post):
    expand_all_see_more(driver, post)

    segs = []
    selectors = [
        "div.xdj266r.x14z9mp.xat24cr.x1lziwak.x1vvkbs",    # dòng đầu
        "div.x14z9mp.xat24cr.x1lziwak.x1vvkbs.xtlvy1s"     # các dòng sau
    ]

    print(">>> Đang lấy text cho post...")
    for sel in selectors:
        els = post.find_elements(By.CSS_SELECTOR, sel)
        print(f"Selector {sel} tìm thấy {len(els)} elements")
        for el in els:
            print("----", (el.text or '').strip()[:80])

    for sel in selectors:
        for el in post.find_elements(By.CSS_SELECTOR, sel):
            try:
                t = (el.get_attribute("textContent") or "").strip()
                if t:
                    segs.append(t)
            except Exception:
                continue

    # Khử trùng lặp
    seen, uniq = set(), []
    for s in segs:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq

def crawl_fanpage():
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    # Tuỳ chọn giảm nghi ngờ bot (không bắt buộc)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(service=Service("chromedriver-win64/chromedriver.exe"), options=options)

    driver.get("https://www.facebook.com")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    load_cookies(driver, COOKIES_FILE)
    driver.refresh()
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    # Vào fanpage
    driver.get(PAGE_URL)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed'], div[role='main']"))
    )

    # Cuộn để tải bài và chờ “ổn định”
    prev = 0         # số bài đã load (0 ban đầu)
    num_scroll = 1   # số lần cuộn, chỉnh theo nhu cầu
    for _ in range(num_scroll):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3 + random.random())
        cur = len(driver.find_elements(By.CSS_SELECTOR, "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z"))
        if cur == prev:
            # Nếu sau khi cuộn không tăng số bài post, chờ thêm chút cho FB load
            time.sleep(1.0)
        prev = cur

    posts = driver.find_elements(By.CSS_SELECTOR, "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z")
    print(f"🔎 Tìm thấy {len(posts)} bài viết")

    posts_data = []
    
    for post in posts[:crawl_post]:
        try:
            permalink = clean_post_url(pick_post_link(post))
            segs = extract_post_text_segments(driver, post)
            if not segs:
                continue
            permalink = pick_post_link(post)
            permalink = clean_post_url(permalink)
            posts_data.append({
                "index": len(posts_data) + 1,
                "page_url": PAGE_URL,
                "post_url": permalink or "N/A",
                "segments": segs,
                "post_text": "\n".join(segs)
            })
            print("→", (segs[0] if segs else "")[:50], permalink)   # in thử 50 ký tự đầu:
        except Exception as e:
            # Giữ vòng lặp chạy tiếp, không bỏ cả bài
            print("⚠️ Lỗi xử lý một bài:", e)
            continue

    driver.quit()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=4)
    print(f"✅ Đã lưu {len(posts_data)} bài viết vào {OUTPUT_FILE}")


if __name__ == "__main__":
    crawl_fanpage()
