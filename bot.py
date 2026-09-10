import os
import io
import re
import json
import threading
import requests
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageStat
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "fc389bd2dcdb6a12d0c7d839b0d4cf58")

# Canal de destino corregido sin guiones bajos
CANAL_ID = "@MundoPadelEsp"

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
# 5. DETECTOR Y FILTRO ESTRICTO DE IMAGEN
# ==========================================
def es_imagen_valida_producto(url, bytes_img):
    url_lower = url.lower()
    
    palabras_prohibidas = [
        'payment', 'pago', 'visa', 'mastercard', 'paypal', 'sequra', 
        'american', 'express', 'logo', 'icon', 'banner', 'footer', 
        'header', 'sprite', 'badge', 'trust'
    ]
    if any(p in url_lower for p in palabras_prohibidas):
        return False

    try:
        img = Image.open(io.BytesIO(bytes_img)).convert("RGB")
        w, h = img.size
        
        if w < 150 or h < 150:
            return False

        ratio = w / float(h)
        if ratio > 2.2 or ratio < 0.35:
            return False

        return True
    except Exception:
        return False

# ==========================================
# 6. SCRAPERS ESPECÍFICOS
# ==========================================
def obtener_datos_padelnuestro(url_real):
    html_content = ""
    if SCRAPER_API_KEY:
        try:
            payload = {
                'api_key': SCRAPER_API_KEY, 
                'url': url_real, 
                'render': 'true',
                'country_code': 'es'
            }
            r = requests.get('http://api.scraperapi.com', params=payload, timeout=35)
            if r.status_code == 200 and "cloudflare" not in r.text.lower():
                html_content = r.text
        except Exception:
            pass

    if not html_content:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            r = requests.get(url_real, headers=headers, timeout=12)
            if r.status_code == 200:
                html_content = r.text
        except Exception:
            pass

    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
    titulo_elem = soup.find('meta', property='og:title') or soup.find('h1')
    titulo = titulo_elem.get_text().strip() if titulo_elem else "Producto Padel Nuestro"

    candidatos_url = []
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        candidatos_url.append(og_img['content'])

    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if src and ('catalog/product' in src or 'media/catalog' in src):
            candidatos_url.append(src)

    imagen_valida_bytes = None
    headers_img = {'User-Agent': 'Mozilla/5.0'}

    for u in candidatos_url:
        if not u or 'data:image' in u: continue
        if u.startswith('//'): u = 'https:' + u
        elif u.startswith('/'): u = 'https://www.padelnuestro.com' + u

        u = re.sub(r'-\d+x\d+\.', '.', u)
        u = re.sub(r'/cache/[^/]+/', '/image/', u)

        try:
            r_img = requests.get(u, headers=headers_img, timeout=8)
            if r_img.status_code == 200 and es_imagen_valida_producto(u, r_img.content):
                imagen_valida_bytes = r_img.content
                break
        except Exception:
            continue

    return {"titulo": titulo, "imagen_bytes": imagen_valida_bytes}

def obtener_datos_padelmarket(url_real):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url_real, headers=headers, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            titulo = soup.find('meta', property='og:title')
            imagen = soup.find('meta', property='og:image')
            
            img_bytes = None
            if imagen and imagen.get('content'):
                u = imagen['content']
                r = requests.get(u, timeout=8)
                if r.status_code == 200 and es_imagen_valida_producto(u, r.content):
                    img_bytes = r.content

            return {
                "titulo": titulo['content'] if titulo else "Producto PadelMarket",
                "imagen_bytes": img_bytes
            }
    except Exception:
        pass
    return None

