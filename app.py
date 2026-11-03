import streamlit as st
import feedparser
import re
import time
import os
import requests
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from google import genai
from moviepy import VideoClip

# Налаштування сторінки
st.set_page_config(page_title="Reels Генератор — День за Днем", page_icon="📱", layout="wide")
st.title("🤖 Zine-Reels для ДЕНЬ ЗА ДНЕМ")

api_key = st.text_input("Введіть ключ Gemini API (починається з AQ...):", type="password")

WIDTH = 1080
HEIGHT = 1920

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

def create_paper_texture():
    base = Image.new("RGBA", (WIDTH, HEIGHT), (18, 20, 26, 255))
    draw = ImageDraw.Draw(base)
    grid = 36
    for x in range(0, WIDTH, grid):
        for y in range(0, HEIGHT, grid):
            r = 1.5 if (x + y) % (grid * 2) == 0 else 1.0
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 14))
            
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_overlay = ImageDraw.Draw(overlay)
    for y in range(160):
        alpha = int((1 - y / 160) * 110)
        d_overlay.line([(0, y), (WIDTH, y)], fill=(8, 10, 14, alpha))
        d_overlay.line([(0, HEIGHT - y), (WIDTH, HEIGHT - y)], fill=(8, 10, 14, alpha))
    return Image.alpha_composite(base, overlay)

