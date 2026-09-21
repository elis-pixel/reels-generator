import streamlit as st
import feedparser
import re
import time
import requests
from bs4 import BeautifulSoup
from google import genai
from moviepy import ImageClip, CompositeVideoClip, ColorClip, TextClip

# Налаштування сторінки
st.set_page_config(page_title="Reels Генератор", page_icon="📱")
st.title("🤖 Reels для ДЕНЬ ЗА ДНЕМ")

# Зберігаємо ключ у безпечному полі
api_key = st.text_input("Введіть ключ Gemini API (починається з AQ...):", type="password")

def get_full_image_url(thumb_url):
    if thumb_url:
        return re.sub(r'-\d+x\d+(\.\w+)$', r'\1', thumb_url)
    return None

# Функція тепер приймає і посилання на картинку, і згенерований текст
def create_vertical_video(image_url, script_text):
    # 1. Завантажуємо картинку
    img_data = requests.get(image_url).content
    temp_img_path = "temp_news_img.jpg"
    with open(temp_img_path, 'wb') as handler:
        handler.write(img_data)
        
    # 2. Створюємо базове відео (наприклад, 15 секунд)
    video_duration = 15
    bg_clip = ColorClip(size=(1080, 1920), color=(15, 15, 15)).with_duration(video_duration)
    img_clip = ImageClip(temp_img_path).with_duration(video_duration).resized(width=1080)
    
    # 3. Розбиваємо текст на частини та прибираємо зайві символи
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '')
    phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    
    if not phrases:
        phrases = ["Новина завантажується..."]

    text_clips = []
    chunk_duration = video_duration / len(phrases)
    current_time = 0
    
    for phrase in phrases:
        txt = TextClip(
            font="font.ttf",  # Arial Black - жирний і дуже читабельний
            text=phrase,
            font_size=65,                        # Великий текст
            color='white',
            stroke_color='black',
            stroke_width=3,                      # Товста обводка для контрасту
            method='caption',                    # Дозволяє тексту переноситися на нові рядки
            size=(850, None)                     # Вузький блок, щоб не обрізалися краї
        ).with_position(('center', 1350)).with_start(current_time).with_duration(chunk_duration)
        
        text_clips.append(txt)
        current_time += chunk_duration
        
   # 5. Накладаємо картинку і всі субтитри на фон
    final_video = CompositeVideoClip([bg_clip, img_clip.with_position("center")] + text_clips)
    
    # --- НОВИЙ БЛОК ДЛЯ ПАРНИХ РОЗМІРІВ ---
    w, h = final_video.size
    final_video = final_video.cropped(x1=0, y1=0, x2=w - (w % 2), y2=h - (h % 2))
    # --------------------------------------
    
    output_path = "ready_for_reels.mp4"
    final_video.write_videofile(output_path, fps=24, codec="libx264", audio=False, preset="ultrafast", logger=None)
    return output_path

# Кнопка запуску
if st.button("🚀 Згенерувати контент"):
    if not api_key:
        st.warning("Будь ласка, введіть API ключ для роботи штучного інтелекту.")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            with st.status("Обробка...", expanded=True) as status:
                st.write("🔍 Шукаємо свіжо-випечену новину...")
                feed = feedparser.parse("https://denzadnem.com.ua/feed/")
                
                if not feed.entries:
                    st.error("Не вдалося знайти новини.(")
                else:
                    latest_news = feed.entries[0]
                    clean_text = re.sub('<[^<]+>', '', latest_news.summary).strip()
                    
                    # Пошук картинки
                    image_url = None
                    if 'enclosures' in latest_news:
                        for enc in latest_news.enclosures:
                            if 'image' in enc.type:
                                image_url = enc.href
                                break
                    if not image_url and 'summary' in latest_news:
                        soup = BeautifulSoup(latest_news.summary, 'html.parser')
                        img_tag = soup.find('img')
                        if img_tag and img_tag.get('src'):
                            image_url = img_tag['src']
                            
                    original_image_url = get_full_image_url(image_url)
                    
                    st.write("✍️ Генеруємо сценарій...")
                    prompt = f"""Ти креативний контент-мейкер. Напиши текст, який буде з'являтися прямо НА ЕКРАНІ у відео TikTok/Reels. Озвучки не буде, відео читатимуть очима!
                    ВАЖЛИВО: Видай ЛИШЕ чистий текст для екрану. Розбий його на 3-4 короткі фрази (кожна з нового рядка, через Enter). 
                    ЖОДНИХ коментарів, жодних позначок часу, жодних слів "Хук", "Суть", "Текст на екрані", "Кадр". Без зірочок (*) і без форматування. Тільки сам текст, який побачить глядач.
                    Новина: {clean_text}"""

                    chat = client.chats.create(model='gemini-3.6-flash')
                    script = "Не вдалося згенерувати сценарій через перевантаження серверів."

                    for sproba in range(3):
                        try:
                            response = chat.send_message(prompt)
                            script = response.text
                            break
                        except Exception as e:
                        # Тепер ми ловимо і 503 (перевантаження), і 429 (ліміт запитів)
                            if "503" in str(e) or "429" in str(e):
                                st.warning(f"Сервери Google зайняті або перевищено ліміт запитів. Спроба {sproba + 1} з 3... Чекаємо 15 секунд.")
                                time.sleep(15) # Збільшуємо паузу до 15 секунд, щоб дати API "відпочити"
                            else:
                                raise e
                    
                    st.write("🎬 Монтуємо відео...")
                    video_path = create_vertical_video(original_image_url, script)
                    
                    status.update(label="Готово!", state="complete", expanded=False)
            
            # Виведення результатів на екран
            st.success(f"Новина: {latest_news.title}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Відеофон (9:16)")
                st.video(video_path)
                with open(video_path, "rb") as file:
                    st.download_button("⬇️ Завантажити відео", data=file, file_name="reels_bg.mp4", mime="video/mp4")
                    
            with col2:
                st.subheader("Сценарій / Субтитри")
                st.text_area("Скопіюй цей текст:", script, height=300)
                
        except Exception as e:
            st.error(f"Виникла помилка: {e}")
