# ==========================================
# 5. MANEJO DE MENSAJES
# ==========================================
async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    linea_limpia = texto.replace('\n', ' ')
    datos = [d.strip() for d in linea_limpia.split("|") if d.strip()]

    if len(datos) < 3 or len(datos) > 4:
        await update.message.reply_text(
            f"❌ Formato de datos recibido incorrecto ({len(datos)} campos).\n\n"
            f"Envía la oferta en 4 campos (o 3 opcionales):\n"
            f"ENLACE | PRECIO_OFERTA | PRECIO_ANTIGUO | DESCRIPCION"
        )
        return

    try:
        enlace = datos[0]
        p_oferta = datos[1]
        p_antiguo = datos[2]
        desc_usuario = datos[3] if len(datos) == 4 else ""

        # TRUCO: Asegurar que el enlace siempre lleve tu Tag de Afiliado de Amazon
        TU_TAG = "mundopadel03-21"  # <--- Pon aquí tu ID exacto de afiliado
        if "tag=" not in enlace:
            if "?" in enlace:
                enlace = f"{enlace}&tag={TU_TAG}"
            else:
                enlace = f"{enlace}?tag={TU_TAG}"

        msg_espera = await update.message.reply_text("⏳ Descorchando URL y procesando la foto...")

        url_foto, titulo_auto = obtener_datos_amazon_scraper(enlace)
        texto_descripcion = desc_usuario if desc_usuario else titulo_auto

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

        foto_bytes = generar_imagen_chollo(url_foto, p_oferta, p_antiguo, logo_bytes)

        try:
            val_oferta = float(p_oferta.replace(',', '.'))
            val_antiguo = float(p_antiguo.replace(',', '.'))
            desc_pct = int(round((1 - (val_oferta / val_antiguo)) * 100))
            str_desc = f"-{desc_pct}%"
        except Exception:
            str_desc = ""

        caption = (
            f"🎾 NUEVO CHOLLAZO {str_desc} #Publicidad\n\n"
            f"✅ {texto_descripcion}\n\n"
            f"Sugerido por TU CANAL DE CHOLLOS\n@mundopadelesp\n"
            f"TU CANAL DE VÍDEOS 👉\n@mundopadelvid\n"
            f"INSTAGRAM @mundo_padel_esp"
        )

        # Creación del botón flotante (Inline Keyboard)
        keyboard = [
            [InlineKeyboardButton("🛍️ VER OFERTA EN AMAZON", url=enlace)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(
            chat_id=CANAL_ID,
            photo=foto_bytes,
            caption=caption,
            reply_markup=reply_markup
        )

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text("✅ ¡Chollo publicado con éxito!")

    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar: {str(e)}")
