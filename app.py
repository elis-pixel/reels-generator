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

st.set_page_config(page_title="Reels Генератор — День за Днем", page_icon="📱", layout="wide")
st.title("🤖 Zine-Reels для ДЕНЬ ЗА ДНЕМ")

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

def create_editorial_bg():
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (22, 24, 30, 255))
    draw = ImageDraw.Draw(canvas)
    
    # Діагональні смуги
    for x in range(-WIDTH, WIDTH * 2, 48):
        draw.line([(x, 0), (x + HEIGHT, HEIGHT)], fill=(255, 255, 255, 6), width=2)
        
    # Крапки halftone
    for x in range(30, WIDTH, 36):
        for y in range(30, HEIGHT, 36):
            draw.ellipse([x-1, y-1, x+1, y+1], fill=(255, 255, 255, 12))
            
    # Віньєтка
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for y in range(200):
        a = int((1 - y/200) * 130)
        v_draw.line([(0, y), (WIDTH, y)], fill=(12, 14, 18, a))
        v_draw.line([(0, HEIGHT - y), (WIDTH, HEIGHT - y)], fill=(12, 14, 18, a))
    canvas = Image.alpha_composite(canvas, vignette)
    
    # Верхня шапка
    font_masthead = get_best_font(34, bold=True)
    font_category = get_best_font(28, bold=True)
    
    header_box = Image.new("RGBA", (WIDTH, 170), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(header_box)
    h_draw.rectangle([0, 15, WIDTH, 72], fill=(255, 215, 0))
    h_draw.text((WIDTH // 2, 43), "● ДЕНЬ ЗА ДНЕМ • КРИМІНАЛЬНА ХРОНІКА ●", font=font_masthead, fill=(15, 15, 15), anchor="mm")
    
    h_draw.rectangle([0, 72, WIDTH, 120], fill=(32, 36, 46))
    h_draw.text((60, 96), "РЕГІОН: ХМЕЛЬНИЧЧИНА", font=font_category, fill=(200, 210, 230), anchor="lm")
    h_draw.text((WIDTH - 60, 96), "ЕКСКЛЮЗИВ", font=font_category, fill=(255, 85, 0), anchor="rm")
    
    canvas.paste(header_box, (0, 0), header_box)
    return canvas

def create_photo_cutout(img_path):
    try:
        src = Image.open(img_path).convert("RGBA")
    except Exception:
        src = Image.new("RGBA", (800, 600), (45, 52, 68, 255))
        
    target_w = 880
    aspect = src.height / src.width
    target_h = int(target_w * aspect)
    if target_h > 860:
        target_h = 860
        target_w = int(target_h / aspect)
    src = src.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    border = 20
    pw = target_w + border * 2
    ph = target_h + border * 2 + 42
    
    polaroid = Image.new("RGBA", (pw, ph), (252, 250, 245, 255))
    polaroid.paste(src, (border, border))
    
    font_category = get_best_font(28, bold=True)
    font_small = get_best_font(24, bold=False)
    
    p_draw = ImageDraw.Draw(polaroid)
    p_draw.rectangle([border, border, border + target_w, border + target_h], outline=(210, 205, 195), width=2)
    p_draw.text((border + 20, border + target_h + 21), "МАТЕРІАЛИ СПРАВИ • СЛІДСТВО", font=font_small, fill=(120, 115, 105), anchor="lm")
    
    # Штамп ДОКАЗ №1
    stamp = Image.new("RGBA", (190, 44), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(stamp)
    s_draw.rectangle([0, 0, 190, 44], fill=(220, 40, 40), outline=(255, 255, 255), width=2)
    s_draw.text((95, 22), "ДОКАЗ №1", font=font_category, fill=(255, 255, 255), anchor="mm")
    polaroid.paste(stamp, (pw - 210, border + target_h - 22), stamp)
    
    # Скотч на кутах
    def add_tape(im, x, y, rot):
        tape = Image.new("RGBA", (140, 40), (240, 230, 195, 220))
        t_draw = ImageDraw.Draw(tape)
        t_draw.line([(0, 0), (140, 0)], fill=(255, 245, 220, 240), width=1)
        r = tape.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
        im.paste(r, (x, y), r)
        
    add_tape(polaroid, 20, -12, 14)
    add_tape(polaroid, pw - 145, -12, -12)
    
    rotated = polaroid.rotate(-1.5, expand=True, resample=Image.Resampling.BICUBIC)
    
    pad = 40
    shadow = Image.new("RGBA", (rotated.width + pad * 2, rotated.height + pad * 2), (0, 0, 0, 0))
    alpha = rotated.split()[3]
    dark = Image.new("RGBA", rotated.size, (10, 12, 16, 140))
    shadow.paste(dark, (pad + 10, pad + 18), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=16))
    shadow.paste(rotated, (pad, pad), rotated)
    return shadow

def pre_render_sticker(text, font, bg_color, text_color, angle=0.0, pad_x=24, pad_y=12):
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

def create_vertical_video(image_urls, script_text):
    # Швидкий, енергійний темп для TikTok (9 секунд)
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
                
    cutouts = []
    if valid_img_paths:
        for p in valid_img_paths:
            cutouts.append(create_photo_cutout(p))
    else:
        dummy = Image.new("RGB", (800, 600), (35, 42, 54))
        dummy.save("temp_dummy.jpg")
        cutouts.append(create_photo_cutout("temp_dummy.jpg"))
        
    clean_script = script_text.replace('*', '').replace('_', '').replace('"', '').replace('«', '').replace('»', '')
    raw_phrases = [p.strip() for p in clean_script.split('\n') if len(p.strip()) > 3]
    if not raw_phrases:
        raw_phrases = ["Головна подія дня", "Подробиці події на сайті", "Читайте на День за Днем"]
        
    num_phrases = len(raw_phrases)
    time_per_phrase = video_duration / num_phrases
    
    font_sticker = get_best_font(48, bold=True)
    font_category = get_best_font(28, bold=True)
    font_small = get_best_font(26, bold=False)
    
    base_bg = create_editorial_bg()
    
    # Картка розслідування (досьє)
    card_w = 940
    card_h = 560
    card_x = (WIDTH - card_w) // 2
    card_y = 1140
    
    note_box = Image.new("RGBA", (card_w, card_h), (28, 32, 42, 245))
    n_draw = ImageDraw.Draw(note_box)
    n_draw.rectangle([0, 0, card_w - 1, card_h - 1], outline=(255, 215, 0), width=3)
    
    pin_tag = Image.new("RGBA", (240, 40), (255, 85, 0))
    p_draw = ImageDraw.Draw(pin_tag)
    p_draw.text((120, 20), "СУТЬ ПОДІЇ", font=font_category, fill=(255, 255, 255), anchor="mm")
    note_box.paste(pin_tag, (30, -18), pin_tag)
    
    note_shadow = Image.new("RGBA", (card_w + 30, card_h + 30), (0, 0, 0, 0))
    ns_draw = ImageDraw.Draw(note_shadow)
    ns_draw.rectangle([10, 10, card_w + 10, card_h + 10], fill=(0, 0, 0, 120))
    note_shadow = note_shadow.filter(ImageFilter.GaussianBlur(radius=12))

    cta_y = card_y + card_h - 85
    
    sticker_color_schemes = [
        [( (255, 220, 0), (15, 15, 15), -1.0 ), ( (255, 255, 255), (15, 15, 15), 1.2 ), ( (255, 60, 40), (255, 255, 255), -0.8 )],
        [( (255, 85, 0), (255, 255, 255), 1.0 ), ( (255, 255, 255), (15, 15, 15), -1.2 ), ( (255, 220, 0), (15, 15, 15), 1.4 )],
        [( (0, 225, 245), (15, 15, 15), -1.2 ), ( (255, 255, 255), (15, 15, 15), 1.0 ), ( (255, 60, 40), (255, 255, 255), -1.0 )]
    ]

    timeline_states = []

    for p_idx, phrase_text in enumerate(raw_phrases):
        p_start = p_idx * time_per_phrase
        
        # Обгортання ТІЛЬКИ ЦІЛИМИ СЛОВАМИ (без обрізання!)
        wrapped_lines = textwrap.wrap(phrase_text, width=22)[:3]
        
        p_canvas = base_bg.copy()
        photo = cutouts[p_idx % len(cutouts)]
        px = (WIDTH - photo.width) // 2
        p_canvas.paste(photo, (px, 150), photo)
        
        p_canvas.paste(note_shadow, (card_x - 5, card_y - 5), note_shadow)
        p_canvas.paste(note_box, (card_x, card_y), note_box)
        
        c_draw = ImageDraw.Draw(p_canvas)
        c_draw.rectangle([card_x + 30, cta_y, card_x + card_w - 30, cta_y + 55], fill=(20, 24, 32), outline=(255, 255, 255, 50), width=1)
        c_draw.text((WIDTH // 2, cta_y + 27), "Читайте продовження на denzadnem.com.ua", font=font_small, fill=(255, 215, 0), anchor="mm")
        
        scheme = sticker_color_schemes[p_idx % len(sticker_color_schemes)]
        y_pos = card_y + 65
        line_stickers = []
        for l_idx, line in enumerate(wrapped_lines):
            bg_c, txt_c, ang = scheme[l_idx % len(scheme)]
            stk = pre_render_sticker(line.upper(), font_sticker, bg_c, txt_c, angle=ang, pad_x=24, pad_y=12)
            sx = int(WIDTH // 2 - stk.width / 2)
            line_stickers.append((stk, sx, y_pos))
            y_pos += 110
            
        # Енергійна поява: рядки з'являються кожні 0.35 с
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
                        print(f"Помилка парсингу статті: {e}")

                st.write("✍️ Генеруємо сценарій...")
                prompt = f"""Ти креативний контент-мейкер. Напиши текст, який буде з'являтися прямо НА ЕКРАНІ у відео TikTok/Reels. Озвучки не буде, відео читатимуть очима!
ВАЖЛИВО: Видай ЛИШЕ чистий текст для екрану. Розбий його на 3 короткі фрази (кожна з нового рядка). 
Пиши інтригуюче, кожна фраза максимум 5-7 слів! ЖОДНИХ коментарів, зірочок і тире.
Новина: {clean_text}"""

                prompt_desc = f"""Напиши короткий, інтригуючий опис для TikTok до цієї новини з 5-7 хештегами (#новини #деньзаднем #хмельниччина).
Новина: {clean_text}"""

                # Надійний бекап-сценарій без обрізання слів
                words_title = latest_news.title.split()
                line1 = " ".join(words_title[:6])
                line2 = " ".join(words_title[6:12]) if len(words_title) > 6 else "Подробиці зухвалого злочину"
                line3 = "Деталі розслідування на сайті"
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
                
                st.write("🎬 Збираємо динамічне відео...")
                video_path = create_vertical_video(found_images, script)
                status.update(label="Готово!", state="complete", expanded=False)
            
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
            st.error(f"Виникла помилка: {e}")
