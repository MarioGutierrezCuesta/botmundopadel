import os
import io
import re
import json
import threading
import requests
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageChops
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "fc389bd2dcdb6a12d0c7d839b0d4cf58")
CANAL_ID = "@mundopadelesp"

# Tags y Parámetros de Afiliado
TAG_AMAZON = "mundopadel09a-21" 
TAG_TEMU = "ala334124"
TAG_PADELMARKET = "24562"

# Configuración CJ Affiliate (PadelNuestro)
CJ_PID = os.environ.get("CJ_PID", "101860715")
CJ_AID_PADELNUESTRO = os.environ.get("CJ_AID", "17306895")

# Configuración de Marca (Ruta del Logo Local)
LOGO_PATH = "logo.png"

# ==========================================
# 2. SERVIDOR WEB (Keep-Alive para Render)
# ==========================================
web_app = Flask('')

@web_app.route('/')
@web_app.route('/health')
def home():
    return "Bot Chollos PADEL activo", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 3. TRATAMIENTO DE ENLACES Y AFILIACIÓN
# ==========================================
def descorchar_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        r = requests.get(url, allow_redirects=True, headers=headers, timeout=15)
        return r.url
    except Exception:
        return url

def procesar_enlace_afiliado(url_original):
    # CJ Affiliate (PadelNuestro)
    cj_domains = ["anrdoezrs.net", "dpbolvw.net", "tkqlhce.com", "jdoqocy.com", "kqzyfj.com"]
    if any(domain in url_original for domain in cj_domains):
        match_url = re.search(r'url=([^&]+)', url_original)
        if match_url:
            url_real = unquote(match_url.group(1))
        else:
            url_real = descorchar_url(url_original.strip())
        return url_original.strip(), "PADELNUESTRO", url_real

    # Awin / PadelMarket acortados (tidd.ly)
    if "tidd.ly" in url_original:
        url_real = descorchar_url(url_original.strip())
        url_base = url_real.split('?')[0]
        url_final = f"{url_base}?ref={TAG_PADELMARKET}"
        return url_final, "PADELMARKET", url_real

    url_real = descorchar_url(url_original.strip())
    
    # PadelNuestro
    if "padelnuestro.com" in url_real or "padelnuestro" in url_original:
        tienda = "PADELNUESTRO"
        if f"click-{CJ_PID}" not in url_real:
            url_encoded = quote(url_real, safe='')
            url_final = f"https://www.anrdoezrs.net/click-{CJ_PID}-{CJ_AID_PADELNUESTRO}?url={url_encoded}"
        else:
            url_final = url_real
        return url_final, tienda, url_real

    # PadelMarket (Sin créditos)
    if "padelmarket.com" in url_real or "padelmarket" in url_original:
        tienda = "PADELMARKET"
        url_base = url_real.split('?')[0]
        url_final = f"{url_base}?ref={TAG_PADELMARKET}"
        return url_final, tienda, url_real

    # Temu
    if "temu.com" in url_real or "temu.to" in url_original or "share.temu.com" in url_original:
        tienda = "TEMU"
        if "share.temu.com" in url_original:
            return url_original.strip(), tienda, url_real
        
        if "referral_code" not in url_real:
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}referral_code={TAG_TEMU}"
        else:
            url_final = url_real
        return url_final, tienda, url_real

    # Amazon
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
            
    return url_final, tienda, url_real

