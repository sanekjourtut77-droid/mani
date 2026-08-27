import asyncio
import aiosqlite

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberUpdated,
)
from aiogram.client.default import DefaultBotProperties


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = "PASTE_BOT_TOKEN_HERE"

# ID обязательного канала
CHANNEL_ID = -1001234567890

# Ссылка на обязательный канал
CHANNEL_LINK = "https://t.me/YOUR_CHANNEL"

# Telegram ID администратора
ADMIN_IDS = {
    123456789
}

# Награда за одного активного реферала
REWARD_PER_REF = 10

# Минимальный вывод
MIN_WITHDRAW = 100

# База данных
DB_NAME = "referral_bot.db"


# =========================================================
# PREMIUM CUSTOM EMOJI
# =========================================================
#
# Твои найденные Premium / Custom Emoji.
# ⚠️ WARNING специально остаётся обычным emoji.
#

EMOJI_IDS = [
    5938537205847822613,
    5258011929993026890,
    5258513401784573443,
    6028338546736107668,
    4965219701572503640,
    5904462880941545555,
    6028171274939797252,
    5258204546391351475,
    6037083366438737901,
    5449730014431959418,
    6032644646587338669,
    6032742198179532882,
    5454160256017908632,
    5386367538735104399,
    5325945307454789973,
    5398095307714099676,
    5316635411789931847,
    5321300317504030049,
    5244484741515732344,
    5145427681680032825,
    5053473385355412667,
    5044126248029128166,
]


def ce(index: int, fallback: str = "⭐") -> str:
    """
    Возвращает Telegram Custom Emoji.
    """

    emoji_id = EMOJI_IDS[index]

    return (
        f'<tg-emoji emoji-id="{emoji_id}">'
        f'{fallback}'
        f'</tg-emoji>'
    )


# =========================================================
# EMOJI НА КАЖДЫЙ ЭЛЕМЕНТ ИНТЕРФЕЙСА
# =========================================================

HOME = ce(0, "🏠")
USER = ce(1, "👤")
REFERRALS = ce(2, "👥")
STAR = ce(3, "⭐")
BALANCE = ce(4, "💰")
PAID = ce(5, "💸")
LINK = ce(6, "🔗")
TRANSACTIONS = ce(7, "💳")
WITHDRAW = ce(8, "💎")
STATS = ce(9, "📊")
GIFT = ce(10, "🎁")
SETTINGS = ce(11, "⚙️")
CHECK = ce(12, "✅")
PENDING = ce(13, "🟡")
APPROVED = ce(14, "🟢")
REJECTED = ce(15, "🔴")
BACK = ce(16, "⬅️")
NEXT = ce(17, "➡️")
INFO = ce(18, "ℹ️")

# ВАЖНО: warning оставляем обычным
WARNING = "⚠️"

ROCKET = ce(19, "🚀")
FIRE = ce(20, "🔥")
CROWN = ce(21, "👑")


# =========================================================
# DATABASE
# =========================================================

