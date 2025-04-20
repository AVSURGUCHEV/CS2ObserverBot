import os
import re
import json
import uuid
from datetime import datetime, timezone
from aiogram import types, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram import Router
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
CHANNEL_ID = -1002559015377
VOTES_FILE = "votes.json"
REPORTS_FILE = "reports.json"


def load_votes():
    if not os.path.exists(VOTES_FILE):
        return {}
    with open(VOTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_votes(votes):
    with open(VOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(votes, f, indent=2, ensure_ascii=False)


vote_counts = load_votes()

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
form_router = Router()
dp.include_router(form_router)


class FSMReport(StatesGroup):
    waiting_for_link = State()
    waiting_for_reason = State()
    waiting_for_comment = State()
    waiting_for_video = State()


class ReportForm(StatesGroup):
    profile_link = State()
    reason = State()
    comment = State()
    video = State()


reason_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Aim", callback_data="Aim")],
        [InlineKeyboardButton(text="🧱 WallHack", callback_data="WallHack")],
        [InlineKeyboardButton(text="🎯+🧱 Aim+WH", callback_data="Aim+WH")],
        [InlineKeyboardButton(text="🤔 Другая причина", callback_data="Other")],
    ]
)

main_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📩 Отправить репорт", callback_data="report")],
        [InlineKeyboardButton(text="📹 Как записать видео?", callback_data="how_to_record")],
    ]
)

reply_main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📩 Отправить репорт")],
        [KeyboardButton(text="📹 Как записать видео?")],
    ],
    resize_keyboard=True
)

channel_button = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚨 Подать жалобу", url=f"https://t.me/{os.getenv('BOT_USERNAME')}")]
    ]
)


def load_reports():
    if not os.path.exists(REPORTS_FILE):
        return []
    with open(REPORTS_FILE, "r", encoding="utf-8") as f:
        reports = json.load(f)
        for r in reports:
            if "uuid" in r.get("data", {}):
                del r["data"]["uuid"]
            if "timestamp" in r.get("data", {}):
                del r["data"]["timestamp"]
        return reports


def save_report(report):
    reports = load_reports()
    reports.append(report)
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)


async def is_admin(message: Message) -> bool:
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Эта команда доступна только администратору.")
        return False
    return True


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в CS2ObserverBot!\n\n"
        "📩 Нажми кнопку ниже, чтобы подать репорт на подозрительного игрока, "
        "или узнай, как записывать видео через Steam:",
        reply_markup=reply_main_keyboard
    )

@dp.message(F.text.lower().in_(["начать", "старт", "report", "репорт", "📩 отправить репорт", "📹 как записать видео?"]))
async def alt_start(message: Message):
    text = message.text.lower()
    if "видео" in text:
        await how_to_record(message)
    else:
        await start_report_fake(message)


async def start_report_fake(message: Message):
    callback_query = types.CallbackQuery(
        id="fake",
        from_user=message.from_user,
        message=message
    )
    await start_report(callback_query, state=dp.fsm.storage)


@dp.message(F.text.lower() == "начать")
async def alt_start(message: Message):
    await cmd_start(message)


@dp.callback_query(F.data == "how_to_record")
async def how_to_record(callback_query):
    if isinstance(callback_query, Message):
        message = callback_query
    else:
        message = callback_query.message

    await message.answer(
        "<b>Как записывать видео через Steam:</b>\n\n"
        "1. Зайди в Steam → Настройки → В игре → Game Recording\n"
        "2. Включи запись\n"
        "3. Запусти CS2 и начни играть. Видео будет сохраняться автоматически\n\n"
        "🔗 Подробнее: https://store.steampowered.com/gamerecording",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "report")
async def start_report(callback_query: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()

    if user_data.get("in_progress"):
        await callback_query.message.answer(
            "⚠️ У тебя уже есть незавершённый репорт. Хочешь продолжить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Продолжить", callback_data="continue_report")],
                    [InlineKeyboardButton(text="❌ Начать заново", callback_data="restart_report")],
                ]
            )
        )
        return

    await callback_query.message.answer("🔗 Отправь ссылку на профиль Steam:")
    await state.update_data(in_progress=True)
    await state.set_state(ReportForm.profile_link)


async def start_report_fake(message: Message):
    callback_query = types.CallbackQuery(
        id="fake",
        from_user=message.from_user,
        message=message
    )
    await start_report(callback_query, state=dp.fsm.storage)


