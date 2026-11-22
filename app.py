import streamlit as st
import feedparser
import re
import time
import textwrap
import os
import urllib.request
import xml.etree.ElementTree as ET
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from google import genai
from moviepy import VideoClip

# ==================== НАЛАШТУВАННЯ СТОРІНКИ ====================
st.set_page_config(
    page_title="Reels Генератор | День за днем",
    page_icon="📱",
    layout="wide"
)

st.title("🤖 Новинний Reels Генератор — «ДЕНЬ ЗА ДНЕМ»")
st.caption("Автоматичне створення стильних 15-секундних відео для TikTok та Instagram Reels")

# Введення API ключа
api_key = st.text_input("Введіть ключ Gemini API (починається з AIza...):", type="password")

WIDTH = 1080
HEIGHT = 1920

# ==================== ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ ШРИФТІВ ====================
def get_font(size, bold=True):
    """Підбирає якісний доступний шрифт на сервері (Windows / Linux / Streamlit Cloud)."""
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

# ==================== ПАРСИНГ НОВИН ТА СТАТЕЙ ====================
def fetch_rss_feed():
    """Завантажує актуальну стрічку новин сайту."""
    url = 'https://denzadnem.com.ua/feed/gn'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        items = root.find('channel').findall('item')
        feed_data = []
        for item in items[:15]:
            title = item.find('title').text if item.find('title') is not None else ''
            link = item.find('link').text if item.find('link') is not None else ''
            desc = item.find('description').text if item.find('description') is not None else ''
            content_el = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
            content_raw = content_el.text if content_el is not None else ''
            feed_data.append({
                'title': title.strip(),
                'link': link.strip(),
                'desc': desc.strip(),
                'content_raw': content_raw
            })
        return feed_data
    except Exception as e:
        print(f"Помилка завантаження RSS: {e}")
        try:
            f = feedparser.parse("https://denzadnem.com.ua/feed/gn")
            feed_data = []
            for e in f.entries[:15]:
                feed_data.append({
                    'title': e.title.strip(),
                    'link': e.link.strip(),
                    'desc': e.get('summary', '').strip(),
                    'content_raw': e.content[0].value if 'content' in e else ''
                })
            return feed_data
        except Exception:
            return []

def get_article_details(article_url, fallback_content=''):
    """
    Завантажує сторінку новини:
    - Знаходить ВСІ реальні ілюстрації цієї статті (og:image + картинки з div.entry);
    - Витягує повний чистий текст саме цієї статті.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://denzadnem.com.ua/'
    }
    images = []
    article_text = ""
    try:
        req = urllib.request.Request(article_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Головне OG фото статті
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            images.append(og['content'])
            
        # 2. Картинки безпосередньо з тіла статті div.entry
        entry = soup.find('div', class_='entry')
        if entry:
            for img in entry.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src and src.startswith('http'):
                    # Відфільтровуємо дрібні іконки, емодзі, аватарки
                    if any(x in src.lower() for x in ['avatar', 'emoji', 'icon', 'logo', 'addtoany', '.svg']):
                        continue
                    clean_src = re.sub(r'-\d+x\d+(\.\w+)$', r'\1', src)
                    if clean_src not in images and src not in images:
                        images.append(src)
                        
            # Очищений текст статті
            for s in entry(['script', 'style', 'iframe', 'noscript']):
                s.decompose()
            for share in entry.find_all('div', class_=re.compile(r'addtoany')):
                share.decompose()
            article_text = re.sub(r'\s+', ' ', entry.get_text()).strip()
    except Exception as e:
        print(f"Помилка завантаження статті: {e}")
        
    if not article_text and fallback_content:
        soup_fb = BeautifulSoup(fallback_content, 'html.parser')
        article_text = re.sub(r'\s+', ' ', soup_fb.get_text()).strip()
        
    return images, article_text

def download_image(url, save_path):
    """Завантажує фото з захистом від блокувань."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://denzadnem.com.ua/'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            with open(save_path, "wb") as f:
                f.write(r.read())
        return save_path
    except Exception as e:
        print(f"Помилка завантаження фото: {e}")
        return None

