import random
import json
import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = "ТОКЕН_БОТА"  # вставь сюда свой токен от BotFather

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# =============================
# База игроков
# =============================
conn = sqlite3.connect("dungeon.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    floor INTEGER,
    weapon INTEGER,
    difficulty TEXT,
    legend_fragments TEXT,
    coins INTEGER,
    inventory TEXT
)
""")
conn.commit()

# =============================
# Данные игры
# =============================
mobs = ["Скелет", "Гоблин", "Орк", "Крысиный король", "Призрак"]
mini_bosses = ["Призрак Героя", "Древний Чешуйчатый Страж", "Алтарный Хранитель", "Бессмертный Бард", "Тень Абсолюта"]
all_fragments = set(mini_bosses)

hints = {
    "Призрак Героя": "Я пал в битве... но мой клинок всё ещё существует.",
    "Древний Чешуйчатый Страж": "Чешуя хранит секрет меча.",
    "Алтарный Хранитель": "Клинок спрятан там, где огонь и тьма сливаются в одно.",
    "Бессмертный Бард": "Герой живёт в клинке. Найди его.",
    "Тень Абсолюта": "Даже если найдёшь меч — конец неизбежен!"
}

difficulties = {
    "easy": {"mob_chance": 0.8, "boss_chance": 0.2},
    "normal": {"mob_chance": 0.7, "boss_chance": 0.3},
    "hard": {"mob_chance": 0.6, "boss_chance": 0.4},
    "master": {"mob_chance": 0.5, "boss_chance": 0.5},
}

common_items = ["Зелье лечения", "Малый меч", "Щит новичка", "Кинжал разведчика"]
rare_items = ["Огненный меч", "Амулет скорости", "Кираса героя", "Посох шамана"]
legendary_items = ["Кусок Легендарного меча", "Крылья дракона", "Посох Архимага", "Корона древних", "Меч Вечной Силы"]

# =============================
# Вспомогательные функции
# =============================
def get_player(user_id):
    cur.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        return {
            "user_id": row[0],
            "floor": row[1],
            "weapon": row[2],
            "difficulty": row[3],
            "legend_fragments": set(json.loads(row[4])),
            "coins": row[5],
            "inventory": json.loads(row[6])
        }
    else:
        cur.execute("INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, 1, 0, "normal", json.dumps([]), 1000, json.dumps([])))
        conn.commit()
        return get_player(user_id)

def save_player(player):
    cur.execute("""
    UPDATE players SET floor=?, weapon=?, difficulty=?, legend_fragments=?, coins=?, inventory=?
    WHERE user_id=?
    """, (player["floor"], player["weapon"], player["difficulty"],
          json.dumps(list(player["legend_fragments"])), player["coins"],
          json.dumps(player["inventory"]), player["user_id"]))
    conn.commit()

# =============================
# Сундуки с шансами
# =============================
def get_reward(box_type):
    roll = random.uniform(0, 100)
    if box_type == "обычный":
        if roll <= 80:
            return random.choice(common_items)
        else:
            return random.choice(rare_items)
    elif box_type == "золотой":
        if roll <= 60:
            return random.choice(common_items)
        elif roll <= 90:
            return random.choice(rare_items)
        else:
            return random.choice(legendary_items[:-1])
    elif box_type == "легендарный":
        if roll <= 40:
            return random.choice(common_items)
        elif roll <= 80:
            return random.choice(rare_items)
        elif roll <= 99.5:
            return random.choice(legendary_items[:-1])
        else:
            return "Меч Вечной Силы"
    else:
        return "Ошибка!"

def open_box(player, box_type):
    cost_dict = {"обычный":100, "золотой":300, "легендарный":700}
    cost = cost_dict.get(box_type, 0)
    if player["coins"] < cost:
        return "❌ Не хватает монет!"
    player["coins"] -= cost
    reward = get_reward(box_type)
    player["inventory"].append(reward)
    save_player(player)
    return f"🎁 Ты открыл {box_type} сундук и получил: {reward}\n💰 Баланс: {player['coins']} монет"

# =============================
# Платежи через Kaspi
# =============================
pending_payments = {}  # user_id: {"box": "легендарный", "amount": 200, "paid": False}
KASPI_QR_URL = "https://kaspi.kz/pay/7715275280"

@dp.message_handler(commands=["buy"])
async def cmd_buy(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Обычный сундук (200₸)", "Золотой сундук (500₸)", "Легендарный сундук (1000₸)")
    await message.answer("💰 Выберите сундук для покупки через Kaspi. После выбора откроется QR для оплаты.", reply_markup=keyboard)

@dp.message_handler(lambda message: "сундук" in message.text.lower())
async def select_box(message: types.Message):
    user_id = message.from_user.id
    text = message.text.lower()
    if "обычный" in text:
        pending_payments[user_id] = {"box": "обычный", "amount": 200, "paid": False}
    elif "золотой" in text:
        pending_payments[user_id] = {"box": "золотой", "amount": 500, "paid": False}
    elif "легендарный" in text:
        pending_payments[user_id] = {"box": "легендарный", "amount": 1000, "paid": False}
    else:
        await message.answer("❌ Такой сундук не найден.")
        return

    qr_keyboard = InlineKeyboardMarkup()
    qr_button = InlineKeyboardButton(text="Оплатить через Kaspi", url=KASPI_QR_URL)
    qr_keyboard.add(qr_button)

    await message.answer(
        f"📲 Сундук: {pending_payments[user_id]['box']}\nСумма: {pending_payments[user_id]['amount']}₸\nНажми кнопку ниже, чтобы открыть Kaspi QR и оплатить. После перевода напиши /paid",
        reply_markup=qr_keyboard
    )

@dp.message_handler(commands=["paid"])
async def cmd_paid(message: types.Message):
    user_id = message.from_user.id
    if user_id not in pending_payments:
        await message.answer("❌ У тебя нет ожидающей покупки.")
        return

    payment = pending_payments[user_id]
    payment["paid"] = True

    # автоматически выдаём сундук
    player = get_player(user_id)
    result = open_box(player, payment["box"])
    await message.answer(f"✅ Платёж подтверждён!\n🎁 Твой сундук открыт:\n{result}")

    # удаляем из ожидающих
    del pending_payments[user_id]

# =============================
# Основные команды игры
# =============================
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    player = get_player(message.from_user.id)
    await message.answer(f"⚔️ Добро пожаловать в Подземелье! У тебя {player['coins']} монет.\nВыбери сложность: /easy /normal /hard /master")

@dp.message_handler(commands=["easy","normal","hard","master"])
async def cmd_difficulty(message: types.Message):
    diff = message.text[1:]
    player = get_player(message.from_user.id)
    player["difficulty"] = diff
    save_player(player)
    await message.answer(f"🎮 Сложность установлена: {diff}. Напиши /next чтобы начать")

@dp.message_handler(commands=["next"])
async def cmd_next(message: types.Message):
    player = get_player(message.from_user.id)
    floor = player["floor"]
    diff = player["difficulty"]
    settings = difficulties[diff]

    if floor >= 50:
        if player["weapon"]:
            await message.answer("🔥 Ты победил Аб
