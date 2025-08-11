import json
import re
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
import anthropic
from dotenv import load_dotenv
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()

@dataclass
class Product:
    code: str
    name: str
    size: str
    price: int = 290

@dataclass
class OrderItem:
    product: Product
    quantity: int

@dataclass
class ParsedOrder:
    customer_name: Optional[str]
    items: List[OrderItem]
    total_amount: int
    raw_message: str
    payment_method: Optional[str] = None
    customer_location: Optional[str] = None
    auto_sold_by: Optional[str] = None
    discount_percentage: Optional[float] = None
    discount_amount: Optional[int] = None
    shipping_fee: Optional[int] = None

# Product catalog
PRODUCTS = {
    "P-CHZ": Product("P-CHZ", "Cheese", "Pouch", 150),
    "P-SC": Product("P-SC", "Sour Cream", "Pouch", 150),
    "P-BBQ": Product("P-BBQ", "BBQ", "Pouch", 150),
    "P-OG": Product("P-OG", "Original Blend", "Pouch", 150),
    "2L-CHZ": Product("2L-CHZ", "Cheese", "Tub", 290),
    "2L-SC": Product("2L-SC", "Sour Cream", "Tub", 290),
    "2L-BBQ": Product("2L-BBQ", "BBQ", "Tub", 290),
    "2L-OG": Product("2L-OG", "Original Spice Blend", "Tub", 290),
}

