# Preetos Telegram Bot

A Telegram bot for processing chickpea chips orders from Facebook Messenger messages with Google Sheets integration.

## Features

- **Telegram Bot Interface**: Process orders directly in Telegram
- **Claude AI Integration**: Intelligent parsing of Filipino-English customer orders
- **Google Sheets Integration**: Automatic order updates to Google Sheets
- **Payment Method Detection**: Auto-detects GCash, BPI, Maya, Cash, BDO, Others
- **Location-Based Assignment**: Auto-assigns to Ferdie (QC) or Nina (Paranaque) 
- **Product Catalog**: Supports 8 products (4 flavors × 2 sizes)
- **Interactive Confirmation**: Review orders before saving
- **Real-time Status**: Check bot and integration status

## Setup

### 1. Install Dependencies

```bash
cd telegram-bot
pip install -r requirements.txt
```

### 2. Create Telegram Bot

1. Message @BotFather on Telegram
2. Send `/newbot` command
3. Choose a name and username for your bot
4. Save the bot token provided

### 3. Configure Environment Variables

1. Copy `.env.template` to `.env`:
```bash
cp .env.template .env
```

2. Fill in your credentials in `.env`:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF1234567890abcdef1234567890

# Claude API
CLAUDE_API_KEY=sk-ant-api03-...

# Google Sheets
GOOGLE_SPREADSHEET_ID=1DGt5u6QWWIMRZmU1MzfM3sowFPt9lOJPAgjqxZ6uGtc
GOOGLE_CREDENTIALS_JSON={"type": "service_account", "project_id": "your_project_id", "private_key_id": "...", "private_key": "...", "client_email": "...", "client_id": "...", "auth_uri": "...", "token_uri": "...", "auth_provider_x509_cert_url": "...", "client_x509_cert_url": "..."}
```

### 4. Run the Bot

```bash
python bot.py
```

## Usage

### Bot Commands

- `/start` - Show welcome message and instructions
- `/help` - Show detailed help information
- `/status` - Check bot status and connections

### Processing Orders

1. **Send Message**: Paste or forward customer messages to the bot
2. **Review Order**: Bot parses and shows order summary with confirmation buttons
3. **Confirm**: Click "✅ Confirm Order" to save to Google Sheets
4. **Cancel**: Click "❌ Cancel" if there are issues

### Supported Message Formats

**English:**
```
Hi! I'd like 2 cheese pouches and 1 BBQ tub please. 
This is for Maria Santos.
```

**Filipino:**
```
gusto ko po ng dalawang cheese pouch at isang sour cream tub
para kay Juan, gcash payment
```

**Mixed (Taglish):**
```
pwede bang 2 cheese pouches at 1 BBQ tub po
for Maria, QC area
```

## Product Catalog

### Pouches (₱150 each)
- P-CHZ: Cheese
- P-SC: Sour Cream  
- P-BBQ: BBQ
- P-OG: Original

### Tubs (₱290 each)
- 2L-CHZ: Cheese
- 2L-SC: Sour Cream
- 2L-BBQ: BBQ
- 2L-OG: Original

## Bot Features

### Smart Parsing
- Detects Filipino number words ("isa", "dalawa", "tatlo")
- Handles casual product names ("cheese", "bbq", "sour")
- Processes order modifications ("patanggal", "pa-add")
- Supports gram-based sizing ("100g", "200g")

### Auto-Detection
- **Payment Methods**: GCash, BPI, Maya, Cash, BDO
- **Locations**: Quezon City → Ferdie, Paranaque → Nina
- **Order Status**: Always sets to "Reserved" for bot orders

### Interactive Interface
- Order preview with status indicators
- Confirmation buttons before saving
- Detailed order breakdown available
- Real-time processing feedback

## Error Handling

- Graceful fallback to basic parsing if Claude API fails
- Clear error messages for configuration issues
- Automatic retry suggestions for failed operations
- Comprehensive logging for debugging

## Deployment

### Local Development
```bash
python bot.py
```

### Production (with webhook)
1. Set up webhook URL in environment variables
2. Configure reverse proxy (nginx)
3. Use process manager (PM2, systemd)

Example systemd service:
```ini
[Unit]
Description=Preetos Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/telegram-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

### Common Issues

1. **Bot not responding**
   - Check if `TELEGRAM_BOT_TOKEN` is correct
   - Verify bot is running (`/status` command)

2. **Claude API errors**
   - Verify `CLAUDE_API_KEY` is valid
   - Check API rate limits

3. **Google Sheets not updating**
   - Confirm `GOOGLE_CREDENTIALS_JSON` is properly formatted
   - Check spreadsheet sharing permissions
   - Verify `GOOGLE_SPREADSHEET_ID` is correct

4. **Order parsing issues**
   - Test with simple messages first
   - Use `/status` to check all integrations
   - Check logs for detailed error information

### Logs

Bot logs are printed to console. For production, redirect to file:
```bash
python bot.py > bot.log 2>&1
```

## Migration from Streamlit

This bot maintains all functionality from the original Streamlit app:

- Same Claude AI prompts and parsing logic
- Identical Google Sheets integration
- All product codes and pricing
- Same Filipino-English support
- Enhanced with interactive Telegram interface

Key advantages over web app:
- No need to open browser
- Real-time notifications
- Mobile-first experience  
- Integrated with chat workflow