def create_photo_cutout(img_path, target_width=860, angle=-1.8):
    try:
        src = Image.open(img_path).convert("RGBA")
    except Exception:
        src = Image.new("RGBA", (800, 600), (35, 42, 54, 255))
        
    aspect = src.height / src.width
    th = int(target_width * aspect)
    if th > 950:
        th = 950
        target_width = int(th / aspect)
        
    src = src.resize((target_width, th), Image.Resampling.LANCZOS)
    
    border_px = 22
    pw = target_width + border_px * 2
    ph = th + border_px * 2 + 25
    
    paper = Image.new("RGBA", (pw, ph), (250, 248, 242, 255))
    paper.paste(src, (border_px, border_px))
    
    p_draw = ImageDraw.Draw(paper)
    p_draw.rectangle([border_px, border_px, border_px + target_width, border_px + th], outline=(205, 200, 190), width=2)
    
    # Скотч на кутах
    def apply_tape(im, x, y, rot):
        tape = Image.new("RGBA", (140, 42), (235, 225, 190, 210))
        t_draw = ImageDraw.Draw(tape)
        t_draw.line([(0, 0), (140, 0)], fill=(245, 238, 215, 230), width=1)
        r_tape = tape.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
        im.paste(r_tape, (x, y), r_tape)
        
    apply_tape(paper, 18, -12, 16)
    apply_tape(paper, pw - 145, -12, -14)
    
    rotated = paper.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    
    pad = 40
    shadow = Image.new("RGBA", (rotated.width + pad * 2, rotated.height + pad * 2), (0, 0, 0, 0))
    alpha_mask = rotated.split()[3]
    dark_shape = Image.new("RGBA", rotated.size, (10, 10, 14, 130))
    shadow.paste(dark_shape, (pad + 10, pad + 16), alpha_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
    shadow.paste(rotated, (pad, pad), rotated)
    return shadow

def pre_render_sticker(text, font, bg_color, text_color, angle=0.0, pad_x=28, pad_y=14):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    
    sticker = Image.new("RGBA", (bw + 20, bh + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sticker)
    draw.rectangle([8, 8, bw + 8, bh + 8], fill=(0, 0, 0, 110))
    draw.rectangle([3, 3, bw + 3, bh + 3], fill=bg_color)
    draw.text((3 + pad_x - bbox[0], 3 + pad_y - bbox[1]), text, font=font, fill=text_color)
    
    if angle != 0:
        sticker = sticker.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    return sticker

def get_full_image_url(thumb_url):
    if thumb_url:
        return re.sub(r'-\d+x\d+(\.\w+)$', r'\1', thumb_url)
    return None

def create_vertical_video(image_urls, script_text):
    video_duration = 15.0
    fps = 20  # 20 FPS забезпечує плавний рух і вдвічі швидший експорт
    output_path = "ready_for_reels.mp4"
    
    if isinstance(image_urls, str):
        image_urls = [image_urls]
        
    valid_img_paths = []
    if image_urls:
        headers = {'User-Agent': 'Mozilla/5.0'}
        for i, url in enumerate(image_urls[:3]):
            if not url:
                continue
            if url.startswith("http://") or url.startswith("https://"):
                try:
                    img_response = requests.get(url, headers=headers, timeout=4)
                    if img_response.status_code == 200:
                        path = f"temp_news_img_{i}.jpg"
                        with open(path, 'wb') as handler:
                            handler.write(img_response.content)
                        valid_img_paths.append(path)
                except Exception as e:
                    print(f"Помилка завантаження: {e}")
            elif os.path.exists(url):
                valid_img_paths.append(url)
                
    cutouts = []
    angles = [-2.0, 1.8, -1.2]
    if valid_img_paths:
        for idx, p in enumerate(valid_img_paths):
            cutouts.append(create_photo_cutout(p, target_width=860, angle=angles[idx % len(angles)]))
    else:
        dummy = Image.new("RGB", (800, 600), (35, 42, 54))
        d_draw = ImageDraw.Draw(dummy)
        d_draw.text((400, 300), "ДЕНЬ ЗА ДНЕМ", anchor="mm", fill=(180, 190, 210))
        dummy.save("temp_dummy.jpg")
        cutouts.append(create_photo_cutout("temp_dummy.jpg", target_width=860, angle=-1.5))
        
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '').replace('«', '').replace('»', '')
    raw_phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    if not raw_phrases:
        raw_phrases = ["Головна подія дня", "Подробиці події на сайті", "Читайте на День за Днем"]
        
    num_phrases = len(raw_phrases)
    time_per_phrase = video_duration / num_phrases
    
    font_header = get_best_font(42, bold=True)
    font_sticker = get_best_font(52, bold=True)
    font_badge = get_best_font(32, bold=True)
    font_small = get_best_font(28, bold=False)
    
    base_bg = create_paper_texture()
    
    # Заголовок зверху
    badge_layer = Image.new("RGBA", (WIDTH, 140), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(badge_layer)
    b_draw.rectangle([70, 40, WIDTH - 70, 115], fill=(255, 85, 0))
    b_draw.text((WIDTH // 2, 77), "ДЕНЬ ЗА ДНЕМ • ЕКСКЛЮЗИВ", font=font_header, fill=(255, 255, 255), anchor="mm")
    tape = Image.new("RGBA", (90, 30), (240, 230, 200, 210))
    badge_layer.paste(tape, (55, 25), tape)
    base_bg.paste(badge_layer, (0, 0), badge_layer)
    
    # Нижній напис
    f_draw = ImageDraw.Draw(base_bg)
    f_draw.line([(60, 1780), (WIDTH - 60, 1780)], fill=(120, 125, 140), width=2)
    f_draw.text((WIDTH // 2, 1830), "Читайте повну новину на сайті denzadnem.com.ua", font=font_small, fill=(200, 205, 220), anchor="mm")

    # Плашка деталей розслідування
    badge_w = 680
    badge_h = 52
    m_box = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    m_draw = ImageDraw.Draw(m_box)
    m_draw.rectangle([0, 0, badge_w, badge_h], fill=(20, 24, 34, 235), outline=(255, 215, 0), width=2)
    m_draw.text((badge_w // 2, badge_h // 2), "ПОДРОБИЦІ РОЗСЛІДУВАННЯ", font=font_badge, fill=(255, 230, 0), anchor="mm")

    sticker_color_schemes = [
        [( (255, 230, 0), (15, 15, 15), -1.5 ), ( (250, 250, 250), (15, 15, 15), 1.2 ), ( (255, 55, 35), (255, 255, 255), -0.8 )],
        [( (255, 85, 0), (255, 255, 255), 1.0 ), ( (250, 250, 250), (15, 15, 15), -1.2 ), ( (255, 230, 0), (15, 15, 15), 1.5 )],
        [( (0, 220, 240), (15, 15, 15), -1.0 ), ( (250, 250, 250), (15, 15, 15), 1.4 ), ( (255, 55, 35), (255, 255, 255), -1.2 )],
        [( (255, 230, 0), (15, 15, 15), 1.2 ), ( (255, 85, 0), (255, 255, 255), -1.0 ), ( (250, 250, 250), (15, 15, 15), 0.8 )],
    ]

    # Швидке попереднє кешування станів кадрів
    timeline_states = []
    y_center_start = 1260
    line_spacing = 115

    for p_idx, text in enumerate(raw_phrases):
        p_start = p_idx * time_per_phrase
        p_dur = time_per_phrase
        
        words = text.split()
        lines = []
        cur = []
        for w in words:
            cur.append(w)
            if len(" ".join(cur)) > 19:
                if len(cur) > 1:
                    cur.pop()
                    lines.append(" ".join(cur))
                    cur = [w]
                else:
                    lines.append(" ".join(cur))
                    cur = []
        if cur:
            lines.append(" ".join(cur))
        lines = lines[:3]
        
        phrase_canvas = base_bg.copy()
        cutout = cutouts[p_idx % len(cutouts)]
        px = (WIDTH - cutout.width) // 2
        py = 175
        phrase_canvas.paste(cutout, (px, py), cutout)
        
        scheme = sticker_color_schemes[p_idx % len(sticker_color_schemes)]
        rendered_stickers = []
        for l_idx, line_txt in enumerate(lines):
            bg_c, txt_c, ang = scheme[l_idx % len(scheme)]
            stk = pre_render_sticker(line_txt.upper(), font_sticker, bg_c, txt_c, angle=ang)
            stk_x = int(WIDTH // 2 - stk.width / 2)
            stk_y = int((y_center_start + l_idx * line_spacing) - stk.height / 2)
            rendered_stickers.append((stk, stk_x, stk_y))
            
        # Етапи появи рядків
        s1 = phrase_canvas.copy()
        if len(rendered_stickers) > 0:
            stk, sx, sy = rendered_stickers[0]
            s1.paste(stk, (sx, sy), stk)
            
        t_s1 = p_start
        t_s2 = p_start + p_dur * 0.28
        t_s3 = p_start + p_dur * 0.56
        t_s4 = p_start + p_dur * 0.75
        
        s2 = s1.copy()
        if len(rendered_stickers) > 1:
            stk, sx, sy = rendered_stickers[1]
            s2.paste(stk, (sx, sy), stk)
            
        s3 = s2.copy()
        if len(rendered_stickers) > 2:
            stk, sx, sy = rendered_stickers[2]
            s3.paste(stk, (sx, sy), stk)
            
        s4 = s3.copy()
        s4.paste(m_box, ((WIDTH - badge_w) // 2, 1660), m_box)
        
        timeline_states.append({"t_start": t_s1, "img": s1})
        timeline_states.append({"t_start": t_s2, "img": s2})
        timeline_states.append({"t_start": t_s3, "img": s3})
        timeline_states.append({"t_start": t_s4, "img": s4})

    timeline_states.sort(key=lambda s: s["t_start"])

    # Турбо-генератор кадрів
    def make_frame(t):
        chosen = timeline_states[0]["img"]
        for s in timeline_states:
            if t >= s["t_start"]:
                chosen = s["img"]
            else:
                break
                
        frame = chosen.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle([0, 0, WIDTH, 12], fill=(40, 45, 55))
        prog = min(1.0, max(0.0, t / video_duration))
        draw.rectangle([0, 0, int(WIDTH * prog), 12], fill=(255, 85, 0))
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
                st.write("🔍 Аналізуємо обрану новину...")
                latest_news = selected_news 
                clean_text = re.sub('<[^<]+>', '', latest_news.summary).strip()
                
                found_images = []
                if 'enclosures' in latest_news:
                    for enc in latest_news.enclosures:
                        if 'image' in enc.type:
                            found_images.append(enc.href)
                            
                if 'media_content' in latest_news:
                    for media in latest_news.media_content:
                        if 'url' in media:
                            found_images.append(media['url'])
                            
                if 'content' in latest_news or 'summary' in latest_news:
                    html_source = latest_news.content[0].value if 'content' in latest_news else latest_news.summary
                    soup = BeautifulSoup(html_source, 'html.parser')
                    for img_tag in soup.find_all('img'):
                        if img_tag.get('src') and img_tag['src'] not in found_images:
                            found_images.append(img_tag['src'])
                            
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

                # 1. Запит тексту
                for sproba in range(3):
                    try:
                        response = client.models.generate_content(
                            model='gemini-3.8-flash',
                            contents=prompt
                        )
                        if response.text:
                            script = response.text 
                            break 
                    except Exception as e:
                        if "503" in str(e) or "429" in str(e):
                            st.warning(f"Сервер зайнятий. Спроба {sproba + 1} з 3... Очікування...")
                            time.sleep(5) 
                        else:
                            st.warning(f"Помилка ШІ (сценарій): {e}")
                            break
                            
                # 2. Запит опису (швидка пауза 1 сек)
                time.sleep(1)
                st.write("📝 Генеруємо опис для соцмереж...")
                for sproba in range(3):
                    try:
                        resp_desc = client.models.generate_content(
                            model='gemini-3.8-flash',
                            contents=prompt_desc
                        )
                        if resp_desc.text:
                            social_desc = resp_desc.text
                            break
                    except Exception as e:
                        if "503" in str(e) or "429" in str(e):
                            time.sleep(5)
                        else:
                            break
                
                st.write("🎬 Швидкий монтаж відеоколажу...")
                video_path = create_vertical_video(original_image_urls, script)
                status.update(label="Готово!", state="complete", expanded=False)
            
            # Результати
            st.success(f"Новина: {latest_news.title}")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Відеоколаж (9:16)")
                st.video(video_path)
                with open(video_path, "rb") as file:
                    st.download_button("⬇️ Завантажити відео", data=file, file_name="reels_collage.mp4", mime="video/mp4")
                    
            with col2:
                st.subheader("Текст на відео")
                st.text_area("Сценарій (субтитри):", script, height=150)
                
                st.subheader("Опис для соцмереж")
                st.text_area("Скопіюй для публікації (можна редагувати):", social_desc, height=200)
                
        except Exception as e:
            st.error(f"Виникла загальна помилка: {e}")
