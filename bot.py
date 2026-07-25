import os
import io
import threading
import requests
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN DE TUS DATOS ---
TELEGRAM_TOKEN = "8801288601:AAGjU2UNrzNurMg1XGVdL_tWjrLqIcRBWUc"
CANAL_ID = "@mundopadelesp"

# --- SERVIDOR WEB PARA MANTENER RENDER ACTIVO GRATIS ---
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot de chollos activo"

def run_web():
    web_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_web, daemon=True).start()

 # --- FUNCIÓN PARA GENERAR LA IMAGEN CON FRANJA NEGRA Y PRECIOS ---
def generar_imagen_chollo(url_imagen, p_oferta, p_antiguo, tienda="amazon"):
    # 1. Descargar imagen simulando navegador real
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'image/*,*/*;q=0.8'
    }
    resp = requests.get(url_imagen, headers=headers, timeout=10)
    resp.raise_for_status()
    
    img_prod = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    
    # Redimensionar producto a 800x800px
    img_prod = img_prod.resize((800, 800))

    # 2. Crear lienzo más alto (800x1000px) para darle 200px a la franja
    lienzo = Image.new("RGBA", (800, 1000), (255, 255, 255, 255))
    lienzo.paste(img_prod, (0, 0))

    # 3. Dibujar franja negra inferior más ancha (de y=800 a y=1000)
    draw = ImageDraw.Draw(lienzo)
    draw.rectangle([(0, 800), (800, 1000)], fill=(20, 20, 20))

    # 4. Cargar tipografía accesible con tamaño grande garantizado
    try:
        font_p = ImageFont.truetype("DejaVuSans-Bold.ttf", 65)
        font_a = ImageFont.truetype("DejaVuSans.ttf", 40)
        font_t = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except:
        # Si no encuentra DejaVu, cargamos la fuente por defecto pero escalada
        font_p = font_a = font_t = ImageFont.load_default(size=45)

    # 5. Escribir Tienda/Logo, Precio Oferta y Precio Antiguo centrados
    color_tienda = (255, 153, 0) if tienda.lower() == "amazon" else (255, 71, 19)
    
    # Nombre de tienda
    draw.text((30, 875), tienda.capitalize(), fill=color_tienda, font=font_t)
    
    # Precio oferta (en grande)
    draw.text((280, 860), f"{p_oferta}€", fill=(255, 255, 255), font=font_p)
    
    # Precio antiguo tachado
    draw.text((580, 875), f"{p_antiguo}€", fill=(220, 50, 50), font=font_a)
    draw.line([(575, 900), (720, 900)], fill=(220, 50, 50), width=4)

    # Convertir a JPEG y guardar en memoria
    output = io.BytesIO()
    lienzo.convert("RGB").save(output, format='JPEG', quality=95)
    output.seek(0)
    return output



# --- RECEPCIÓN Y PROCESAMIENTO DE MENSAJES ---
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    
    # Unificar saltos de línea y limpiar campos
    linea_limpia = texto.replace('\n', ' ')
    datos = [d.strip() for d in linea_limpia.split("|") if d.strip()]
    
    if len(datos) != 6:
        await update.message.reply_text(
            f"❌ **He leído {len(datos)} de 6 campos.**\n\n"
            f"Recuerda usar exactamente **5 barras `|`** para separar los 6 datos:\n"
            f"`FOTO | PRECIO | ANTES | TIENDA | TITULO | LINK`"
        )
        return

    try:
        url_foto, p_oferta, p_antiguo, tienda, titulo, enlace = datos

        msg_espera = await update.message.reply_text("⏳ Generando imagen y publicando...")

        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, tienda)

        caption = f"🔥 **{titulo}**\n\n💰 **Precio:** {p_oferta}€ *(Antes: {p_antiguo}€)*\n\n🛒 **Comprar aquí:** {enlace}"
        
        await context.bot.send_photo(chat_id=CANAL_ID, photo=foto_bytes, caption=caption, parse_mode="Markdown")
        await update.message.reply_text("✅ ¡Publicado en el canal con éxito!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error al crear/enviar la imagen: {str(e)}")

# --- ARRANQUE DEL BOT ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