class OrderParser:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('CLAUDE_API_KEY')
        
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        else:
            self.client = None
    
    def _filipino_number_to_int(self, text: str) -> Dict[str, int]:
        """Convert Filipino number words to integers"""
        filipino_numbers = {
            'isa': 1, 'isang': 1, 'ung': 1,
            'dalawa': 2, 'dalawang': 2, 
            'tatlo': 3, 'tatlong': 3,
            'apat': 4, 'apatna': 4,
            'lima': 5, 'limang': 5,
            'anim': 6, 'anim na': 6,
            'pito': 7, 'pitong': 7,
            'walo': 8, 'walong': 8,
            'siyam': 9, 'siyamna': 9,
            'sampu': 10, 'sampung': 10
        }
        return filipino_numbers
    
    def _get_product_aliases(self) -> Dict[str, str]:
        """Map casual/Filipino product names to product codes"""
        return {
            # Cheese variations
            'cheese': ['P-CHZ', '2L-CHZ'],
            'cheesy': ['P-CHZ', '2L-CHZ'], 
            'cheese chips': ['P-CHZ'],
            'cheese tub': ['2L-CHZ'],
            'cheese pouch': ['P-CHZ'],
            'keso': ['P-CHZ', '2L-CHZ'],
            
            # Sour Cream variations
            'sour cream': ['P-SC', '2L-SC'],
            'sour': ['P-SC', '2L-SC'],
            'sc': ['P-SC', '2L-SC'],
            'sour cream chips': ['P-SC'],
            'sour cream tub': ['2L-SC'],
            'sour cream pouch': ['P-SC'],
            
            # BBQ variations
            'bbq': ['P-BBQ', '2L-BBQ'],
            'barbeque': ['P-BBQ', '2L-BBQ'],
            'barbecue': ['P-BBQ', '2L-BBQ'],
            'bbq chips': ['P-BBQ'],
            'bbq tub': ['2L-BBQ'],
            'bbq pouch': ['P-BBQ'],
            
            # Original variations
            'original': ['P-OG', '2L-OG'],
            'plain': ['P-OG', '2L-OG'],
            'orig': ['P-OG', '2L-OG'],
            'original chips': ['P-OG'],
            'original tub': ['2L-OG'],
            'original pouch': ['P-OG'],
            
            # Size indicators
            'pouch': 'pouch_size',
            'tub': 'tub_size',
            'malaki': 'tub_size',
            'maliit': 'pouch_size'
        }
    
    def parse_order_with_claude(self, message: str) -> ParsedOrder:
        """Parse order using enhanced Claude API with Filipino-English support"""
        if not self.client:
            return self._basic_parse(message)
        
        try:
            prompt = f"""
            You are an expert at parsing Filipino-English (Taglish) customer orders for chickpea chips from Facebook Messenger. 

            PRODUCTS AVAILABLE:
            - Pouches/100g (₱150 each): Cheese (P-CHZ), Sour Cream (P-SC), BBQ (P-BBQ), Original (P-OG)
            - Tubs/200g (₱290 each): Cheese (2L-CHZ), Sour Cream (2L-SC), BBQ (2L-BBQ), Original (2L-OG)

            FILIPINO NUMBER WORDS TO RECOGNIZE:
            - isa/isang = 1, dalawa/dalawang = 2, tatlo/tatlong = 3, apat = 4, lima/limang = 5
            - sampung = 10, etc.

            PRODUCT NAME VARIATIONS TO RECOGNIZE:
            - "cheese/cheesy/keso" = Cheese flavor
            - "sour cream/sour/sc" = Sour Cream flavor  
            - "bbq/barbeque/barbecue" = BBQ flavor
            - "original/plain/orig" = Original flavor
            - "pouch/maliit/100g/100 grams" = small size, "tub/malaki/200g/200 grams" = large size
            - Casual terms: "chips", "chickpea chips", etc.

            GRAM-BASED SIZE RECOGNITION:
            - "100g", "100 grams", "100g lang", "100 grams po" → Pouch size (₱150)
            - "200g", "200 grams", "200g naman", "200 grams po" → Tub size (₱290)
            - Examples: "2 x 100g cheese", "isang 200g BBQ", "100 grams sour cream"

            FILIPINO/CASUAL EXPRESSIONS TO HANDLE:
            - Politeness: "po", "please", "pwede", "pwede ba"
            - Requests: "gusto ko", "order ko", "bill ko"
            - For someone: "para kay [Name]", "para sa [Name]"
            - Quantities: "mga 2" (about 2), "mga tatlo" (about 3)

            PAYMENT METHODS TO DETECT:
            Look for these payment method keywords and map them to exact values:
            - "gcash", "g-cash", "GCash", "GCASH" → "Gcash"
            - "bpi", "BPI" → "BPI"  
            - "maya", "Maya", "MAYA", "paymaya" → "Maya"
            - "cash", "CASH", "cod", "cash on delivery", "bayad cash" → "Cash"
            - "bdo", "BDO" → "BDO"
            - Other payment methods → "Others"
            
            FILIPINO PAYMENT EXPRESSIONS:
            - "gcash ko", "sa gcash", "bayad gcash", "transfer gcash"
            - "maya payment", "bayad maya", "sa maya"
            - "cash po", "bayad cash", "cash on delivery"
            - "bpi transfer", "sa bpi", "bayad bpi"
            - "bdo naman", "sa bdo"

            LOCATION DETECTION FOR AUTOMATIC SELLER ASSIGNMENT:
            Look for location keywords to determine which seller handles the order:
            - "Quezon City", "QC", "quezon city", "qc" → "Quezon City"
            - "Paranaque", "Paranañaque", "paranaque", "parañaque" → "Paranaque"
            
            FILIPINO LOCATION EXPRESSIONS:
            - "sa QC", "galing QC", "dito sa Quezon City", "taga QC"
            - "sa Paranaque", "galing Paranaque", "dito sa Paranaque", "taga Paranaque"
            - "QC area", "Quezon City area", "Paranaque area"

            CRITICAL: HANDLE ORDER MODIFICATIONS AND REPLACEMENTS:
            Process modifications in CHRONOLOGICAL ORDER. Apply each change step-by-step.
            
            MODIFICATION KEYWORDS TO RECOGNIZE:
            - Additions: "add pa", "pa-add", "dagdag pa", "plus", "at saka", "pati", "kasama"
            - Removals: "tanggal", "patanggal", "remove", "wag na", "cancel", "hindi na"
            - Replacements: "replace", "pareplace", "palit", "change to", "instead of"
            - Complete changes: "hindi", "wait", "actually", "scratch that", "mas gusto ko"

            MANDATORY STEP-BY-STEP PROCESSING - FOLLOW EXACTLY:
            
            WHEN YOU SEE "patanggal" / "tanggal" / "remove":
            1. Identify EXACTLY what item and quantity to remove
            2. SUBTRACT that item from your current order list  
            3. Continue with remaining items only
            4. DO NOT include removed items in final result
            
            PROCESSING EXAMPLE - YOUR TEST CASE:
            "isang tub cheese po tapos padd na rin ng tatlong bbq pouch
            ay wait pwede patanggal yung tub cheese tapos pa-add na lang ng 3 sour cream tub
            tapos padd ng isa pang original blend na tub"
            
            MANDATORY STEP-BY-STEP:
            Step 1: Initial order = 1 cheese tub + 3 BBQ pouches
            Step 2: "patanggal yung tub cheese" = REMOVE 1 cheese tub 
                    Current order = 3 BBQ pouches (cheese tub DELETED)
            Step 3: "pa-add na lang ng 3 sour cream tub" = ADD 3 sour cream tubs
                    Current order = 3 BBQ pouches + 3 sour cream tubs  
            Step 4: "padd ng isa pang original blend na tub" = ADD 1 original tub
                    FINAL = 3 BBQ pouches + 3 sour cream tubs + 1 original tub = 7 items
            
            CRITICAL REMOVAL EXAMPLES:
            1. "2 cheese tub + 1 BBQ... patanggal yung cheese tub"
               → RESULT: 1 BBQ tub only (cheese REMOVED)
               
            2. "3 original pouch... tanggal ng dalawa... add BBQ tub"  
               → RESULT: 1 original pouch + 1 BBQ tub (2 original REMOVED)
               
            3. "cheese tub + sour tub... patanggal cheese... add 3 BBQ pouch"
               → RESULT: 1 sour tub + 3 BBQ pouches (cheese REMOVED)

            MANDATORY INSTRUCTIONS - NO EXCEPTIONS:
            1. Process modifications in EXACT chronological order
            2. When you see "patanggal"/"tanggal"/"remove": IMMEDIATELY delete that item from your running list
            3. When you see "pa-add"/"add"/"padd": ADD new items to your running list  
            4. When you see "pareplace"/"replace": DELETE old item FIRST, then ADD new item
            5. NEVER include removed items in your final JSON result
            6. Double-check: removed items should NOT appear in final order
            7. In "notes": List each step you processed: "Removed X, Added Y, etc."
            8. Verify final count: does it match your step-by-step calculation?
            
            ABSOLUTE RULE: If customer says "patanggal yung [item]" - that item MUST NOT be in final result.

            DISCOUNT DETECTION:
            Look for discount keywords and extract percentage:
            - "15% off", "15% discount", "15%" → 15% discount
            - "5 off", "discount 5" → 5% discount (treat as percentage, not fixed amount)
            - "discount", "diskarte", "bawas" → generic discount (set to 0)
            - Filipino: "may discount", "may bawas", "diskarte naman"
            
            IMPORTANT: ALL numeric discount values should be treated as PERCENTAGE, not fixed peso amounts.

            SHIPPING FEE DETECTION:
            Look for shipping fee keywords and extract amount:
            - "shipping 50", "shipping fee 75", "delivery 100" → shipping fee amount
            - "sf 60", "sf fee 80" → shipping fee amount (sf = shipping fee)
            - "padala 50", "hatid 75" → Filipino shipping terms
            - "plus 50 shipping", "50 sf", "delivery fee 100" → various formats
            
            IMPORTANT: Shipping fees are ALWAYS fixed peso amounts, not percentages.

            Return ONLY valid JSON with the FINAL corrected order:
            {{
                "customer_name": "extracted name or null",
                "payment_method": "Gcash" or "BPI" or "Maya" or "Cash" or "BDO" or "Others" or null,
                "customer_location": "Quezon City" or "Paranaque" or null,
                "discount_percentage": 15.0 or null,
                "discount_amount": 150 or null,
                "shipping_fee": 50 or null,
                "items": [
                    {{"product_code": "P-CHZ", "quantity": 2}},
                    {{"product_code": "2L-BBQ", "quantity": 1}}
                ],
                "confidence": 0.95,
                "notes": "detected order modification/replacement" or "straightforward order"
            }}

            CUSTOMER MESSAGE TO PARSE:
            {message}
            """
            
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return self._extract_and_validate_response(response, message)
                
        except Exception as e:
            print(f"Claude API error: {str(e)}")
            return self._basic_parse(message)
    
    def _extract_and_validate_response(self, response, original_message: str) -> ParsedOrder:
        """Extract and validate Claude's response with multiple fallback strategies"""
        try:
            response_text = response.content[0].text
            
            # Try to extract JSON with multiple strategies
            json_data = None
            
            # Strategy 1: Find JSON block
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    json_data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # Strategy 2: Find JSON between ```json blocks  
            if not json_data:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    try:
                        json_data = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass
            
            # Strategy 3: Try parsing entire response as JSON
            if not json_data:
                try:
                    json_data = json.loads(response_text)
                except json.JSONDecodeError:
                    pass
            
            if json_data and 'items' in json_data:
                return self._create_order_from_json(json_data, original_message)
            else:
                # Fallback to basic parsing
                return self._basic_parse(original_message)
                
        except Exception as e:
            print(f"Response parsing error: {str(e)}")
            return self._basic_parse(original_message)
    
    def _basic_parse(self, message: str) -> ParsedOrder:
        """Basic parsing without Claude API"""
        items = []
        
        # Simple pattern matching for product codes and quantities
        patterns = [
            r'(\d+)\s*x?\s*(P-CHZ|P-SC|P-BBQ|P-OG|2L-CHZ|2L-SC|2L-BBQ|2L-OG)',
            r'(P-CHZ|P-SC|P-BBQ|P-OG|2L-CHZ|2L-SC|2L-BBQ|2L-OG)\s*x?\s*(\d+)',
            r'(cheese|sour cream|bbq|original).*?(\d+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    if match[0].isdigit():
                        quantity, product_code = int(match[0]), match[1].upper()
                    elif match[1].isdigit():
                        product_code, quantity = match[0].upper(), int(match[1])
                    else:
                        continue
                    
                    if product_code in PRODUCTS:
                        items.append(OrderItem(PRODUCTS[product_code], quantity))
        
        # Extract customer name (basic attempt)
        name_patterns = [
            r'for\s+([A-Za-z\s]+)',           # "for nina"
            r'para\s+(sa\s+)?([A-Za-z\s]+)', # "para nina" or "para sa nina"
            r'kay\s+([A-Za-z\s]+)',          # "kay nina"
            r'from\s+([A-Za-z\s]+)',         # "from nina"
            r'([A-Za-z\s]+)\s+ordered',      # "nina ordered"
            r'customer:\s*([A-Za-z\s]+)',    # "customer: nina"
        ]
        
        customer_name = None
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                # Handle the "para sa" pattern which has 2 groups
                if 'para' in pattern:
                    customer_name = (match.group(2).strip() if match.group(2) else match.group(1).strip()).title()
                else:
                    customer_name = match.group(1).strip().title()
                break
        
        total = sum(item.quantity * item.product.price for item in items)
        
        # Basic payment method detection for fallback
        payment_method = self._detect_payment_method(message)
        
        # Basic location detection and seller assignment
        location, auto_sold_by = self._detect_location_and_seller(message)
        
        # Detect discount
        discount_percentage, discount_amount = self._detect_discount(message, total)
        
        # Detect shipping fee
        shipping_fee = self._detect_shipping_fee(message)
        
        return ParsedOrder(customer_name, items, total, message, payment_method, location, auto_sold_by, discount_percentage, discount_amount, shipping_fee)
    
    def _detect_payment_method(self, message: str) -> Optional[str]:
        """Basic payment method detection for fallback when Claude API is not available"""
        message_lower = message.lower()
        
        # Check for payment method keywords
        if any(keyword in message_lower for keyword in ['gcash', 'g-cash', 'g cash']):
            return 'Gcash'
        elif any(keyword in message_lower for keyword in ['bpi']):
            return 'BPI'
        elif any(keyword in message_lower for keyword in ['maya', 'paymaya', 'pay maya']):
            return 'Maya'
        elif any(keyword in message_lower for keyword in ['cash', 'cod', 'cash on delivery', 'bayad cash']):
            return 'Cash'
        elif any(keyword in message_lower for keyword in ['bdo']):
            return 'BDO'
        elif any(keyword in message_lower for keyword in ['transfer', 'bank', 'online']):
            return 'Others'
        
        return None  # No payment method detected
    
    def _detect_location_and_seller(self, message: str) -> tuple[Optional[str], Optional[str]]:
        """Detect customer location and automatically assign seller"""
        message_lower = message.lower()
        
        # Check for Quezon City / QC keywords
        qc_keywords = ['quezon city', 'qc', 'sa qc', 'galing qc', 'dito sa quezon city', 'taga qc', 'qc area']
        if any(keyword in message_lower for keyword in qc_keywords):
            return 'Quezon City', 'Ferdie'
        
        # Check for Paranaque keywords  
        paranaque_keywords = ['paranaque', 'paranañaque', 'parañaque', 'sa paranaque', 'galing paranaque', 
                             'dito sa paranaque', 'taga paranaque', 'paranaque area']
        if any(keyword in message_lower for keyword in paranaque_keywords):
            return 'Paranaque', 'Nina'
        
        return None, None  # No location detected
    
    def _detect_discount(self, message: str, total_amount: int) -> tuple[Optional[float], Optional[int]]:
        """Detect discount in message and calculate discount amount"""
        message_lower = message.lower()
        
        # Discount patterns to match - all treated as percentage
        discount_patterns = [
            r'(\d+)%\s*off',           # "15% off"
            r'(\d+)%\s*discount',      # "15% discount"  
            r'(\d+)%',                 # "15%"
            r'(\d+)\s*off',            # "5 off" - treat as 5% off
            r'discount\s*(\d+)%',      # "discount 15%"
            r'discount\s*(\d+)',       # "discount 5" - treat as 5%
        ]
        
        for pattern in discount_patterns:
            match = re.search(pattern, message_lower)
            if match:
                discount_value = float(match.group(1))
                
                # All patterns are treated as percentage
                discount_percentage = discount_value
                discount_amount = int(total_amount * (discount_percentage / 100))
                return discount_percentage, discount_amount
        
        # Check for generic "discount" without specific amount
        if any(word in message_lower for word in ['discount', 'diskarte', 'bawas']):
            # Default to 0 - could be manually entered later
            return 0.0, 0
        
        return None, None  # No discount detected
    
    def _detect_shipping_fee(self, message: str) -> Optional[int]:
        """Detect shipping fee in message"""
        message_lower = message.lower()
        
        # Shipping fee patterns to match
        shipping_patterns = [
            r'shipping\s*(?:fee)?\s*(\d+)',     # "shipping 50", "shipping fee 50"
            r'delivery\s*(?:fee)?\s*(\d+)',     # "delivery 50", "delivery fee 50"
            r'sf\s*(?:fee)?\s*(\d+)',           # "sf 50", "sf fee 50"
            r'padala\s*(\d+)',                  # "padala 50"
            r'hatid\s*(\d+)',                   # "hatid 50"
            r'ship\s*(\d+)',                    # "ship 50"
            r'deliver\s*(\d+)',                 # "deliver 50"
            r'(\d+)\s*shipping',                # "50 shipping"
            r'(\d+)\s*sf',                      # "50 sf"
            r'plus\s*(\d+)\s*(?:shipping|sf|delivery|padala)', # "plus 50 shipping"
        ]
        
        for pattern in shipping_patterns:
            match = re.search(pattern, message_lower)
            if match:
                shipping_amount = int(match.group(1))
                return shipping_amount
        
        return None  # No shipping fee detected
    
    def _create_order_from_json(self, data: dict, raw_message: str) -> ParsedOrder:
        """Create ParsedOrder from JSON data with enhanced information"""
        items = []
        for item_data in data.get('items', []):
            product_code = item_data.get('product_code', '').upper()
            quantity = item_data.get('quantity', 0)
            
            if product_code in PRODUCTS and quantity > 0:
                items.append(OrderItem(PRODUCTS[product_code], quantity))
        
        total = sum(item.quantity * item.product.price for item in items)
        
        # Get location from Claude response and determine seller
        location = data.get('customer_location')
        auto_sold_by = None
        if location == 'Quezon City':
            auto_sold_by = 'Ferdie'
        elif location == 'Paranaque':
            auto_sold_by = 'Nina'
        
        # Format customer name with proper capitalization
        customer_name = data.get('customer_name')
        if customer_name:
            customer_name = customer_name.strip().title()
        
        # Get discount data from Claude response
        discount_percentage = data.get('discount_percentage')
        discount_amount = data.get('discount_amount')
        
        # If percentage but no amount, calculate it
        if discount_percentage and not discount_amount:
            discount_amount = int(total * (discount_percentage / 100))
        
        # Get shipping fee from Claude response
        shipping_fee = data.get('shipping_fee')
        
        # Create enhanced ParsedOrder with additional Claude data
        order = ParsedOrder(
            customer_name=customer_name,
            items=items,
            total_amount=total,
            raw_message=raw_message,
            payment_method=data.get('payment_method'),
            customer_location=location,
            auto_sold_by=auto_sold_by,
            discount_percentage=discount_percentage,
            discount_amount=discount_amount,
            shipping_fee=shipping_fee
        )
        
        # Add Claude-specific metadata
        if hasattr(order, '__dict__'):
            order.confidence = data.get('confidence', 0.0)
            order.parsing_notes = data.get('notes', '')
        
        return order

class GoogleSheetsIntegration:
    def __init__(self, credentials_json: str = None, spreadsheet_id: str = None):
        """Initialize Google Sheets integration with service account credentials"""
        self.credentials_json = credentials_json or os.getenv('GOOGLE_CREDENTIALS_JSON')
        self.spreadsheet_id = spreadsheet_id or os.getenv('GOOGLE_SPREADSHEET_ID')
        self.gc = None
        self.spreadsheet = None
        self.worksheet = None
        self.is_railway = os.getenv('GOOGLE_CREDENTIALS_B64') is not None
        self.last_error = None
        
    def connect(self, worksheet_name: str = "ORDER") -> bool:
        """Connect to Google Sheets API and open the specified spreadsheet"""
        try:
            if not self.spreadsheet_id:
                self.last_error = "Missing spreadsheet ID"
                raise Exception(self.last_error)
            
            # Handle Railway vs local environment
            if self.is_railway:
                # Railway environment - use base64 encoded credentials
                import base64
                credentials_b64 = os.getenv('GOOGLE_CREDENTIALS_B64')
                if not credentials_b64:
                    self.last_error = "GOOGLE_CREDENTIALS_B64 environment variable is required for Railway"
                    raise Exception(self.last_error)
                
                # Decode base64 credentials
                try:
                    credentials_json = base64.b64decode(credentials_b64).decode('utf-8')
                    creds_data = json.loads(credentials_json)
                    print("Using base64 encoded credentials from Railway")
                except Exception as decode_error:
                    self.last_error = f"Failed to decode credentials: {decode_error}"
                    raise Exception(self.last_error)
            else:
                # Local environment - use JSON string or file
                if self.credentials_json:
                    try:
                        creds_data = json.loads(self.credentials_json)
                    except Exception as json_error:
                        self.last_error = f"Invalid JSON credentials: {json_error}"
                        raise Exception(self.last_error)
                else:
                    self.last_error = "Missing Google credentials"
                    raise Exception(self.last_error)
            
            # Set up credentials with required scopes
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            try:
                credentials = Credentials.from_service_account_info(creds_data, scopes=scopes)
                self.gc = gspread.authorize(credentials)
            except Exception as auth_error:
                self.last_error = f"Google auth failed: {auth_error}"
                raise Exception(self.last_error)
            
            # Open the spreadsheet and worksheet
            try:
                self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
                self.worksheet = self.spreadsheet.worksheet(worksheet_name)
            except Exception as sheet_error:
                self.last_error = f"Failed to open spreadsheet/worksheet: {sheet_error}"
                raise Exception(self.last_error)
            
            self.last_error = None
            return True
            
        except Exception as e:
            error_msg = f"Failed to connect to Google Sheets: {str(e)}"
            print(error_msg)
            self.last_error = str(e)
            return False
    
    def find_next_available_row(self) -> int:
        """Find the next available row by checking both customer name (D) and product columns (N,O,P,Q,T,U,V,W)"""
        try:
            # Get all data for the relevant columns at once
            # Column D = Customer Name, Columns N,O,P,Q,T,U,V,W = Product quantities
            relevant_columns = ['D', 'N', 'O', 'P', 'Q', 'T', 'U', 'V', 'W']
            
            # Get data from all relevant columns (we'll check up to row 2000 to be safe)
            range_to_check = "D1:W2000"
            all_data = self.worksheet.get(range_to_check)
            
            last_row_with_data = 1  # Start from row 1 (headers)
            
            # Check each row for data in relevant columns
            for row_index, row_data in enumerate(all_data):
                actual_row_number = row_index + 1  # Convert to 1-based row number
                
                if actual_row_number == 1:  # Skip header row
                    continue
                
                # Check if this row has data in customer name (column D = index 0 in our range)
                has_customer_data = False
                if len(row_data) > 0 and row_data[0] and str(row_data[0]).strip():
                    has_customer_data = True
                
                # Check if this row has data in any product columns (N,O,P,Q,T,U,V,W)
                # In our range D1:W2000, columns N,O,P,Q,T,U,V,W are at indices 10,11,12,13,16,17,18,19
                product_column_indices = [10, 11, 12, 13, 16, 17, 18, 19]  # N,O,P,Q,T,U,V,W
                has_product_data = False
                
                for col_index in product_column_indices:
                    if (len(row_data) > col_index and 
                        row_data[col_index] and 
                        str(row_data[col_index]).strip() and
                        str(row_data[col_index]).strip() != '0'):
                        has_product_data = True
                        break
                
                # If either customer data OR product data exists, this row is occupied
                if has_customer_data or has_product_data:
                    last_row_with_data = actual_row_number
            
            # Return the next available row
            next_available = last_row_with_data + 1
            
            return next_available
                
        except Exception as e:
            print(f"Could not auto-detect next row: {str(e)}")
            return 526  # Fallback to expected row
    
    def update_order_row(self, parsed_order: ParsedOrder, row_number: int = None) -> bool:
        """Update Google Sheet with order data"""
        try:
            if not self.worksheet:
                print("No worksheet connection available")
                return False
            
            if row_number is None:
                row_number = self.find_next_available_row()
                
            today = datetime.now(pytz.timezone('Asia/Manila'))
            
            # Update only specific cells to avoid overwriting formulas
            updates = {}
            
            # Basic order info
            updates['C'] = today.strftime("%m/%d/%Y")                    # Column C: Date
            updates['D'] = parsed_order.customer_name or "Unknown"       # Column D: Customer
            
            # Sold By - only update if location was detected and seller assigned
            if parsed_order.auto_sold_by:
                updates['E'] = parsed_order.auto_sold_by                 # Column E: Auto-assigned Sold By
            
            updates['H'] = "Unpaid"                                      # Column H: Payment Status
            
            # Payment method - only update if detected
            if parsed_order.payment_method:
                updates['G'] = parsed_order.payment_method               # Column G: Payment Method
            
            # Fun note - add robot emoji with timestamp
            current_time = datetime.now(pytz.timezone('Asia/Manila')).strftime("%I:%M %p")
            updates['J'] = f"🤖 {current_time}"                         # Column J: Notes with timestamp
            
            # Order type - always set to Reserved for bot orders
            updates['K'] = "Reserved"                                    # Column K: Note (always Reserved)
            
            # Product quantities
            for item in parsed_order.items:
                product_code = item.product.code
                quantity = item.quantity
                
                if product_code == "P-CHZ":      # Column N
                    updates['N'] = quantity
                elif product_code == "P-SC":     # Column O
                    updates['O'] = quantity
                elif product_code == "P-BBQ":    # Column P
                    updates['P'] = quantity
                elif product_code == "P-OG":     # Column Q
                    updates['Q'] = quantity
                elif product_code == "2L-CHZ":   # Column T
                    updates['T'] = quantity
                elif product_code == "2L-SC":    # Column U
                    updates['U'] = quantity
                elif product_code == "2L-BBQ":   # Column V
                    updates['V'] = quantity
                elif product_code == "2L-OG":    # Column W
                    updates['W'] = quantity
            
            # Add discount to Column AA if present
            if parsed_order.discount_amount and parsed_order.discount_amount > 0:
                updates['AA'] = parsed_order.discount_amount
            
            # Add shipping fee to Column Z if present
            if parsed_order.shipping_fee and parsed_order.shipping_fee > 0:
                updates['Z'] = parsed_order.shipping_fee
            
            # Update cells individually
            for column_letter, value in updates.items():
                if value:  # Only update non-empty values
                    # Handle double-letter columns like AA
                    if column_letter == 'AA':
                        col_num = 27  # AA is the 27th column
                    elif column_letter == 'Z':
                        col_num = 26  # Z is the 26th column
                    else:
                        col_num = ord(column_letter) - ord('A') + 1
                    self.worksheet.update_cell(row_number, col_num, value)
            
            return True
            
        except Exception as e:
            print(f"Update failed: {str(e)}")
            return False