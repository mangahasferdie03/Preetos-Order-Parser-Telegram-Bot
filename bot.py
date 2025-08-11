import os
import logging
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv

from order_processor import OrderParser, GoogleSheetsIntegration, PRODUCTS

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class PreetosTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.parser = OrderParser()
        self.sheets = GoogleSheetsIntegration()
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        welcome_message = """
🍟 Welcome to Preetos.ai Bot!

I can help you process chickpea chips orders from Facebook Messenger messages.

**How to use:**
1. Simply paste or forward customer messages to me
2. I'll parse the order using AI
3. Review and confirm the order
4. I'll automatically update your Google Sheet

**Available Products:**
🥤 **Pouches (₱150)**
• P-CHZ: Cheese
• P-SC: Sour Cream  
• P-BBQ: BBQ
• P-OG: Original

🏺 **Tubs (₱290)**
• 2L-CHZ: Cheese
• 2L-SC: Sour Cream
• 2L-BBQ: BBQ
• 2L-OG: Original

**Commands:**
/start - Show this welcome message
/help - Show help information
/status - Check bot status
/debug - Show Railway debug info
/testsheets - Test Google Sheets connection

Just send me a customer message to get started! 🚀
        """
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help information."""
        help_text = """
🤖 **Preetos.ai Bot Help**

**How to process orders:**
1. Copy customer message from Facebook Messenger
2. Send it to me (paste or forward)
3. I'll show you the parsed order
4. Click "✅ Confirm Order" to save to Google Sheets
5. Click "❌ Cancel" if there are issues

**Supported Languages:**
• English: "I want 2 cheese pouches"
• Filipino: "gusto ko ng dalawang cheese pouch"
• Mixed (Taglish): "pwede bang 2 cheese pouches po"

**Supported Features:**
• Auto-detects payment methods (GCash, BPI, Maya, Cash, BDO)
• Auto-assigns seller based on location (QC→Ferdie, Paranaque→Nina)
• Handles order modifications ("patanggal", "pa-add")
• Supports Filipino number words ("isa", "dalawa", etc.)

**Example Messages:**
```
Hi! I'd like 2 cheese pouches and 1 BBQ tub please. 
This is for Maria Santos.
```

```
Order for Juan:
dalawang cheese tub at isang sour cream pouch po
```

