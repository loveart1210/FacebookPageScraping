import pandas as pd
import json
import time
import logging
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import os

# Cấu hình logging
logging.basicConfig(
    filename='processing.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w',  # Ghi đè file log mỗi lần chạy
    encoding='utf-8'
)

genai.configure(api_key="AIzaSyAY76hftIXFHe9zxXPR00FYePmoZQ1TLZg")
model = genai.GenerativeModel('gemini-2.0-flash')

def detect_abbreviations(post_text, index):
    """
    Phát hiện các từ viết tắt hoặc thuật ngữ/ký hiệu không rõ ràng trong nội dung bài viết.
    Trả về danh sách các từ viết tắt duy nhất hoặc danh sách rỗng nếu không tìm thấy.
    Ghi log lỗi nếu xảy ra.
    """
    try:
        prompt = f"""
        Phân tích văn bản tiếng Việt sau từ bài viết Facebook và xác định các từ viết tắt, thuật ngữ, hoặc ký hiệu không rõ ràng về ngữ nghĩa (ví dụ: 'ad', 'ib', 'tt', 'rep'). 
        Chỉ trả về danh sách các từ viết tắt hoặc thuật ngữ, không kèm giải thích. 
        Nếu không tìm thấy, trả về danh sách rỗng.
        Văn bản: {post_text}
        """
        response = model.generate_content(prompt)
        # Giả định phản hồi là danh sách các thuật ngữ hoặc rỗng
        abbreviations = response.text.strip().split('\n') if response.text else []
        # Loại bỏ trùng lặp và các chuỗi rỗng
        abbreviations = list(set([term.strip() for term in abbreviations if term.strip()]))
        return abbreviations
    except Exception as e:
        logging.error(f"Lỗi khi xử lý văn bản tại index {index}: {str(e)}")
        print(f"Lỗi tại index {index}: {str(e)}")
        return []
    
def process_excel_file(input_file, output_file):
    """
    Xử lý file Excel để phát hiện các từ viết tắt và lưu kết quả vào file JSON.
    Ghi log tiến độ và lỗi theo thời gian thực.
    """
    # Đọc file Excel
    try:
        df = pd.read_excel(input_file)
        logging.info("Đọc file Excel thành công")
    except Exception as e:
        logging.error(f"Lỗi khi đọc file Excel: {str(e)}")
        print(f"Lỗi khi đọc file Excel: {str(e)}")
        return

    # Xác minh các cột bắt buộc
    required_columns = ['index', 'Page URL', 'Page Name', 'Post URL', 'Post Text']
    if not all(col in df.columns for col in required_columns):
        error_msg = f"File Excel thiếu một hoặc nhiều cột bắt buộc: {required_columns}"
        logging.error(error_msg)
        print(error_msg)
        return

    # Danh sách lưu kết quả
    results = []
    request_count = 0
    start_time = time.time()
    total_rows = len(df)  # Tổng số dòng trong file Excel
    processed_rows = 0    # Số dòng đã xử lý

    logging.info(f"Bắt đầu xử lý {total_rows} dòng dữ liệu")

    # Xử lý từng dòng
    for _, row in df.iterrows():
        index = int(row['index'])
        # Kiểm tra giới hạn API: 10 yêu cầu trong 60 giây
        if request_count >= 10:
            elapsed_time = time.time() - start_time
            if elapsed_time < 60:
                sleep_time = 60 - elapsed_time
                logging.info(f"Đã đạt giới hạn 10 yêu cầu, tạm dừng {sleep_time:.2f} giây")
                print(f"Đã đạt giới hạn 10 yêu cầu, tạm dừng {sleep_time:.2f} giây...")
                time.sleep(sleep_time)
            request_count = 0
            start_time = time.time()

        # Lấy nội dung Post Text
        post_text = str(row['Post Text']) if pd.notnull(row['Post Text']) else ""
        abbreviations = detect_abbreviations(post_text, index) if post_text else []
        
        # Tăng số đếm yêu cầu API
        request_count += 1

        # Tạo bản ghi kết quả
        result = {
            "index": index,
            "Page URL": str(row['Page URL']),
            "Page Name": str(row['Page Name']),
            "Post URL": str(row['Post URL']),
            "Post Text": post_text,
            "Abbreviation": abbreviations
        }
        results.append(result)

        # Tăng số dòng đã xử lý và ghi log tiến độ
        processed_rows += 1
        logging.info(f"Đã xử lý {processed_rows}/{total_rows} dòng (Index: {index})")
        print(f"Đã xử lý {processed_rows}/{total_rows} dòng (Index: {index})")

        # Tạm dừng 2 giây giữa các yêu cầu API
        time.sleep(2)

    # Ghi kết quả ra file JSON
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logging.info(f"Kết quả đã được lưu vào {output_file}")
        print(f"Kết quả đã được lưu vào {output_file}")
    except Exception as e:
        logging.error(f"Lỗi khi ghi file JSON: {str(e)}")
        print(f"Lỗi khi ghi file JSON: {str(e)}")
        
# Thực thi chương trình
if __name__ == "__main__":
    input_file = "../../Facebook Page Posts Scraping/Clean Data/output/Confessions of HNMU.xlsx"
    output_file = "output/Confessions of HNMU.json"
    process_excel_file(input_file, output_file)