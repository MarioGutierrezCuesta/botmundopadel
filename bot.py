import os
import io
import threading
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
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
# 3. GENERADOR DE IMAGEN (Nuevo Diseño Chollo)
# ==========================================
def crear_degradado_fondo(ancho, alto):
    base = Image.new("RGBA", (ancho, alto), (255, 255, 255, 255))
    bottom_color = (210, 247, 220)  # Verde menta suave
    
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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    }
    
    resp = requests.get(url_imagen.strip(), headers=headers, timeout=12)
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
    except:
        font_p = font_a = font_tienda = ImageFont.load_default(size=50)

    nombre_tienda = tienda.lower()
    if "amazon" in nombre_tienda:
        draw.text((40, 680), "amazon", fill=(0, 0, 0), font=font_tienda)
        draw.arc([55, 725, 230, 755], start=10, end=170, fill=(255, 153, 0), width=6)
    else:
        draw.text((40, 690), tienda.upper(), fill=(20, 20, 20), font=font_tienda)

    txt_antiguo = f"{p_antiguo}€"
    pos_a_x, pos_a_y = 550, 580
    draw.text((pos_a_x, pos_a_y), txt_antiguo, fill=(0, 0, 0), font=font_a)
    
    draw.line([(pos_a_x - 10, pos_a_y + 45), (pos_a_x + 160, pos_a_y + 5)], fill=(220, 30, 30), width=7)
    draw.line([(pos_a_x - 10, pos_a_y + 5), (pos_a_x + 160, pos_a_y + 45)], fill=(220, 30, 30), width=7)

    txt_oferta = f"{p_oferta}€"
    box_x1, box_y1 = 400, 660
    box_x2, box_y2 = 760, 765
    
    draw.rounded_rectangle([(box_x1, box_y1), (box_x2, box_y2)], radius=25, fill=(255, 115, 35))
    draw.text((box_x1 + 20, box_y1 + 10), txt_oferta, fill=(255, 255, 255), font=font_p)

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
# 4. PROCESAMIENTO DE MENSAJES Y FORMATO
# ==========================================
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    linea_limpia = texto.replace('\n', ' ')
    datos = [d.strip() for d in linea_limpia.split("|") if d.strip()]

    if len(datos) != 7:
        await update.message.reply_text(
            f"❌ **Error:** Se leyeron {len(datos)} de 7 campos.\n\n"
            f"Envía los datos separados por `|`:\n"
            f"`FOTO | PRECIO_OFERTA | PRECIO_ANTIGUO | TIENDA | TITULO | DESCRIPCION | ENLACE`"
        )
        return

    try:
        url_foto, p_oferta, p_antiguo, tienda, titulo, descripcion, enlace = datos

        msg_espera = await update.message.reply_text("⏳ Generando chollo y publicando...")

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

        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, tienda, logo_bytes)

        try:
            val_oferta = float(p_oferta.replace(',', '.'))
            val_antiguo = float(p_antiguo.replace(',', '.'))
            desc_pct = int(round((1 - (val_oferta / val_antiguo)) * 100))
            str_desc = f"-{desc_pct}%"
        except Exception:
            str_desc = ""

        caption = (
            f"🎾 **NUEVO CHOLLAZO {str_desc}** #Publicidad\n\n"
            f"✅ **{titulo}:** {descripcion}\n\n"
            f"📎 **Enlace:** {enlace}"
        )

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
# 5. ARRANQUE DEL BOT
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    app.run_polling()