class Database:

    def __init__(self, path: str):

        self.path = path
        self.db = None

    # -----------------------------------------------------

    async def connect(self):

        self.db = await aiosqlite.connect(
            self.path
        )

        self.db.row_factory = aiosqlite.Row

        # USERS
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS users (

            user_id INTEGER PRIMARY KEY,

            username TEXT,

            full_name TEXT,

            balance INTEGER NOT NULL DEFAULT 0,

            paid_out INTEGER NOT NULL DEFAULT 0,

            referrer_id INTEGER,

            joined_bot_at TEXT
                DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # REFERRALS
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS referrals (

            referred_id INTEGER PRIMARY KEY,

            referrer_id INTEGER NOT NULL,

            is_active INTEGER NOT NULL DEFAULT 0,

            counted INTEGER NOT NULL DEFAULT 0,

            created_at TEXT
                DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # TRANSACTIONS
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            amount INTEGER NOT NULL,

            status TEXT NOT NULL
                DEFAULT 'processing',

            created_at TEXT
                DEFAULT CURRENT_TIMESTAMP,

            processed_at TEXT,

            processed_by INTEGER
        )
        """)

        await self.db.commit()

    # -----------------------------------------------------

    async def close(self):

        if self.db:

            await self.db.close()

    # -----------------------------------------------------
    # USER
    # -----------------------------------------------------

    async def add_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str
    ):

        await self.db.execute("""
        INSERT INTO users (
            user_id,
            username,
            full_name
        )
        VALUES (?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET

            username = excluded.username,

            full_name = excluded.full_name
        """, (
            user_id,
            username,
            full_name
        ))

        await self.db.commit()

    # -----------------------------------------------------

    async def get_user(
        self,
        user_id: int
    ):

        cursor = await self.db.execute("""
        SELECT *
        FROM users
        WHERE user_id = ?
        """, (
            user_id,
        ))

        return await cursor.fetchone()

    # -----------------------------------------------------
    # REFERRER
    # -----------------------------------------------------

    async def set_referrer_once(
        self,
        referred_id: int,
        referrer_id: int
    ):

        # Нельзя пригласить самого себя
        if referred_id == referrer_id:

            return False

        # Проверяем, есть ли уже реферер
        cursor = await self.db.execute("""
        SELECT referred_id
        FROM referrals
        WHERE referred_id = ?
        """, (
            referred_id,
        ))

        existing = await cursor.fetchone()

        # Один человек может быть привязан
        # только к одному рефереру.
        if existing:

            return False

        # Проверяем существование пригласившего
        referrer = await self.get_user(
            referrer_id
        )

        if not referrer:

            return False

        await self.db.execute("""
        INSERT INTO referrals (
            referred_id,
            referrer_id,
            is_active,
            counted
        )
        VALUES (?, ?, 0, 0)
        """, (
            referred_id,
            referrer_id
        ))

        await self.db.execute("""
        UPDATE users
        SET referrer_id = ?
        WHERE user_id = ?
        """, (
            referrer_id,
            referred_id
        ))

        await self.db.commit()

        return True

    # -----------------------------------------------------

    async def get_referral(
        self,
        referred_id: int
    ):

        cursor = await self.db.execute("""
        SELECT *
        FROM referrals
        WHERE referred_id = ?
        """, (
            referred_id,
        ))

        return await cursor.fetchone()

    # -----------------------------------------------------
    # ACTIVATE REFERRAL
    # -----------------------------------------------------

    async def activate_referral(
        self,
        referred_id: int
    ):

        ref = await self.get_referral(
            referred_id
        )

        if not ref:

            return False

        # Уже активен
        if ref["is_active"] == 1:

            return False

        referrer_id = ref["referrer_id"]

        # Активируем
        await self.db.execute("""
        UPDATE referrals
        SET
            is_active = 1,
            counted = 1
        WHERE referred_id = ?
        """, (
            referred_id,
        ))

        # Начисляем 10 Stars
        await self.db.execute("""
        UPDATE users
        SET balance = balance + ?
        WHERE user_id = ?
        """, (
            REWARD_PER_REF,
            referrer_id
        ))

        await self.db.commit()

        return True

    # -----------------------------------------------------
    # DEACTIVATE REFERRAL
    # -----------------------------------------------------

    async def deactivate_referral(
        self,
        referred_id: int
    ):

        ref = await self.get_referral(
            referred_id
        )

        if not ref:

            return False

        if ref["is_active"] == 0:

            return False

        referrer_id = ref["referrer_id"]

        # Убираем активность
        await self.db.execute("""
        UPDATE referrals
        SET
            is_active = 0,
            counted = 0
        WHERE referred_id = ?
        """, (
            referred_id,
        ))

        # Снимаем бонус
        # Баланс не уходит ниже нуля.
        await self.db.execute("""
        UPDATE users
        SET balance = MAX(balance - ?, 0)
        WHERE user_id = ?
        """, (
            REWARD_PER_REF,
            referrer_id
        ))

        await self.db.commit()

        return True

    # -----------------------------------------------------
    # ACTIVE REFERRALS COUNT
    # -----------------------------------------------------

    async def get_active_referrals_count(
        self,
        user_id: int
    ):

        cursor = await self.db.execute("""
        SELECT COUNT(*)
        FROM referrals

        WHERE referrer_id = ?

        AND is_active = 1

        AND counted = 1
        """, (
            user_id,
        ))

        row = await cursor.fetchone()

        return row[0]

    # -----------------------------------------------------
    # REFERRALS LIST
    # -----------------------------------------------------

    async def get_referrals(
        self,
        user_id: int,
        limit: int = 50
    ):

        cursor = await self.db.execute("""
        SELECT

            r.referred_id,

            r.is_active,

            r.created_at,

            u.username,

            u.full_name

        FROM referrals r

        LEFT JOIN users u
            ON u.user_id = r.referred_id

        WHERE r.referrer_id = ?

        ORDER BY r.created_at DESC

        LIMIT ?
        """, (
            user_id,
            limit
        ))

        return await cursor.fetchall()

    # -----------------------------------------------------
    # TRANSACTIONS
    # -----------------------------------------------------

    async def create_transaction(
        self,
        user_id: int,
        amount: int
    ):

        # Сначала списываем сумму с баланса.
        #
        # Поэтому после создания заявки
        # эти Stars уже нельзя повторно вывести.
        cursor = await self.db.execute("""
        UPDATE users

        SET balance = balance - ?

        WHERE user_id = ?

        AND balance >= ?
        """, (
            amount,
            user_id,
            amount
        ))

        if cursor.rowcount == 0:

            await self.db.rollback()

            return None

        # Создаём заявку
        cursor = await self.db.execute("""
        INSERT INTO transactions (
            user_id,
            amount,
            status
        )
        VALUES (
            ?,
            ?,
            'processing'
        )
        """, (
            user_id,
            amount
        ))

        transaction_id = cursor.lastrowid

        await self.db.commit()

        return transaction_id

    # -----------------------------------------------------

    async def get_transactions(
        self,
        user_id: int,
        limit: int = 20
    ):

        cursor = await self.db.execute("""
        SELECT *

        FROM transactions

        WHERE user_id = ?

        ORDER BY id DESC

        LIMIT ?
        """, (
            user_id,
            limit
        ))

        return await cursor.fetchall()

    # -----------------------------------------------------

    async def get_transaction(
        self,
        transaction_id: int
    ):

        cursor = await self.db.execute("""
        SELECT

            t.*,

            u.username,

            u.full_name,

            u.balance,

            u.paid_out

        FROM transactions t

        LEFT JOIN users u
            ON u.user_id = t.user_id

        WHERE t.id = ?
        """, (
            transaction_id,
        ))

        return await cursor.fetchone()

    # -----------------------------------------------------

    async def get_processing_transactions(
        self,
        limit: int = 50
    ):

        cursor = await self.db.execute("""
        SELECT

            t.*,

            u.username,

            u.full_name

        FROM transactions t

        LEFT JOIN users u
            ON u.user_id = t.user_id

        WHERE t.status = 'processing'

        ORDER BY t.id ASC

        LIMIT ?
        """, (
            limit,
        ))

        return await cursor.fetchall()

    # -----------------------------------------------------
    # APPROVE
    # -----------------------------------------------------

    async def approve_transaction(
        self,
        transaction_id: int,
        admin_id: int
    ):

        transaction = await self.get_transaction(
            transaction_id
        )

        if not transaction:

            return "not_found"

        if transaction["status"] != "processing":

            return "already_processed"

        # ВАЖНО:
        #
        # Balance уже списан при создании заявки.
        #
        # Здесь только увеличиваем
        # показатель "Выплачено".
        await self.db.execute("""
        UPDATE users

        SET paid_out = paid_out + ?

        WHERE user_id = ?
        """, (
            transaction["amount"],
            transaction["user_id"]
        ))

        await self.db.execute("""
        UPDATE transactions

        SET

            status = 'approved',

            processed_at =
                CURRENT_TIMESTAMP,

            processed_by = ?

        WHERE id = ?
        """, (
            admin_id,
            transaction_id
        ))

        await self.db.commit()

        return "approved"

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------

    async def reject_transaction(
        self,
        transaction_id: int,
        admin_id: int
    ):

        transaction = await self.get_transaction(
            transaction_id
        )

        if not transaction:

            return "not_found"

        if transaction["status"] != "processing":

            return "already_processed"

        # При отказе возвращаем Stars
        # обратно пользователю.
        await self.db.execute("""
        UPDATE users

        SET balance = balance + ?

        WHERE user_id = ?
        """, (
            transaction["amount"],
            transaction["user_id"]
        ))

        await self.db.execute("""
        UPDATE transactions

        SET

            status = 'rejected',

            processed_at =
                CURRENT_TIMESTAMP,

            processed_by = ?

        WHERE id = ?
        """, (
            admin_id,
            transaction_id
        ))

        await self.db.commit()

        return "rejected"

    # -----------------------------------------------------
    # STATS
    # -----------------------------------------------------

    async def get_stats(self):

        cursor = await self.db.execute("""
        SELECT

            COUNT(*) AS users_count,

            COALESCE(
                SUM(balance),
                0
            ) AS total_balance,

            COALESCE(
                SUM(paid_out),
                0
            ) AS total_paid

        FROM users
        """)

        stats = await cursor.fetchone()

        cursor = await self.db.execute("""
        SELECT COUNT(*)

        FROM referrals

        WHERE is_active = 1

        AND counted = 1
        """)

        active_refs = (
            await cursor.fetchone()
        )[0]

        cursor = await self.db.execute("""
        SELECT COUNT(*)

        FROM transactions
        """)

        total_transactions = (
            await cursor.fetchone()
        )[0]

        return {
            "users": stats["users_count"],
            "balance": stats["total_balance"],
            "paid": stats["total_paid"],
            "active_refs": active_refs,
            "transactions": total_transactions
        }


# =========================================================
# GLOBAL INIT
# =========================================================

db = Database(DB_NAME)

bot = Bot(
    token=BOT_TOKEN,

    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()

router = Router()

dp.include_router(router)


# =========================================================
# ПРОВЕРКА ПОДПИСКИ
# =========================================================

async def is_subscribed(
    user_id: int
) -> bool:

    try:

        member = await bot.get_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id
        )

        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.RESTRICTED
        }

    except Exception as error:

        print(
            f"Subscription check error: {error}"
        )

        return False


# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🔗 Моя ссылка",
                    callback_data="my_link"
                )
            ],

            [
                InlineKeyboardButton(
                    text="👥 Рефералы",
                    callback_data="refs"
                ),

                InlineKeyboardButton(
                    text="💳 Транзакции",
                    callback_data="transactions"
                )
            ],

            [
                InlineKeyboardButton(
                    text="💸 Вывести Stars",
                    callback_data="withdraw"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🔄 Проверить подписку",
                    callback_data="check_sub"
                )
            ]
        ]
    )


def back_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_profile"
                )
            ]

        ]
    )


def admin_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin_stats"
                )
            ],

            [
                InlineKeyboardButton(
                    text="💳 Заявки",
                    callback_data="admin_transactions"
                )
            ],

            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_profile"
                )
            ]
        ]
    )


def status_text(status: str):

    if status == "processing":

        return (
            f"{PENDING} "
            f"<b>В обработке</b>"
        )

    if status == "approved":

        return (
            f"{APPROVED} "
            f"<b>Одобрено</b>"
        )

    if status == "rejected":

        return (
            f"{REJECTED} "
            f"<b>Отклонено</b>"
        )
# =========================================================
# ТРАНЗАКЦИИ
# =========================================================

@router.callback_query(F.data == "transactions")
async def transactions_handler(callback: CallbackQuery):

    user_id = callback.from_user.id

    transactions = await db.get_transactions(
        user_id,
        limit=50
    )

    text = (
        f"{TRANSACTIONS} "
        f"<b>ВАШИ ТРАНЗАКЦИИ</b>\n\n"
    )

    if not transactions:

        text += "У вас пока нет заявок."

    else:

        for tr in transactions:

            text += (
                f"🧾 <b>#{tr['id']}</b>\n"
                f"{STAR} Сумма: "
                f"<b>{tr['amount']} ⭐</b>\n"
                f"{status_text(tr['status'])}\n"
                f"📅 {tr['created_at']}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# СОЗДАНИЕ ЗАЯВКИ НА ВЫВОД
# =========================================================

@router.callback_query(F.data == "withdraw")
async def withdraw_handler(callback: CallbackQuery):

    user_id = callback.from_user.id

    user = await db.get_user(
        user_id
    )

    if not user:

        await callback.answer(
            "❌ Профиль не найден.",
            show_alert=True
        )

        return

    # -----------------------------------------------------
    # Проверяем минимальный баланс
    # -----------------------------------------------------

    if user["balance"] < MIN_WITHDRAW:

        await callback.answer(
            f"❌ Минимальный вывод — "
            f"{MIN_WITHDRAW} ⭐",
            show_alert=True
        )

        return

    # -----------------------------------------------------
    # Проверяем незакрытую заявку
    # -----------------------------------------------------

    transactions = await db.get_transactions(
        user_id,
        limit=100
    )

    for tr in transactions:

        if tr["status"] == "processing":

            await callback.answer(
                "🟡 У вас уже есть заявка "
                "в обработке.",
                show_alert=True
            )

            return

    # -----------------------------------------------------
    # Выводим весь доступный баланс
    # -----------------------------------------------------

    amount = user["balance"]

    transaction_id = (
        await db.create_transaction(
            user_id,
            amount
        )
    )

    if transaction_id is None:

        await callback.answer(
            "❌ Не удалось создать заявку.",
            show_alert=True
        )

        return

    # -----------------------------------------------------
    # Уведомление пользователю
    # -----------------------------------------------------

    await callback.message.edit_text(

        f"{PENDING} "
        f"<b>ЗАЯВКА СОЗДАНА</b>\n\n"

        f"🧾 Номер: "
        f"<b>#{transaction_id}</b>\n"

        f"{STAR} Сумма: "
        f"<b>{amount} ⭐</b>\n\n"

        f"{INFO} Статус: "
        f"{PENDING} <b>В обработке</b>\n\n"

        "Баланс уже зарезервирован "
        "для этой заявки."
        ,

        reply_markup=back_keyboard()
    )

    await callback.answer(
        "✅ Заявка отправлена."
    )

    # -----------------------------------------------------
    # Уведомление администраторам
    # -----------------------------------------------------

    username = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else "без username"
    )

    admin_text = (

        f"{PENDING} "
        f"<b>НОВАЯ ЗАЯВКА НА ВЫВОД</b>\n\n"

        f"🧾 Заявка: "
        f"<b>#{transaction_id}</b>\n"

        f"👤 Пользователь: "
        f"<b>{callback.from_user.full_name}</b>\n"

        f"🔗 Username: "
        f"<b>{username}</b>\n"

        f"🆔 ID: "
        f"<code>{user_id}</code>\n\n"

        f"{STAR} Сумма: "
        f"<b>{amount} ⭐</b>"
    )

    admin_buttons = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🟢 Одобрить",
                    callback_data=(
                        f"approve:{transaction_id}"
                    )
                ),

                InlineKeyboardButton(
                    text="🔴 Отклонить",
                    callback_data=(
                        f"reject:{transaction_id}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    text="💳 Открыть заявку",
                    callback_data=(
                        f"admin_tx:{transaction_id}"
                    )
                )
            ]

        ]
    )

    for admin_id in ADMIN_IDS:

        try:

            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=admin_buttons
            )

        except Exception as error:

            print(
                f"Admin notification error: {error}"
            )


# =========================================================
# АДМИН: ПРОВЕРКА ПРАВ
# =========================================================

def is_admin(user_id: int) -> bool:

    return user_id in ADMIN_IDS


# =========================================================
# АДМИН-ПАНЕЛЬ
# =========================================================

@router.message(F.text == "/admin")
async def admin_handler(message: Message):

    if not is_admin(
        message.from_user.id
    ):

        await message.answer(
            "❌ Доступ запрещён."
        )

        return

    await message.answer(

        f"{CROWN} "
        f"<b>АДМИН-ПАНЕЛЬ</b>\n\n"

        f"{INFO} Выберите раздел:",

        reply_markup=admin_keyboard()
    )


# =========================================================
# АДМИН: СТАТИСТИКА
# =========================================================

@router.callback_query(
    F.data == "admin_stats"
)
async def admin_stats_handler(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Нет доступа.",
            show_alert=True
        )

        return

    stats = await db.get_stats()

    text = (

        f"{STATS} "
        f"<b>СТАТИСТИКА БОТА</b>\n\n"

        f"👤 Пользователей: "
        f"<b>{stats['users']}</b>\n"

        f"{REFERRALS} Активных рефералов: "
        f"<b>{stats['active_refs']}</b>\n"

        f"{BALANCE} Балансов пользователей: "
        f"<b>{stats['balance']} ⭐</b>\n"

        f"{PAID} Выплачено: "
        f"<b>{stats['paid']} ⭐</b>\n"

        f"{TRANSACTIONS} Всего заявок: "
        f"<b>{stats['transactions']}</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# =========================================================
# АДМИН: СПИСОК ЗАЯВОК
# =========================================================

@router.callback_query(
    F.data == "admin_transactions"
)
async def admin_transactions_handler(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Нет доступа.",
            show_alert=True
        )

        return

    transactions = (
        await db.get_processing_transactions(
            limit=50
        )
    )

    text = (
        f"{TRANSACTIONS} "
        f"<b>ЗАЯВКИ В ОБРАБОТКЕ</b>\n\n"
    )

    buttons = []

    if not transactions:

        text += (
            f"{CHECK} "
            "Новых заявок нет."
        )

    else:

        for tr in transactions:

            username = (
                f"@{tr['username']}"
                if tr["username"]
                else tr["full_name"]
            )

            text += (
                f"🧾 <b>#{tr['id']}</b> — "
                f"{username}\n"
                f"{STAR} "
                f"<b>{tr['amount']} ⭐</b>\n\n"
            )

            buttons.append([

                InlineKeyboardButton(
                    text=(
                        f"🧾 #{tr['id']} — "
                        f"{tr['amount']} ⭐"
                    ),
                    callback_data=(
                        f"admin_tx:{tr['id']}"
                    )
                )

            ])

    buttons.append([

        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_admin"
        )

    ])

    await callback.message.edit_text(

        text,

        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# =========================================================
# АДМИН: ОТКРЫТЬ КОНКРЕТНУЮ ЗАЯВКУ
# =========================================================

@router.callback_query(
    F.data.startswith("admin_tx:")
)
async def admin_transaction_handler(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Нет доступа.",
            show_alert=True
        )

        return

    try:

        transaction_id = int(
            callback.data.split(":")[1]
        )

    except (ValueError, IndexError):

        await callback.answer(
            "❌ Неверный номер заявки.",
            show_alert=True
        )

        return

    tr = await db.get_transaction(
        transaction_id
    )

    if not tr:

        await callback.answer(
            "❌ Заявка не найдена.",
            show_alert=True
        )

        return

    username = (
        f"@{tr['username']}"
        if tr["username"]
        else "без username"
    )

    text = (

        f"{TRANSACTIONS} "
        f"<b>ЗАЯВКА #{tr['id']}</b>\n\n"

        f"👤 Пользователь: "
        f"<b>{tr['full_name']}</b>\n"

        f"🔗 Username: "
        f"<b>{username}</b>\n"

        f"🆔 ID: "
        f"<code>{tr['user_id']}</code>\n\n"

        f"{STAR} Сумма: "
        f"<b>{tr['amount']} ⭐</b>\n"

        f"📅 Создана: "
        f"<b>{tr['created_at']}</b>\n\n"

        f"Статус: "
        f"{status_text(tr['status'])}"
    )

    buttons = []

    if tr["status"] == "processing":

        buttons.append([

            InlineKeyboardButton(
                text="🟢 Одобрить",
                callback_data=(
                    f"approve:{tr['id']}"
                )
            ),

            InlineKeyboardButton(
                text="🔴 Отклонить",
                callback_data=(
                    f"reject:{tr['id']}"
                )
            )

        ])

    buttons.append([

        InlineKeyboardButton(
            text="⬅️ К заявкам",
            callback_data="admin_transactions"
        )

    ])

    await callback.message.edit_text(

        text,

        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# =========================================================
# АДМИН: ОДОБРЕНИЕ
# =========================================================

@router.callback_query(
    F.data.startswith("approve:")
)
async def approve_handler(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Нет доступа.",
            show_alert=True
        )

        return

    try:

        transaction_id = int(
            callback.data.split(":")[1]
        )

    except (ValueError, IndexError):

        await callback.answer(
            "❌ Ошибка номера заявки.",
            show_alert=True
        )

        return

    tr = await db.get_transaction(
        transaction_id
    )

    if not tr:

        await callback.answer(
            "❌ Заявка не найдена.",
            show_alert=True
        )

        return

    result = await db.approve_transaction(
        transaction_id,
        callback.from_user.id
    )

    if result == "already_processed":

        await callback.answer(
            "⚠️ Заявка уже обработана.",
            show_alert=True
        )

        return

    if result != "approved":

        await callback.answer(
            "❌ Не удалось одобрить заявку.",
            show_alert=True
        )

        return

    # -----------------------------------------------------
    # Обновляем сообщение администратора
    # -----------------------------------------------------

    await callback.message.edit_text(

        f"{APPROVED} "
        f"<b>ЗАЯВКА #{transaction_id} ОДОБРЕНА</b>\n\n"

        f"👤 Пользователь: "
        f"<b>{tr['full_name']}</b>\n"

        f"{STAR} Сумма: "
        f"<b>{tr['amount']} ⭐</b>\n\n"

        f"👮 Одобрил: "
        f"<code>{callback.from_user.id}</code>"
    )

    # -----------------------------------------------------
    # Уведомляем пользователя
    # -----------------------------------------------------

    try:

        await bot.send_message(

            tr["user_id"],

            f"{APPROVED} "
            f"<b>ВЫПЛАТА ОДОБРЕНА</b>\n\n"

            f"🧾 Заявка: "
            f"<b>#{transaction_id}</b>\n"

            f"{STAR} Сумма: "
            f"<b>{tr['amount']} ⭐</b>\n\n"

            "Выплата подтверждена "
            "администратором."
        )

    except Exception as error:

        print(
            f"User notification error: {error}"
        )

    await callback.answer(
        "✅ Выплата одобрена."
    )


# =========================================================
# АДМИН: ОТКЛОНЕНИЕ
# =========================================================

@router.callback_query(
    F.data.startswith("reject:")
)
async def reject_handler(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Нет доступа.",
            show_alert=True
        )

        return

    try:

        transaction_id = int(
            callback.data.split(":")[1]
        )

    except (ValueError, IndexError):

        await callback.answer(
            "❌ Ошибка номера заявки.",
            show_alert=True
        )

        return

    tr = await db.get_transaction(
        transaction_id
    )

    if not tr:

        await callback.answer(
            "❌ Заявка не найдена.",
            show_alert=True
        )

        return

    result = await db.reject_transaction(
        transaction_id,
        callback.from_user.id
    )

    if result == "already_processed":

        await callback.answer(
            "⚠️ Заявка уже обработана.",
            show_alert=True
        )

        return

    if result != "rejected":

        await callback.answer(
            "❌ Не удалось отклонить заявку.",
            show_alert=True
        )

        return

    # -----------------------------------------------------
    # Админское сообщение
    # -----------------------------------------------------

    await callback.message.edit_text(

        f"{REJECTED} "
        f"<b>ЗАЯВКА #{transaction_id} ОТКЛОНЕНА</b>\n\n"

        f"👤 Пользователь: "
        f"<b>{tr['full_name']}</b>\n"

        f"{STAR} Сумма: "
        f"<b>{tr['amount']} ⭐</b>\n\n"

        f"{INFO} Средства возвращены "
        "на баланс пользователя."
    )

    # -----------------------------------------------------
    # Пользователю
    # -----------------------------------------------------

    try:

        await bot.send_message(

            tr["user_id"],

            f"{REJECTED} "
            f"<b>ВЫПЛАТА ОТКЛОНЕНА</b>\n\n"

            f"🧾 Заявка: "
            f"<b>#{transaction_id}</b>\n"

            f"{STAR} Сумма: "
            f"<b>{tr['amount']} ⭐</b>\n\n"

            f"{INFO} Средства возвращены "
            "на ваш баланс."
        )

    except Exception as error:

        print(
            f"User notification error: {error}"
        )

    await callback.answer(
        "❌ Заявка отклонена."
    )


# =========================================================
# НАЗАД В ПРОФИЛЬ
# =========================================================

@router.callback_query(
    F.data == "back_profile"
)
async def back_profile_handler(
    callback: CallbackQuery
):

    await callback.message.edit_text(

        await profile_text(
            callback.from_user.id
        ),

        reply_markup=main_keyboard()
    )

    await callback.answer()


# =========================================================
# НАЗАД В АДМИНКУ
# =========================================================

@router.callback_query(
    F.data == "back_admin"
)
async def back_admin_handler(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Нет доступа.",
            show_alert=True
        )

        return

    await callback.message.edit_text(

        f"{CROWN} "
        f"<b>АДМИН-ПАНЕЛЬ</b>\n\n"

        f"{INFO} Выберите раздел:",

        reply_markup=admin_keyboard()
    )

    await callback.answer()


# =========================================================
# ОТСЛЕЖИВАНИЕ ВЫХОДА ИЗ КАНАЛА
# =========================================================

@router.chat_member()
async def channel_member_update(
    event: ChatMemberUpdated
):

    # Реагируем только на нужный канал
    if event.chat.id != CHANNEL_ID:

        return

    user_id = event.from_user.id

    new_status = event.new_chat_member.status

    # -----------------------------------------------------
    # Пользователь вышел / был удалён
    # -----------------------------------------------------

    left_statuses = {

        ChatMemberStatus.LEFT,

        ChatMemberStatus.KICKED
    }

    if new_status in left_statuses:

        changed = (
            await db.deactivate_referral(
                user_id
            )
        )

        if changed:

            ref = await db.get_referral(
                user_id
            )

            if ref:

                try:

                    await bot.send_message(

                        ref["referrer_id"],

                        f"{WARNING} "
                        f"<b>Реферал стал неактивным</b>\n\n"

                        f"Один пользователь "
                        f"вышел из обязательного канала.\n\n"

                        f"{STAR} "
                        f"С баланса снято "
                        f"<b>{REWARD_PER_REF} ⭐</b>."
                    )

                except Exception as error:

                    print(
                        f"Referrer notification error: {error}"
                    )


# =========================================================
# ЗАПУСК
# =========================================================

async def main():

    print("=" * 55)

    print(
        "🚀 REFERRAL STARS BOT"
    )

    print("=" * 55)

    print(
        f"Reward: {REWARD_PER_REF} Stars"
    )

    print(
        f"Minimum withdraw: {MIN_WITHDRAW} Stars"
    )

    print(
        f"Channel ID: {CHANNEL_ID}"
    )

    print("=" * 55)

    await db.connect()

    try:

        # Удаляем старые webhook,
        # чтобы polling нормально запускался.
        await bot.delete_webhook(
            drop_pending_updates=True
        )

        print(
            "🟢 Бот запущен."
        )

        await dp.start_polling(
            bot
        )

    finally:

        await db.close()

        await bot.session.close()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "\n🛑 Бот остановлен."
        )

    except Exception as error:

        print(
            "\n❌ КРИТИЧЕСКАЯ ОШИБКА:"
        )

        print(
            repr(error)
        )