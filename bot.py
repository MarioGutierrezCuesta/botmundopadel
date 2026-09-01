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
TAG_TEMU = "TU_CODIGO_TEMU"                # Reemplaza con tu código de Temu si lo utilizas
TAG_PADELMARKET = "24562"                   # Tu código de afiliado de PadelMarket

# ==========================================
# 2. SERVIDOR WEB (Keep-Alive para Render)
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        r = requests.get(url, allow_redirects=True, headers=headers, timeout=15)
        return r.url
    except Exception:
        return url

def procesar_enlace_afiliado(url_original):
    if "tidd.ly" in url_original:
        return url_original.strip(), "PADELMARKET"

    url_real = descorchar_url(url_original.strip())
    
    if "padelmarket.com" in url_real or "padelmarket" in url_original:
        tienda = "PADELMARKET"
        if "ref=" not in url_real:
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}ref={TAG_PADELMARKET}"
        else:
            url_final = url_real
        return url_final, tienda

    if "temu.com" in url_real or "temu.to" in url_original:
        tienda = "TEMU"
        if "referral_code" not in url_real and TAG_TEMU != "TU_CODIGO_TEMU":
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}referral_code={TAG_TEMU}"
        else:
            url_final = url_real
        return url_final, tienda

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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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

def obtener_datos_padelmarket(url_real):
    url_destino = descorchar_url(url_real)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    resp = requests.get(url_destino, headers=headers, timeout=15)
    if resp.status_code != 200:
        raise ValueError("No se pudo acceder a la página de PadelMarket.")

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    og_img = soup.find("meta", property="og:image")
    url_foto = og_img["content"] if og_img else None

    og_title = soup.find("meta", property="og:title")
    h1_title = soup.find("h1")
    
    if og_title and og_title.get("content"):
        titulo = og_title["content"].strip()
    elif h1_title:
        titulo = h1_title.text.strip()
    else:
        titulo = "Producto PadelMarket"

    return url_foto, titulo

# ==========================================
# 4. GENERADOR DE BANNER CON PRECIO FINAL
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

def calcular_precio_con_cupon(p_oferta_str, cupon_str):
    """Calcula el precio resultante al aplicar un porcentaje de cupón si se detecta un número en el código."""
    try:
        val_o = float(p_oferta_str.replace(',', '.'))
        if not cupon_str:
            return val_o, p_oferta_str

        # Busca dígitos en el cupón (ej. "15EXTRA" -> 15)
        match = re.search(r'(\d+)', cupon_str)
        if match:
            pct_cupon = float(match.group(1))
            precio_final = val_o * (1 - (pct_cupon / 100.0))
            return precio_final, f"{precio_final:.2f}".replace('.', ',')
        
        return val_o, p_oferta_str
    except Exception:
        return None, p_oferta_str

