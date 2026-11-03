import streamlit as st
import feedparser
import re
import time
import os
import textwrap
import requests
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from google import genai
from moviepy import VideoClip

st.set_page_config(page_title="Reels Генератор — День за Днем", page_icon="📰", layout="wide")
st.title("📰 Новини для ДЕНЬ ЗА ДНЕМ (Reels / TikTok)")

api_key = st.text_input("Введіть ключ Gemini API (починається з AQ...):", type="password")

WIDTH = 1080
HEIGHT = 1920

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
    'Referer': 'https://denzadnem.com.ua/'
}

def get_best_font(size, bold=True):
    candidates = [
        "font.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()

def create_news_background():
    """Створює стриманий сучасний графітовий фон з легким патерном"""
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (18, 20, 26, 255))
    draw = ImageDraw.Draw(canvas)
    
    # Геометрична сітка
    for x in range(30, WIDTH, 40):
        for y in range(30, HEIGHT, 40):
            draw.ellipse([x-1, y-1, x+1, y+1], fill=(255, 255, 255, 8))
            
    # М'яка віньєтка
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for y in range(180):
        a = int((1 - y/180) * 110)
        v_draw.line([(0, y), (WIDTH, y)], fill=(10, 12, 16, a))
        v_draw.line([(0, HEIGHT - y), (WIDTH, HEIGHT - y)], fill=(10, 12, 16, a))
    canvas = Image.alpha_composite(canvas, vignette)
    
    # Офіційна плашка медіа зверху
    font_logo = get_best_font(38, bold=True)
    font_category = get_best_font(28, bold=True)
    font_small = get_best_font(24, bold=False)
    
    h_box = Image.new("RGBA", (WIDTH, 140), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(h_box)
    
    h_draw.rectangle([50, 40, WIDTH - 50, 115], fill=(26, 30, 40), outline=(255, 255, 255, 30), width=1)
    # Червоний бейдж "НОВИНИ"
    h_draw.rectangle([50, 40, 250, 115], fill=(225, 40, 40))
    h_draw.text((150, 77), "НОВИНИ", font=font_category, fill=(255, 255, 255), anchor="mm")
    # Назва видання
    h_draw.text((280, 77), "ДЕНЬ ЗА ДНЕМ", font=font_logo, fill=(255, 255, 255), anchor="lm")
    # Домен
    h_draw.text((WIDTH - 80, 77), "denzadnem.com.ua", font=font_small, fill=(160, 175, 195), anchor="rm")
    
    canvas.paste(h_box, (0, 0), h_box)
    return canvas

def create_clean_photo_frame(img_path):
    """Створює чисту білу рамку навколо фото статті"""
    try:
        src = Image.open(img_path).convert("RGBA")
    except Exception:
        src = Image.new("RGBA", (800, 600), (45, 52, 68, 255))
        
    target_w = 940
    aspect = src.height / src.width
    target_h = int(target_w * aspect)
    if target_h > 920:
        target_h = 920
        target_w = int(target_h / aspect)
    src = src.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    border = 14
    fw = target_w + border * 2
    fh = target_h + border * 2
    
    frame = Image.new("RGBA", (fw, fh), (255, 255, 255, 255))
    frame.paste(src, (border, border))
    
    pad = 35
    shadow = Image.new("RGBA", (fw + pad * 2, fh + pad * 2), (0, 0, 0, 0))
    alpha = frame.split()[3]
    dark = Image.new("RGBA", frame.size, (10, 12, 16, 130))
    shadow.paste(dark, (pad + 6, pad + 14), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=16))
    shadow.paste(frame, (pad, pad), frame)
    return shadow

