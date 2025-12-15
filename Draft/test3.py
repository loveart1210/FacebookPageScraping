# fb_scrape_requests.py
import json
import time
import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import requests
from bs4 import BeautifulSoup

COOKIES_FILE = "cookies.json"        # file do fb_save_cookies.py tạo ra
OUTPUT_FILE = "hnmu_posts_mb.json"
PAGE_M_BASIC = "https://mbasic.facebook.com/profile.php?id=61555234277669"

# ---------- cookie loader (hỗ trợ Selenium output) ----------
def load_cookies_to_session(session, cookies_file):
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    count = 0
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = c.get("domain")
        path = c.get("path", "/")
        # requests' cookies.set chấp nhận domain param; nếu domain None -> no domain set
        if domain:
            session.cookies.set(name, value, domain=domain, path=path)
        else:
            session.cookies.set(name, value, path=path)
        count += 1
    print(f"Loaded {count} cookies into session (cookie jar size: {len(session.cookies)})")

# ---------- check login ----------
def is_logged_in(session, test_url="https://mbasic.facebook.com/"):
    try:
        r = session.get(test_url, timeout=20)
    except Exception as e:
        return False, f"request error: {e}"
    if r.status_code != 200:
        return False, f"status {r.status_code}"
    html = r.text.lower()
    # heuristic: nếu thấy "log in" form hoặc "email or phone" thì là logged out
    if "log in to facebook" in html or "email or phone" in html or "đăng nhập" in html:
        return False, "login page detected"
    # else assume logged in
    return True, "ok"

# ---------- helpers ----------
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

TIME_RE = re.compile(r"^\d+\s*(s|m|h|d|w|y)$", re.I)
NOISE_WORDS = {"like","reply","share","comment","send","follow","thích","trả lời","chia sẻ","bình luận"}
def is_noise_line(s):
    s = s.strip()
    if not s:
        return True
    if TIME_RE.match(s):
        return True
    if s.isdigit():
        return True
    if s.lower() in NOISE_WORDS:
        return True
    if len(s) <= 2:
        return True
    return False

# ---------- parsing per-article ----------
def extract_segments_from_article(soup_article):
    """
    Trả về danh sách đoạn text (post + inline comments) đã lọc rác.
    """
    segments = []
    used = set()

    # Thử ưu tiên vùng story_body_container nếu có
    body = soup_article.select_one("div.story_body_container")
    candidates = body.find_all(["div","span"], recursive=True) if body else soup_article.find_all(["div","span"], recursive=True)

    for el in candidates:
        try:
            text = el.get_text(separator=" ", strip=True)
            if not text:
                continue
            text = re.sub(r"\s+", " ", text).strip()
            if is_noise_line(text):
                continue
            if text in used:
                continue
            used.add(text)
            segments.append(text)
        except Exception:
            continue

    # Fallback: nếu không có gì, lấy toàn bộ article text
    if not segments:
        all_text = soup_article.get_text(separator="\n", strip=True)
        all_text = re.sub(r"\s+", " ", all_text).strip()
        if all_text:
            segments = [all_text]
    return segments

def parse_feed_page(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    # mbasic thường có div[data-ft] cho từng post
    articles = soup.select("article, div[data-ft], div[role='article']")
    if not articles:
        # fallback
        articles = soup.find_all("div")
    results = []
    for art in articles:
        try:
            # tìm permalink (nhiều khi a tag đầu là permalink)
            a = art.find("a", href=True)
            post_url = clean_post_url(urljoin(base_url, a["href"])) if a else None
            segments = extract_segments_from_article(art)
            if not segments:
                continue
            results.append({
                "post_url": post_url or "N/A",
                "segments": segments,
                "post_text": "\n".join(segments)
            })
        except Exception:
            continue
    return results

# ---------- main ----------
def main():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
    })

    load_cookies_to_session(s, COOKIES_FILE)
    ok, note = is_logged_in(s)
    print("Login check:", ok, note)
    if not ok:
        print("Cookies không hợp lệ/đã hết hạn. Hãy chạy fb_save_cookies.py để tạo cookies mới.")
        return

    print("Requesting feed:", PAGE_M_BASIC)
    r = s.get(PAGE_M_BASIC, timeout=20)
    if r.status_code != 200:
        print("Request failed:", r.status_code)
        return

    results = parse_feed_page(r.text, PAGE_M_BASIC)
    print("Found posts:", len(results))
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved to", OUTPUT_FILE)

if __name__ == "__main__":
    main()
