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
st.caption("Генерація професійних 15-секундних відео для TikTok та Instagram Reels")

# Введення API ключа
api_key = st.text_input("Введіть ключ Gemini API (починається з AIza...):", type="password")

WIDTH = 1080
HEIGHT = 1920

# ==================== ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ ШРИФТІВ ====================
def get_font(size, bold=True):
    """Підбирає доступний якісний шрифт на сервері (Windows / Linux / Streamlit Cloud)."""
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
    Завантажує безпосередньо сторінку новини:
    - Витягує 100% правильне офіційне фото статті (OpenGraph);
    - Витягує повний чистий текст саме цієї статті з блоку div.entry.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://denzadnem.com.ua/'
    }
    img_url = None
    article_text = ""
    try:
        req = urllib.request.Request(article_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Головне OG фото статті
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            img_url = og['content']
            
        # 2. Повний текст статті
        entry = soup.find('div', class_='entry')
        if entry:
            for s in entry(['script', 'style', 'iframe', 'noscript']):
                s.decompose()
            for share in entry.find_all('div', class_=re.compile(r'addtoany')):
                share.decompose()
            article_text = re.sub(r'\s+', ' ', entry.get_text()).strip()
    except Exception as e:
        print(f"Помилка завантаження сторінки статті: {e}")
        
    if not article_text and fallback_content:
        soup_fb = BeautifulSoup(fallback_content, 'html.parser')
        article_text = re.sub(r'\s+', ' ', soup_fb.get_text()).strip()
        
    return img_url, article_text

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

# ==================== ВІЗУАЛЬНИЙ ДИЗАЙН НОВИН ====================
def create_news_background():
    """Створює сучасний графітовий фон із фірмовою шапкою видання."""
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

def pre_render_news_sticker(text, font, bg_color, text_color, pad_x=26, pad_y=12):
    """Формує контрастну новинну плашку для окремого рядка тексту."""
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

# ==================== ГЕНЕРАЦІЯ 15-СЕКУНДНОГО ВІДЕО ====================
def create_vertical_video(image_path, phrases, output_path):
    """
    Рендерить відео на 15 секунд:
    - 3 фрази по 5.0 секунд кожна — спокійне читання без поспіху;
    - 1 зафіксоване головне фото статті (не перемикається);
    - Рядки з'являються за 0.22 с і залишаються на екрані майже 4 секунди;
    - Плавний верхній прогрес-бар.
    """
    video_duration = 15.0
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
    time_per_phrase = video_duration / max(1, num_phrases)  # 5.0 с на фразу
    
    phrase_data = []
    for p_text in phrases:
        clean = p_text.replace('*', '').replace('_', '').replace('"', '').strip()
        lines = textwrap.wrap(clean, width=25)
        if not lines:
            lines = [clean]
            
        n = len(lines)
        if n <= 2:
            f_size, spacing, y_start = 52, 115, 1260
        elif n == 3:
            f_size, spacing, y_start = 48, 105, 1220
        elif n == 4:
            f_size, spacing, y_start = 42, 92, 1180
        elif n == 5:
            f_size, spacing, y_start = 38, 84, 1160
        else:
            f_size, spacing, y_start = 34, 76, 1140
            
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
        
        y_pos = p_info["y_start"]
        for l_idx, stk in enumerate(p_info["lines"]):
            t_appear = l_idx * 0.22
            if t_in_phrase >= t_appear:
                sx = int(WIDTH // 2 - stk.width / 2)
                frame.paste(stk, (sx, y_pos), stk)
            y_pos += p_info["spacing"]
            
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
                st.write(f"🔍 Завантажуємо повний матеріал: **{selected_news['title']}**...")
                
                # 1. Завантаження повного тексту та фото саме цієї статті
                img_url, full_text = get_article_details(
                    selected_news['link'], 
                    selected_news.get('content_raw', '')
                )
                
                # 2. Унікальне ім'я для фото (проти кешування)
                ts = int(time.time() * 1000)
                temp_img_path = f"temp_img_{ts}.jpg"
                
                if img_url:
                    img_path = download_image(img_url, temp_img_path)
                else:
                    img_path = None
                    
                if not img_path or not os.path.exists(img_path):
                    dummy = Image.new("RGB", (940, 600), (35, 42, 54))
                    dummy.save(temp_img_path)
                    img_path = temp_img_path
                    
                # 3. Складання сценарію суто за фактами цієї статті
                st.write("✍️ Складаємо лаконічний новинний сценарій...")
                prompt_script = f"""Ти — професійний редактор новинного сайту "День за днем" для TikTok/Reels.
Напиши сценарій для динамічного 15-секундного відео суворо за фактами цієї статті.

Заголовок новини: {selected_news['title']}
Повний текст новини:
{full_text[:1800]}

ВИМОГИ ДО СЦЕНАРІЮ:
1. Рівно 3 короткі змістовні фрази, кожна з нового рядка:
   - Фраза 1: Головний факт події (стисло, зрозуміло, 5-8 слів).
   - Фраза 2: Ключова деталь чи результат саме з цієї статті (5-8 слів).
   - Фраза 3: Деталі читайте на сайті День за днем
2. Текст має бути СУВОРО ПРО ЦЮ КОНКРЕТНУ НОВИНУ! Без вигадок і без сторонніх тем!
3. Жодних позначок "Фраза 1", "Хук", без лапок, без зірочок (*), без емодзі. Лише 3 рядки чистого українського тексту."""

                # Безпечний виклик моделей
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
                        
                # 4. Якщо ШІ недоступний — точний розумний алгоритм з тексту статті
                if not script_text:
                    st.info("ℹ️ Формуємо точні субтитри безпосередньо з тексту обраної статті...")
                    t_clean = re.sub(r'[\r\n]+', ' ', selected_news['title']).strip()
                    t_clean = re.sub(r'\s*\((?:фото|відео|оновлено|ексклюзив)\)', '', t_clean, flags=re.IGNORECASE).strip()
                    if len(t_clean) > 75 and (',' in t_clean or ':' in t_clean):
                        t_clean = re.split(r'[,:]', t_clean)[0].strip()
                        
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if len(s.strip()) > 25]
                    p2 = ""
                    for s in sentences:
                        s_clean = re.sub(r'\s+', ' ', s).strip()
                        if 25 < len(s_clean) < 110:
                            p2 = s_clean
                            break
                    if not p2 and sentences:
                        words = sentences[0].split()[:10]
                        p2 = ' '.join(words) + '...'
                    if not p2:
                        p2 = "Більше деталей події у матеріалі"
                        
                    p3 = "Подробиці читайте на сайті День за днем"
                    phrases = [t_clean, p2, p3]
                else:
                    phrases = [p.strip() for p in script_text.split('\n') if len(p.strip()) > 3]
                    if len(phrases) < 2:
                        phrases = [selected_news['title'], "Подробиці читайте на сайті День за днем"]
                        
                # 5. Рендеримо відео з унікальним іменем
                st.write("🎬 Рендеримо відео на 15 секунд...")
                temp_video_path = f"reels_{ts}.mp4"
                video_file = create_vertical_video(img_path, phrases, temp_video_path)
                
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
                st.markdown("### 📝 Текст на відео (субтитри)")
                st.text_area("Фрази відео:", value="\n\n".join(phrases), height=140)
                
                st.markdown("### 📢 Опис для соцмереж")
                caption = f"{selected_news['title']}\n\nПодробиці читайте на сайті «День за днем» за посиланням у профілі!\n\n#новини #деньзаднем #хмельниччина #шепетівка #україна"
                st.text_area("Скопіюйте опис для публікації:", value=caption, height=140)
                
            # Очищення тимчасових файлів
            try:
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
            except Exception:
                pass
                
        except Exception as e:
            st.error(f"Виникла помилка: {e}")
