import os
import feedparser
from google import genai
import requests
import time
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from time import mktime

# โหลดค่าจากไฟล์ .env (ถ้ามี)
load_dotenv()

RSS_URLS_STR = os.getenv("RSS_URLS", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIME_WINDOW_MINUTES = int(os.getenv("TIME_WINDOW_MINUTES", "60"))
AI_PERSONA = os.getenv("AI_PERSONA", "คุณคือนักข่าวเทคโนโลยีสาย AI (Artificial Intelligence)")
CUSTOM_INSTRUCTION = os.getenv("CUSTOM_INSTRUCTION", "แปลหัวข้อข่าวต้นฉบับเป็น 'ภาษาไทย' ให้อ่านง่ายและน่าสนใจ และเขียนสรุปเนื้อหาข่าวแบบลงรายละเอียดให้ได้ใจความครบถ้วน")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY is not set.")
    exit(1)

# ใช้ระบบเชื่อมต่อใหม่ของ Google (google.genai)
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
                            'description': getattr(entry, 'description', ''),
                            'source': getattr(feed.feed, 'title', url)
                        })
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    return recent_news

def summarize_with_gemini(news_item):
    prompt = f"""
    บทบาทของคุณ: {AI_PERSONA}
    
    ข้อมูลข่าว:
    หัวข้อ: {news_item['title']}
    เนื้อหา: {news_item['description']}
    แหล่งที่มา: {news_item['source']}
    
    คำสั่ง: {CUSTOM_INSTRUCTION}
    
    (หากข่าวนี้เป็นเพียงข่าวขยะ, โฆษณา, หรือไม่มีเนื้อหาสาระสำคัญ ให้คุณพิมพ์ตอบกลับมาคำเดียวสั้นๆ ว่า "SKIP" เพื่อให้ระบบข้ามข่าวนี้ไป)
    """
    try:
        # อัปเกรดคำสั่งเรียก AI รุ่นใหม่ล่าสุด
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error summarizing {news_item['title']}: {e}")
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
        "disable_web_page_preview": False
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
    
    for item in news_items:
        print(f"Processing: {item['title']}")
        summary = summarize_with_gemini(item)
        
        if summary:
            if summary.strip().upper() == "SKIP":
                print(f"Skipping junk news: {item['title']}")
                continue
                
            # ส่งเข้า Telegram ทีละข่าว
            message_text = f"🤖 {summary}\n\n🔗 <a href='{item['link']}'>อ่านข่าวเต็มคลิกที่นี่</a>"
            send_to_telegram(message_text)
            print("Sent to Telegram.")
            time.sleep(3) # หน่วงเวลาส่งเพื่อป้องกันสแปม
        
if __name__ == "__main__":
    main()