@dp.callback_query(F.data == "continue_report")
async def continue_report(callback_query: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    if "reason" not in user_data:
        await callback_query.message.answer("Выбери причину подозрения:", reply_markup=reason_keyboard)
        await state.set_state(ReportForm.reason)
    elif "comment" not in user_data:
        await callback_query.message.answer("📝 Напиши комментарий к подозрениям:")
        await state.set_state(ReportForm.comment)
    elif "video" not in user_data:
        await callback_query.message.answer("📹 Прикрепи видео (до 50 МБ, только .mp4):")
        await state.set_state(ReportForm.video)
    else:
        await callback_query.message.answer("✅ Репорт уже заполнен.")
        await state.clear()


@dp.callback_query(F.data == "restart_report")
async def restart_report(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.answer("🔄 Начнём сначала.\n🔗 Отправь ссылку на профиль Steam:")
    await state.update_data(in_progress=True)
    await state.set_state(ReportForm.profile_link)


@form_router.message(ReportForm.profile_link)
async def process_profile_link(message: Message, state: FSMContext):
    link = message.text.strip().replace('\u200b', '').replace('\xa0', '').replace(' ', '')
    if link.endswith("/"):
        link = link[:-1]

    pattern = r"^https://steamcommunity\\.com/profiles/(\d{17})$"
    match = re.match(pattern, link)
    if not match:
        await message.answer(
            "⚠️ Пожалуйста, отправь корректную ссылку на профиль Steam, например:\n"
            "`https://steamcommunity.com/profiles/76561198000000000`",
            parse_mode="Markdown"
        )
        return

    steam_id = match.group(1)
    profile_link = f"https://steamcommunity.com/profiles/{steam_id}"

    existing_reports = load_reports()
    for r in existing_reports:
        if r["profile_link"] == profile_link:
            msg_id = r.get("channel_msg_id")
            buttons = [[InlineKeyboardButton(text="📝 Продолжить оформление", callback_data="continue_report")]]
            if msg_id:
                buttons.insert(0, [InlineKeyboardButton(text="📄 Посмотреть репорт", url=f"https://t.me/CS2Observers/{msg_id}")])
            reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(
                f"⚠️ На этот профиль уже существует репорт. Хотите продолжить оформление нового?",
                reply_markup=reply_markup
            )
            await state.update_data(profile_link=profile_link, steam_id=steam_id, duplicate=True)
            return

    await state.update_data(profile_link=profile_link, steam_id=steam_id)
    await message.answer("Выбери причину подозрения:", reply_markup=reason_keyboard)
    await state.set_state(ReportForm.reason)

async def send_video_to_channel(video_path, profile_link, reason, comment, uuid_str, message):
    caption = f"<b>🚨 Новый репорт</b>\n\n"
    caption += f"<b>🔗 Профиль:</b> {profile_link}\n"
    caption += f"<b>🎯 Причина:</b> {reason}\n"
    caption += f"<b>💬 Комментарий:</b> {comment or '—'}\n"
    caption += f"<b>🕒 Отправлено:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    caption += f"<b>📄 UUID:</b> {uuid_str}"

    video = FSInputFile(video_path)
    msg = await bot.send_video(
        chat_id=CHANNEL_ID,
        video=video,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Виновен", callback_data=f"vote:{uuid_str}:guilty"),
                    InlineKeyboardButton(text="❌ Не виновен", callback_data=f"vote:{uuid_str}:not_guilty")
                ]
            ]
        )
    )

    await bot.send_message(
        OWNER_ID,
        f"📩 Новый репорт от @{message.from_user.username or message.from_user.full_name}:\n{profile_link}",
    )

    return msg.message_id

# Проверка VAC-статуса перед отправкой репорта
async def check_vac_before_report(steam_profile_url: str):
    steam_id = steam_profile_url.split('/')[-1]  # Извлекаем Steam ID из URL
    vac_banned = check_vac_ban(steam_id)
    
    if vac_banned:
        # Если игрок имеет VAC-бан, уведомляем модератора
        return "Игрок имеет VAC-бан!"
    else:
        return "Игрок не имеет VAC-бан."



@dp.callback_query(F.data.in_(["Aim", "WallHack", "Aim+WH", "Other"]))
async def process_reason(callback_query, state: FSMContext):
    await state.update_data(reason=callback_query.data)
    await callback_query.message.answer("✍️ Добавь короткий комментарий:")
    await state.set_state(ReportForm.comment)

@form_router.message(ReportForm.comment)
async def process_comment(message: Message, state: FSMContext):
    await state.update_data(comment=message.text)
    await message.answer("📎 Загрузите видео (до 50 МБ, формат mp4):")
    await state.set_state(ReportForm.video)

