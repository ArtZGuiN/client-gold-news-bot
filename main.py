import os
import feedparser
from google import genai
import requests
import time
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from time import mktime

# โหลดค่าจากไฟล์ .env
load_dotenv()

RSS_URLS_STR = os.getenv("RSS_URLS", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIME_WINDOW_MINUTES = int(os.getenv("TIME_WINDOW_MINUTES", "60"))

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY is not set.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_recent_news(rss_urls, time_window_minutes):
    rss_list = [url.strip() for url in rss_urls.split(',') if url.strip()]
    now = datetime.now(timezone.utc)
    recent_news = []
    
    for url in rss_list:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_time = datetime.fromtimestamp(mktime(entry.published_parsed), timezone.utc)
                    age_minutes = (now - published_time).total_seconds() / 60
                    
                    if age_minutes <= time_window_minutes:
                        recent_news.append({
                            'title': entry.title,
                            'link': entry.link,
                            'description': getattr(entry, 'description', '')
                        })
                else:
                    # ถ้า Feed ไหนไม่บอกเวลา ให้ดึงมาให้ AI ช่วยคัดกรองก่อน
                    recent_news.append({
                        'title': entry.title,
                        'link': entry.link,
                        'description': getattr(entry, 'description', '')
                    })
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    return recent_news

def summarize_batch_with_gemini(news_items):
    # รวมข่าวทั้งหมดให้เป็นก้อนเดียว และตัดเนื้อหาให้สั้นลง
    news_text = ""
    for i, item in enumerate(news_items, 1):
        # ตัดเนื้อหาให้เหลือแค่ 200 ตัวอักษร เพื่อป้องกันข้อความยาวเกิน Limit AI
        raw_desc = item.get('description', '')
        short_desc = raw_desc[:200] + "..." if len(raw_desc) > 200 else raw_desc
        
        news_text += f"\n[{i}] หัวข้อ: {item['title']}\nเนื้อหา: {short_desc}\nลิงก์: {item['link']}\n"

    prompt = f"""
    คุณคือนักวิเคราะห์ข่าวเศรษฐกิจและตลาดทองคำมืออาชีพ (Gold Market Analyst)
    
    รายชื่อข่าวทั้งหมดที่เพิ่งออกในช่วงที่ผ่านมามีดังนี้:
    {news_text}
    
    คำสั่งของคุณ:
    1. ให้คัดเลือก "เฉพาะข่าวที่สำคัญและส่งผลกระทบต่อราคาทองคำ" (เช่น ข่าวราคาทองคำ, นโยบายดอกเบี้ย Fed, เงินเฟ้อสหรัฐ, หรือสงคราม/ภูมิรัฐศาสตร์) 
    2. คัดมาเฉพาะข่าวระดับ Top Impact เท่านั้น (ไม่เกิน 3-5 ข่าว) ข่าวขยะ ข่าวเหล็ก ทองแดง สังกะสี แบตเตอรี่ (ที่ไม่เกี่ยวกับทอง) ให้คุณละทิ้งไปให้หมด
    3. หากในรายชื่อนี้ **ไม่มีข่าวที่ส่งผลต่อทองคำเลย** หรือมีแต่ข่าวที่ไม่สำคัญ ให้คุณพิมพ์ตอบกลับมาคำเดียวสั้นๆ ว่า "SKIP" ห้ามแต่งเรื่องเพิ่ม
    4. หากมีข่าวสำคัญ ให้สรุปข่าวเหล่านั้นรวมกันเป็น "1 ข้อความสรุป" (ภาษาไทย) ที่อ่านเข้าใจง่ายสำหรับนักเทรด นำเสนอในรูปแบบที่น่าสนใจ มี Emoji ประกอบ 
    5. ตอนท้ายของแต่ละข่าวที่สรุป ให้แนบ 'ลิงก์' ของข่าวนั้นๆ เพื่อให้ลูกค้ากดอ่านต่อได้
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None

def send_to_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token or chat id missing.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True # ปิดรูปพรีวิวเว็บ ป้องกันแชทรก
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def main():
    if not RSS_URLS_STR:
        print("No RSS URLs provided.")
        return
        
    print(f"Fetching news from the last {TIME_WINDOW_MINUTES} minutes...")
    news_items = fetch_recent_news(RSS_URLS_STR, TIME_WINDOW_MINUTES)
    print(f"Found {len(news_items)} recent news items.")
    
    if len(news_items) == 0:
        print("No news to process.")
        return

    print("Sending all news to Gemini for batch filtering and summarization...")
    summary = summarize_batch_with_gemini(news_items)
    
    if summary:
        if summary.strip().upper() == "SKIP":
            print("AI determined there are no important gold news. Skipping telegram message.")
        else:
            send_to_telegram(summary)
            print("Sent consolidated summary to Telegram.")
        
if __name__ == "__main__":
    main()
