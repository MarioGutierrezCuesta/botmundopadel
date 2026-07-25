import os
import io
import threading
import requests
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
# 2. SERVIDOR WEB (Para Render Gratuito)
# ==========================================
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot de chollos activo"

def run_web():
    web_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 3. CARGA DE FUENTE GIGANTE DESDE GOOGLE
# ==========================================
URL_FONT_BOLD = "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Bold.ttf"
URL_FONT_REGULAR = "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Regular.ttf"

try:
    bytes_font_bold = io.BytesIO(requests.get(URL_FONT_BOLD, timeout=10).content)
    bytes_font_regular = io.BytesIO(requests.get(URL_FONT_REGULAR, timeout=10).content)
    FONT_OBTENIDA = True
except Exception:
    FONT_OBTENIDA = False

def obtener_fuentes():
    if FONT_OBTENIDA:
        bytes_font_bold.seek(0)
        bytes_font_regular.seek(0)
        font_logo = ImageFont.truetype(bytes_font_bold, 38)
        bytes_font_bold.seek(0)
        font_p = ImageFont.truetype(bytes_font_bold, 65)
        bytes_font_regular.seek(0)
        font_a = ImageFont.truetype(bytes_font_regular, 36)
        return font_logo, font_p, font_a
    else:
        f = ImageFont.load_default(size=50)
        return f, f, f

# ==========================================
# 4. GENERADOR DE IMAGEN (Con verificación de formato)
# ==========================================
def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, tienda="amazon"):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    }
    
    # Limpieza básica de la URL por si contiene espacios
    url_imagen = url_imagen.strip()
    
    resp = requests.get(url_imagen, headers=headers, timeout=12)
    resp.raise_for_status()

    # Comprobar si lo devuelto es realmente una imagen
    content_type = resp.headers.get('Content-Type', '')
    if 'text/html' in content_type:
        raise ValueError("La URL proporcionada es una página web, no un enlace directo a una imagen.")

    # Abrir e interpretar la imagen
    img_bytes = io.BytesIO(resp.content)
    img_prod = Image.open(img_bytes)
    img_prod = img_prod.convert("RGBA")
    img_prod = img_prod.resize((800, 800))

    lienzo = Image.new("RGBA", (800, 920), (255, 255, 255, 255))
    lienzo.paste(img_prod, (0, 0))

    draw = ImageDraw.Draw(lienzo)
    draw.rectangle([(0, 800), (800, 920)], fill=(20, 20, 20))

    font_logo, font_p, font_a = obtener_fuentes()

    nombre_tienda = tienda.lower()
    color_tienda = (255, 153, 0) if "amazon" in nombre_tienda else (255, 71, 19)
    
    # Nombre Tienda / Logo
    draw.text((25, 835), tienda.lower(), fill=color_tienda, font=font_logo)
    if "amazon" in nombre_tienda:
        draw.arc([35, 870, 130, 890], start=10, end=170, fill=(255, 153, 0), width=4)

    # Precio Oferta
    draw.text((250, 820), f"{p_oferta}€", fill=(255, 255, 255), font=font_p)

    # Precio Antiguo Tachado
    draw.text((630, 835), f"{p_antiguo}€", fill=(220, 60, 60), font=font_a)
    draw.line([(620, 855), (750, 855)], fill=(220, 60, 60), width=3)

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

    if len(datos) != 6:
        await update.message.reply_text(
            f"❌ **Error:** Se leyeron {len(datos)} de 6 campos.\n\n"
            f"Envía los datos así:\n"
            f"`URL_FOTO | PRECIO_OFERTA | PRECIO_ANTIGUO | TIENDA | TITULO | ENLACE`"
        )
        return

    try:
        url_foto, p_oferta, p_antiguo, tienda, titulo, enlace = datos

        msg_espera = await update.message.reply_text("⏳ Generando oferta y publicando...")

        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, tienda)

        try:
            val_oferta = float(p_oferta.replace(',', '.'))
            val_antiguo = float(p_antiguo.replace(',', '.'))
            desc_pct = int(round((1 - (val_oferta / val_antiguo)) * 100))
            str_desc = f"{desc_pct}%"
        except Exception:
            str_desc = "OFERTA"

        caption = (
            f"🔥 **{titulo}** 🔥 | #{tienda.capitalize()} #Publicidad #OfertaFlash\n\n"
            f"📉 **DESCUENTO:** {str_desc}\n"
            f"🔥 **Precio:** {p_oferta}€\n"
            f"❌ **Precio recomendado:** {p_antiguo}€\n\n"
            f"👉 [Ver aquí en {tienda.capitalize()}]({enlace})"
        )

        await context.bot.send_photo(
            chat_id=CANAL_ID,
            photo=foto_bytes,
            caption=caption,
            parse_mode="Markdown"
        )

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text("✅ ¡Publicado en el canal con éxito!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar: {str(e)}")

# ==========================================
# 6. ARRANQUE DEL BOT
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