@form_router.message(ReportForm.video)
async def process_video(message: Message, state: FSMContext):
    if (
        not message.video or 
        message.video.file_size > 50 * 1024 * 1024 or 
        message.video.mime_type not in ["video/mp4", "video/x-m4v"]
    ):
        await message.answer("⚠️ Пожалуйста, прикрепи видео в формате .mp4 до 50 МБ.")
        return

    data = await state.get_data()
    report_id = str(uuid.uuid4())

    report = {
        "id": report_id,
        "profile_link": data['profile_link'],
        "reason": data['reason'],
        "comment": data['comment'],
        "video_id": message.video.file_id,
        "video_path": None,
        "user_id": message.from_user.id,
        "timestamp": datetime.now(timezone.utc).timestamp(),
        "status": "pending"
    }

    save_report(report)

    # Здесь мы жестко заменяем никнейм на "Профиль подозреваемого"
    nickname = "Профиль подозреваемого"  # заменено на фиксированный текст
    profile_link = data["profile_link"]
    
    # Формируем сообщение для канала
    channel_message = f"Репорт на игрока: [{nickname}]({profile_link})\nПричина: {data['reason']}\nКомментарий: {data['comment']}"

    # Отправляем сообщение в канал
    chat_id = '@CS2Observers'  # Используй свой chat_id
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    await bot.send_message(chat_id=chat_id, text=channel_message, parse_mode="Markdown")

    await message.answer("✅ Репорт отправлен на модерацию.")
    await send_moderation_request(report, message.from_user.username)
    await state.clear()


async def send_moderation_request(report, username=None):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[ 
            InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{report['id']}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{report['id']}")
        ]]
    )

    caption = (
        f"🆕 *Новый репорт* от @{username or 'пользователя'}\n\n"
        f"*👤 Профиль:* [ссылка]({report['profile_link']})\n"
        f"*🚩 Причина:* {report['reason']}\n"
        f"*💬 Комментарий:* {report['comment'] or '—'}"
    )

    # Проверка на наличие video_id
    video_id = report.get("video_id")
    if not video_id:
        await bot.send_message(OWNER_ID, "❌ Видео не найдено в репорте.")
        return

    message = await bot.send_video(
        chat_id=OWNER_ID,
        video=video_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    # Сохраняем message_id для дальнейшего голосования
    vote_counts[message.message_id] = {
        "yes": 0,
        "no": 0,
        "report_id": report['id'],
        "profile_link": report["profile_link"],
        "user_votes": {}  # user_id -> "yes" / "no"
    }

@router.callback_query(lambda c: c.data.startswith("approve_"))
async def approve_report(callback_query: CallbackQuery):
    report_id = callback_query.data.split("_")[1]

    # Загрузка репортов из файла
    with open(REPORTS_FILE, "r", encoding="utf-8") as f:
        reports = json.load(f)

    report = next((r for r in reports if r.get("id") == report_id), None)
    if not report:
        await callback_query.message.answer("❌ Репорт не найден.")
        return

    # Обновляем статус репорта на "approved"
    report["status"] = "approved"

    # Сохраняем изменения в репортах
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)

    # Уведомляем пользователя о принятии репорта
    await bot.send_message(
        report["user_id"],
        f"✅ Репорт на {report['profile_link']} принят модерацией!"
    )

    # Форматируем сообщение с подробностями
    caption = (
        f"👤 [Профиль подозреваемого]({report['profile_link']})\n"
        f"🕵️ Причина: *{report['reason']}*\n"
        f"💬 Комментарий: {report['comment'] or '–'}\n"
        f"📅 Время: {datetime.fromtimestamp(report['timestamp']).strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Голосуйте ниже ⬇️"
    )

    # Генерация клавиатуры с голосованием
    keyboard = InlineKeyboardMarkup(inline_keyboard=[ 
        [
            InlineKeyboardButton(text=f"Виновен ({vote_counts.get(report['channel_msg_id'], {}).get('yes', 0)})", callback_data=f"vote_yes_{report_id}"),
            InlineKeyboardButton(text=f"Не виновен ({vote_counts.get(report['channel_msg_id'], {}).get('no', 0)})", callback_data=f"vote_no_{report_id}")
        ],
        [
            InlineKeyboardButton(text="🔗 Открыть профиль", url=report["profile_link"])
        ]
    ])

    # Отправка видео с голосованием в канал
    video_id = report.get("video_id")
    if not video_id:
        await callback_query.message.answer("❌ Видео не найдено.")
        return

    # Отправляем репорт с видео в канал
    message = await bot.send_video(
        chat_id=CHANNEL_ID,
        video=video_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    # Сохраняем ID сообщения для дальнейшего использования
    report["channel_msg_id"] = message.message_id
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)

    # Обновляем голосование
    vote_counts[message.message_id] = {
        "yes": 0,
        "no": 0,
        "report_id": report_id,
        "profile_link": report["profile_link"],
        "user_votes": {}
    }

    # Подтверждаем принятие репорта
    await callback_query.message.answer("✅ Репорт опубликован в канале.")




