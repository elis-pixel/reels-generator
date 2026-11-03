import streamlit as st
import feedparser
import re
import time
import textwrap
import os
import requests
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from google import genai
from moviepy import VideoClip

# Налаштування сторінки Streamlit
st.set_page_config(
    page_title="Reels Генератор | День за днем",
    page_icon="📱",
    layout="wide"
)

st.title("🤖 Новинний Reels Генератор — «ДЕНЬ ЗА ДНЕМ»")
st.caption("Автоматичне створення стильних вертикальних відео для TikTok / Instagram Reels за 1 клік")

# Введення API ключа
api_key = st.text_input("Введіть ключ Gemini API:", type="password")

WIDTH = 1080
HEIGHT = 1920

def get_font(size, bold=True):
    """Підбирає відповідний шрифт для Windows, Linux (Streamlit Cloud) або MacOS."""
    candidates = [
        "font_bold.ttf" if bold else "font.ttf",
        "font.ttf",
        # Windows
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        # Linux (Streamlit Cloud)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        # macOS
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()

def get_article_main_image(article_url):
    """
    Витягує виключно офіційне головне зображення статті через OpenGraph.
    Уникає мініатюр з сайдбару та інших матеріалів.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://denzadnem.com.ua/'
    }
    try:
        res = requests.get(article_url, headers=headers, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # 1. Головне OpenGraph фото статті
            og_img = soup.find('meta', property='og:image')
            if og_img and og_img.get('content'):
                return og_img['content']
            # 2. Twitter card фото
            tw_img = soup.find('meta', attrs={'name': 'twitter:image'})
            if tw_img and tw_img.get('content'):
                return tw_img['content']
            # 3. Фото безпосередньо з контенту публікації
            entry = soup.find('div', class_=re.compile(r'(entry-content|post-content)'))
            if entry:
                img_tag = entry.find('img')
                if img_tag and img_tag.get('src'):
                    return img_tag['src']
    except Exception as e:
        print(f"Помилка отримання фото: {e}")
    return None

def download_image(url, save_path="temp_news_img.jpg"):
    """Завантажує зображення з правильними заголовками проти блокувань."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://denzadnem.com.ua/'
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(res.content)
            return save_path
    except Exception as e:
        print(f"Помилка завантаження фото: {e}")
    return None

def create_news_background():
    """Створює сучасний новинний фон із фірмовою шапкою «День за днем»."""
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (18, 20, 26, 255))
    draw = ImageDraw.Draw(canvas)
    
    # Тонка геометрична сітка
    for x in range(30, WIDTH, 40):
        for y in range(30, HEIGHT, 40):
            draw.ellipse([x-1, y-1, x+1, y+1], fill=(255, 255, 255, 8))
            
    # М'яке віньєтування зверху і знизу
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for y in range(180):
        a = int((1 - y/180) * 110)
        v_draw.line([(0, y), (WIDTH, y)], fill=(10, 12, 16, a))
        v_draw.line([(0, HEIGHT - y), (WIDTH, HEIGHT - y)], fill=(10, 12, 16, a))
    canvas = Image.alpha_composite(canvas, vignette)
    
    # Верхня шапка видання
    h_box = Image.new("RGBA", (WIDTH, 140), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(h_box)
    
    font_category = get_font(28, bold=True)
    font_logo = get_font(38, bold=True)
    font_small = get_font(26, bold=False)
    
    # Контейнер шапки
    h_draw.rectangle([50, 40, WIDTH - 50, 115], fill=(26, 30, 40), outline=(255, 255, 255, 30), width=1)
    # Червоний бейдж НОВИНИ
    h_draw.rectangle([50, 40, 250, 115], fill=(225, 40, 40))
    h_draw.text((150, 77), "НОВИНИ", font=font_category, fill=(255, 255, 255), anchor="mm")
    # Назва видання
    h_draw.text((280, 77), "ДЕНЬ ЗА ДНЕМ", font=font_logo, fill=(255, 255, 255), anchor="lm")
    # Веб-сайт
    h_draw.text((WIDTH - 80, 77), "denzadnem.com.ua", font=font_small, fill=(160, 175, 195), anchor="rm")
    
    canvas.paste(h_box, (0, 0), h_box)
    
    # Нижній колонтитул
    f_draw = ImageDraw.Draw(canvas)
    f_draw.line([(60, 1780), (WIDTH - 60, 1780)], fill=(60, 65, 80), width=1)
    f_draw.text((WIDTH // 2, 1825), "Більше новин на сайті denzadnem.com.ua", font=font_small, fill=(180, 190, 205), anchor="mm")
    
    return canvas

def create_clean_photo_frame(img_path):
    """Формує акуратну фото-рамку з м'якою тінню (без детективних написів)."""
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

def pre_render_news_sticker(text, font, bg_color, text_color, pad_x=26, pad_y=12):
    """Створює контрастну новинну плашку для рядка тексту."""
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

def create_vertical_video(image_path, phrases, output_path="ready_for_reels.mp4"):
    """
    Рендерить динамічне 9-секундне відео:
    - 1 зафіксоване головне фото статті;
    - Адаптивний шрифт без обрізання слів;
    - Почергова динамічна поява плашок (кожні 0.35 с);
    - Червоний прогрес-бар.
    """
    video_duration = 9.0
    fps = 20
    
    bg_canvas = create_news_background()
    photo = create_clean_photo_frame(image_path)
    px = (WIDTH - photo.width) // 2
    bg_canvas.paste(photo, (px, 155), photo)
    
    news_colors = [
        ((255, 215, 0), (15, 15, 15)),   # Жовта плашка
        ((255, 255, 255), (15, 15, 15)), # Біла плашка
        ((225, 40, 40), (255, 255, 255)), # Червона плашка
        ((255, 215, 0), (15, 15, 15))
    ]
    
    num_phrases = len(phrases)
    time_per_phrase = video_duration / max(1, num_phrases)
    
    phrase_data = []
    for p_text in phrases:
        clean = p_text.replace('*', '').replace('_', '').replace('"', '').strip()
        lines = textwrap.wrap(clean, width=24) # Без відкидання рядків
        if not lines:
            lines = [clean]
            
        n = len(lines)
        if n <= 2:
            f_size = 52
            spacing = 115
            y_start = 1260
        elif n == 3:
            f_size = 48
            spacing = 105
            y_start = 1220
        elif n == 4:
            f_size = 42
            spacing = 92
            y_start = 1180
        else:
            f_size = 36
            spacing = 80
            y_start = 1140
            
        font_dyn = get_font(f_size, bold=True)
        
        line_stickers = []
        for i, line in enumerate(lines):
            bg_c, txt_c = news_colors[i % len(news_colors)]
            stk = pre_render_news_sticker(line.upper(), font_dyn, bg_c, txt_c, pad_x=24, pad_y=12)
            line_stickers.append(stk)
            
        phrase_data.append({
            "lines": line_stickers,
            "y_start": y_start,
            "spacing": spacing
        })
        
    def make_frame(t):
        frame = bg_canvas.copy()
        p_idx = min(int(t / time_per_phrase), num_phrases - 1)
        p_info = phrase_data[p_idx]
        t_in_phrase = t - (p_idx * time_per_phrase)
        
        # Почергова швидка поява рядків
        y_pos = p_info["y_start"]
        for l_idx, stk in enumerate(p_info["lines"]):
            t_appear = l_idx * 0.35
            if t_in_phrase >= t_appear:
                sx = int(WIDTH // 2 - stk.width / 2)
                frame.paste(stk, (sx, y_pos), stk)
            y_pos += p_info["spacing"]
            
        # Червоний прогрес-бар угорі
        progress_w = int((t / video_duration) * WIDTH)
        p_draw = ImageDraw.Draw(frame)
        p_draw.rectangle([0, 0, WIDTH, 10], fill=(30, 34, 44))
        p_draw.rectangle([0, 0, progress_w, 10], fill=(225, 40, 40))
        
        return np.array(frame.convert("RGB"))
        
    clip = VideoClip(make_frame, duration=video_duration).with_fps(fps)
    clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        preset="ultrafast",
        threads=2,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None
    )
    return output_path

# ==================== СЕКЦІЯ ВИБОРУ НОВИНИ ====================
st.markdown("### 📰 Вибір новини")
feed = feedparser.parse("https://denzadnem.com.ua/feed/gn")

if not feed.entries:
    st.error("Не вдалося завантажити новини. Перевірте з'єднання з сайтом.")
    selected_news = None
else:
    recent_news = feed.entries[:15]
    news_options = {entry.title: entry for entry in recent_news}
    selected_title = st.selectbox("Оберіть новину для створення відео:", list(news_options.keys()))
    selected_news = news_options[selected_title]

# ==================== КНОПКА ЗАПУСКУ ====================
if st.button("🚀 Згенерувати відео"):
    if not api_key:
        st.warning("⚠️ Будь ласка, введіть API ключ Gemini.")
    elif not selected_news:
        st.error("Будь ласка, оберіть новину зі списку.")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            with st.status("Генерація відео...", expanded=True) as status:
                st.write("🔍 Аналізуємо обрану новину...")
                latest_news = selected_news
                clean_text = re.sub('<[^<]+>', '', latest_news.summary).strip()
                
                # Завантаження виключно офіційного фото статті
                st.write("🖼️ Завантажуємо оригінальне фото статті...")
                article_url = latest_news.link
                img_url = get_article_main_image(article_url)
                
                img_path = None
                if img_url:
                    img_path = download_image(img_url, "temp_article_main.jpg")
                    
                if not img_path or not os.path.exists(img_path):
                    dummy = Image.new("RGB", (940, 600), (35, 42, 54))
                    dummy.save("temp_article_main.jpg")
                    img_path = "temp_article_main.jpg"
                    
                st.write("✍️ Складаємо чіткий новинний сценарій...")
                prompt_script = f"""Ти — професійний редактор сайту "День за днем" для TikTok/Reels.
Напиши сценарій для швидкого динамічного відео (8-10 секунд) за цією новиною.

Заголовок: {latest_news.title}
Текст: {clean_text[:1000]}

ВИМОГИ ДО СЦЕНАРІЮ:
1. Рівно 3 короткі змістовні фрази, кожна з нового рядка.
2. Це СЕРЙОЗНІ НОВИНИ (не детектив, без слів "ексклюзив", "розслідування", "доказ", без жартів).
3. Рядок 1: Головний факт події (що сталося).
4. Рядок 2: Важлива ключова деталь події.
5. Рядок 3: "Подробиці читайте на сайті День за днем"
6. Кожен рядок до 5-8 слів, суто факти, без лапок, зірочок, нумерації та емодзі."""

                # Безпечний виклик моделей з пріоритетом актуальної gemini-3.8-flash
                script_text = ""
                available_models = [
                    "gemini-3.8-flash",
                    "gemini-3-flash",
                    "gemini-2.5-flash",
                    "gemini-2.0-flash"
                ]
                last_err = None
                
                for mod in available_models:
                    try:
                        res = client.models.generate_content(
                            model=mod,
                            contents=prompt_script
                        )
                        if res and res.text:
                            script_text = res.text.strip()
                            break
                    except Exception as e:
                        last_err = e
                        continue
                        
                # Якщо ШІ тимчасово недоступний або лімітований, створюємо фрази з самої статті
                if not script_text:
                    st.info("ℹ️ Формуємо текст субтитрів безпосередньо з обраної новини...")
                    p1 = re.sub(r'[\r\n]+', ' ', latest_news.title).strip()
                    sentences = [s.strip() for s in re.split(r'[.!?]+', clean_text) if len(s.strip()) > 15 and len(s.strip()) < 90]
                    p2 = sentences[0] if sentences else "Подробиці події на Хмельниччині з'ясовують правоохоронці"
                    p3 = "Подробиці читайте на сайті День за днем"
                    phrases = [p1, p2, p3]
                else:
                    phrases = [p.strip() for p in script_text.split('\n') if len(p.strip()) > 3]
                    if len(phrases) < 2:
                        phrases = [latest_news.title, "Подробиці читайте на сайті День за днем"]
                    
                st.write("🎬 Рендеримо відео...")
                video_file = create_vertical_video(img_path, phrases, "ready_for_reels.mp4")
                
                status.update(label="✅ Відео готове до публікації!", state="complete", expanded=False)

            # Результати
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("### 📱 Попередній перегляд (9:16)")
                st.video(video_file)
                with open(video_file, "rb") as f:
                    st.download_button(
                        label="⬇️ Завантажити відео (MP4)",
                        data=f,
                        file_name="reels_denzadnem.mp4",
                        mime="video/mp4"
                    )
                    
            with col2:
                st.markdown("### 📝 Текст на відео")
                st.text_area("Фрази (субтитри):", value="\n\n".join(phrases), height=140)
                
                st.markdown("### 📢 Опис для соцмереж")
                caption = f"{latest_news.title}\n\nПодробиці читайте на сайті «День за днем» за посиланням у профілі!\n\n#новини #деньзаднем #хмельниччина #шепетівка #україна"
                st.text_area("Скопіюйте опис для публікації:", value=caption, height=140)
                
        except Exception as e:
            st.error(f"Виникла помилка: {e}")