def generar_imagen_chollo(img_input_bytes, p_oferta, p_antiguo, logo_canal_bytes=None, cupon=None):
    img_prod = Image.open(img_input_bytes).convert("RGBA")
    lienzo = crear_degradado_fondo(800, 800)
    img_prod.thumbnail((620, 500), Image.Resampling.LANCZOS)
    lienzo.paste(img_prod, ((800 - img_prod.width) // 2, 50), img_prod)

    draw = ImageDraw.Draw(lienzo)
    
    try:
        font_p = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
        font_a = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
        font_cup = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except Exception:
        font_p = ImageFont.load_default()
        font_a = ImageFont.load_default()
        font_cup = ImageFont.load_default()

    # Determinar si hay precio con descuento de cupón
    v_final, p_mostrar = calcular_precio_con_cupon(p_oferta, cupon)

    if cupon:
        txt_cup = f"✂️ CUPÓN: {cupon.upper()}"
        bbox = draw.textbbox((0, 0), txt_cup, font=font_cup)
        w_box = (bbox[2] - bbox[0]) + 30
        h_box = (bbox[3] - bbox[1]) + 20
        x1_cup = 760 - w_box
        draw.rounded_rectangle([(x1_cup, 30), (760, 30 + h_box)], radius=12, fill=(220, 30, 30))
        draw.text((x1_cup + 15, 38), txt_cup, fill=(255, 255, 255), font=font_cup)

    # Si hay cupón, se toma como precio de referencia previo el de la oferta inicial
    precio_referencia_antiguo = p_oferta if (cupon and v_final) else p_antiguo

    hay_descuento = False
    try:
        v_a = float(precio_referencia_antiguo.replace(',', '.'))
        if v_final and v_a > v_final:
            hay_descuento = True
    except Exception:
        pass

    if hay_descuento:
        txt_antiguo = f"{precio_referencia_antiguo}€"
        draw.text((450, 590), txt_antiguo, fill=(100, 100, 100), font=font_a)
        draw.line([(440, 615), (600, 605)], fill=(220, 30, 30), width=5)

    box_x1 = 430 if hay_descuento else 260
    box_x2 = 750 if hay_descuento else 580
    draw.rounded_rectangle([(box_x1, 650), (box_x2, 755)], radius=20, fill=(255, 115, 35))
    draw.text((box_x1 + 25, 665), f"{p_mostrar}€", fill=(255, 255, 255), font=font_p)

    if logo_canal_bytes:
        try:
            logo_img = Image.open(logo_canal_bytes).convert("RGBA").resize((110, 110))
            mask = Image.new('L', (110, 110), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 110, 110), fill=255)
            pos_logo_x = 50
            lienzo.paste(logo_img, (pos_logo_x, 645), mask)
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

    if len(datos) < 3 or len(datos) > 5:
        await update.message.reply_text("❌ Formato requerido:\n`ENLACE | OFERTA | ANTES | [TITULO] | [CUPON_OPCIONAL]`", parse_mode="Markdown")
        return

    msg_espera = None
    try:
        enlace_input = datos[0]
        p_oferta = datos[1]
        p_antiguo = datos[2]
        desc_usuario = datos[3] if len(datos) >= 4 else ""
        cupon_codigo = datos[4] if len(datos) == 5 else None

        msg_espera = await update.message.reply_text("⏳ Generando publicación...")

        enlace_final, tienda = procesar_enlace_afiliado(enlace_input)

        if es_foto:
            file_photo = await context.bot.get_file(update.message.photo[-1].file_id)
            img_bytes = io.BytesIO()
            await file_photo.download_to_memory(img_bytes)
            img_bytes.seek(0)
            texto_descripcion = desc_usuario if desc_usuario else "Producto de Pádel"
        else:
            if tienda == "AMAZON":
                url_foto, titulo_auto = obtener_datos_amazon(enlace_final)
            elif tienda == "PADELMARKET":
                url_foto, titulo_auto = obtener_datos_padelmarket(enlace_final)
            else:
                raise ValueError("Para enlaces de Temu debes adjuntar la foto del producto en el mensaje de Telegram.")

            if not url_foto:
                raise ValueError(f"No se pudo obtener la imagen del producto de {tienda}.")
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(url_foto, headers=headers, timeout=15)
            resp.raise_for_status()
            img_bytes = io.BytesIO(resp.content)
            texto_descripcion = desc_usuario if desc_usuario else titulo_auto

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

        banner_bytes = generar_imagen_chollo(img_bytes, p_oferta, p_antiguo, logo_bytes, cupon=cupon_codigo)

        # Cálculo global del descuento para la cabecera del mensaje
        v_final, p_final_str = calcular_precio_con_cupon(p_oferta, cupon_codigo)
        str_desc = ""
        try:
            val_a = float(p_antiguo.replace(',', '.'))
            if v_final and val_a > v_final:
                pct = int(round((1 - (v_final / val_a)) * 100))
                str_desc = f"-{pct}%"
        except Exception:
            pass

        encabezado = f"🎾 NUEVO CHOLLAZO {str_desc}" if str_desc else "🎾 NOVEDAD / DISPONIBLE"
        
        if tienda == "AMAZON":
            texto_tienda = "En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas."
        elif tienda == "PADELMARKET":
            texto_tienda = "Enlace de afiliado de PadelMarket."
        else:
            texto_tienda = "Enlace de afiliado de Temu."
        
        texto_cupon = f"\n🏷️ **Aplica el cupón:** `{cupon_codigo.upper()}`\n" if cupon_codigo else ""

        caption = (
            f"{encabezado} #Publicidad\n\n"
            f"✅ {texto_descripcion}\n"
            f"{texto_cupon}\n"
            f"Sugerido por TU CANAL DE CHOLLOS\n@mundopadelesp\n\n"
            f"{texto_tienda}"
        )

        boton_texto = f"🛍️ VER OFERTA EN {tienda}"
        keyboard = [[InlineKeyboardButton(boton_texto, url=enlace_final)]]
        
        await context.bot.send_photo(chat_id=CANAL_ID, photo=banner_bytes, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        
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