def obtener_datos_amazon(url_real):
    html_content = ""
    
    if SCRAPER_API_KEY:
        try:
            payload = {
                'api_key': SCRAPER_API_KEY, 
                'url': url_real, 
                'render': 'true',
                'country_code': 'es'
            }
            r = requests.get('http://api.scraperapi.com', params=payload, timeout=35)
            if r.status_code == 200 and "captcha" not in r.text.lower():
                html_content = r.text
        except Exception:
            pass

    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
    
    titulo = None
    titulo_elem = soup.find(id="productTitle")
    if titulo_elem:
        titulo = titulo_elem.get_text().strip()
    else:
        og_title = soup.find('meta', property='og:title')
        if og_title:
            titulo = og_title.get('content')
            
    titulo_final = titulo if titulo else "Producto Amazon"
    candidatos_img = []
    
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        candidatos_img.append(og_image['content'])

    landing_img = soup.find(id="landingImage") or soup.find(id="imgBlkFront")
    if landing_img:
        for attr in ['data-old-hires', 'data-a-dynamic-image', 'src']:
            val = landing_img.get(attr)
            if val:
                if attr == 'data-a-dynamic-image':
                    try:
                        dict_imgs = json.loads(val.replace('&quot;', '"'))
                        for img_url in dict_imgs.keys():
                            candidatos_img.append(img_url)
                    except Exception:
                        pass
                else:
                    candidatos_img.append(val)

    imagen_valida_bytes = None
    headers_img = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.amazon.es/',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    }

    for u in candidatos_img:
        if not u or 'data:image' in u or 'transparent-pixel' in u:
            continue
            
        u_limpia = re.sub(r'\._AC_SR\d+,\d+_', '', u)
        u_limpia = re.sub(r'\._AC_UY\d+_', '', u_limpia)
        u_limpia = re.sub(r'\._AC_UL\d+_', '', u_limpia)
        u_limpia = re.sub(r'\._[A-Z0-9_,]+_\.', '.', u_limpia)

        try:
            r_img = requests.get(u_limpia, headers=headers_img, timeout=8)
            if r_img.status_code == 200 and es_imagen_valida_producto(u_limpia, r_img.content):
                imagen_valida_bytes = r_img.content
                break
        except Exception:
            continue

    return {"titulo": titulo_final, "imagen_bytes": imagen_valida_bytes}

# ==========================================
# 7. RECORTE DE MARGENES Y FONDOS
# ==========================================
def recortar_espacio_blanco_seguro(img_pil):
    try:
        img_rgba = img_pil.convert("RGBA")
        bg = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
        diff = ImageChops.difference(img_rgba.convert("RGB"), bg.convert("RGB")).convert("L")
        mask = diff.point(lambda p: 255 if p > 15 else 0)
        bbox = mask.getbbox()
        
        if bbox:
            w, h = img_rgba.size
            x1 = max(0, bbox[0] - 12)
            y1 = max(0, bbox[1] - 12)
            x2 = min(w, bbox[2] + 12)
            y2 = min(h, bbox[3] + 12)
            if (x2 - x1) > 100 and (y2 - y1) > 100:
                return img_rgba.crop((x1, y1, x2, y2))
    except Exception:
        pass
    return img_pil

def crear_fondo_degradado_ejemplo(width, height):
    color_blanco = (255, 255, 255)
    color_menta = (220, 245, 235)
    base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(base)
    for y in range(height):
        if y < int(height * 0.45):
            r, g, b = color_blanco
        else:
            factor = (y - height * 0.45) / (height * 0.55)
            factor = factor ** 1.3
            r = int(color_blanco[0] + (color_menta[0] - color_blanco[0]) * factor)
            g = int(color_blanco[1] + (color_menta[1] - color_blanco[1]) * factor)
            b = int(color_blanco[2] + (color_menta[2] - color_blanco[2]) * factor)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    return base

