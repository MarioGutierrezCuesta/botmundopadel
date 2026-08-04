import os
import io
import re
import json
import threading
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# 1. CONFIGURACIÓN DE TUS DATOS
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "fc389bd2dcdb6a12d0c7d839b0d4cf58")
CANAL_ID = "@mundopadelesp"
TU_TAG = "mundopadel09a-21" 

# ==========================================
# 2. SERVIDOR WEB (Para Render / Keep-Alive)
# ==========================================
web_app = Flask('')

@web_app.route('/')
@web_app.route('/health')
def home():
    return "Bot de chollos activo con ScraperAPI", 200

def run_web():
    # Render asigna dinámicamente un puerto en la variable PORT (por defecto 8080)
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# Arranque del servidor Flask en hilo independiente para no bloquear Telegram
threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 3. EXTRACCIÓN CON SCRAPERAPI
# ==========================================
def descorchar_url_corta(url):
    # Si detecta que ya es una URL de producto, la devuelve tal cual
    if "amazon.es/dp/" in url or "amazon.es/gp/" in url:
        return url
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    try:
        # Usamos get con redirecciones activas para seguir el amzn.to hasta la URL final
        r = requests.get(url, allow_redirects=True, headers=headers, timeout=15)
        return r.url
    except Exception:
        return url

def obtener_datos_amazon_scraper(url_afiliado):
    if not SCRAPER_API_KEY:
        raise ValueError("No se ha configurado la SCRAPER_API_KEY.")

    url_real = descorchar_url_corta(url_afiliado.strip())

    payload = {
        'api_key': SCRAPER_API_KEY,
        'url': url_real,
        'country_code': 'es'
    }
    
    resp = requests.get('http://api.scraperapi.com', params=payload, timeout=60)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')

    url_foto = None
    titulo = "Producto de Padel"

    # Intentos de extraer imagen
    img_tag = (
        soup.find("img", {"id": "landingImage"}) or 
        soup.find("img", {"id": "imgBlkFront"}) or
        soup.find("img", {"id": "main-image"}) or
        soup.find("img", {"class": "a-dynamic-image"}) or
        soup.find("img", {"id": "landingImage_0"})
    )

    if img_tag:
        if img_tag.get("data-old-hires"):
            url_foto = img_tag["data-old-hires"]
        elif img_tag.get("data-a-dynamic-image"):
            try:
                dyn_dict = json.loads(img_tag["data-a-dynamic-image"])
                url_foto = list(dyn_dict.keys())[0]
            except Exception:
                pass
        if not url_foto and img_tag.get("src"):
            url_foto = img_tag["src"]

    if not url_foto:
        og_img = soup.find("meta", property="og:image") or soup.find("meta", {"name": "twitter:image"})
        if og_img and og_img.get("content"):
            url_foto = og_img["content"]

    if not url_foto:
        all_imgs = soup.find_all("img", src=True)
        for img in all_imgs:
            src = img["src"]
            if "media-amazon.com/images/I/" in src and not src.endswith(".gif") and "sprite" not in src and "captcha" not in src:
                url_foto = src
                break

    # Limpieza de parámetros de URL de imagen
    if url_foto and "media-amazon.com" in url_foto:
        url_foto = re.sub(r'\._AC_.*_\.', '.', url_foto)
        url_foto = re.sub(r'\._SX\d+_\.', '.', url_foto)
        url_foto = re.sub(r'\._SY\d+_\.', '.', url_foto)

    title_tag = soup.find("span", {"id": "productTitle"})
    if title_tag:
        titulo = title_tag.text.strip()
    else:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            titulo = og_title["content"].split(":")[0].strip()

    if not url_foto:
        raise ValueError("No se pudo extraer la imagen del producto.")

    return url_foto, titulo

# ==========================================
# 4. GENERADOR DE IMAGEN
# ==========================================
def crear_degradado_fondo(ancho, alto):
    base = Image.new("RGBA", (ancho, alto), (255, 255, 255, 255))
    bottom_color = (210, 247, 220)
    
    mask = Image.new("L", (1, alto))
    for y in range(alto):
        if y < int(alto * 0.55):
            val = 0
        else:
            val = int(255 * (y - alto * 0.55) / (alto * 0.45))
        mask.putpixel((0, y), val)
    
    mask = mask.resize((ancho, alto))
    bottom_layer = Image.new("RGBA", (ancho, alto), bottom_color + (255,))
    base.paste(bottom_layer, (0, 0), mask)
    return base

