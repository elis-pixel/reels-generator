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
    # 1. Створюємо базове відео (одразу задаємо FPS для стабільності)
    video_duration = 15
    bg_clip = ColorClip(size=(1080, 1920), color=(15, 15, 15)).with_duration(video_duration).with_fps(24)
    
    clips_to_composite = [bg_clip]
    
    # 2. Безпечно завантажуємо картинку (імітуємо звичайний браузер, щоб сайт не блокував)
    if image_url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            img_response = requests.get(image_url, headers=headers, timeout=10)
            
            # Перевіряємо, чи це дійсно картинка, а не сторінка з помилкою
            if img_response.status_code == 200 and 'image' in img_response.headers.get('Content-Type', ''):
                temp_img_path = "temp_news_img.jpg"
                with open(temp_img_path, 'wb') as handler:
                    handler.write(img_response.content)
                
                img_clip = ImageClip(temp_img_path).with_duration(video_duration).resized(width=1080)
                clips_to_composite.append(img_clip.with_position("center"))
        except Exception as e:
            print(f"Помилка завантаження картинки: {e}")
            # Якщо картинка не завантажилась, відео згенерується просто на чорному фоні
            
    # 3. Розбиваємо текст на частини
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '')
    phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    
    if not phrases:
        phrases = ["Новина завантажується..."]

    text_clips = []
    chunk_duration = video_duration / len(phrases)
    current_time = 0
    
    for phrase in phrases:
        txt = TextClip(
            font="font.ttf",
            text=phrase,
            font_size=65,
            color='white',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(850, None)
        ).with_position(('center', 1350)).with_start(current_time).with_duration(chunk_duration)
        
        text_clips.append(txt)
        current_time += chunk_duration
        
    # 4. Збираємо всі шари разом
    clips_to_composite.extend(text_clips)
    final_video = CompositeVideoClip(clips_to_composite).with_fps(24)
    
    # 5. Зберігаємо (з обмеженням потоків для слабких серверів)
    output_path = "ready_for_reels.mp4"
    final_video.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        preset="ultrafast", 
        threads=1,            # Найважливіший параметр: рендер в 1 потік, щоб сервер не "падав"
        ffmpeg_params=["-pix_fmt", "yuv420p"], 
        logger=None
    )
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

                    chat = client.chats.create(model='gemini-1.5-flash')
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
