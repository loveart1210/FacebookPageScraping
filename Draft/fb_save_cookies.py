import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

CHROMEDRIVER_PATH = "YOUR_CHROMEDRIVER_PATH"  # sửa đường dẫn nếu cần
COOKIES_FILE = "YOUR_COOKIES_FILE.json" # sử dụng extension EditThisCookie V3 để lấy cookies
FB_URL = "https://www.facebook.com/"

def save_cookies(driver, path):
    cookies = driver.get_cookies()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved {len(cookies)} cookies to {path}")

def main():
    opts = Options()
    opts.add_argument("--start-maximized")
    # Không bật headless vì bạn cần thao tác thủ công
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)

    driver.get(FB_URL)
    print("➡️ Mở Facebook. Vui lòng đăng nhập thủ công trong cửa sổ trình duyệt.")
    input("✅ Sau khi login thành công (vào được News Feed), nhấn Enter ở đây để lưu cookies...")

    time.sleep(1.0)  # đợi Facebook load hết
    save_cookies(driver, COOKIES_FILE)
    driver.quit()

if __name__ == "__main__":
    main()
