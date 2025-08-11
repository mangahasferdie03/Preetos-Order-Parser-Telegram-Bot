#!/usr/bin/env python3
"""
Debug version of bot.py with extensive Railway logging
"""
import os
import logging
import json
import base64
import time
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv

from order_processor import OrderParser, GoogleSheetsIntegration, PRODUCTS

# Load environment variables
load_dotenv()

# Enable detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DebugPreetosTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.parser = OrderParser()
        self.sheets = GoogleSheetsIntegration()
        
        # Log environment check
        logger.info("🔍 RAILWAY ENVIRONMENT DEBUG:")
        logger.info(f"TELEGRAM_BOT_TOKEN: {'SET' if self.bot_token else 'MISSING'}")
        logger.info(f"GOOGLE_CREDENTIALS_B64: {'SET' if os.getenv('GOOGLE_CREDENTIALS_B64') else 'MISSING'}")
        logger.info(f"GOOGLE_SPREADSHEET_ID: {'SET' if os.getenv('GOOGLE_SPREADSHEET_ID') else 'MISSING'}")
        logger.info(f"CLAUDE_API_KEY: {'SET' if os.getenv('CLAUDE_API_KEY') else 'MISSING'}")
        
        if os.getenv('GOOGLE_CREDENTIALS_B64'):
            creds_len = len(os.getenv('GOOGLE_CREDENTIALS_B64'))
            logger.info(f"GOOGLE_CREDENTIALS_B64 length: {creds_len} characters")
            
            # Try to decode and check
            try:
                decoded = base64.b64decode(os.getenv('GOOGLE_CREDENTIALS_B64')).decode('utf-8')
                parsed = json.loads(decoded)
                logger.info(f"✅ Credentials decode successful")
                logger.info(f"Service account: {parsed.get('client_email', 'NOT_FOUND')}")
                logger.info(f"Project ID: {parsed.get('project_id', 'NOT_FOUND')}")
                logger.info(f"Private key ID: {parsed.get('private_key_id', 'NOT_FOUND')}")
                
                # Check private key format
                private_key = parsed.get('private_key', '')
                logger.info(f"Private key length: {len(private_key)}")
                logger.info(f"Private key starts with BEGIN: {private_key.startswith('-----BEGIN PRIVATE KEY-----')}")
                logger.info(f"Private key ends with END: {private_key.endswith('-----END PRIVATE KEY-----')}")
                logger.info(f"Private key first 100 chars: {private_key[:100]}")
                
            except Exception as decode_error:
                logger.error(f"❌ Credentials decode failed: {decode_error}")
        
        # Log system time for JWT debugging
        utc_time = datetime.now(pytz.timezone('UTC'))
        logger.info(f"🕐 System UTC time: {utc_time}")
        logger.info(f"🕐 Unix timestamp: {int(utc_time.timestamp())}")
        
        # Log Railway-specific environment
        logger.info(f"🚂 RAILWAY_ENVIRONMENT: {os.getenv('RAILWAY_ENVIRONMENT', 'NOT_SET')}")
        logger.info(f"🚂 RAILWAY_SERVICE_ID: {os.getenv('RAILWAY_SERVICE_ID', 'NOT_SET')}")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        welcome_message = """
🍟 Welcome to Preetos.ai Debug Bot!

This is a debug version that logs detailed information.
Send me a test order to see the Google Sheets integration.

**Debug Commands:**
/start - Show this message
/debug - Show detailed debug information
/test - Test Google Sheets connection

Just send me a customer message to get started! 🚀
        """
        await update.message.reply_text(welcome_message)
    
    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show debug information."""
        debug_info = "🔍 **Debug Information**\n\n"
        
        # Environment variables
        debug_info += f"🔑 CLAUDE_API_KEY: {'✅ SET' if os.getenv('CLAUDE_API_KEY') else '❌ MISSING'}\n"
        debug_info += f"📊 GOOGLE_CREDENTIALS_B64: {'✅ SET' if os.getenv('GOOGLE_CREDENTIALS_B64') else '❌ MISSING'}\n"
        debug_info += f"📋 GOOGLE_SPREADSHEET_ID: {'✅ SET' if os.getenv('GOOGLE_SPREADSHEET_ID') else '❌ MISSING'}\n"
        debug_info += f"🤖 TELEGRAM_BOT_TOKEN: {'✅ SET' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ MISSING'}\n"
        
        if os.getenv('GOOGLE_CREDENTIALS_B64'):
            debug_info += f"📏 Credentials length: {len(os.getenv('GOOGLE_CREDENTIALS_B64'))} chars\n"
        
        # System info
        utc_time = datetime.now(pytz.timezone('UTC'))
        debug_info += f"\n🕐 UTC Time: {utc_time}\n"
        debug_info += f"⏰ Unix timestamp: {int(utc_time.timestamp())}\n"
        
        # Railway info
        debug_info += f"\n🚂 Railway Environment: {os.getenv('RAILWAY_ENVIRONMENT', 'Not detected')}\n"
        
        await update.message.reply_text(debug_info, parse_mode='Markdown')
    
    async def test_sheets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test Google Sheets connection."""
        await update.message.reply_text("🔄 Testing Google Sheets connection...")
        
        try:
            logger.info("🧪 Manual Google Sheets test starting...")
            
            # Test connection
            if self.sheets.connect("ORDER"):
                logger.info("✅ Google Sheets connection successful!")
                next_row = self.sheets.find_next_available_row()
                logger.info(f"📈 Next available row: {next_row}")
                
                await update.message.reply_text(
                    f"✅ **Google Sheets Test Successful!**\n\n"
                    f"📊 Connected to spreadsheet\n"
                    f"📋 Accessed ORDER worksheet\n"
                    f"📈 Next available row: {next_row}",
                    parse_mode='Markdown'
                )
            else:
                error_detail = getattr(self.sheets, 'last_error', 'Unknown error')
                logger.error(f"❌ Google Sheets connection failed: {error_detail}")
                
                await update.message.reply_text(
                    f"❌ **Google Sheets Test Failed**\n\n"
                    f"Error: {error_detail}",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"❌ Test error: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            await update.message.reply_text(f"❌ Test failed with error: {str(e)}")
    
    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process customer order messages with debug logging."""
        user_message = update.message.text
        chat_id = update.message.chat_id
        
        logger.info(f"🔄 Processing message from chat {chat_id}: {user_message[:100]}...")
        
        # Show processing message
        processing_msg = await update.message.reply_text("🔄 Processing your order message...")
        
        try:
            # Parse the order
            parsed_order = self.parser.parse_order_with_claude(user_message)
            logger.info(f"✅ Order parsed. Items found: {len(parsed_order.items) if parsed_order else 0}")
            
            # Delete processing message
            await processing_msg.delete()
            
            if not parsed_order.items:
                await update.message.reply_text("❌ No valid products found in message")
                return
            
            # Create simple test order summary
            summary = f"🛒 **Test Order Parsed**\n\n"
            summary += f"👤 Customer: {parsed_order.customer_name or 'Not specified'}\n"
            summary += f"💳 Payment: {parsed_order.payment_method or 'Not specified'}\n"
            summary += f"📍 Location: {parsed_order.customer_location or 'Not specified'}\n"
            summary += f"\n📦 Items: {len(parsed_order.items)}\n"
            
            for item in parsed_order.items:
                summary += f"• {item.product.name} {item.product.size} x{item.quantity}\n"
            
            summary += f"\n💰 Total: ₱{parsed_order.total_amount:,}\n"
            summary += f"\n🧪 **Click Test to try Google Sheets save**"
            
            # Create test button
            keyboard = [[InlineKeyboardButton("🧪 Test Google Sheets Save", callback_data=f"test_save_{chat_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store order for testing
            context.user_data['test_order'] = parsed_order
            
            await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Processing error: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            try:
                await processing_msg.delete()
            except:
                pass
            await update.message.reply_text(f"❌ Processing failed: {str(e)}")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle test button."""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("test_save_"):
            await self._test_save_order(query, context)
    
    async def _test_save_order(self, query, context):
        """Test saving order with extensive debugging."""
        test_order = context.user_data.get('test_order')
        
        if not test_order:
            await query.edit_message_text("❌ No test order found")
            return
        
        await query.edit_message_text("🧪 Testing Google Sheets save with full debug logging...")
        
        logger.info("🧪 DETAILED GOOGLE SHEETS SAVE TEST:")
        logger.info(f"Items to save: {len(test_order.items)}")
        
        try:
            # Step 1: Connection test with detailed logging
            logger.info("Step 1: Testing connection...")
            if not self.sheets.connect("ORDER"):
                error_detail = getattr(self.sheets, 'last_error', 'Unknown connection error')
                logger.error(f"❌ Connection failed: {error_detail}")
                
                await query.edit_message_text(
                    f"❌ **Connection Test Failed**\n\n"
                    f"Detailed error: {error_detail}\n\n"
                    f"Check Railway logs for more details.",
                    parse_mode='Markdown'
                )
                return
            
            logger.info("✅ Connection successful!")
            
            # Step 2: Find next row
            logger.info("Step 2: Finding next row...")
            try:
                next_row = self.sheets.find_next_available_row()
                logger.info(f"✅ Next row found: {next_row}")
            except Exception as row_error:
                logger.error(f"❌ Row finding failed: {row_error}")
                await query.edit_message_text(f"❌ Row finding failed: {row_error}")
                return
            
            # Step 3: Attempt save
            logger.info(f"Step 3: Attempting to save to row {next_row}...")
            success = self.sheets.update_order_row(test_order, next_row)
            
            if success:
                logger.info("✅ Save successful!")
                await query.edit_message_text(
                    f"🎉 **Test Save Successful!**\n\n"
                    f"✅ Connected to Google Sheets\n"
                    f"✅ Found next available row: {next_row}\n"
                    f"✅ Successfully saved order data\n\n"
                    f"The Google Sheets integration is working!",
                    parse_mode='Markdown'
                )
            else:
                logger.error("❌ Save failed")
                await query.edit_message_text(
                    f"❌ **Save Failed**\n\n"
                    f"Connection worked but save failed.\n"
                    f"Check Railway logs for detailed error.",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"❌ Test save error: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await query.edit_message_text(
                f"❌ **Test Error**\n\n"
                f"Error: {str(e)}\n\n"
                f"Check Railway logs for full traceback.",
                parse_mode='Markdown'
            )
    
    def run(self):
        """Start the debug bot."""
        application = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("debug", self.debug_command))
        application.add_handler(CommandHandler("test", self.test_sheets))
        
        # Handle all text messages
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_message))
        
        # Handle button callbacks
        application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Start the bot
        logger.info("🚀 Starting Debug Preetos Telegram Bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Main function to run the debug bot."""
    try:
        bot = DebugPreetosTelegramBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    main()