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

# Tags de Afiliado
TAG_AMAZON = "mundopadel09a-21" 
TAG_TEMU = "TU_CODIGO_TEMU"  # Reemplaza con tu código de Temu

# ==========================================
# 2. SERVIDOR WEB (Keep-Alive)
# ==========================================
web_app = Flask('')

@web_app.route('/')
@web_app.route('/health')
def home():
    return "Bot de chollos activo", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 3. TRATAMIENTO DE ENLACES Y SCRAPING
# ==========================================
def descorchar_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        r = requests.get(url, allow_redirects=True, headers=headers, timeout=15)
        return r.url
    except Exception:
        return url

def procesar_enlace_afiliado(url_original):
    url_real = descorchar_url(url_original.strip())
    
    # Si es TEMU
    if "temu.com" in url_real or "temu.to" in url_original:
        tienda = "TEMU"
        if "referral_code" not in url_real and TAG_TEMU != "TU_CODIGO_TEMU":
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}referral_code={TAG_TEMU}"
        else:
            url_final = url_real
        return url_final, tienda

    # Si es AMAZON
    tienda = "AMAZON"
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url_real)
    if match:
        asin = match.group(1)
        url_final = f"https://www.amazon.es/dp/{asin}?tag={TAG_AMAZON}"
    else:
        if "tag=" not in url_real:
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}tag={TAG_AMAZON}"
        else:
            url_final = url_real
            
    return url_final, tienda

