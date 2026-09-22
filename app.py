import streamlit as st
import feedparser
import re
import time
import textwrap
from PIL import Image, ImageFilter, ImageEnhance
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
    video_duration = 15
    clips_to_composite = []
    
    # 1. Завантажуємо картинку
    if image_url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            img_response = requests.get(image_url, headers=headers, timeout=10)
            
            if img_response.status_code == 200 and 'image' in img_response.headers.get('Content-Type', ''):
                temp_img_path = "temp_news_img.jpg"
                with open(temp_img_path, 'wb') as handler:
                    handler.write(img_response.content)
                
                # --- СТВОРЮЄМО КІНЕМАТОГРАФІЧНИЙ ФОН ---
                # Відкриваємо картинку і розтягуємо на 1080x1920
                img = Image.open(temp_img_path).convert("RGB")
                img_ratio = img.width / img.height
                target_ratio = 1080 / 1920
                
                # Масштабуємо та обрізаємо зайве, щоб заповнити весь екран
                if img_ratio > target_ratio:
                    new_h = 1920
                    new_w = int(new_h * img_ratio)
                    img_bg = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = (new_w - 1080) / 2
                    img_bg = img_bg.crop((left, 0, left + 1080, 1920))
                else:
                    new_w = 1080
                    new_h = int(new_w / img_ratio)
                    img_bg = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    top = (new_h - 1920) / 2
                    img_bg = img_bg.crop((0, top, 1080, top + 1920))
                
                # Сильно розмиваємо і затемнюємо на 70% (залишаємо 30% яскравості)
                img_bg = img_bg.filter(ImageFilter.GaussianBlur(radius=30))
                enhancer = ImageEnhance.Brightness(img_bg)
                img_bg = enhancer.enhance(0.3) 
                
                bg_path = "temp_bg_blurred.jpg"
                img_bg.save(bg_path)
                
                # Додаємо фон та оригінальну картинку
                bg_clip = ImageClip(bg_path).with_duration(video_duration).with_fps(24)
                img_clip = ImageClip(temp_img_path).with_duration(video_duration).resized(width=900)
                
                clips_to_composite.append(bg_clip)
                # Підняли картинку трохи вгору, щоб внизу було місце для тексту
                clips_to_composite.append(img_clip.with_position(("center", 350)))
                
        except Exception as e:
            print(f"Помилка завантаження картинки: {e}")
            
    # Якщо картинка не завантажилася, робимо чорний фон
    if not clips_to_composite:
        bg_clip = ColorClip(size=(1080, 1920), color=(15, 15, 15)).with_duration(video_duration).with_fps(24)
        clips_to_composite.append(bg_clip)

    # 2. РОБОТА З ТЕКСТОМ (Розумний перенос)
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '')
    phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    
    if not phrases:
        phrases = ["Новина завантажується..."]

    text_clips = []
    chunk_duration = video_duration / len(phrases)
    current_time = 0
    
    for phrase in phrases:
        # Розумно розбиваємо рядок по словах (максимум 22 символи на рядок)
        wrapped_text = textwrap.fill(phrase, width=22)
        
        # МАГІЧНИЙ ТРЮК: Додаємо новий рядок і пробіл знизу ("\n "), 
        # щоб сервер гарантовано не відрізав нижню частину тексту
        safe_text = wrapped_text + "\n "
        
        txt = TextClip(
            font="font.ttf",
            text=safe_text,       # Використовуємо наш текст із "подушкою безпеки"
            font_size=60,         
            color='white',
            stroke_color='black',
            stroke_width=2.5,
            method='label'        
        ).with_position(('center', 1250)).with_start(current_time).with_duration(chunk_duration)
        
        text_clips.append(txt)
        current_time += chunk_duration
        
    clips_to_composite.extend(text_clips)
    final_video = CompositeVideoClip(clips_to_composite).with_fps(24)
    
    # 3. Гарантуємо парні розміри і зберігаємо
    w, h = final_video.size
    final_video = final_video.cropped(x1=0, y1=0, x2=int(w - (w % 2)), y2=int(h - (h % 2)))
    
    output_path = "ready_for_reels.mp4"
    final_video.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        preset="ultrafast", 
        threads=1, 
        ffmpeg_params=["-pix_fmt", "yuv420p"], 
        logger=None
    )
    return output_path

# --- НОВИЙ БЛОК: ВИБІР НОВИНИ ---
st.markdown("### 📰 Вибір новини")
feed = feedparser.parse("https://denzadnem.com.ua/feed/")

if not feed.entries:
    st.error("Не вдалося завантажити новини. Перевірте з'єднання.")
    selected_news = None
else:
    # Беремо останні 15 новин
    recent_news = feed.entries[:15]
    # Створюємо словник (Заголовок -> сама новина)
    news_options = {entry.title: entry for entry in recent_news}
    
    # Випадаючий список у Streamlit
    selected_title = st.selectbox("Оберіть новину для створення відео:", list(news_options.keys()))
    selected_news = news_options[selected_title]

# Кнопка запуску
if st.button("🚀 Згенерувати контент"):
    if not api_key:
        st.warning("Будь ласка, введіть API ключ для роботи штучного інтелекту.")
    elif not selected_news:
        st.error("Будь ласка, оберіть новину зі списку.")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            with st.status("Обробка...", expanded=True) as status:
                st.write(f"🔍 Аналізуємо обрану новину...")
                
                # Замість першої новини беремо ту, яку ти обрала у списку!
                latest_news = selected_news 
                clean_text = re.sub('<[^<]+>', '', latest_news.summary).strip()
                
                # --- Далі старий код  ---
                    
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

                    # Використовуємо твою робочу версію моделі
                    chat = client.chats.create(model='gemini-3.6-flash')
                    script = "Не вдалося згенерувати сценарій через перевантаження серверів."

                    for sproba in range(3):
                        try:
                            response = chat.send_message(prompt)
                            # ВАЖЛИВО: зберігаємо відповідь саме у змінну script!
                            script = response.text 
                            break
                        except Exception as e:
                            if "503" in str(e) or "429" in str(e):
                                st.warning(f"Сервери Google зайняті. Спроба {sproba + 1} з 3... Чекаємо 15 секунд.")
                                time.sleep(15)
                            else:
                                raise e
                    
                    st.write("🎬 Монтуємо відео...")
                    # Передаємо наш успішний script у відео
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
