import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

PAGE_NAME = "hnmuconfessions"
OUTPUT_FILE = "hnmu_posts.json"
COOKIES_FILE = "cookies.json"   # cookies export từ EditThisCookie (JSON)

def load_cookies(driver, cookies_file):
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)
        for cookie in cookies:
            # Selenium yêu cầu một số key nhất định
            cookie_dict = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie["path"]
            }
            if "expiry" in cookie:
                cookie_dict["expiry"] = cookie["expiry"]
            try:
                driver.add_cookie(cookie_dict)
            except Exception as e:
                print(f"⚠️ Không thêm được cookie {cookie['name']}: {e}")
                
def crawl_fanpage():
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(service=Service("chromedriver-win64/chromedriver.exe"), options=options)

    # 1. Mở Facebook trước (phải load ít nhất 1 lần domain)
    driver.get("https://www.facebook.com")
    time.sleep(3)

    # 2. Nạp cookies đã export
    load_cookies(driver, COOKIES_FILE)
    driver.refresh()
    time.sleep(3)

    # 3. Truy cập fanpage
    driver.get(f"https://www.facebook.com/{PAGE_NAME}")
    time.sleep(5)

    # 4. Cuộn xuống để load nhiều bài
    for _ in range(5):  # tăng số lần để lấy nhiều bài hơn
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

    # 5. Lấy các bài viết
    posts_data = []
    posts = driver.find_elements(By.XPATH, "//div[@role='article']")
    print(f"🔎 Tìm thấy {len(posts)} bài viết")

    for post in posts:
        try:
            text = post.text
            url_element = post.find_element(By.XPATH, ".//a[contains(@href,'/posts/')]")
            post_url = url_element.get_attribute("href")

            posts_data.append({
                "page_name": PAGE_NAME,
                "page_url": f"https://www.facebook.com/{PAGE_NAME}",
                "post_url": post_url,
                "post_text": text,
            })
        except Exception:
            continue

    driver.quit()

    # 6. Lưu file JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=4)

    print(f"✅ Đã lưu {len(posts_data)} bài viết vào {OUTPUT_FILE}")
    
if __name__ == "__main__":
    crawl_fanpage()
