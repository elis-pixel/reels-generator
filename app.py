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

def create_vertical_video(image_urls, script_text):
    video_duration = 15
    clips_to_composite = []
    
    # Перевіряємо, чи нам передали список
    if isinstance(image_urls, str):
        image_urls = [image_urls]
        
    valid_img_paths = []
    
    # 1. Завантажуємо всі картинки (максимум 3)
    if image_urls:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        for i, url in enumerate(image_urls[:3]):
            try:
                img_response = requests.get(url, headers=headers, timeout=5)
                if img_response.status_code == 200:
                    path = f"temp_news_img_{i}.jpg"
                    with open(path, 'wb') as handler:
                        handler.write(img_response.content)
                    valid_img_paths.append(path)
            except Exception as e:
                print(f"Помилка картинки: {e}")
                
    # 2. Робимо фон і слайди
    if valid_img_paths:
        # Фон беремо з ПЕРШОЇ картинки і розмиваємо його на все відео
        img = Image.open(valid_img_paths[0]).convert("RGB")
        img_ratio = img.width / img.height
        target_ratio = 1080 / 1920
        
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
        
        img_bg = img_bg.filter(ImageFilter.GaussianBlur(radius=30))
        enhancer = ImageEnhance.Brightness(img_bg)
        img_bg = enhancer.enhance(0.3) 
        bg_path = "temp_bg_blurred.jpg"
        img_bg.save(bg_path)
        
        bg_clip = ImageClip(bg_path).with_duration(video_duration).with_fps(24)
        clips_to_composite.append(bg_clip)
        
        # --- МАГІЯ СЛАЙД-ШОУ ---
        num_images = len(valid_img_paths)
        time_per_slide = video_duration / num_images
        
        for i, img_path in enumerate(valid_img_paths):
            slide_clip = ImageClip(img_path).resized(width=900)
            # Кожна картинка стартує у свій час і триває певну частку відео
            slide_clip = slide_clip.with_start(i * time_per_slide).with_duration(time_per_slide).with_position(("center", 350))
            clips_to_composite.append(slide_clip)
            
    else:
        # Якщо картинок взагалі нуль
        bg_clip = ColorClip(size=(1080, 1920), color=(15, 15, 15)).with_duration(video_duration).with_fps(24)
        clips_to_composite.append(bg_clip)

    # 3. Додаємо текст (код без змін)
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '')
    phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    
    if not phrases:
        phrases = ["Новина завантажується..."]

    text_clips = []
    chunk_duration = video_duration / len(phrases)
    current_time = 0
    
    for phrase in phrases:
        wrapped_text = textwrap.fill(phrase, width=22)
        safe_text = wrapped_text + "\n "
        
        txt = TextClip(
            font="font.ttf",
            text=safe_text,
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

# --- БЛОК: ВИБІР НОВИНИ ---
st.markdown("### 📰 Вибір новини")
feed = feedparser.parse("https://denzadnem.com.ua/feed/gn")

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
                
                latest_news = selected_news 
                clean_text = re.sub('<[^<]+>', '', latest_news.summary).strip()
                
                # Пошук картинки (Збираємо список для слайд-шоу)
                found_images = []
                
                if 'enclosures' in latest_news:
                    for enc in latest_news.enclosures:
                        if 'image' in enc.type:
                            found_images.append(enc.href)
                            
                if 'media_content' in latest_news:
                    for media in latest_news.media_content:
                        if 'url' in media:
                            found_images.append(media['url'])
                            
                # Шукаємо всі теги <img> у тексті статті
                if 'content' in latest_news or 'summary' in latest_news:
                    html_source = latest_news.content[0].value if 'content' in latest_news else latest_news.summary
                    soup = BeautifulSoup(html_source, 'html.parser')
                    for img_tag in soup.find_all('img'):
                        if img_tag.get('src') and img_tag['src'] not in found_images:
                            found_images.append(img_tag['src'])
                            
                # Перетворюємо відносні посилання на повні
                original_image_urls = [get_full_image_url(url) for url in found_images]
                
                st.write("✍️ Генеруємо сценарій...")
                
                prompt = f"""Ти креативний контент-мейкер. Напиши текст, який буде з'являтися прямо НА ЕКРАНІ у відео TikTok/Reels. Озвучки не буде, відео читатимуть очима!
ВАЖЛИВО: Видай ЛИШЕ чистий текст для екрану. Розбий його на 3-4 короткі фрази (кожна з нового рядка, через Enter). 
ЖОДНИХ коментарів, жодних позначок часу, жодних слів "Хук", "Суть", "Текст на екрані", "Кадр". Без зірочок (*) і без форматування. Тільки сам текст, який побачить глядач.
Новина: {clean_text}"""

                prompt_desc = f"""Напиши короткий, інтригуючий текст для опису під відео в TikTok/Reels про цю новину. 
Обов'язково додай 5-7 релевантних хештегів (завжди включай #новини #деньзаднем #хмельниччина). 
Пиши простою мовою, без зірочок і складного форматування.
Новина: {clean_text}"""

                script = "Не вдалося згенерувати сценарій. Перевірте API ключ або ліміти."
                social_desc = f"{latest_news.title}\n\nДеталі на сайті!\n#новини #деньзаднем #хмельниччина"

                # 1. Запит до ШІ для тексту відео
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=prompt
                    )
                    if response.text:
                        script = response.text 
                except Exception as e:
                    st.warning(f"Помилка ШІ (сценарій): {e}")
                    
                st.info("⏳ Робимо паузу 5 секунд, щоб не перевантажити сервер...")
                time.sleep(5)
                            
                # 2. Запит до ШІ для опису та хештегів
                try:
                    resp_desc = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=prompt_desc
                    )
                    if resp_desc.text:
                        social_desc = resp_desc.text
                except Exception as e:
                    st.warning(f"Помилка ШІ (опис): {e}")
                
                st.write("🎬 Монтуємо відео...")
                video_path = create_vertical_video(original_image_urls, script)
                
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
                st.subheader("Текст на відео")
                st.text_area("Сценарій (субтитри):", script, height=150)
                
                st.subheader("Опис для соцмереж")
                st.text_area("Скопіюй для публікації (можна редагувати):", social_desc, height=200)
                
        except Exception as e:
            st.error(f"Виникла загальна помилка: {e}")