Need more help? Contact your administrator.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check bot status and connections."""
        status_message = "🔍 **Bot Status Check**\n\n"
        
        # Check Claude API
        if self.parser.client:
            status_message += "✅ Claude API: Connected\n"
        else:
            status_message += "❌ Claude API: Not configured\n"
        
        # Check Google Sheets
        try:
            if self.sheets.connect():
                status_message += "✅ Google Sheets: Connected\n"
                next_row = self.sheets.find_next_available_row()
                status_message += f"📊 Next available row: {next_row}\n"
            else:
                status_message += "❌ Google Sheets: Connection failed\n"
        except Exception as e:
            status_message += f"❌ Google Sheets: Error - {str(e)}\n"
        
        # Current time
        manila_time = datetime.now(pytz.timezone('Asia/Manila'))
        status_message += f"🕐 Current time (Manila): {manila_time.strftime('%Y-%m-%d %I:%M:%S %p')}\n"
        
        await update.message.reply_text(status_message, parse_mode='Markdown')
    
    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process customer order messages."""
        user_message = update.message.text
        chat_id = update.message.chat_id
        
        # Show processing message
        processing_msg = await update.message.reply_text("🔄 Processing your order message...")
        
        try:
            # Parse the order
            logger.info(f"Processing message: {user_message[:100]}...")
            parsed_order = self.parser.parse_order_with_claude(user_message)
            logger.info(f"Parsed order completed. Items found: {len(parsed_order.items) if parsed_order else 0}")
            
            # Delete processing message
            await processing_msg.delete()
            
            if not parsed_order.items:
                await update.message.reply_text(
                    "❌ **No valid products found**\n\n"
                    "I couldn't detect any valid product orders in your message. "
                    "Please make sure to include product names and quantities.\n\n"
                    "**Example:** '2 cheese pouches and 1 BBQ tub for Maria'",
                    parse_mode='Markdown'
                )
                return
            
            # Format order summary
            order_summary = self._format_order_summary(parsed_order)
            
            # Create confirmation buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm Order", callback_data=f"confirm_{chat_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{chat_id}")
                ],
                [InlineKeyboardButton("📋 Show Details", callback_data=f"details_{chat_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store order data in context for later use
            context.user_data['pending_order'] = parsed_order
            context.user_data['order_message'] = user_message
            
            await update.message.reply_text(
                order_summary,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            try:
                await processing_msg.delete()
            except:
                pass  # Message might already be deleted
            logger.error(f"Error processing message: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            await update.message.reply_text(
                f"❌ **Processing Error**\n\n"
                f"Sorry, I encountered an error while processing your message:\n"
                f"`{str(e)}`\n\n"
                f"Please try again or contact support.",
                parse_mode='Markdown'
            )
    
    def _format_order_summary(self, order):
        """Format the parsed order into a readable summary."""
        summary = "🛒 **Order Parsed Successfully!**\n\n"
        
        # Customer info
        customer_status = "🟢" if order.customer_name else "🔘"
        payment_status = "🟢" if order.payment_method else "🔘"
        location_status = "🟢" if order.customer_location else "🔘"
        
        summary += f"{customer_status} **Customer:** {order.customer_name or 'Not specified'}\n"
        summary += f"{payment_status} **Payment:** {order.payment_method or 'Not specified'}\n"
        summary += f"{location_status} **Location:** {order.customer_location or 'Not specified'}\n"
        
        if order.auto_sold_by:
            summary += f"👤 **Assigned to:** {order.auto_sold_by}\n"
        
        summary += "\n📦 **Order Items:**\n"
        
        # Sort items: pouches first, then tubs
        sorted_items = sorted(order.items, key=lambda x: 0 if x.product.size == "Pouch" else 1)
        
        total_items = sum(item.quantity for item in order.items)
        
        for item in sorted_items:
            item_total = item.quantity * item.product.price
            summary += f"• {item.product.size} {item.product.name} - {item.quantity} - ₱{item_total:,}\n"
        
        # Show discount and shipping if present
        has_extras = (order.discount_amount and order.discount_amount > 0) or (order.shipping_fee and order.shipping_fee > 0)
        
        if has_extras:
            summary += f"\n💰 **Subtotal:** ₱{order.total_amount:,}\n"
            
            # Add shipping fee
            if order.shipping_fee and order.shipping_fee > 0:
                summary += f"🚚 **Shipping:** +₱{order.shipping_fee:,.0f}\n"
            
            # Add discount
            if order.discount_amount and order.discount_amount > 0:
                discount_percentage = order.discount_percentage or 0
                # Format percentage and amount without unnecessary decimals
                percentage_str = f"{discount_percentage:g}"
                amount_str = f"{order.discount_amount:,.0f}"
                summary += f"🏷️ **Discount:** {percentage_str}% (-₱{amount_str})\n"
            
            # Calculate final total
            final_total = order.total_amount
            if order.shipping_fee:
                final_total += order.shipping_fee
            if order.discount_amount:
                final_total -= order.discount_amount
            
            # Add space before Final Total and format item counts
            item_breakdown = self._format_item_breakdown(order.items)
            summary += f"\n💰 **Final Total:** ₱{final_total:,.0f} ({item_breakdown})\n"
        else:
            item_breakdown = self._format_item_breakdown(order.items)
            summary += f"\n💰 **Total:** ₱{order.total_amount:,} ({item_breakdown})\n"
        summary += "\n👆 **Confirm to save to Google Sheets**"
        
        return summary
    
    def _format_saved_order_summary(self, order):
        """Format the saved order summary for reference (Message #1)."""
        summary = "✅ **Order Saved**\n\n"
        
        # Customer info
        customer_status = "🟢" if order.customer_name else "🔘"
        payment_status = "🟢" if order.payment_method else "🔘"
        location_status = "🟢" if order.customer_location else "🔘"
        
        summary += f"{customer_status} **Customer:** {order.customer_name or 'Not specified'}\n"
        summary += f"{payment_status} **Payment:** {order.payment_method or 'Not specified'}\n"
        summary += f"{location_status} **Location:** {order.customer_location or 'Not specified'}\n"
        
        if order.auto_sold_by:
            summary += f"👤 **Assigned to:** {order.auto_sold_by}\n"
        
        summary += "\n📦 **Order Items:**\n"
        
        # Sort items: pouches first, then tubs
        sorted_items = sorted(order.items, key=lambda x: 0 if x.product.size == "Pouch" else 1)
        
        total_items = sum(item.quantity for item in order.items)
        
        for item in sorted_items:
            item_total = item.quantity * item.product.price
            summary += f"• {item.product.size} {item.product.name} - {item.quantity} - ₱{item_total:,}\n"
        
        # Show discount and shipping if present
        has_extras = (order.discount_amount and order.discount_amount > 0) or (order.shipping_fee and order.shipping_fee > 0)
        
        if has_extras:
            summary += f"\n💰 **Subtotal:** ₱{order.total_amount:,}\n"
            
            # Add shipping fee
            if order.shipping_fee and order.shipping_fee > 0:
                summary += f"🚚 **Shipping:** +₱{order.shipping_fee:,.0f}\n"
            
            # Add discount
            if order.discount_amount and order.discount_amount > 0:
                discount_percentage = order.discount_percentage or 0
                # Format percentage and amount without unnecessary decimals
                percentage_str = f"{discount_percentage:g}"
                amount_str = f"{order.discount_amount:,.0f}"
                summary += f"🏷️ **Discount:** {percentage_str}% (-₱{amount_str})\n"
            
            # Calculate final total
            final_total = order.total_amount
            if order.shipping_fee:
                final_total += order.shipping_fee
            if order.discount_amount:
                final_total -= order.discount_amount
            
            # Add space before Final Total and format item counts
            item_breakdown = self._format_item_breakdown(order.items)
            summary += f"\n💰 **Final Total:** ₱{final_total:,.0f} ({item_breakdown})"
        else:
            item_breakdown = self._format_item_breakdown(order.items)
            summary += f"\n💰 **Total:** ₱{order.total_amount:,} ({item_breakdown})"
        
        return summary
    
    def _format_item_breakdown(self, items):
        """Format item count breakdown like '2 pouches | 1 tub'"""
        pouch_count = sum(item.quantity for item in items if item.product.size == "Pouch")
        tub_count = sum(item.quantity for item in items if item.product.size == "Tub")
        
        parts = []
        if pouch_count > 0:
            parts.append(f"{pouch_count} {'pouch' if pouch_count == 1 else 'pouches'}")
        if tub_count > 0:
            parts.append(f"{tub_count} {'tub' if tub_count == 1 else 'tubs'}")
        
        return " | ".join(parts) if parts else "0 items"
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        action, chat_id = query.data.split('_', 1)
        
        if action == "confirm":
            await self._confirm_order(query, context)
        elif action == "cancel":
            await self._cancel_order(query, context)
        elif action == "details":
            await self._show_details(query, context)
    
    async def _confirm_order(self, query, context):
        """Confirm and save order to Google Sheets with detailed debugging."""
        pending_order = context.user_data.get('pending_order')
        
        if not pending_order:
            await query.edit_message_text("❌ No pending order found. Please try again.")
            return
        
        # Show initial processing message
        await query.edit_message_text("🔄 Step 1/5: Starting Google Sheets save process...")
        
        try:
            # Step 1: Environment Check
            await query.edit_message_text("🔍 Step 1/5: Checking Railway environment...")
            
            import os
            from datetime import datetime, timezone
            import json
            import base64
            
            # Check environment variables
            debug_info = []
            debug_info.append("🔍 **RAILWAY DEBUG INFO:**")
            debug_info.append(f"📊 GOOGLE_CREDENTIALS_B64: {'✅' if os.getenv('GOOGLE_CREDENTIALS_B64') else '❌'}")
            debug_info.append(f"📋 GOOGLE_SPREADSHEET_ID: {'✅' if os.getenv('GOOGLE_SPREADSHEET_ID') else '❌'}")
            
            if os.getenv('GOOGLE_CREDENTIALS_B64'):
                creds_len = len(os.getenv('GOOGLE_CREDENTIALS_B64'))
                debug_info.append(f"📏 Credentials length: {creds_len} chars")
                
                # Test decode
                try:
                    decoded = base64.b64decode(os.getenv('GOOGLE_CREDENTIALS_B64')).decode('utf-8')
                    parsed = json.loads(decoded)
                    debug_info.append(f"✅ Credentials decode: OK")
                    debug_info.append(f"📧 Service account: {parsed.get('client_email', 'NOT_FOUND')[:50]}...")
                    debug_info.append(f"🏢 Project: {parsed.get('project_id', 'NOT_FOUND')}")
                except Exception as decode_err:
                    debug_info.append(f"❌ Credentials decode: {decode_err}")
            
            # Check system time
            utc_now = datetime.now(timezone.utc)
            unix_ts = int(utc_now.timestamp())
            debug_info.append(f"🕐 Railway UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
            debug_info.append(f"⏰ Unix timestamp: {unix_ts}")
            
            # Time sanity check
            if unix_ts < 1735689600:  # 2025-01-01
                debug_info.append("⚠️ WARNING: Clock appears to be before 2025!")
            elif unix_ts > 1767225600:  # 2026-01-01
                debug_info.append("⚠️ WARNING: Clock appears to be after 2025!")
            else:
                debug_info.append("✅ Clock appears reasonable")
            
            # Send debug info
            debug_msg = "\n".join(debug_info[:15])  # Limit message length
            await query.edit_message_text(debug_msg, parse_mode='Markdown')
            
            # Wait a moment then continue
            import asyncio
            await asyncio.sleep(2)
            
            # Step 2: Connection Test
            await query.edit_message_text("🔗 Step 2/5: Testing Google Sheets connection...")
            
            # Try connection with detailed error capture
            connection_success = False
            connection_error = "Unknown error"
            
            try:
                connection_success = self.sheets.connect()
                if not connection_success:
                    connection_error = getattr(self.sheets, 'last_error', 'No error details available')
            except Exception as conn_err:
                connection_error = str(conn_err)
            
            if not connection_success:
                # Show detailed connection failure
                error_details = []
                error_details.append("❌ **CONNECTION FAILED**")
                error_details.append(f"Error: {connection_error}")
                
                # Check if it's JWT signature error
                if "Invalid JWT Signature" in connection_error:
                    error_details.append("")
                    error_details.append("🔍 **JWT SIGNATURE ERROR ANALYSIS:**")
                    error_details.append("• This usually means:")
                    error_details.append("  - Railway clock is out of sync")
                    error_details.append("  - Service account key is invalid")
                    error_details.append("  - Private key format issue")
                    error_details.append("")
                    error_details.append("💡 **SOLUTIONS TO TRY:**")
                    error_details.append("1. Regenerate service account key")
                    error_details.append("2. Check Google Cloud Console")
                    error_details.append("3. Verify service account permissions")
                
                error_msg = "\n".join(error_details)
                await query.edit_message_text(error_msg, parse_mode='Markdown')
                return
            
            await query.edit_message_text("✅ Step 2/5: Google Sheets connection successful!")
            await asyncio.sleep(1)
            
            # Step 3: Find Next Row
            await query.edit_message_text("📊 Step 3/5: Finding next available row...")
            next_row = self.sheets.find_next_available_row()
            
            await query.edit_message_text(f"✅ Step 3/5: Next row found: {next_row}")
            await asyncio.sleep(1)
            
            # Step 4: Save Data
            await query.edit_message_text(f"💾 Step 4/5: Saving order to row {next_row}...")
            success = self.sheets.update_order_row(pending_order, next_row)
            
            if success:
                # Update original message to show "Order Saved" with full details
                saved_msg = self._format_saved_order_summary(pending_order)
                await query.edit_message_text(saved_msg, parse_mode='Markdown')
                
                # Send separate message with clean breakdown for customer
                order_lines = []
                # Sort items: pouches first, then tubs
                sorted_items = sorted(pending_order.items, key=lambda x: 0 if x.product.size == "Pouch" else 1)
                for item in sorted_items:
                    total_item_price = item.quantity * item.product.price
                    # Map product names to match your sheet format
                    product_name = item.product.name
                    if product_name == "BBQ":
                        product_name = "Barbecue"
                    order_lines.append(f"{item.product.size} {product_name} - {item.quantity} - ₱{total_item_price:,}")
                
                # Add shipping line if present
                if pending_order.shipping_fee and pending_order.shipping_fee > 0:
                    order_lines.append(f"Shipping : ₱{pending_order.shipping_fee:,.0f}")
                
                # Add discount line if present
                if pending_order.discount_amount and pending_order.discount_amount > 0:
                    order_lines.append(f"Discount : -₱{pending_order.discount_amount:,.0f}")
                
                order_lines.append("----------")
                
                # Calculate final total (add shipping, subtract discount)
                final_total = pending_order.total_amount
                if pending_order.shipping_fee:
                    final_total += pending_order.shipping_fee
                if pending_order.discount_amount:
                    final_total -= pending_order.discount_amount
                
                order_lines.append(f"Total - ₱{final_total:,.0f}")
                order_breakdown = "\n".join(order_lines)
                
                # Send new separate message with clean breakdown
                await query.message.reply_text(order_breakdown)
                
                # Clear pending order
                context.user_data.pop('pending_order', None)
                context.user_data.pop('order_message', None)
                
            else:
                raise Exception("Failed to update Google Sheet")
                
        except Exception as e:
            logger.error(f"Error saving order: {str(e)}")
            await query.edit_message_text(
                f"❌ **Save Failed**\n\n"
                f"Could not save order to Google Sheets:\n"
                f"`{str(e)}`\n\n"
                f"Please check your configuration and try again.",
                parse_mode='Markdown'
            )
    
    async def _cancel_order(self, query, context):
        """Cancel the current order."""
        await query.edit_message_text(
            "❌ **Order Cancelled**\n\n"
            "The order has been cancelled and not saved to Google Sheets.\n"
            "Send me another message to process a new order."
        )
        
        # Clear pending order
        context.user_data.pop('pending_order', None)
        context.user_data.pop('order_message', None)
    
    async def _show_details(self, query, context):
        """Show detailed order information."""
        pending_order = context.user_data.get('pending_order')
        original_message = context.user_data.get('order_message', '')
        
        if not pending_order:
            await query.answer("No order details available.")
            return
        
        # Format detailed view
        details = "📋 **Detailed Order Information**\n\n"
        
        # Claude metadata if available
        if hasattr(pending_order, 'confidence'):
            details += f"🤖 **AI Confidence:** {pending_order.confidence:.2%}\n"
        if hasattr(pending_order, 'parsing_notes'):
            details += f"📝 **Notes:** {pending_order.parsing_notes}\n"
        
        details += "\n**Product Breakdown:**\n"
        for item in pending_order.items:
            details += f"• **{item.product.code}** - {item.product.name} {item.product.size}\n"
            details += f"  Quantity: {item.quantity} × ₱{item.product.price} = ₱{item.quantity * item.product.price:,}\n"
        
        details += f"\n**Original Message:**\n```\n{original_message[:500]}{'...' if len(original_message) > 500 else ''}\n```"
        
        # Create back button
        keyboard = [[InlineKeyboardButton("⬅️ Back to Order", callback_data=f"back_{query.message.chat.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(details, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed Railway debug information."""
        debug_info = ["🔍 **RAILWAY DEBUG INFO:**"]
        
        import os
        from datetime import datetime, timezone
        import json
        import base64
        
        # Environment variables check
        debug_info.append(f"📊 GOOGLE_CREDENTIALS_B64: {'✅' if os.getenv('GOOGLE_CREDENTIALS_B64') else '❌'}")
        debug_info.append(f"📋 GOOGLE_SPREADSHEET_ID: {'✅' if os.getenv('GOOGLE_SPREADSHEET_ID') else '❌'}")
        debug_info.append(f"🤖 TELEGRAM_BOT_TOKEN: {'✅' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌'}")
        debug_info.append(f"🔑 CLAUDE_API_KEY: {'✅' if os.getenv('CLAUDE_API_KEY') else '❌'}")
        
        if os.getenv('GOOGLE_CREDENTIALS_B64'):
            creds_len = len(os.getenv('GOOGLE_CREDENTIALS_B64'))
            debug_info.append(f"📏 Credentials length: {creds_len} chars")
            
            # Test decode
            try:
                decoded = base64.b64decode(os.getenv('GOOGLE_CREDENTIALS_B64')).decode('utf-8')
                parsed = json.loads(decoded)
                debug_info.append(f"✅ Credentials decode: OK")
                debug_info.append(f"📧 Service account: {parsed.get('client_email', 'NOT_FOUND')[:50]}...")
                debug_info.append(f"🏢 Project: {parsed.get('project_id', 'NOT_FOUND')}")
            except Exception as decode_err:
                debug_info.append(f"❌ Credentials decode: {decode_err}")
        
        # System time
        utc_now = datetime.now(timezone.utc)
        unix_ts = int(utc_now.timestamp())
        debug_info.append(f"🕐 Railway UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
        debug_info.append(f"⏰ Unix timestamp: {unix_ts}")
        
        # Time sanity check
        if unix_ts < 1735689600:  # 2025-01-01
            debug_info.append("⚠️ WARNING: Clock appears to be before 2025!")
        elif unix_ts > 1767225600:  # 2026-01-01
            debug_info.append("⚠️ WARNING: Clock appears to be after 2025!")
        else:
            debug_info.append("✅ Clock appears reasonable")
        
        # Railway specific info
        debug_info.append(f"🚂 Railway Environment: {os.getenv('RAILWAY_ENVIRONMENT', 'Not detected')}")
        debug_info.append(f"🚂 Railway Service: {os.getenv('RAILWAY_SERVICE_ID', 'Not detected')}")
        
        debug_msg = "\n".join(debug_info[:20])  # Limit message length
        await update.message.reply_text(debug_msg, parse_mode='Markdown')
    
    async def test_sheets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test Google Sheets connection manually."""
        await update.message.reply_text("🔄 Testing Google Sheets connection...")
        
        try:
            # Test connection
            connection_success = False
            connection_error = "Unknown error"
            
            try:
                connection_success = self.sheets.connect()
                if not connection_success:
                    connection_error = getattr(self.sheets, 'last_error', 'No error details available')
            except Exception as conn_err:
                connection_error = str(conn_err)
            
            if connection_success:
                next_row = self.sheets.find_next_available_row()
                
                await update.message.reply_text(
                    f"✅ **Google Sheets Test Successful!**\n\n"
                    f"📊 Connected to spreadsheet\n"
                    f"📋 Accessed ORDER worksheet\n"
                    f"📈 Next available row: {next_row}",
                    parse_mode='Markdown'
                )
            else:
                # Show detailed connection failure
                error_details = []
                error_details.append("❌ **CONNECTION TEST FAILED**")
                error_details.append(f"Error: {connection_error}")
                
                # Check if it's JWT signature error
                if "Invalid JWT Signature" in connection_error:
                    error_details.append("")
                    error_details.append("🔍 **JWT SIGNATURE ERROR DETECTED:**")
                    error_details.append("• This typically means:")
                    error_details.append("  - Railway clock is out of sync with Google")
                    error_details.append("  - Service account key needs regeneration")
                    error_details.append("  - Private key format corruption")
                    error_details.append("")
                    error_details.append("💡 **RECOMMENDED ACTIONS:**")
                    error_details.append("1. Generate new service account key")
                    error_details.append("2. Check Google Cloud Console permissions")
                    error_details.append("3. Verify system time synchronization")
                
                error_msg = "\n".join(error_details)
                await update.message.reply_text(error_msg, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Test error: {str(e)}")
            await update.message.reply_text(f"❌ Test failed with error: {str(e)}")
    
    def run(self):
        """Start the bot."""
        # Create the Application
        application = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("debug", self.debug_command))
        application.add_handler(CommandHandler("testsheets", self.test_sheets_command))
        
        # Handle all text messages
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_message))
        
        # Handle button callbacks
        application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Start the bot
        logger.info("Starting Preetos Telegram Bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Main function to run the bot."""
    try:
        bot = PreetosTelegramBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")

if __name__ == '__main__':
    main()