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
TELEGRAM_TOKEN "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc"  # Reemplaza con el token de tu bot
CANAL_ID = "@mundopadelesp"          # Reemplaza con el @alias de tu canal

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
# 3. GENERADOR DE IMAGEN CON FRANJA NEGRA
# ==========================================
def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, tienda="amazon"):
    # Descargar la imagen simulando un navegador web real para evitar bloqueos (403/404)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    }
    resp = requests.get(url_imagen, headers=headers, timeout=10)
    resp.raise_for_status()

    # Redimensionar producto a 800x800px
    img_prod = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    img_prod = img_prod.resize((800, 800))

    # Crear lienzo blanco de 800x1000px (200px de franja inferior)
    lienzo = Image.new("RGBA", (800, 1000), (255, 255, 255, 255))
    lienzo.paste(img_prod, (0, 0))

    # Dibujar franja negra inferior
    draw = ImageDraw.Draw(lienzo)
    draw.rectangle([(0, 800), (800, 1000)], fill=(20, 20, 20))

    # Cargar tipografías grandes compatibles con Linux/Render
    try:
        font_p = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
        font_a = ImageFont.truetype("DejaVuSans.ttf", 36)
        font_t = ImageFont.truetype("DejaVuSans-Bold.ttf", 38)
    except:
        font_p = font_a = font_t = ImageFont.load_default(size=45)

    # Definir color según la tienda
    color_tienda = (255, 153, 0) if tienda.lower() == "amazon" else (255, 71, 19)

    # Escribir textos en la franja
    draw.text((35, 875), tienda.upper(), fill=color_tienda, font=font_t)
    draw.text((270, 865), f"{p_oferta}€", fill=(255, 255, 255), font=font_p)
    draw.text((580, 875), f"{p_antiguo}€", fill=(220, 60, 60), font=font_a)
    
    # Línea roja para tachar el precio antiguo
    draw.line([(575, 898), (715, 898)], fill=(220, 60, 60), width=4)

    # Convertir a JPEG y devolver en memoria
    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ==========================================
# 4. PROCESAMIENTO DE MENSAJES DE TELEGRAM
# ==========================================
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    # Limpiar saltos de línea y separar por barras '|'
    linea_limpia = texto.replace('\n', ' ')
    datos = [d.strip() for d in linea_limpia.split("|") if d.strip()]

    if len(datos) != 6:
        await update.message.reply_text(
            f"❌ **Error:** Se leyeron {len(datos)} de 6 campos.\n\n"
            f"Estructura requerida (5 barras `|`):\n"
            f"`URL_FOTO | PRECIO_OFERTA | PRECIO_ANTIGUO | TIENDA | TITULO | ENLACE`"
        )
        return

    try:
        url_foto, p_oferta, p_antiguo, tienda, titulo, enlace = datos

        msg_espera = await update.message.reply_text("⏳ Generando imagen y publicando chollo...")

        # Generar imagen maquetada
        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, tienda)

        # Crear texto con formato para el canal
        caption = f"🔥 **{titulo.upper()}**\n\n💰 **Precio:** {p_oferta}€ *(Antes: {p_antiguo}€)*\n\n🛒 **Comprar aquí:** {enlace}"

        # Publicar en el canal
        await context.bot.send_photo(chat_id=CANAL_ID, photo=foto_bytes, caption=caption, parse_mode="Markdown")
        
        # Eliminar mensaje de espera y confirmar
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
