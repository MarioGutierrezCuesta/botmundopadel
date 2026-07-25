import os
import io
import requests
import threading
from flask import Flask

# Servidor web falso para que Render no mate el proceso
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot de chollos activo"

def run_web():
    web_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_web).start()

from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- TUS DATOS ---
TELEGRAM_TOKEN = "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc"
CANAL_ID = "@mundopadelesp" # Incluye el @

def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, tienda="amazon"):
    # 1. Descargar imagen original
    resp = requests.get(url_imagen)
    img_prod = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    img_prod = img_prod.resize((800, 800))

    # 2. Lienzo blanco
    lienzo = Image.new("RGBA", (800, 920), (255, 255, 255, 255))
    lienzo.paste(img_prod, (0, 0))

    # 3. Franja negra inferior
    draw = ImageDraw.Draw(lienzo)
    draw.rectangle([(0, 800), (800, 920)], fill=(20, 20, 20))

    # 4. Fuentes
    try:
        font_p = ImageFont.truetype("arial.ttf", 55)
        font_a = ImageFont.truetype("arial.ttf", 35)
        font_t = ImageFont.truetype("arial.ttf", 30)
    except:
        font_p = font_a = font_t = ImageFont.load_default()

    # 5. Textos (Tienda, Oferta, Antiguo)
    color_tienda = (255, 153, 0) if tienda.lower() == "amazon" else (255, 71, 19)
    draw.text((20, 835), tienda.capitalize(), fill=color_tienda, font=font_t)
    draw.text((240, 825), f"{p_oferta}€", fill=(255, 255, 255), font=font_p)
    
    # Precio antiguo tachado
    draw.text((600, 835), f"{p_antiguo}€", fill=(220, 50, 50), font=font_a)
    draw.line([(595, 855), (710, 855)], fill=(220, 50, 50), width=3)

    # Guardar en memoria
    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG')
    output.seek(0)
    return output

async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Formato esperado del mensaje:
    # URL_FOTO | PRECIO_OFERTA | PRECIO_ANTIGUO | TIENDA | TITULO | ENLACE_AFILIADO
    try:
        texto = update.message.text
        datos = [d.strip() for d in texto.split("|")]
        
        url_foto, p_oferta, p_antiguo, tienda, titulo, enlace = datos

        # Crear imagen en la nube
        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, tienda)

        # Publicar en el canal
        caption = f"🔥 **{titulo}**\n\n💰 **Precio:** {p_oferta}€ *(Antes: {p_antiguo}€)*\n\n🛒 **Comprar aquí:** {enlace}"
        await context.bot.send_photo(chat_id=CANAL_ID, photo=foto_bytes, caption=caption, parse_mode="Markdown")
        
        await update.message.reply_text("✅ ¡Publicado en el canal con éxito!")
    except Exception as e:
        await update.message.reply_text("❌ Formato incorrecto. Envía:\n`URL_FOTO | PRECIO | ANTES | TIENDA | TITULO | LINK`")

if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