# ==================== ВІЗУАЛЬНИЙ ДИЗАЙН ====================
def create_news_background():
    """Створює сучасний графітовий фон із фірмовою шапкою «День за днем»."""
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (18, 20, 26, 255))
    draw = ImageDraw.Draw(canvas)
    
    # Тонка геометрична сітка
    for x in range(30, WIDTH, 40):
        for y in range(30, HEIGHT, 40):
            draw.ellipse([x-1, y-1, x+1, y+1], fill=(255, 255, 255, 8))
            
    # Віньєтування
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for y in range(180):
        a = int((1 - y/180) * 110)
        v_draw.line([(0, y), (WIDTH, y)], fill=(10, 12, 16, a))
        v_draw.line([(0, HEIGHT - y), (WIDTH, HEIGHT - y)], fill=(10, 12, 16, a))
    canvas = Image.alpha_composite(canvas, vignette)
    
    # Шапка сайту
    h_box = Image.new("RGBA", (WIDTH, 140), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(h_box)
    
    font_category = get_font(28, bold=True)
    font_logo = get_font(38, bold=True)
    font_small = get_font(26, bold=False)
    
    h_draw.rectangle([50, 40, WIDTH - 50, 115], fill=(26, 30, 40), outline=(255, 255, 255, 30), width=1)
    h_draw.rectangle([50, 40, 250, 115], fill=(225, 40, 40))
    h_draw.text((150, 77), "НОВИНИ", font=font_category, fill=(255, 255, 255), anchor="mm")
    h_draw.text((280, 77), "ДЕНЬ ЗА ДНЕМ", font=font_logo, fill=(255, 255, 255), anchor="lm")
    h_draw.text((WIDTH - 80, 77), "denzadnem.com.ua", font=font_small, fill=(160, 175, 195), anchor="rm")
    
    canvas.paste(h_box, (0, 0), h_box)
    
    # Нижній колонтитул
    f_draw = ImageDraw.Draw(canvas)
    f_draw.line([(60, 1780), (WIDTH - 60, 1780)], fill=(60, 65, 80), width=1)
    f_draw.text((WIDTH // 2, 1825), "Більше новин на сайті denzadnem.com.ua", font=font_small, fill=(180, 190, 205), anchor="mm")
    return canvas

def create_clean_photo_frame(img_path):
    """Створює елегантну білу рамку для фото з м'якою тінню."""
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

def pre_render_news_sticker(text, font, bg_color, text_color, pad_x=24, pad_y=12):
    """Формує контрастну новинну плашку для рядка тексту."""
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

# ==================== ВІДЕОГЕНЕРАТОР З ЧЕРГУВАННЯМ ФОТО ====================
def create_vertical_video(image_paths, phrases, output_path):
    """
    Рендерить 15-секундне відео:
    - 3 змістовні речення (по 5.0 с на речення);
    - Якщо фото декілька — вони по черзі змінюються разом із реченнями;
    - Якщо фото одне — воно залишається на все відео;
    - Адаптивний шрифт, щоб жодне слово не обрізалося;
    - Плавний верхній прогрес-бар.
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]
        
    video_duration = 15.0
    fps = 20
    num_phrases = len(phrases)
    time_per_phrase = video_duration / max(1, num_phrases)  # ~5.0 с на речення
    
    # 1. Створюємо рамки для кожної доступної картинки статті
    photo_frames = [create_clean_photo_frame(p) for p in image_paths if os.path.exists(p)]
    if not photo_frames:
        photo_frames = [create_clean_photo_frame(None)]
        
    # 2. Створюємо фон для кожної фрази з відповідним фото по черзі
    base_bg = create_news_background()
    phrase_bgs = []
    for p_idx in range(num_phrases):
        photo = photo_frames[p_idx % len(photo_frames)]
        canvas = base_bg.copy()
        px = (WIDTH - photo.width) // 2
        canvas.paste(photo, (px, 155), photo)
        phrase_bgs.append(canvas)
        
    news_colors = [
        ((255, 215, 0), (15, 15, 15)),   # Жовта плашка
        ((255, 255, 255), (15, 15, 15)), # Біла плашка
        ((225, 40, 40), (255, 255, 255)), # Червона плашка
        ((255, 215, 0), (15, 15, 15))
    ]
    
    # 3. Підготовка тексту речень
    phrase_data = []
    for p_text in phrases:
        clean = p_text.replace('*', '').replace('_', '').replace('"', '').strip()
        lines = textwrap.wrap(clean, width=26)
        if not lines:
            lines = [clean]
            
        n = len(lines)
        if n <= 2:
            f_size, spacing, y_start = 52, 115, 1260
        elif n == 3:
            f_size, spacing, y_start = 46, 100, 1220
        elif n == 4:
            f_size, spacing, y_start = 40, 88, 1180
        elif n == 5:
            f_size, spacing, y_start = 36, 80, 1150
        else:
            f_size, spacing, y_start = 32, 72, 1130
            
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
        p_idx = min(int(t / time_per_phrase), num_phrases - 1)
        # Фон із відповідним фото для поточної фрази
        frame = phrase_bgs[p_idx].copy()
        p_info = phrase_data[p_idx]
        t_in_phrase = t - (p_idx * time_per_phrase)
        
        # Швидка поява кожного рядка за 0.22 с (усі рядки готові за ~1 с, 4 с спокійного читання)
        y_pos = p_info["y_start"]
        for l_idx, stk in enumerate(p_info["lines"]):
            t_appear = l_idx * 0.22
            if t_in_phrase >= t_appear:
                sx = int(WIDTH // 2 - stk.width / 2)
                frame.paste(stk, (sx, y_pos), stk)
            y_pos += p_info["spacing"]
            
        # Прогрес-бар
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

if 'feed_items' not in st.session_state:
    st.session_state.feed_items = fetch_rss_feed()

col_sel, col_ref = st.columns([5, 1])
with col_ref:
    if st.button("🔄 Оновити стрічку"):
        st.session_state.feed_items = fetch_rss_feed()
        st.rerun()

items = st.session_state.feed_items
if not items:
    st.error("Не вдалося завантажити стрічку новин. Перевірте з'єднання.")
    st.stop()

item_titles = [it['title'] for it in items]
selected_index = st.selectbox(
    "Оберіть новину для створення відео:",
    range(len(item_titles)),
    format_func=lambda i: item_titles[i]
)
selected_news = items[selected_index]

# ==================== КНОПКА ЗАПУСКУ ====================
if st.button("🚀 Згенерувати відео (15 секунд)"):
    if not api_key:
        st.warning("⚠️ Будь ласка, введіть API ключ Gemini у верхнє поле.")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            with st.status("Генерація відео (15 секунд)...", expanded=True) as status:
                st.write(f"🔍 Завантажуємо матеріал: **{selected_news['title']}**...")
                
                # 1. Завантаження повного тексту та ВСІХ фото саме цієї статті
                img_urls, full_text = get_article_details(
                    selected_news['link'], 
                    selected_news.get('content_raw', '')
                )
                
                ts = int(time.time() * 1000)
                valid_img_paths = []
                
                # Завантажуємо до 3-х картинок статті
                if img_urls:
                    st.write(f"🖼️ Знайдено ілюстрацій до статті: {len(img_urls)}. Завантажуємо...")
                    for idx, u in enumerate(img_urls[:3]):
                        p = f"temp_img_{ts}_{idx}.jpg"
                        saved = download_image(u, p)
                        if saved and os.path.exists(saved):
                            valid_img_paths.append(saved)
                            
                if not valid_img_paths:
                    dummy_path = f"temp_img_{ts}_dummy.jpg"
                    dummy = Image.new("RGB", (940, 600), (35, 42, 54))
                    dummy.save(dummy_path)
                    valid_img_paths.append(dummy_path)
                    
                # 2. Складання сценарію: 3 повноцінні речення
                st.write("✍️ Складаємо змістовний новинний сценарій (3 речення)...")
                prompt_script = f"""Ти — професійний редактор новинного сайту "День за днем" для TikTok/Reels.
Напиши сценарій для 15-секундного відео суворо на основі цієї статті.

Заголовок новини: {selected_news['title']}
Повний текст новини:
{full_text[:2000]}

ВИМОГИ ДО СЦЕНАРІЮ:
Напиши РІВНО 3 ПОВНОЦІННІ РЕЧЕННЯ (не скорочені фрази, а саме зв'язні змістовні речення приблизно по 9–14 слів кожне), кожне з нового рядка:
1. Перше речення: Що саме, де і за яких обставин сталося (основна подія статті).
2. Друге речення: Ключова важлива подробиця, деталі чи наслідки саме з цієї статті.
3. Третє речення: Заключне речення із закликом або підсумком (наприклад: "Більше подробиць та фотографій дивіться на сайті День за днем").

ВАЖЛИВО:
- Кожне речення має бути закінченою думкою, змістовним і легко читатися з екрана.
- Текст має бути СУВОРО ПРО ЦЮ КОНКРЕТНУ НОВИНУ!
- Жодних службових слів ("Речення 1", "Хук"), без лапок, без зірочок (*) і смайликів. Лише 3 чисті рядки тексту."""

                # Безпечний виклик моделей Gemini
                script_text = ""
                available_models = [
                    "gemini-3.8-flash",
                    "gemini-3-flash",
                    "gemini-2.5-flash",
                    "gemini-2.0-flash",
                    "gemini-1.5-flash"
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
                        
                # 3. Якщо ШІ недоступний — точний розумний алгоритм з 3-х повних речень
                if not script_text:
                    st.info("ℹ️ Формуємо 3 повні речення безпосередньо з тексту обраної статті...")
                    t_clean = re.sub(r'[\r\n]+', ' ', selected_news['title']).strip()
                    t_clean = re.sub(r'\s*\((?:фото|відео|оновлено|ексклюзив)\)', '', t_clean, flags=re.IGNORECASE).strip()
                    if not t_clean.endswith(('.', '!', '?')):
                        t_clean += '.'
                        
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if len(s.strip()) > 30]
                    p2 = ""
                    for s in sentences:
                        s_clean = re.sub(r'\s+', ' ', s).strip()
                        if 35 < len(s_clean) < 130:
                            p2 = s_clean
                            break
                    if not p2 and sentences:
                        p2 = sentences[0]
                    if not p2.endswith(('.', '!', '?')):
                        p2 += '.'
                    if not p2 or len(p2) < 20:
                        p2 = "Усі деталі та розвиток подій з’ясовуються у громаді."
                        
                    p3 = "Більше подробиць та фотографій дивіться на сайті День за днем."
                    phrases = [t_clean, p2, p3]
                else:
                    phrases = [p.strip() for p in script_text.split('\n') if len(p.strip()) > 5]
                    if len(phrases) < 2:
                        phrases = [selected_news['title'], "Подробиці читайте на сайті День за днем"]
                        
                # 4. Рендеримо відео на 15 секунд з чергуванням картинок
                st.write(f"🎬 Рендеримо 15-секундне відео (використано картинок: {len(valid_img_paths)})...")
                temp_video_path = f"reels_{ts}.mp4"
                video_file = create_vertical_video(valid_img_paths, phrases, temp_video_path)
                
                status.update(label="✅ Відео готове до публікації!", state="complete", expanded=False)

            # Читаємо відео в байти для уникнення кешу браузера
            with open(video_file, "rb") as vf:
                video_bytes = vf.read()

            # Відображення результатів
            col1, col2 = st.columns([1, 1])
            with col1:
                st.markdown("### 📱 Попередній перегляд (9:16, 15 сек)")
                st.video(video_bytes)
                st.download_button(
                    label="⬇️ Завантажити відео (MP4)",
                    data=video_bytes,
                    file_name=f"reels_{selected_index+1}.mp4",
                    mime="video/mp4"
                )
                
            with col2:
                st.markdown("### 📝 Текст на відео (3 речення)")
                st.text_area("Субтитри:", value="\n\n".join(phrases), height=140)
                
                st.markdown("### 📢 Опис для соцмереж")
                caption = f"{selected_news['title']}\n\nПодробиці читайте на сайті «День за днем» за посиланням у профілі!\n\n#новини #деньзаднем #хмельниччина #шепетівка #україна"
                st.text_area("Скопіюйте опис для публікації:", value=caption, height=140)
                
            # Очищення тимчасових файлів
            for p in valid_img_paths:
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            try:
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
            except Exception:
                pass
                
        except Exception as e:
            st.error(f"Виникла помилка: {e}")