def obtener_datos_amazon(url_real):
    html_content = ""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    try:
        resp = requests.get(url_real, headers=headers, timeout=10)
        if resp.status_code == 200 and "captcha" not in resp.text.lower():
            html_content = resp.text
    except Exception:
        pass

    if not html_content and SCRAPER_API_KEY:
        payload = {'api_key': SCRAPER_API_KEY, 'url': url_real, 'country_code': 'es'}
        try:
            resp_scraper = requests.get('http://api.scraperapi.com', params=payload, timeout=30)
            if resp_scraper.status_code == 200:
                html_content = resp_scraper.text
        except Exception:
            pass

    if not html_content:
        raise ValueError("No se pudo extraer la información de Amazon.")

    soup = BeautifulSoup(html_content, 'html.parser')
    url_foto = None
    titulo = "Producto de Pádel"

    img_tag = (
        soup.find("img", {"id": "landingImage"}) or 
        soup.find("img", {"id": "imgBlkFront"}) or
        soup.find("img", {"id": "main-image"}) or
        soup.find("img", {"class": "a-dynamic-image"})
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

    if url_foto and "media-amazon.com" in url_foto:
        url_foto = re.sub(r'\._AC_.*_\.', '.', url_foto)

    title_tag = soup.find("span", {"id": "productTitle"})
    if title_tag:
        titulo = title_tag.text.strip()

    return url_foto, titulo

# ==========================================
# 4. GENERADOR DE BANNER
# ==========================================
def crear_degradado_fondo(ancho, alto):
    base = Image.new("RGBA", (ancho, alto), (255, 255, 255, 255))
    bottom_color = (210, 247, 220)
    mask = Image.new("L", (1, alto))
    for y in range(alto):
        val = 0 if y < int(alto * 0.55) else int(255 * (y - alto * 0.55) / (alto * 0.45))
        mask.putpixel((0, y), val)
    
    mask = mask.resize((ancho, alto))
    bottom_layer = Image.new("RGBA", (ancho, alto), bottom_color + (255,))
    base.paste(bottom_layer, (0, 0), mask)
    return base

def generar_imagen_chollo(img_input_bytes, p_oferta, p_antiguo, logo_canal_bytes=None):
    img_prod = Image.open(img_input_bytes).convert("RGBA")
    lienzo = crear_degradado_fondo(800, 800)
    img_prod.thumbnail((620, 520), Image.Resampling.LANCZOS)
    lienzo.paste(img_prod, ((800 - img_prod.width) // 2, 60), img_prod)

    draw = ImageDraw.Draw(lienzo)
    try:
        font_p = ImageFont.truetype("DejaVuSans-Bold.ttf", 68)
        font_a = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
    except Exception:
        font_p = font_a = ImageFont.load_default(size=50)

    # Validar si existe un precio antiguo real y superior
    hay_descuento = False
    try:
        v_o = float(p_oferta.replace(',', '.'))
        v_a = float(p_antiguo.replace(',', '.'))
        if v_a > v_o:
            hay_descuento = True
    except Exception:
        pass

    # Dibujar precio antiguo tachado solo si hay descuento real
    if hay_descuento:
        txt_antiguo = f"{p_antiguo}€"
        draw.text((550, 580), txt_antiguo, fill=(0, 0, 0), font=font_a)
        draw.line([(540, 625), (710, 585)], fill=(220, 30, 30), width=7)
        draw.line([(540, 585), (710, 625)], fill=(220, 30, 30), width=7)

    # Precio Oferta / Final
    box_x1 = 400 if hay_descuento else 250
    box_x2 = 760 if hay_descuento else 610
    draw.rounded_rectangle([(box_x1, 660), (box_x2, 765)], radius=25, fill=(255, 115, 35))
    draw.text((box_x1 + 20, 670), f"{p_oferta}€", fill=(255, 255, 255), font=font_p)

    # Logo del canal
    if logo_canal_bytes:
        try:
            logo_img = Image.open(logo_canal_bytes).convert("RGBA").resize((100, 100))
            mask = Image.new('L', (100, 100), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 100, 100), fill=255)
            pos_logo_x = 50 if hay_descuento else 80
            lienzo.paste(logo_img, (pos_logo_x, 660), mask)
        except Exception:
            pass

    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ==========================================
# 5. LÓGICA DE PROCESAMIENTO UNIFICADA
# ==========================================
async def procesar_publicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    es_foto = bool(update.message.photo)
    texto_recibido = update.message.caption if es_foto else update.message.text

    if not texto_recibido:
        return

    texto_limpio = texto_recibido.replace('\n', ' ')
    datos = [d.strip() for d in texto_limpio.split("|") if d.strip()]

    if len(datos) < 3 or len(datos) > 4:
        await update.message.reply_text("❌ Formato requerido:\n`ENLACE | OFERTA | ANTES | [TITULO]`", parse_mode="Markdown")
        return

    msg_espera = None
    try:
        enlace_input = datos[0]
        p_oferta = datos[1]
        p_antiguo = datos[2]
        desc_usuario = datos[3] if len(datos) == 4 else ""

        msg_espera = await update.message.reply_text("⏳ Generando publicación...")

        # Procesar enlace y detectar tienda
        enlace_final, tienda = procesar_enlace_afiliado(enlace_input)

        # Obtener la imagen
        if es_foto:
            file_photo = await context.bot.get_file(update.message.photo[-1].file_id)
            img_bytes = io.BytesIO()
            await file_photo.download_to_memory(img_bytes)
            img_bytes.seek(0)
            texto_descripcion = desc_usuario if desc_usuario else "Producto de Pádel"
        else:
            if tienda == "AMAZON":
                url_foto, titulo_auto = obtener_datos_amazon(enlace_final)
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(url_foto, headers=headers, timeout=15)
                resp.raise_for_status()
                img_bytes = io.BytesIO(resp.content)
                texto_descripcion = desc_usuario if desc_usuario else titulo_auto
            else:
                raise ValueError("Para enlaces de Temu debes adjuntar la foto del producto en el mensaje de Telegram.")

        # Obtener logo del canal
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

        # Generar banner
        banner_bytes = generar_imagen_chollo(img_bytes, p_oferta, p_antiguo, logo_bytes)

        # Cálculo de descuento
        str_desc = ""
        try:
            val_o = float(p_oferta.replace(',', '.'))
            val_a = float(p_antiguo.replace(',', '.'))
            if val_a > val_o:
                pct = int(round((1 - (val_o / val_a)) * 100))
                str_desc = f"-{pct}%"
        except Exception:
            pass

        encabezado = f"🎾 NUEVO CHOLLAZO {str_desc}" if str_desc else "🎾 NOVEDAD / DISPONIBLE"
        texto_tienda = "En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas." if tienda == "AMAZON" else "Enlace de afiliado de Temu."
        
        caption = (
            f"{encabezado} #Publicidad\n\n"
            f"✅ {texto_descripcion}\n\n"
            f"Sugerido por TU CANAL DE CHOLLOS\n@mundopadelesp\n"
            f"TU CANAL DE VÍDEOS 👉\n@mundopadelvid\n"
            f"INSTAGRAM @mundo_padel_esp\n\n"
            f"{texto_tienda}"
        )

        boton_texto = f"🛍️ VER OFERTA EN {tienda}"
        keyboard = [[InlineKeyboardButton(boton_texto, url=enlace_final)]]
        
        await context.bot.send_photo(chat_id=CANAL_ID, photo=banner_bytes, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
        
        if msg_espera:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(f"✅ ¡Chollo de {tienda} publicado con éxito!")

    except Exception as e:
        if msg_espera:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
            except Exception:
                pass
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ==========================================
# 6. ARRANQUE DEL BOT
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, procesar_publicacion))
    app.run_polling()
