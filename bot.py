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

TAG_AMAZON = "mundopadel09a-21" 
TAG_TEMU = "ala334124"
TAG_PADELMARKET = "24562"

CJ_PID = os.environ.get("CJ_PID", "101860715")
CJ_AID_PADELNUESTRO = os.environ.get("CJ_AID", "17306895")

LOGO_PATH = "logo.png"

# ==========================================
# 2. SERVIDOR WEB (Keep-Alive)
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
# 3. CARGA DE FUENTES TIPOGRÁFICAS
# ==========================================
def cargar_fuente_gigante(tamano=60, es_bold=True):
    nombre_archivo = "OpenSans-Bold.ttf" if es_bold else "OpenSans-Regular.ttf"
    if not os.path.exists(nombre_archivo):
        url = f"https://github.com/google/fonts/raw/main/ofl/opensans/{nombre_archivo}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(nombre_archivo, "wb") as f:
                    f.write(r.content)
        except Exception:
            pass
            
    if os.path.exists(nombre_archivo):
        try:
            return ImageFont.truetype(nombre_archivo, tamano)
        except Exception:
            pass

    for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/ttf/DejaVuSans-Bold.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, tamano)
            except Exception:
                pass

    return ImageFont.load_default()

# ==========================================
# 4. TRATAMIENTO DE ENLACES Y AFILIACIÓN
# ==========================================
def descorchar_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        r = requests.get(url, allow_redirects=True, headers=headers, timeout=15)
        return r.url
    except Exception:
        return url

def procesar_enlace_afiliado(url_original):
    cj_domains = ["anrdoezrs.net", "dpbolvw.net", "tkqlhce.com", "jdoqocy.com", "kqzyfj.com"]
    if any(domain in url_original for domain in cj_domains):
        match_url = re.search(r'url=([^&]+)', url_original)
        if match_url:
            url_real = unquote(match_url.group(1))
        else:
            url_real = descorchar_url(url_original.strip())
        return url_original.strip(), "PADELNUESTRO", url_real

    if "tidd.ly" in url_original:
        url_real = descorchar_url(url_original.strip())
        url_base = url_real.split('?')[0]
        url_final = f"{url_base}?ref={TAG_PADELMARKET}"
        return url_final, "PADELMARKET", url_real

    url_real = descorchar_url(url_original.strip())
    
    if "padelnuestro.com" in url_real or "padelnuestro" in url_original:
        tienda = "PADELNUESTRO"
        if f"click-{CJ_PID}" not in url_real:
            url_encoded = quote(url_real, safe='')
            url_final = f"https://www.anrdoezrs.net/click-{CJ_PID}-{CJ_AID_PADELNUESTRO}?url={url_encoded}"
        else:
            url_final = url_real
        return url_final, tienda, url_real

    if "padelmarket.com" in url_real or "padelmarket" in url_original:
        tienda = "PADELMARKET"
        url_base = url_real.split('?')[0]
        url_final = f"{url_base}?ref={TAG_PADELMARKET}"
        return url_final, tienda, url_real

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
# 5. SCRAPERS DIRECTOS
# ==========================================
def obtener_datos_padelmarket(url_real):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        resp = requests.get(url_real, headers=headers, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            titulo = soup.find('meta', property='og:title')
            
            img_url = None

            # 1. Buscar en JSON-LD (Estructura de datos oficial de productos, evita placeholders)
            scripts_json = soup.find_all('script', type='application/ld+json')
            for s in scripts_json:
                try:
                    data = json.loads(s.string)
                    if isinstance(data, list):
                        data = data[0]
                    if data.get('@type') == 'Product' and 'image' in data:
                        images = data['image']
                        if isinstance(images, list) and len(images) > 0:
                            img_url = images[0]
                        elif isinstance(images, str):
                            img_url = images
                        break
                except Exception:
                    pass

            # 2. Si no hay JSON-LD, buscar la imagen del producto evitando placeholders
            if not img_url:
                imagenes = soup.find_all('img')
                for img in imagenes:
                    src = img.get('data-src') or img.get('data-original') or img.get('src') or ''
                    if src and not any(placeholder in src.lower() for placeholder in ['placeholder', 'loading', 'default', 'svg', 'data:image']):
                        if 'media/catalog/product' in src or 'images/' in src or 'products/' in src:
                            img_url = src
                            break

            # 3. Fallback a og:image
            if not img_url:
                imagen_meta = soup.find('meta', property='og:image')
                if imagen_meta:
                    img_url = imagen_meta['content']

            # Limpiar URL si es relativa o miniatura
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = 'https://www.padelnuestro.com' + img_url

                # Forzar alta resolución sustituyendo dimensiones de caché
                img_url = re.sub(r'-\d+x\d+\.', '.', img_url)
                img_url = re.sub(r'/cache/[^/]+/', '/image/', img_url)

            return {
                "titulo": titulo['content'] if titulo else "Producto Padel Nuestro",
                "imagen_url": img_url
            }
    except Exception:
        pass
    return None

def obtener_datos_amazon(url_real):
    html_content = ""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url_real, headers=headers, timeout=10)
        if resp.status_code == 200 and "captcha" not in resp.text.lower():
            html_content = resp.text
    except Exception:
        pass

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
# 6. GENERADOR GRÁFICO
# ==========================================
def recortar_bordes_blancos(img):
    img_rgb = img.convert("RGB")
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    diff = ImageChops.difference(img_rgb, bg).convert("L")
    mask = diff.point(lambda p: 255 if p > 15 else 0)
    bbox = mask.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

