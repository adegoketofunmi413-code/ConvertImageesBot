import os
import logging
import io
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get bot token from environment variable
TOKEN = os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables!")

# Supported formats
SUPPORTED_FORMATS = {
    'JPEG': '📷 JPEG (JPG)',
    'PNG': '🖼️ PNG',
    'WEBP': '🌐 WebP',
    'GIF': '🎬 GIF',
    'BMP': '🖨️ BMP',
    'ICO': '🔄 ICO',
    'TIFF': '📄 TIFF',
    'PDF': '📕 PDF (Image)'
}

# Store user's selected format
user_format = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when /start is issued."""
    user = update.effective_user
    welcome_text = f"""
🎯 Welcome to ConvertImageesBot, {user.first_name}!

I can convert images between different formats.

📤 Send me an image and choose the format you want!

Supported formats:
• JPEG (JPG) • PNG • WebP
• GIF • BMP • ICO
• TIFF • PDF (Image)

Commands:
/start - Show this menu
/convert - Choose output format
/help - Show all commands
/formats - List all supported formats
"""
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message."""
    help_text = """
📖 How to use ConvertImageesBot:

1️⃣ Send me any image (JPG, PNG, WebP, etc.)
2️⃣ Use /convert to choose your output format
3️⃣ I'll convert and send it back!

Commands:
/start - Welcome message
/convert - Choose output format
/formats - List all supported formats
/help - Show this help message

💡 Pro tip: You can also use /convert before or after sending an image!
"""
    await update.message.reply_text(help_text)


async def formats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all supported formats."""
    format_list = "\n".join([f"• {name}" for name in SUPPORTED_FORMATS.values()])
    await update.message.reply_text(
        f"📋 **Supported Image Formats:**\n\n{format_list}\n\n"
        f"Use /convert to choose your output format!"
    )


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show format selection menu."""
    keyboard = []
    row = []
    for idx, (format_key, format_name) in enumerate(SUPPORTED_FORMATS.items()):
        row.append(InlineKeyboardButton(format_name, callback_data=f"format_{format_key}"))
        if len(row) == 2:  # 2 buttons per row
            keyboard.append(row)
            row = []
    if row:  # Add remaining buttons
        keyboard.append(row)
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="format_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎨 **Select your desired output format:**",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "format_cancel":
        await query.edit_message_text("❌ Format selection cancelled.")
        return
    
    # Extract format
    format_key = query.data.replace("format_", "")
    user_format[user_id] = format_key
    
    format_name = SUPPORTED_FORMATS.get(format_key, format_key)
    await query.edit_message_text(
        f"✅ **Output format set to: {format_name}**\n\n"
        f"Now send me an image to convert!\n"
        f"Or send the image now and I'll use this format."
    )


async def convert_image(image_data, output_format):
    """
    Convert image to target format using Pillow.
    """
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(image_data))
        
        # Handle format-specific conversions
        output_format_upper = output_format.upper()
        
        # Convert RGBA to RGB for JPEG (JPEG doesn't support transparency)
        if output_format_upper == 'JPEG' and img.mode == 'RGBA':
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
            img = background
        elif output_format_upper == 'JPEG' and img.mode == 'P':
            img = img.convert('RGB')
        
        # Convert to RGB for other formats if needed
        if output_format_upper in ['JPEG', 'BMP', 'TIFF'] and img.mode not in ['RGB', 'L']:
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            else:
                img = img.convert('RGB')
        
        # Save to buffer
        output_buffer = io.BytesIO()
        
        # Special handling for GIF
        if output_format_upper == 'GIF':
            img.save(output_buffer, format='GIF', save_all=True)
        else:
            # For PDF, save as PDF
            if output_format_upper == 'PDF':
                img.save(output_buffer, format='PDF', resolution=100.0)
            else:
                img.save(output_buffer, format=output_format_upper)
        
        return output_buffer.getvalue(), len(output_buffer.getvalue()) / 1024  # bytes and size in KB
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        raise e


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming images."""
    user_id = update.effective_user.id
    
    # Get user's selected format or default to PNG
    output_format = user_format.get(user_id, 'PNG')
    format_name = SUPPORTED_FORMATS.get(output_format, output_format)
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🔄 Converting your image to {format_name}..."
    )
    
    try:
        # Get the largest photo available
        photo_file = await update.message.photo[-1].get_file()
        image_data = await photo_file.download_as_bytearray()
        
        # Convert the image
        converted_data, final_size_kb = await convert_image(image_data, output_format)
        
        # Determine the file extension
        ext = output_format.lower()
        if ext == 'jpeg':
            ext = 'jpg'
        
        filename = f"converted.{ext}"
        
        # Send the converted image back as document (supports all formats)
        await update.message.reply_document(
            document=io.BytesIO(converted_data),
            filename=filename,
            caption=f"✅ **Converted successfully!**\n"
                    f"📊 Format: {format_name}\n"
                    f"📏 Size: {final_size_kb:.1f} KB"
        )
        
        # Delete the processing message
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        await processing_msg.edit_text(
            "❌ Sorry, I couldn't convert that image.\n"
            "Make sure it's a valid image file and try again.\n"
            "Supported formats: JPG, PNG, WebP, GIF, BMP, ICO, TIFF"
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image documents."""
    user_id = update.effective_user.id
    document = update.message.document
    
    # Check if it's an image
    if document.mime_type and document.mime_type.startswith('image/'):
        output_format = user_format.get(user_id, 'PNG')
        format_name = SUPPORTED_FORMATS.get(output_format, output_format)
        
        processing_msg = await update.message.reply_text(
            f"🔄 Converting your image to {format_name}..."
        )
        
        try:
            file = await document.get_file()
            image_data = await file.download_as_bytearray()
            
            converted_data, final_size_kb = await convert_image(image_data, output_format)
            
            # Determine the file extension
            ext = output_format.lower()
            if ext == 'jpeg':
                ext = 'jpg'
            
            original_name = document.file_name or "image"
            name_parts = original_name.rsplit('.', 1)
            new_filename = f"{name_parts[0]}_converted.{ext}"
            
            # Send back the converted image
            await update.message.reply_document(
                document=io.BytesIO(converted_data),
                filename=new_filename,
                caption=f"✅ **Converted successfully!**\n"
                        f"📊 Format: {format_name}\n"
                        f"📏 Size: {final_size_kb:.1f} KB"
            )
            
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            await processing_msg.edit_text(
                "❌ Sorry, I couldn't convert that image.\n"
                "Supported formats: JPG, PNG, WebP, GIF, BMP, ICO, TIFF"
            )
    else:
        await update.message.reply_text(
            "📎 Please send an image file (JPG, PNG, WebP, GIF, BMP, ICO, TIFF)."
        )


def main() -> None:
    """Start the bot."""
    # Create Application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("formats", formats_command))
    
    # Add callback handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add message handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    
    # Handle all other messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                           lambda u, c: u.message.reply_text(
                                               "🤔 Send me an image to convert!\n"
                                               "Use /convert to choose output format."
                                           )))
    
    # Start the Bot
    logger.info("Bot started! Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == '__main__':
    main()