# ==========================================
# 8. GENERADOR GRÁFICO 
# ==========================================
def generar_imagen_banner(imagen_bytes, precio_oferta, precio_antes):
    if not imagen_bytes: return None

    try:
        img_producto = Image.open(io.BytesIO(imagen_bytes))
        img_producto = recortar_espacio_blanco_seguro(img_producto).convert("RGBA")
    except Exception:
        return None

    canvas_w, canvas_h = 800, 800
    canvas = crear_fondo_degradado_ejemplo(canvas_w, canvas_h)

    max_w, max_h = 680, 500
    img_producto.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x_pos = (canvas_w - img_producto.width) // 2
    y_pos = (500 - img_producto.height) // 2 + 10
    canvas.paste(img_producto, (x_pos, y_pos), img_producto)

    draw = ImageDraw.Draw(canvas)

    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo.thumbnail((80, 80), Image.Resampling.LANCZOS)
            mask = Image.new('L', logo.size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, logo.size[0], logo.size[1]), fill=255)
            draw.ellipse((35, 675, 35 + logo.size[0] + 8, 675 + logo.size[1] + 8), fill=(255, 255, 255, 255), outline=(210, 225, 220, 255), width=2)
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
        y_ant = 520
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
        draw.rounded_rectangle([rect_x, rect_y, rect_x + rect_w, rect_y + rect_h], radius=22, fill=(255, 102, 0, 255))
        text_x = rect_x + pad_x - bbox_of[0]
        text_y = rect_y + pad_y - bbox_of[1]
        draw.text((text_x, text_y), texto_oferta, fill=(255, 255, 255, 255), font=font_oferta)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=95)
    output.seek(0)
    return output

# ==========================================
# 9. MANEJADOR Y PUBLICADOR DE TELEGRAM
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
    mensaje_actual = update.message or update.channel_post
    if not mensaje_actual: return

    texto = mensaje_actual.text or mensaje_actual.caption
    if not texto: return

    await asegurar_logo_local(context)
    partes = [p.strip() for p in texto.split('|')]
    url_input = partes[0]
    precio_oferta = partes[1] if len(partes) > 1 else None
    precio_antes = partes[2] if len(partes) > 2 else None
    titulo_manual = partes[3] if len(partes) > 3 else None

    urls = re.findall(r'https?://[^\s]+', url_input)
    if not urls:
        await mensaje_actual.reply_text("❌ No se encontró ningún enlace válido en el mensaje recibido.")
        return

    url_original = urls[0]
    url_afiliado, tienda, url_scraping = procesar_enlace_afiliado(url_original)

    datos = None
    try:
        if tienda == "PADELMARKET":
            datos = obtener_datos_padelmarket(url_scraping)
        elif tienda == "PADELNUESTRO":
            datos = obtener_datos_padelnuestro(url_scraping)
        elif tienda == "AMAZON":
            datos = obtener_datos_amazon(url_scraping)
    except Exception as e:
        await mensaje_actual.reply_text(f"⚠️ Aviso al extraer datos: {str(e)}")

    titulo_final = titulo_manual or (datos.get("titulo") if datos else "Producto Pádel")
    imagen_bytes = datos.get("imagen_bytes") if datos else None

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
    caption += f"En calidad de Afiliado de {tienda}, obtengo ingresos por las compras adscritas."

    texto_boton = f"🛍️ VER OFERTA EN {tienda}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(texto_boton, url=url_afiliado)]])

    foto_banner = None
    if imagen_bytes and (precio_oferta or precio_antes):
        try:
            foto_banner = generar_imagen_banner(imagen_bytes, precio_oferta, precio_antes)
        except Exception as e:
            await mensaje_actual.reply_text(f"⚠️ Error al crear banner: {str(e)}. Se publicará solo texto.")

    try:
        if foto_banner:
            await context.bot.send_photo(
                chat_id=CANAL_ID, photo=foto_banner, caption=caption, 
                parse_mode="Markdown", reply_markup=keyboard
            )
            await mensaje_actual.reply_text(f"✅ ¡Anuncio con BANNER de **{tienda}** publicado en el canal!")
        else:
            await context.bot.send_message(
                chat_id=CANAL_ID, text=caption, parse_mode="Markdown", 
                reply_markup=keyboard, disable_web_page_preview=False
            )
            await mensaje_actual.reply_text(f"✅ ¡Anuncio (solo texto) de **{tienda}** publicado! (No se pudo descargar la foto).")
            
    except Exception as e:
        await mensaje_actual.reply_text(f"❌ Error al publicar en Telegram: {str(e)}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler((filters.TEXT | filters.FORWARDED) & ~filters.COMMAND, procesar_mensaje))
    application.run_polling()

if __name__ == '__main__':
    main()