def crear_fondo_degradado(width, height, color_inicio=(255, 255, 255), color_fin=(226, 232, 240)):
    base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(base)
    for y in range(height):
        r = int(color_inicio[0] + (color_fin[0] - color_inicio[0]) * (y / height))
        g = int(color_inicio[1] + (color_fin[1] - color_inicio[1]) * (y / height))
        b = int(color_inicio[2] + (color_fin[2] - color_inicio[2]) * (y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    return base

def generar_imagen_banner(imagen_url, precio_oferta, precio_antes):
    try:
        r = requests.get(imagen_url, timeout=10)
        img_producto = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None

    img_producto = recortar_bordes_blancos(img_producto)

    if img_producto.width < 350 or img_producto.height < 350:
        factor_escala = max(500 / img_producto.width, 500 / img_producto.height)
        nuevo_w = int(img_producto.width * factor_escala)
        nuevo_h = int(img_producto.height * factor_escala)
        img_producto = img_producto.resize((nuevo_w, nuevo_h), Image.Resampling.LANCZOS)

    canvas_w, canvas_h = 800, 800
    canvas = crear_fondo_degradado(canvas_w, canvas_h)

    max_w, max_h = 600, 460
    img_producto.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    
    x_pos = (canvas_w - img_producto.width) // 2
    y_pos = (480 - img_producto.height) // 2 + 10
    canvas.paste(img_producto, (x_pos, y_pos), img_producto)

    draw = ImageDraw.Draw(canvas)

    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            size = (80, 80)
            logo.thumbnail(size, Image.Resampling.LANCZOS)
            
            mask = Image.new('L', logo.size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, logo.size[0], logo.size[1]), fill=255)
            
            draw.ellipse((35, 675, 35 + logo.size[0] + 8, 675 + logo.size[1] + 8), fill=(255, 255, 255, 255), outline=(210, 215, 220, 255), width=2)
            canvas.paste(logo, (39, 679), mask)
        except Exception:
            pass

    font_oferta = cargar_fuente_gigante(tamano=70, es_bold=True)
    font_antes = cargar_fuente_gigante(tamano=45, es_bold=False)

    if precio_antes:
        texto_antes = f"{precio_antes}€"
        bbox_ant = draw.textbbox((0, 0), texto_antes, font=font_antes)
        w_ant = bbox_ant[2] - bbox_ant[0]
        h_ant = bbox_ant[3] - bbox_ant[1]
        x_ant = (canvas_w - w_ant) // 2
        y_ant = 510

        draw.text((x_ant, y_ant), texto_antes, fill=(200, 30, 30, 255), font=font_antes)
        line_y = y_ant + (h_ant // 2) + 2
        draw.line([(x_ant - 12, line_y), (x_ant + w_ant + 12, line_y)], fill=(200, 30, 30, 255), width=5)

    if precio_oferta:
        texto_oferta = f"{precio_oferta}€"
        bbox_of = draw.textbbox((0, 0), texto_oferta, font=font_oferta)
        w_of = bbox_of[2] - bbox_of[0]
        h_of = bbox_of[3] - bbox_of[1]

        pad_x, pad_y = 45, 18
        rect_w = w_of + (pad_x * 2)
        rect_h = h_of + (pad_y * 2)

        rect_x = canvas_w - rect_w - 40
        rect_y = 620

        draw.rounded_rectangle(
            [rect_x, rect_y, rect_x + rect_w, rect_y + rect_h],
            radius=22,
            fill=(255, 102, 0, 255)
        )

        text_x = rect_x + pad_x - bbox_of[0]
        text_y = rect_y + pad_y - bbox_of[1]
        draw.text((text_x, text_y), texto_oferta, fill=(255, 255, 255, 255), font=font_oferta)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=95)
    output.seek(0)
    return output

# ==========================================
# 7. MANEJADOR Y PUBLICADOR DE TELEGRAM
# ==========================================
async def asegurar_logo_local(context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(LOGO_PATH):
        try:
            chat = await context.bot.get_chat(CANAL_ID)
            if chat.photo:
                file = await context.bot.get_file(chat.photo.big_file_id)
                await file.download_to_drive(LOGO_PATH)
        except Exception:
            pass

async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto:
        return

    await asegurar_logo_local(context)

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
