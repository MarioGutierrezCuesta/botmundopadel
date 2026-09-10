import os
import io
import re
import json
import threading
import requests
from urllib.parse import quote, unquote
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

# Tags y Parámetros de Afiliado
TAG_AMAZON = "mundopadel09a-21" 
TAG_TEMU = "TU_CODIGO_TEMU"
TAG_PADELMARKET = "24562"

# Configuración CJ Affiliate (PadelNuestro)
CJ_PID = os.environ.get("CJ_PID", "101860715")
CJ_AID_PADELNUESTRO = os.environ.get("CJ_AID", "17306895")

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
    cj_domains = ["anrdoezrs.net", "dpbolvw.net", "tkqlhce.com", "jdoqocy.com", "kqzyfj.com"]
    
    # Si viene directamente un enlace ya formateado de CJ
    if any(domain in url_original for domain in cj_domains):
        match_url = re.search(r'url=([^&]+)', url_original)
        if match_url:
            url_real = unquote(match_url.group(1))
        else:
            url_real = descorchar_url(url_original.strip())
        return url_original.strip(), "PADELNUESTRO", url_real

    if "tidd.ly" in url_original:
        url_real = descorchar_url(url_original.strip())
        return url_original.strip(), "PADELMARKET", url_real

    url_real = descorchar_url(url_original.strip())
    
    # PadelNuestro (vía CJ Affiliate)
    if "padelnuestro.com" in url_real or "padelnuestro" in url_original:
        tienda = "PADELNUESTRO"
        if f"click-{CJ_PID}" not in url_real and CJ_PID != "TU_CJ_PID":
            url_encoded = quote(url_real, safe='')
            url_final = f"https://www.anrdoezrs.net/click-{CJ_PID}-{CJ_AID_PADELNUESTRO}?url={url_encoded}"
        else:
            url_final = url_real
        return url_final, tienda, url_real

    # PadelMarket
    if "padelmarket.com" in url_real or "padelmarket" in url_original:
        tienda = "PADELMARKET"
        if "ref=" not in url_real:
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}ref={TAG_PADELMARKET}"
        else:
            url_final = url_real
        return url_final, tienda, url_real

    # Temu
    if "temu.com" in url_real or "temu.to" in url_original:
        tienda = "TEMU"
        if "referral_code" not in url_real and TAG_TEMU != "TU_CODIGO_TEMU":
            sep = "&" if "?" in url_real else "?"
            url_final = f"{url_real}{sep}referral_code={TAG_TEMU}"
        else:
            url_final = url_real
        return url_final, tienda, url_real

    # Amazon (Default)
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

def obtener_datos_padelnuestro(url_real):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'es-ES,es;q=0.9'
    }
    try:
        resp = requests.get(url_real, headers=headers, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Intento de extracción por Meta Tags Open Graph
            titulo = soup.find('meta', property='og:title')
            imagen = soup.find('meta', property='og:image')
            
            titulo_val = titulo['content'] if titulo else "Producto Padel Nuestro"
            imagen_val = imagen['content'] if imagen else None
            
            return {
                "titulo": titulo_val,
                "imagen_url": imagen_val
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
# 4. MANEJADOR DE MENSAJES DE TELEGRAM
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto:
        return

    # Extraer primera URL del mensaje
    urls = re.findall(r'https?://[^\s]+', texto)
    if not urls:
        return

    url_original = urls[0]
    url_afiliado, tienda, url_scraping = procesar_enlace_afiliado(url_original)

    # Obtener información según la tienda
    datos = None
    if tienda == "PADELNUESTRO":
        datos = obtener_datos_padelnuestro(url_scraping)
    elif tienda == "AMAZON":
        datos = obtener_datos_amazon(url_scraping)

    if datos and datos.get("imagen_url"):
        mensaje = f"✅ ¡Chollo de **{tienda}** publicado con éxito!\n\nEnlace: {url_afiliado}"
        await update.message.reply_text(mensaje, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Error: No se pudo obtener la información o imagen del producto de {tienda}.")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    application.run_polling()

if __name__ == '__main__':
    main()