def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, logo_canal_bytes=None):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    resp = requests.get(url_imagen, headers=headers, timeout=15)
    resp.raise_for_status()

    img_bytes = io.BytesIO(resp.content)
    img_prod = Image.open(img_bytes).convert("RGBA")
    
    lienzo = crear_degradado_fondo(800, 800)
    img_prod.thumbnail((620, 520), Image.Resampling.LANCZOS)
    pos_x = (800 - img_prod.width) // 2
    pos_y = 60
    lienzo.paste(img_prod, (pos_x, pos_y), img_prod)

    draw = ImageDraw.Draw(lienzo)

    try:
        font_p = ImageFont.truetype("DejaVuSans-Bold.ttf", 68)
        font_a = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
    except Exception:
        font_p = font_a = ImageFont.load_default(size=50)

    # Precio Antiguo
    txt_antiguo = f"{p_antiguo}€"
    pos_a_x, pos_a_y = 550, 580
    draw.text((pos_a_x, pos_a_y), txt_antiguo, fill=(0, 0, 0), font=font_a)
    draw.line([(pos_a_x - 10, pos_a_y + 45), (pos_a_x + 160, pos_a_y + 5)], fill=(220, 30, 30), width=7)
    draw.line([(pos_a_x - 10, pos_a_y + 5), (pos_a_x + 160, pos_a_y + 45)], fill=(220, 30, 30), width=7)

    # Precio Oferta
    txt_oferta = f"{p_oferta}€"
    box_x1, box_y1 = 400, 660
    box_x2, box_y2 = 760, 765
    draw.rounded_rectangle([(box_x1, box_y1), (box_x2, box_y2)], radius=25, fill=(255, 115, 35))
    draw.text((box_x1 + 20, box_y1 + 10), txt_oferta, fill=(255, 255, 255), font=font_p)

    if logo_canal_bytes:
        try:
            logo_img = Image.open(logo_canal_bytes).convert("RGBA")
            logo_img = logo_img.resize((100, 100))
            mask = Image.new('L', (100, 100), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 100, 100), fill=255)
            lienzo.paste(logo_img, (50, 660), mask)
        except Exception:
            pass

    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ==========================================
# 5. MANEJO DE MENSAJES
# ==========================================
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    linea_limpia = texto.replace('\n', ' ')
    datos = [d.strip() for d in linea_limpia.split("|") if d.strip()]

    if len(datos) < 3 or len(datos) > 4:
        await update.message.reply_text(
            f"❌ Formato incorrecto ({len(datos)} campos).\n"
            f"Envía: ENLACE | PRECIO_OFERTA | PRECIO_ANTIGUO | DESCRIPCION"
        )
        return

    try:
        enlace_original = datos[0]
        p_oferta = datos[1]
        p_antiguo = datos[2]
        desc_usuario = datos[3] if len(datos) == 4 else ""

        msg_espera = await update.message.reply_text("⏳ Procesando...")

        # 1. Obtener imagen y título
        url_foto, titulo_auto = obtener_datos_amazon_scraper(enlace_original)
        texto_descripcion = desc_usuario if desc_usuario else titulo_auto

        # 2. Descorchar la URL real y añadirle el tag
        enlace_final = descorchar_url_corta(enlace_original)
        if "tag=" not in enlace_final:
            if "?" in enlace_final:
                enlace_final = f"{enlace_final}&tag={TU_TAG}"
            else:
                enlace_final = f"{enlace_final}?tag={TU_TAG}"

        # 3. Logo del canal
        logo_bytes = None
        try:
            chat_info = await context.bot.get_chat(CANAL_ID)
            if chat_info.photo:
                file_info = await context.bot.get_file(chat_info.photo.small_file_id)
                logo_bytes = io.BytesIO()
                await file_info.download_to_memory(logo_bytes)
                logo_bytes.seek(0)
        except Exception:
            pass

        # 4. Generar imagen
        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, logo_bytes)

        # 5. Calcular descuento
        try:
            val_oferta = float(p_oferta.replace(',', '.'))
            val_antiguo = float(p_antiguo.replace(',', '.'))
            desc_pct = int(round((1 - (val_oferta / val_antiguo)) * 100))
            str_desc = f"-{desc_pct}%"
        except Exception:
            str_desc = ""

        caption = (
            f"🎾 NUEVO CHOLLAZO {str_desc} #Publicidad\n\n"
            f"✅ {texto_descripcion}\n\n"
            f"Sugerido por TU CANAL DE CHOLLOS\n@mundopadelesp\n"
            f"TU CANAL DE VÍDEOS 👉\n@mundopadelvid\n"
            f"INSTAGRAM @mundo_padel_esp"
        )

        # 6. Enviar
        keyboard = [[InlineKeyboardButton("🛍️ VER OFERTA EN AMAZON", url=enlace_final)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(chat_id=CANAL_ID, photo=foto_bytes, caption=caption, reply_markup=reply_markup)
        
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text("✅ ¡Chollo publicado!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar: {str(e)}")

# ==========================================
# 6. ARRANQUE
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
