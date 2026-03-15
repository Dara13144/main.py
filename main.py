import asyncio
import logging
import aiosqlite
import qrcode
from io import BytesIO
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from bakong_khqr import KHQR

# ================= CONFIGURATION =================
BOT_TOKEN = "8268141549:AAElwnPeLfJt9bHznJxSxJLYT_5TCJ4D0sE"
ADMIN_ID = 5169380878
# Your Bakong Developer Token
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiZDE0ZDAwOTJmNzI5NDk3YSJ9LCJpYXQiOjE3NzE3MTI0NDUsImV4cCI6MTc3OTQ4ODQ0NX0.YjTPMjrXEETs1p2luFE3FHHg6K-VjPi6Be_3NNP-ifY"
BAKONG_ACCOUNT = "dara_mao@bkrt"
MERCHANT_NAME = "8Ball Pool Store"
DB_PATH = "8ball_pro_system.db"
# =================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
khqr = KHQR(BAKONG_TOKEN)

# --- DATABASE SYSTEM ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Table for Stock
        await db.execute("""CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            key_value TEXT,
            is_sold INTEGER DEFAULT 0
        )""")
        # Table for Sales
        await db.execute("""CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            price REAL,
            sold_at TEXT
        )""")
        await db.commit()

# --- KEYBOARDS ---
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Buy Game Keys")],
            [KeyboardButton(text="👤 My Profile"), KeyboardButton(text="📞 Support")]
        ], resize_keyboard=True
    )

def get_admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Check Stock"), KeyboardButton(text="➕ Add New Key")],
            [KeyboardButton(text="💰 Sales Report"), KeyboardButton(text="🏠 User Mode")]
        ], resize_keyboard=True
    )

def get_buy_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎱 Weekly Key - $5", callback_data="buy_weekly_5.0")],
        [InlineKeyboardButton(text="🎱 Monthly Key - $15", callback_data="buy_monthly_15.0")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_order")]
    ])

# --- USER HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"👋 Welcome to **{MERCHANT_NAME}**\n\nAutomated delivery for 8Ball Pool keys via Bakong KHQR.",
        reply_markup=get_main_kb(),
        parse_mode="Markdown"
    )
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin access granted. Use /admin to open panel.")

@dp.message(F.text == "🛒 Buy Game Keys")
async def show_store(message: types.Message):
    await message.answer("Please select your package:", reply_markup=get_buy_inline())

@dp.callback_query(F.data.startswith("buy_"))
async def process_payment(callback: types.CallbackQuery):
    _, category, price = callback.data.split("_")
    price = float(price)

    # Check database for available keys
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM keys WHERE category = ? AND is_sold = 0 LIMIT 1", (category,))
        stock_item = await cursor.fetchone()

    if not stock_item:
        await callback.answer("❌ Out of Stock! Please try again later.", show_alert=True)
        return

    # Generate Bakong KHQR
    bill_no = f"INV{int(datetime.now().timestamp())}"
    qr_data = khqr.create_qr(
        bank_account=BAKONG_ACCOUNT,
        merchant_name=MERCHANT_NAME,
        amount=price,
        currency='USD',
        bill_number=bill_no
    )
    md5 = khqr.generate_md5(qr_data)
    
    # Create QR Image for user
    qr_img = qrcode.make(qr_data)
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    
    await callback.message.answer_photo(
        BufferedInputFile(buf.read(), filename="pay.png"),
        caption=f"💳 **Payment Invoice**\n━━━━━━━━━━━━━━\n📦 Item: `{category.upper()}`\n💵 Price: `${price}`\n━━━━━━━━━━━━━━\n\n✅ Scan to pay. Your key will be sent instantly after payment."
    )
    
    # Start auto-checking payment
    asyncio.create_task(check_payment_loop(callback.from_user.id, md5, category, price))

async def check_payment_loop(user_id, md5, category, price):
    for _ in range(60): # Check every 10 seconds for 10 minutes
        await asyncio.sleep(10)
        status = khqr.check_payment(md5)
        
        if status == "SUCCESS":
            async with aiosqlite.connect(DB_PATH) as db:
                # Fetch the key
                cursor = await db.execute("SELECT id, key_value FROM keys WHERE category = ? AND is_sold = 0 LIMIT 1", (category,))
                key_data = await cursor.fetchone()
                
                if key_data:
                    k_id, k_val = key_data
                    # Mark as sold
                    await db.execute("UPDATE keys SET is_sold = 1 WHERE id = ?", (k_id,))
                    await db.execute("INSERT INTO sales (user_id, category, price, sold_at) VALUES (?,?,?,?)",
                                     (user_id, category, price, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    await db.commit()

                    await bot.send_message(user_id, f"✅ **Payment Successful!**\n\n🔑 Your 8Ball Pool Key:\n`{k_val}`\n\nThank you for your purchase!")
                    await bot.send_message(ADMIN_ID, f"💰 **NEW SALE**\nUser: `{user_id}`\nPackage: {category}\nPrice: ${price}")
                    return
    await bot.send_message(user_id, "❌ Payment timeout. Please contact support.")

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_main(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 **Admin Control Panel**", reply_markup=get_admin_kb())

@dp.message(F.text == "🏠 User Mode")
async def switch_user(message: types.Message):
    await message.answer("Switching to User Menu...", reply_markup=get_main_kb())

@dp.message(F.text == "📊 Check Stock")
async def admin_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT category, COUNT(*) FROM keys WHERE is_sold = 0 GROUP BY category")
        rows = await cursor.fetchall()
    
    msg = "📦 **Current Inventory:**\n"
    if not rows: msg += "Stock is empty!"
    for r in rows:
        msg += f"- {r[0].capitalize()}: {r[1]} keys\n"
    await message.answer(msg)

@dp.message(F.text == "➕ Add New Key")
async def add_key_info(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Please send the key in this format:\n`category:keyvalue` \nExample: `weekly:ABCD-1234`")

@dp.message(F.text.contains(":"))
async def handle_key_add(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cat, val = message.text.split(":", 1)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO keys (category, key_value) VALUES (?,?)", (cat.strip().lower(), val.strip()))
            await db.commit()
        await message.answer(f"✅ Key added to **{cat.strip()}**.")
    except:
        await message.answer("❌ Error. Use format `category:key`")

@dp.message(F.text == "💰 Sales Report")
async def sales_report(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT SUM(price), COUNT(*) FROM sales")
        total_revenue, total_sales = await cursor.fetchone()
    
    await message.answer(f"📈 **Sales Statistics**\n\nTotal Sales: {total_sales or 0}\nTotal Revenue: ${total_revenue or 0.0}")

# --- STARTUP ---
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    print("--- 8Ball Bot is Running ---")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