# ==========================================
# 4. SCRAPERS GRATUITOS (DIRECTOS)
# ==========================================
def obtener_datos_padelmarket(url_real):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'es-ES,es;q=0.9'
    }
    try:
        resp = requests.get(url_real, headers=headers, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            titulo = soup.find('meta', property='og:title')
            imagen = soup.find('meta', property='og:image')
            return {
                "titulo": titulo['content'] if titulo else "Producto PadelMarket",
                "imagen_url": imagen['content'] if imagen else None
            }
    except Exception:
        pass
    return None

def obtener_datos_padelnuestro(url_real):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'es-ES,es;q=0.9'
    }
    try:
        resp = requests.get(url_real, headers=headers, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            titulo = soup.find('meta', property='og:title')
            imagen = soup.find('meta', property='og:image')
            return {
                "titulo": titulo['content'] if titulo else "Producto Padel Nuestro",
                "imagen_url": imagen['content'] if imagen else None
            }
    except Exception:
        pass
    return None

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

    # Backup mediante ScraperAPI solo si se bloquea la petición directa
    if not html_content and SCRAPER_API_KEY:
        payload = {'api_key': SCRAPER_API_KEY, 'url': url_real, 'country_code': 'es'}
        try:
            r = requests.get('http://api.scraperapi.com', params=payload, timeout=25)
            if r.status_code == 200:
                html_content = r.text
        except Exception:
            pass

    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        titulo = soup.find(id="productTitle")
        imagen = soup.find(id="landingImage")
        return {
            "titulo": titulo.get_text().strip() if titulo else "Producto Amazon",
            "imagen_url": imagen['src'] if imagen and 'src' in imagen.attrs else None
        }
    return None

# ==========================================
# 5. GENERADOR GRÁFICO (RECORTE Y AUTO-ESCALADO)
# ==========================================
def recortar_bordes_blancos(img):
    """Elimina los márgenes blancos o transparentes sobrantes alrededor del producto"""
    bg = Image.new(img.mode, img.size, (255, 255, 255, 255))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

def generar_imagen_banner(imagen_url, precio_oferta, precio_antes):
    try:
        r = requests.get(imagen_url, timeout=10)
        img_producto = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None

    # Recortar el lienzo blanco gigante que traen las tiendas de origen
    img_producto = recortar_bordes_blancos(img_producto)

    canvas_w, canvas_h = 800, 800
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    # Redimensionar la imagen recortada para maximizar su tamaño visual
    img_producto.thumbnail((700, 480), Image.Resampling.LANCZOS)
    x_pos = (canvas_w - img_producto.width) // 2
    y_pos = (520 - img_producto.height) // 2 + 20
    canvas.paste(img_producto, (x_pos, y_pos), img_producto)

    # Añadir Logo
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo.thumbnail((95, 95))
            canvas.paste(logo, (35, 670), logo)
        except Exception:
            pass

    draw = ImageDraw.Draw(canvas)
    
    try:
        font_oferta = ImageFont.truetype("arialbd.ttf", 68)
        font_antes = ImageFont.truetype("arial.ttf", 42)
    except IOError:
        font_oferta = ImageFont.load_default()
        font_antes = ImageFont.load_default()

    y_cursor = 550

    # Precio Anterior Tachado
    if precio_antes:
        texto_antes = f"{precio_antes}€"
        bbox = draw.textbbox((0, 0), texto_antes, font=font_antes)
        w_text = bbox[2] - bbox[0]
        h_text = bbox[3] - bbox[1]
        x_text = (canvas_w - w_text) // 2

        draw.text((x_text, y_cursor), texto_antes, fill=(200, 40, 40, 255), font=font_antes)
        line_y = y_cursor + (h_text // 2) + 10
        draw.line([(x_text - 10, line_y), (x_text + w_text + 10, line_y)], fill=(200, 40, 40, 255), width=5)
        y_cursor += 60

    # Botón Naranja con Precio Final
    if precio_oferta:
        texto_oferta = f"{precio_oferta}€"
        bbox_of = draw.textbbox((0, 0), texto_oferta, font=font_oferta)
        w_of = bbox_of[2] - bbox_of[0]
        h_of = bbox_of[3] - bbox_of[1]

        padding_x, padding_y = 50, 16
        rect_w = w_of + (padding_x * 2)
        rect_h = h_of + (padding_y * 2)

        rect_x = (canvas_w - rect_w) // 2
        rect_y = y_cursor

        draw.rounded_rectangle([rect_x, rect_y, rect_x + rect_w, rect_y + rect_h], radius=20, fill=(255, 102, 0, 255))
        
        text_x = rect_x + padding_x - bbox_of[0]
        text_y = rect_y + padding_y - bbox_of[1]
        
        draw.text((text_x, text_y), texto_oferta, fill=(255, 255, 255, 255), font=font_oferta)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=95)
    output.seek(0)
    return output

# ==========================================
# 6. MANEJADOR Y PUBLICADOR
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto:
        return

    # Entrada: URL | PRECIO_OFERTA | PRECIO_ANTES | TITULO_OPCIONAL
    partes = [p.strip() for p in texto.split('|')]
    url_input = partes[0]
    precio_oferta = partes[1] if len(partes) > 1 else None
    precio_antes = partes[2] if len(partes) > 2 else None
    titulo_manual = partes[3] if len(partes) > 3 else None

    urls = re.findall(r'https?://[^\s]+', url_input)
    if not urls:
        await update.message.reply_text("❌ No se encontró ningún enlace válido.")
        return

    url_original = urls[0]
    url_afiliado, tienda, url_scraping = procesar_enlace_afiliado(url_original)

    datos = None
    if tienda == "PADELMARKET":
        datos = obtener_datos_padelmarket(url_scraping)
    elif tienda == "PADELNUESTRO":
        datos = obtener_datos_padelnuestro(url_scraping)
    elif tienda == "AMAZON":
        datos = obtener_datos_amazon(url_scraping)

    titulo_final = titulo_manual or (datos.get("titulo") if datos else "Producto Pádel")
    imagen_url_original = datos.get("imagen_url") if datos else None

    # Cálculo Porcentaje Descuento
    dto_str = ""
    if precio_oferta and precio_antes:
        try:
            p_of = float(precio_oferta.replace(',', '.'))
            p_ant = float(precio_antes.replace(',', '.'))
            if p_ant > p_of:
                descuento = round(((p_ant - p_of) / p_ant) * 100)
                dto_str = f" -{descuento}%"
        except ValueError:
            pass

    # Formato visual
    caption = f"🎾 **NUEVO CHOLLAZO{dto_str}** #Publicidad\n\n"
    caption += f"✅ {titulo_final}\n\n"
    caption += f"Sugerido por TU CANAL DE CHOLLOS\n{CANAL_ID}\n\n"

    if tienda == "AMAZON":
        caption += "En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas."
    else:
        caption += f"En calidad de Afiliado de {tienda}, obtengo ingresos por las compras adscritas."

    texto_boton = f"🛍️ VER OFERTA EN {tienda}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(texto_boton, url=url_afiliado)]])

    foto_banner = None
    if imagen_url_original and (precio_oferta or precio_antes):
        foto_banner = generar_imagen_banner(imagen_url_original, precio_oferta, precio_antes)

    try:
        if foto_banner:
            await context.bot.send_photo(
                chat_id=CANAL_ID,
                photo=foto_banner,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        elif imagen_url_original:
            await context.bot.send_photo(
                chat_id=CANAL_ID,
                photo=imagen_url_original,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await context.bot.send_message(
                chat_id=CANAL_ID,
                text=caption,
                parse_mode="Markdown",
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
            
        await update.message.reply_text(f"✅ ¡Anuncio de **{tienda}** generado e insertado correctamente en {CANAL_ID}!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error durante la publicación: {str(e)}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    application.run_polling()

if __name__ == '__main__':
    main()