@dp.callback_query(F.data.startswith("reject_"))
async def reject_report(callback_query: types.CallbackQuery):
    await callback_query.answer("Репорт отклонён.")

    report_id = callback_query.data.split("_")[1]
    reports = load_reports()
    report = next((r for r in reports if r["id"] == report_id), None)

    if not report:
        await callback_query.message.answer("⚠️ Репорт не найден.")
        return

    await callback_query.message.answer(
        f"🚫 Репорт на <a href=\"{report['profile_link']}\">{report['profile_link']}</a> был отклонён.",
        parse_mode="HTML"
    )

@form_router.callback_query(F.data.startswith(("vote_yes_", "vote_no_")))
async def handle_vote(callback_query: types.CallbackQuery):
    if not callback_query.message:
        await callback_query.answer("⚠️ Сообщение не найдено.", show_alert=True)
        return

    message_id = callback_query.message.message_id  # Извлекаем message_id
    user_id = callback_query.from_user.id
    callback_data = callback_query.data

    # Определяем тип голоса
    if callback_data.startswith("vote_yes_"):
        vote_type = "yes"
    elif callback_data.startswith("vote_no_"):
        vote_type = "no"
    else:
        await callback_query.answer("⚠️ Некорректные данные.", show_alert=True)
        return

    if message_id not in vote_counts:
        await callback_query.answer("⚠️ Голосование не найдено.", show_alert=True)
        return

    vote_data = vote_counts[message_id]
    previous_vote = vote_data["user_votes"].get(user_id)

    # Если голос тот же — не даём голосовать повторно
    if previous_vote == vote_type:
        await callback_query.answer("⛔ Ты уже голосовал так.", show_alert=True)
        return

    # Если меняет голос — уменьшаем предыдущий
    if previous_vote:
        vote_data[previous_vote] -= 1

    vote_data[vote_type] += 1
    vote_data["user_votes"][user_id] = vote_type

    # Обновляем клавиатуру с новым количеством голосов
    yes = vote_data["yes"]
    no = vote_data["no"]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[ 
            InlineKeyboardButton(
                text=f"👍 Виновен ({yes})",
                callback_data=f"vote_yes_{vote_data['report_id']}"
            ),
            InlineKeyboardButton(
                text=f"👎 Не виновен ({no})",
                callback_data=f"vote_no_{vote_data['report_id']}"
            )
        ], [
            InlineKeyboardButton(
                text="🔗 Открыть профиль",
                url=vote_data["profile_link"]
            )
        ]]
    )

    try:
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await callback_query.answer("✅ Голос учтён.")
    except Exception as e:
        await callback_query.answer("❌ Не удалось обновить голосование.", show_alert=True)
        print(f"[handle_vote] Ошибка при обновлении голосования (message_id={message_id}, user_id={user_id}, data={callback_data}): {e}")



@dp.message(Command("pending_reports"))
async def pending_reports(message: Message):
    if not await is_admin(message): return
    reports = load_reports()
    count = sum(1 for r in reports if r["status"] == "pending")
    await message.answer(f"📋 На модерации сейчас: {count} репорт(ов)")

    
@dp.callback_query(lambda c: c.data and c.data.startswith("reject:"))
async def handle_reject(callback: types.CallbackQuery):
    profile_link = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        f"❌ Заявка на {profile_link} <b>отклонена</b>.",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("Заявка отклонена.")
CHANNEL_ID = -1002559015377  # замени на свой

async def publish_to_channel(report):
    await bot.send_message(
        CHANNEL_ID,
        f"⚠️ Новый репорт на подозрительного игрока:\n\n"
        f"🔗 <a href='{report['profile_link']}'>Профиль</a>\n"
        f"🚨 Причина: {report['reason']}\n"
        f"📝 Комментарий: {report['comment'] or '—'}\n"
        f"⏰ Время: {report['created_at']}",
        parse_mode="HTML"
    )
    await bot.send_video(CHANNEL_ID, video=report["video_id"])
  

if __name__ == "__main__":
    import asyncio

    async def main():
        print("Бот запускается...")
        bot = Bot(token=BOT_TOKEN)  # ← обязательно создать
        await dp.start_polling(bot)
        print("Бот запущен и ожидает команды...")

    asyncio.run(main())