def pre_render_news_sticker(text, font, bg_color, text_color, pad_x=28, pad_y=14):
    """Створює акуратну плашку для тексту"""
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    
    sticker = Image.new("RGBA", (bw + 16, bh + 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sticker)
    draw.rectangle([6, 6, bw + 6, bh + 6], fill=(0, 0, 0, 95))
    draw.rectangle([2, 2, bw + 2, bh + 2], fill=bg_color)
    draw.text((2 + pad_x - bbox[0], 2 + pad_y - bbox[1]), text, font=font, fill=text_color)
    return sticker

def create_vertical_video(image_urls, script_text):
    # Динамічний хронометраж 9 секунд
    video_duration = 9.0
    fps = 20
    output_path = "ready_for_reels.mp4"
    
    if isinstance(image_urls, str):
        image_urls = [image_urls]
        
    valid_img_paths = []
    if image_urls:
        for i, url in enumerate(image_urls[:3]):
            if not url:
                continue
            if url.startswith("http://") or url.startswith("https://"):
                try:
                    img_response = requests.get(url, headers=BROWSER_HEADERS, timeout=6)
                    if img_response.status_code == 200 and len(img_response.content) > 1000:
                        path = f"temp_news_img_{i}.jpg"
                        with open(path, 'wb') as handler:
                            handler.write(img_response.content)
                        valid_img_paths.append(path)
                except Exception as e:
                    print(f"Помилка фото: {e}")
            elif os.path.exists(url):
                valid_img_paths.append(url)
                
    photos = []
    if valid_img_paths:
        for p in valid_img_paths:
            photos.append(create_clean_photo_frame(p))
    else:
        dummy = Image.new("RGB", (800, 600), (35, 42, 54))
        dummy.save("temp_dummy.jpg")
        photos.append(create_clean_photo_frame("temp_dummy.jpg"))
        
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '').replace('«', '').replace('»', '')
    raw_phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    if not raw_phrases:
        raw_phrases = ["Головна подія дня", "Подробиці події на сайті", "Читайте на День за Днем"]
        
    num_phrases = len(raw_phrases)
    time_per_phrase = video_duration / num_phrases
    
    font_sticker = get_best_font(52, bold=True)
    font_small = get_best_font(26, bold=False)
    
    base_bg = create_news_background()
    
    # Підвал
    f_draw = ImageDraw.Draw(base_bg)
    f_draw.line([(60, 1780), (WIDTH - 60, 1780)], fill=(60, 65, 80), width=1)
    f_draw.text((WIDTH // 2, 1825), "Більше новин на сайті denzadnem.com.ua", font=font_small, fill=(180, 190, 205), anchor="mm")

    # Палітра новинних плашок
    news_colors = [
        ((255, 215, 0), (15, 15, 15)),   # Жовтий новинний
        ((255, 255, 255), (15, 15, 15)), # Чистий білий
        ((225, 40, 40), (255, 255, 255)) # Червоний
    ]

    timeline_states = []

    for p_idx, phrase_text in enumerate(raw_phrases):
        p_start = p_idx * time_per_phrase
        
        # Обгортання ТІЛЬКИ ЦІЛИМИ СЛОВАМИ
        wrapped_lines = textwrap.wrap(phrase_text, width=22)[:3]
        
        p_canvas = base_bg.copy()
        photo = photos[p_idx % len(photos)]
        px = (WIDTH - photo.width) // 2
        p_canvas.paste(photo, (px, 155), photo)
        
        y_pos = 1240
        line_stickers = []
        for l_idx, line in enumerate(wrapped_lines):
            bg_c, txt_c = news_colors[l_idx % len(news_colors)]
            stk = pre_render_news_sticker(line.upper(), font_sticker, bg_c, txt_c)
            sx = int(WIDTH // 2 - stk.width / 2)
            line_stickers.append((stk, sx, y_pos))
            y_pos += 115
            
        # Швидка поява тексту (0.35 с)
        s1 = p_canvas.copy()
        if len(line_stickers) > 0:
            stk, sx, sy = line_stickers[0]
            s1.paste(stk, (sx, sy), stk)
            
        s2 = s1.copy()
        if len(line_stickers) > 1:
            stk, sx, sy = line_stickers[1]
            s2.paste(stk, (sx, sy), stk)
            
        s3 = s2.copy()
        if len(line_stickers) > 2:
            stk, sx, sy = line_stickers[2]
            s3.paste(stk, (sx, sy), stk)
            
        timeline_states.append({"t_start": p_start, "img": s1})
        timeline_states.append({"t_start": p_start + 0.35, "img": s2})
        timeline_states.append({"t_start": p_start + 0.70, "img": s3})

    timeline_states.sort(key=lambda s: s["t_start"])

    def make_frame(t):
        chosen = timeline_states[0]["img"]
        for s in timeline_states:
            if t >= s["t_start"]:
                chosen = s["img"]
            else:
                break
        frame = chosen.copy()
        draw = ImageDraw.Draw(frame)
        # Червоний індикатор прогресу зверху
        draw.rectangle([0, 0, WIDTH, 10], fill=(30, 34, 44))
        prog = min(1.0, max(0.0, t / video_duration))
        draw.rectangle([0, 0, int(WIDTH * prog), 10], fill=(225, 40, 40))
        return np.array(frame.convert("RGB"))

    clip = VideoClip(make_frame, duration=video_duration).with_fps(fps)
    clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        preset="ultrafast",
        audio=False,
        threads=2,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None
    )
    return output_path

# --- ВИБІР НОВИНИ ---
st.markdown("### 📰 Вибір новини")
feed = feedparser.parse("https://denzadnem.com.ua/feed/gn")

if not feed.entries:
    st.error("Не вдалося завантажити новини. Перевірте з'єднання.")
    selected_news = None
else:
    recent_news = feed.entries[:15]
    news_options = {entry.title: entry for entry in recent_news}
    selected_title = st.selectbox("Оберіть новину для створення відео:", list(news_options.keys()))
    selected_news = news_options[selected_title]

# --- КНОПКА ЗАПУСКУ ---
if st.button("🚀 Згенерувати контент"):
    if not api_key:
        st.warning("Будь ласка, введіть API ключ для роботи штучного інтелекту.")
    elif not selected_news:
        st.error("Будь ласка, оберіть новину зі списку.")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            with st.status("Обробка...", expanded=True) as status:
                st.write("🔍 Завантажуємо статтю та фото з сайту...")
                latest_news = selected_news 
                clean_text = re.sub('<[^<]+>', '', latest_news.summary).strip()
                
                # Фото зі сторінки статті
                found_images = []
                if hasattr(latest_news, 'link') and latest_news.link:
                    try:
                        art_resp = requests.get(latest_news.link, headers=BROWSER_HEADERS, timeout=5)
                        if art_resp.status_code == 200:
                            art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                            og_img = art_soup.find('meta', property='og:image')
                            if og_img and og_img.get('content'):
                                found_images.append(og_img['content'])
                            for img_tag in art_soup.find_all('img'):
                                src = img_tag.get('src')
                                if src and 'uploads' in src and src not in found_images:
                                    found_images.append(src)
                    except Exception as e:
                        print(f"Помилка парсингу: {e}")

                st.write("✍️ Генеруємо текст...")
                prompt = f"""Ти редактор новинного сайту. Напиши 3 короткі тези новини для екрану TikTok/Reels. 
Кожна теза з нового рядка. До 5-7 слів у рядку. Без знаків оклику, без зірочок, без клікбейту — просто чітка суть новини!
Новина: {clean_text}"""

                prompt_desc = f"""Напиши короткий новинний опис для TikTok до цієї новини з 5-7 хештегами (#новини #деньзаднем #хмельниччина).
Новина: {clean_text}"""

                words_title = latest_news.title.split()
                line1 = " ".join(words_title[:6])
                line2 = " ".join(words_title[6:12]) if len(words_title) > 6 else "Подробиці події в регіоні"
                line3 = "Деталі читайте на сайті ДЕНЬ ЗА ДНЕМ"
                script = f"{line1}\n{line2}\n{line3}"
                social_desc = f"{latest_news.title}\n\nДеталі читайте на сайті!\n#новини #деньзаднем #хмельниччина"

                models_to_try = ['gemini-3.8-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
                for m_name in models_to_try:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=prompt
                        )
                        if response.text and len(response.text.strip()) > 10:
                            script = response.text.strip()
                            break
                    except Exception:
                        continue
                            
                time.sleep(1)
                st.write("📝 Генеруємо опис...")
                for m_name in models_to_try:
                    try:
                        resp_desc = client.models.generate_content(
                            model=m_name,
                            contents=prompt_desc
                        )
                        if resp_desc.text:
                            social_desc = resp_desc.text.strip()
                            break
                    except Exception:
                        continue
                
                st.write("🎬 Збираємо новинне відео...")
                video_path = create_vertical_video(found_images, script)
                status.update(label="Готово!", state="complete", expanded=False)
            
            st.success(f"Новина: {latest_news.title}")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Новинне відео (9:16)")
                st.video(video_path)
                with open(video_path, "rb") as file:
                    st.download_button("⬇️ Завантажити відео", data=file, file_name="reels_news.mp4", mime="video/mp4")
                    
            with col2:
                st.subheader("Текст на відео")
                st.text_area("Сценарій (субтитри):", script, height=150)
                
                st.subheader("Опис для соцмереж")
                st.text_area("Скопіюй для публікації (можна редагувати):", social_desc, height=200)
                
        except Exception as e:
            st.error(f"Виникла помилка: {e}")
