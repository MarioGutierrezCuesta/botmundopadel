import os
import io
import re
import threading
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# 1. CONFIGURACIÓN DE TUS DATOS
# ==========================================
TELEGRAM_TOKEN = "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc"
CANAL_ID = "@mundopadelesp"

# ==========================================
# 2. SERVIDOR WEB (Para Render)
# ==========================================
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot de chollos activo"

def run_web():
    web_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 3. EXTRACCIÓN AUTOMÁTICA DESDE AMAZON
# ==========================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
}

def obtener_datos_amazon(url_afiliado):
    """Sigue el enlace de afiliados y extrae la URL de la imagen principal y el título."""
    session = requests.Session()
    resp = session.get(url_afiliado.strip(), headers=HEADERS, timeout=12, allow_redirects=True)
    resp.raise_for_status()

    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    url_foto = None
    titulo = "Producto de Padel"

    # 1. Intentar obtener la imagen principal de alta resolución desde las etiquetas de Amazon
    img_tag = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
    if img_tag:
        if img_tag.get("data-old-hires"):
            url_foto = img_tag["data-old-hires"]
        elif img_tag.get("data-a-dynamic-image"):
            import json
            try:
                dyn_dict = json.loads(img_tag["data-a-dynamic-image"])
                url_foto = list(dyn_dict.keys())[0]  # Obtener la primera URL de la lista
            except Exception:
                pass
        if not url_foto and img_tag.get("src"):
            url_foto = img_tag["src"]

    # Meta tag OpenGraph (Fallback si no encuentra la imagen del DOM)
    if not url_foto:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            url_foto = og_img["content"]

    # Limpiar URL de imagen para forzar la máxima resolución si es de Amazon
    if url_foto and "media-amazon.com" in url_foto:
        url_foto = re.sub(r'\._AC_.*_\.', '.', url_foto)

    # 2. Extraer el Título del Producto
    title_tag = soup.find("span", {"id": "productTitle"})
    if title_tag:
        titulo = title_tag.text.strip()
    else:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            titulo = og_title["content"].split(":")[0].strip()

    if not url_foto:
        raise ValueError("No se pudo extraer la imagen del enlace. Comprueba que el producto esté disponible en Amazon.")

    return url_foto, titulo

# ==========================================
# 4. GENERADOR DE IMAGEN (Diseño Chollo)
# ==========================================
def crear_degradado_fondo(ancho, alto):
    base = Image.new("RGBA", (ancho, alto), (255, 255, 255, 255))
    bottom_color = (210, 247, 220)  # Verde menta
    
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

def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, tienda="amazon", logo_canal_bytes=None):
    resp = requests.get(url_imagen, headers=HEADERS, timeout=12)
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
        font_tienda = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
    except Exception:
        font_p = font_a = font_tienda = ImageFont.load_default(size=50)

    # Logo Amazon
    draw.text((40, 680), "amazon", fill=(0, 0, 0), font=font_tienda)
    draw.arc([55, 725, 230, 755], start=10, end=170, fill=(255, 153, 0), width=6)

    # Precio Antiguo con X roja
    txt_antiguo = f"{p_antiguo}€"
    pos_a_x, pos_a_y = 550, 580
    draw.text((pos_a_x, pos_a_y), txt_antiguo, fill=(0, 0, 0), font=font_a)
    draw.line([(pos_a_x - 10, pos_a_y + 45), (pos_a_x + 160, pos_a_y + 5)], fill=(220, 30, 30), width=7)
    draw.line([(pos_a_x - 10, pos_a_y + 5), (pos_a_x + 160, pos_a_y + 45)], fill=(220, 30, 30), width=7)

    # Cápsula Naranja con Precio Rebajado
    txt_oferta = f"{p_oferta}€"
    box_x1, box_y1 = 400, 660
    box_x2, box_y2 = 760, 765
    draw.rounded_rectangle([(box_x1, box_y1), (box_x2, box_y2)], radius=25, fill=(255, 115, 35))
    draw.text((box_x1 + 20, box_y1 + 10), txt_oferta, fill=(255, 255, 255), font=font_p)

    # Watermark del Canal
    if logo_canal_bytes:
        try:
            logo_img = Image.open(logo_canal_bytes).convert("RGBA")
            logo_img = logo_img.resize((90, 90))
            mask = Image.new('L', (90, 90), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 90, 90), fill=255)
            lienzo.paste(logo_img, (30, 30), mask)
        except Exception:
            pass

    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ==========================================
# 5. PROCESAMIENTO DE MENSAJES
# ==========================================
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    linea_limpia = texto.replace('\n', ' ')
    datos = [d.strip() for d in linea_limpia.split("|") if d.strip()]

    if len(datos) != 4:
        await update.message.reply_text(
            f"❌ **Error:** Se leyeron {len(datos)} de 4 campos.\n\n"
            f"Envía los datos así:\n"
            f"`ENLACE | PRECIO_OFERTA | PRECIO_ANTIGUO | DESCRIPCION`"
        )
        return

    try:
        enlace, p_oferta, p_antiguo, descripcion = datos

        msg_espera = await update.message.reply_text("⏳ Capturando datos de Amazon y generando chollo...")

        # 1. Extraer foto y título automáticamente desde el enlace
        url_foto, titulo_auto = obtener_datos_amazon(enlace)

        # 2. Obtener avatar del canal para la marca de agua
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

        # 3. Generar la imagen del chollo
        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, "amazon", logo_bytes)

        # 4. Calcular el % de descuento
        try:
            val_oferta = float(p_oferta.replace(',', '.'))
            val_antiguo = float(p_antiguo.replace(',', '.'))
            desc_pct = int(round((1 - (val_oferta / val_antiguo)) * 100))
            str_desc = f"-{desc_pct}%"
        except Exception:
            str_desc = ""

        # 5. Redactar caption
        caption = (
            f"🎾 **NUEVO CHOLLAZO {str_desc}** #Publicidad\n\n"
            f"✅ **{titulo_auto}:** {descripcion}\n\n"
            f"📎 **Enlace:** {enlace}"
        )

        # 6. Publicar en el canal
        await context.bot.send_photo(
            chat_id=CANAL_ID,
            photo=foto_bytes,
            caption=caption,
            parse_mode="Markdown"
        )

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text("✅ ¡Chollo publicado en el canal con éxito!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar: {str(e)}")

# ==========================================
# 6. ARRANQUE DEL BOT
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
