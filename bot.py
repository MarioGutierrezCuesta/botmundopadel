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
# 3. GENERADOR DE IMAGEN (Estilo exacto)
# ==========================================
def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, tienda="amazon"):
    # Descargar imagen simulando navegador real
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    }
    resp = requests.get(url_imagen, headers=headers, timeout=10)
    resp.raise_for_status()

    # Redimensionar producto
    img_prod = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    img_prod = img_prod.resize((800, 800))

    # Lienzo de 800x920px (120px de franja negra)
    lienzo = Image.new("RGBA", (800, 920), (255, 255, 255, 255))
    lienzo.paste(img_prod, (0, 0))

    # Franja negra inferior
    draw = ImageDraw.Draw(lienzo)
    draw.rectangle([(0, 800), (800, 920)], fill=(20, 20, 20))

    # Cargar tipografías
    try:
        font_logo = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_p = ImageFont.truetype("DejaVuSans-Bold.ttf", 55)
        font_a = ImageFont.truetype("DejaVuSans.ttf", 32)
    except:
        font_logo = font_p = font_a = ImageFont.load_default(size=40)

    # Dibujar logo Amazon / Tienda
    nombre_tienda = tienda.lower()
    color_tienda = (255, 153, 0) if "amazon" in nombre_tienda else (255, 71, 19)
    draw.text((25, 835), tienda.lower(), fill=color_tienda, font=font_logo)
    
    if "amazon" in nombre_tienda:
        draw.arc([35, 865, 130, 885], start=10, end=170, fill=(255, 153, 0), width=4)

    # Precio oferta (Blanco, grande)
    draw.text((250, 825), f"{p_oferta}€", fill=(255, 255, 255), font=font_p)

    # Precio antiguo tachado (Rojo)
    draw.text((630, 840), f"{p_antiguo}€", fill=(220, 60, 60), font=font_a)
    draw.line([(625, 858), (750, 858)], fill=(220, 60, 60), width=3)

    # Devolver imagen en memoria
    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ==========================================
# 4. PROCESAMIENTO DE MENSAJES Y FORMATO
# ==========================================
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    # Unificar saltos de línea y separar por '|'
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

        # Generar imagen
        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, tienda)

        # Calcular porcentaje de descuento automáticamente
        try:
            val_oferta = float(p_oferta.replace(',', '.'))
            val_antiguo = float(p_antiguo.replace(',', '.'))
            desc_pct = int(round((1 - (val_oferta / val_antiguo)) * 100))
            str_desc = f"{desc_pct}%"
        except:
            str_desc = "OFERTA"

        # Formato del texto exactamente igual al ejemplo
        caption = (
            f"🔥 **{titulo}** 🔥 | #{tienda.capitalize()} #Publicidad #OfertaFlash\n\n"
            f"📉 **DESCUENTO:** {str_desc}\n"
            f"🔥 **Precio:** {p_oferta}€\n"
            f"❌ **Precio recomendado:** {p_antiguo}€\n\n"
            f"👉 [Ver aquí en {tienda.capitalize()}]({enlace})"
        )

        # Publicar en el canal
        await context.bot.send_photo(
            chat_id=CANAL_ID,
            photo=foto_bytes,
            caption=caption,
            parse_mode="Markdown"
        )

        # Confirmación
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text("✅ ¡Publicado en el canal con éxito!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar: {str(e)}")

# ==========================================
# 5. ARRANQUE DEL BOT
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
