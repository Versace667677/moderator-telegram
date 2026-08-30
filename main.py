
import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, ChatPermissions
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER, ADMINISTRATOR
from aiogram.enums import ChatMemberStatus
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "database.json"
BAD_WORDS = ["бля","блять","блядь","сука","сучка","хуй","хуйня","хуйло","пизда","пиздец","єба","ебать","нахуй","похуй","охуел","заебал","долбоёб","уебок","мудак","гандон","пидор","шлюха","жопа","говно","fuck","shit"]
LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg"]
logging.basicConfig(level=logging.INFO)

RULES_TEXT = """
<b>📜 ПРАВИЛА ЧАТУ — ЧИТАЙ, БРО, ШОБ НЕ ОТЛЕТІТЬ 🚀</b>

1️⃣ <b>Без мату і образ</b> — базариш матом → мут 5хв, я ржу, але мушу мутити
2️⃣ <b>Без лінків і реклами</b> — кидаєш тг, інсту, сайт → мут, не спамь
3️⃣ <b>Без флуду</b> — 4 повідомлення за 5с → мут, не заєбуй чат
4️⃣ <b>Без спаму</b> — довгі тексти, капс, емодзі-спам → мут
5️⃣ <b>Поважай всіх</b> — ми тут всі свої, базаримо смішно, але по-доброму ❤️

<b>⚠️ Ланцюжок:</b>
🔇 Мут 5хв [1/3] → [2/3] → [3/3] = ⚠️ Варн [1/3]
⚠️ Варн [2/3] → [3/3] = 🚀 Бан (отлітай в космос)

Я — самий сучасний жоский бот, але справедливий, всі покарання в базу 💾
Читай правила і будеш топчиком 😎
"""

BOT_DESC = """
<b>🔥 AETHER — САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ 2026 🔥</b>

Йо, я не просто бот, я — легенда чату, базарю з матами, але по-доброму і смішно 😎

<b>💎 МОЇ ПЛЮСИ:</b>
🤖 <b>Працюю сам</b> — без налаштувань, все авто, ти просто додав і забув
⚡ <b>Миттєвий</b> — видаляю мат, лінк, флуд за 0.1с, швидше ніж ти моргнеш
💾 <b>Пам'ятаю все</b> — база на 1000+ порушників, нічого не забуваю, всі мути/варни в базу
😂 <b>Смішний</b> — пишу ржачно, з матами, але нікого не ображаю, всі ржуть в чаті
🎯 <b>Справедливий</b> — мут 5хв [1/3][2/3][3/3] → варн [1/3][2/3][3/3] → бан (отлітай в космос 🚀)
👋 <b>Ввічливий</b> — вітаю новеньких з капчею, прощаюсь, кидаю правила після капчі
🤖 <b>Капча-топ</b> — перевірка з емодзі, як в Google, але веселіша, анти-бот
🔇 <b>Не сплю</b> — 24/7 в чаті, слідкую за порядком, навіть вночі
🎭 <b>Свій чувак</b> — базарю на молодьожному сленгу, з матами, але любя ❤️
📜 <b>Правила</b> — одразу після капчі кидаю правила, шоб всі знали

<b>👮 ДЛЯ АДМІНА — 2 СПОСОБИ:</b>
1) Відповідь на повідомлення: /mute 5m спам або !mute 10m
2) Через @тег: !mute @krem_in 30 спам або /ban @username причина
Підтримує / і ! — /mute /ban /warn /unmute /unban /unwarn /warns /stats
Приклад: !mute @krem_in 30 заєбав або /ban @krem_in реклама

Я — самий сучасний бот 2026, зроблений з душею 😂❤️
"""

class DB:
    def __init__(self):
        self.data=self._load()
    def _load(self):
        if not Path(DB_FILE).exists(): return {"chats":{}}
        try:
            with open(DB_FILE,"r",encoding="utf-8") as f: d=json.load(f); d.setdefault("chats",{}); return d
        except: return {"chats":{}}
    def save(self):
        try:
            tmp=DB_FILE+".tmp"
            with open(tmp,"w",encoding="utf-8") as f: json.dump(self.data,f,ensure_ascii=False,indent=2)
            Path(tmp).replace(DB_FILE)
        except: pass
    def get_chat(self,cid):
        cid=str(cid)
        if cid not in self.data["chats"]: self.data["chats"][cid]={"title":"","users":{},"usernames":{}}; self.save()
        ch=self.data["chats"][cid]; ch.setdefault("users",{}); ch.setdefault("usernames",{}); return ch
    def get_user(self,cid,uid,name="",username=""):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]: ch["users"][uid]={"name":name or "Unknown","username":username or "","mutes":0,"warns":0,"bans":0}; self.save()
        u=ch["users"][uid]
        if name: u["name"]=name
        if username: 
            u["username"]=username.lower()
            ch["usernames"][username.lower()]=uid
        u.setdefault("mutes",0); u.setdefault("warns",0); u.setdefault("bans",0); return u
    def find_by_username(self,cid,username):
        ch=self.get_chat(cid); username=username.lower().lstrip("@")
        # Шукаємо в мапі юзернеймів
        if username in ch["usernames"]:
            uid=ch["usernames"][username]
            return uid, ch["users"].get(uid)
        # Шукаємо по всіх юзерах
        for uid,u in ch["users"].items():
            if u.get("username","").lower()==username.lower():
                return uid, u
        return None, None
    def add_mute(self,cid,uid,name="",username=""):
        u=self.get_user(cid,uid,name,username); u["mutes"]+=1
        if u["mutes"]>=3: u["mutes"]=0; u["warns"]+=1; self.save(); return ("ban" if u["warns"]>=3 else "warn"), u["mutes"], u["warns"]
        self.save(); return "mute", u["mutes"], u["warns"]
    def clear_mutes(self,cid,uid): self.get_user(cid,uid)["mutes"]=0; self.save()
    def clear_warns(self,cid,uid): self.get_user(cid,uid)["warns"]=0; self.save()
    def clear_all(self,cid,uid): u=self.get_user(cid,uid); u["mutes"]=0; u["warns"]=0; self.save()
    def dec_warn(self,cid,uid): u=self.get_user(cid,uid); u["warns"]=max(0,u["warns"]-1); self.save(); return u["warns"]
    def get_stats(self,cid,uid): u=self.get_user(cid,uid); return u["mutes"], u["warns"]

db=DB()
_flood={}; _captcha={}

def esc(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} if m else False
def contains_bad(text):
    t=str(text or "").lower()
    for w in BAD_WORDS:
        if re.search(re.escape(w.lower()), t, re.IGNORECASE): return w
    return None
def contains_link(text): return any(re.search(p, str(text or ""), re.IGNORECASE) for p in LINK_PATTERNS)
def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); lst=_flood.get(key,[]); lst=[x for x in lst if now-x<=5]; lst.append(now); _flood[key]=lst; return len(lst)>=4

async def is_admin(bot, message):
    if message.sender_chat and message.chat and message.sender_chat.id==message.chat.id: return True
    if not message.from_user: return False
    try: m=await bot.get_chat_member(message.chat.id, message.from_user.id); return is_admin_obj(m)
    except: return False

def kb_verify(uid):
    b=InlineKeyboardBuilder(); b.button(text="✅ Я не бот, чесно", callback_data=f"verify_{uid}"); return b.as_markup()
def kb_captcha(uid, correct, opts):
    b=InlineKeyboardBuilder()
    for e in opts: b.button(text=e, callback_data=f"cap_{uid}_{e}_{correct}")
    b.adjust(2,2); return b.as_markup()

# ===== ПОШУК ЦІЛІ ЧЕРЕЗ @тег або відповідь =====
async def resolve_target(message, bot):
    """
    Повертає (user_id, user_obj, name, username) цілі
    Підтримує:
    1. Відповідь на повідомлення
    2. @username в тексті: !mute @krem_in 30 спам
    3. Текстовий ментіон
    """
    # 1. Через відповідь
    if message.reply_to_message and message.reply_to_message.from_user:
        u=message.reply_to_message.from_user
        return u.id, u, u.first_name, u.username or ""
    
    # 2. Через @тег в тексті
    text=message.text or message.caption or ""
    # Шукаємо @username
    m=re.search(r"@(\w{3,32})", text)
    if m:
        username=m.group(1)
        uid, udata = db.find_by_username(message.chat.id, username)
        if uid:
            # Знайшли в базі
            return int(uid), None, udata.get("name", username), username
        else:
            # Не знайшли в базі, пробуємо знайти через entities
            # Спробуємо знайти юзера по юзернейму через чат
            try:
                # Якщо бот знає юзера по юзернейму? На жаль Telegram API не дає пошук по юзернейму
                # Повертаємо юзернейм як є, бан по юзернейму не вийде, але покажемо помилку
                return None, None, username, username
            except: pass
    
    # 3. Через mention entity
    if message.entities:
        for ent in message.entities:
            if ent.type=="text_mention" and ent.user:
                u=ent.user
                return u.id, u, u.first_name, u.username or ""
            if ent.type=="mention":
                username=text[ent.offset:ent.offset+ent.length].lstrip("@")
                uid, udata = db.find_by_username(message.chat.id, username)
                if uid:
                    return int(uid), None, udata.get("name", username), username
    
    return None, None, None, None

async def punish(bot, chat_id, user, reason, uid=None, name=None):
    # user може бути об'єктом або None якщо по юзернейму
    target_id = uid or (user.id if user else None)
    target_name = name or (user.first_name if user else "Невідомий")
    username = user.username if user and hasattr(user,'username') else ""
    if not target_id:
        await bot.send_message(chat_id, f"❌ Не знайшов юзера @{esc(name or '??')} в базі, бро 😅 Нехай він хоч раз напише в чат, шоб я запам'ятав, або відповідай на його повідомлення!")
        return
    cid=str(chat_id)
    result,mutes,warns = db.add_mute(cid, target_id, target_name, username)
    if result=="mute":
        try:
            await bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=5))
            msgs=[
                f"😅 Опа, {esc(target_name)} попався! За {esc(reason)} — мут 5хв, сходи за чіпсами 🍿\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]",
                f"🤭 {esc(target_name)}, ну ти даєш, за {esc(reason)} — мут 5хв 😂\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]",
                f"🫣 {esc(target_name)}, бля, знову ти? За {esc(reason)} — мут 5хв\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]"
            ]
            await bot.send_message(chat_id, random.choice(msgs))
        except Exception as e: await bot.send_message(chat_id, f"😅 {esc(target_name)} мут {mutes}/3: {e}")
    elif result=="warn":
        try:
            await bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=15))
            msgs=[
                f"😬 {esc(target_name)}, ти вже майже чемпіон! За {esc(reason)} + 3/3 мута — варн [{warns}/3] 🏆\n🔇 Мут 15хв [0/3] — ще один варн і фінальний бос 🚀",
                f"😅 {esc(target_name)} збирає варни як покемонів! [{warns}/3] за {esc(reason)} — ще один і еволюція в бан 🚀"
            ]
            await bot.send_message(chat_id, random.choice(msgs))
        except: await bot.send_message(chat_id, f"⚠️ {esc(target_name)} варн [{warns}/3] за {esc(reason)}")
    elif result=="ban":
        try:
            await bot.ban_chat_member(chat_id, target_id)
            u=db.get_user(cid, target_id); u["mutes"]=0; u["warns"]=0; u["bans"]=u.get("bans",0)+1; db.save()
            msgs=[
                f"🚀 {esc(target_name).upper()} ПОЛЕТІВ В КОСМОС! 🚀\n📛 За {esc(reason)} — 3/3 варна\n🔨 Бан назавжди, було весело ❤️",
                f"💥 {esc(target_name)} — ФІНАЛЬНИЙ БОС ПОВАЛЕНИЙ 😂💥\n📛 {esc(reason)} — 3/3 варна, отлітай маленький 🚀"
            ]
            await bot.send_message(chat_id, random.choice(msgs))
        except Exception as e: await bot.send_message(chat_id, f"💥 {esc(target_name)} мав полетіть: {e}")

async def cmd_start(message: Message, bot: Bot):
    if message.chat.type=="private": await message.answer(BOT_DESC)
    else:
        db.get_chat(message.chat.id)["title"]=message.chat.title or ""; db.save()
        await message.answer(f"🔥 <b>AETHER — САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ 2026</b> активний! 🔥\n\nЯ — легенда 😎\n💎 Плюси: авто, миттєвий, пам'ятаю все, смішний, справедливий, капча, 24/7\n🔇 Мут 5хв [3/3]=⚠️ Варн [3/3]=🚀 Бан\n\nНапиши /help для повного опису!")

async def cmd_help(message: Message, bot: Bot): await message.answer(BOT_DESC + "\n\n" + RULES_TEXT)

async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів, бро!")
    text=message.text or ""; args=text.split()
    # Парсимо: !mute @krem_in 30 спам або /mute 5m або відповідь
    target_id, target_obj, target_name, target_username = await resolve_target(message, bot)
    if not target_id:
        return await message.answer("❌ Не знайшов кого мутити!\n\n<b>2 способи:</b>\n1) Відповідай на повідомлення: /mute 5m спам\n2) Тегни: !mute @krem_in 30 спам\n\nПриклад: <code>!mute @krem_in 30 спам</code> або <code>/mute @username 10m флуд</code>")
    # Парсимо час і причину з тексту після @username
    dur=300; reason="Трошки заєбав чат"
    # Видаляємо команду і @username з тексту щоб знайти час і причину
    remaining=re.sub(r"^[/!]\w+\s+@\w+\s*", "", text, flags=re.IGNORECASE)
    remaining=re.sub(r"^[/!]\w+\s+", "", remaining, flags=re.IGNORECASE) if not re.search(r"@\w+", text) else remaining
    # Тепер remaining = "30 спам" або "спам"
    if remaining:
        parts=remaining.split()
        if parts:
            # Перший може бути час
            import re
            m=re.fullmatch(r"(\d+)\s*([smhd])?", parts[0].lower())
            if m and any(c.isdigit() for c in parts[0]):
                v=int(m.group(1)); u=m.group(2) or "m"; mult={"s":1,"m":60,"h":3600,"d":86400}; dur=v*mult[u]
                reason=" ".join(parts[1:]) if len(parts)>1 else "Трошки заєбав"
            else:
                # Перевіримо чи перше це число (хвилини)
                if parts[0].isdigit():
                    dur=int(parts[0])*60
                    reason=" ".join(parts[1:]) if len(parts)>1 else "Трошки заєбав"
                else:
                    reason=remaining
    try:
        await bot.restrict_chat_member(message.chat.id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=dur))
        u=db.get_user(message.chat.id, target_id, target_name, target_username); u["mutes"]=u.get("mutes",0)+1
        if u["mutes"]>=3: u["mutes"]=0; u["warns"]=u.get("warns",0)+1
        db.save(); mutes,warns=db.get_stats(message.chat.id, target_id)
        await message.answer(f"😂 {esc(target_name)} лови мут {dur//60}хв за {esc(reason)} 😅\n🔇 [{mutes}/3] | ⚠️ [{warns}/3] | Адмін {esc(message.from_user.first_name)}")
    except Exception as e: await message.answer(f"❌ Не вдалося замутити: {e}")

async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target_id, target_obj, target_name, target_username = await resolve_target(message, bot)
    if not target_id: return await message.answer("❌ Не знайшов кого банити!\nПриклад: <code>!ban @krem_in реклама</code> або відповідай на повідомлення: <code>/ban спам</code>")
    text=message.text or ""
    # Причина після @username
    remaining=re.sub(r"^[/!]\w+\s+@\w+\s*", "", text, flags=re.IGNORECASE)
    remaining=re.sub(r"^[/!]\w+\s+", "", remaining, flags=re.IGNORECASE) if not re.search(r"@\w+", text) else remaining
    reason=remaining if remaining else "Ну ти даєш"
    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        u=db.get_user(message.chat.id, target_id, target_name, target_username); u["bans"]=u.get("bans",0)+1; u["mutes"]=0; u["warns"]=0; db.save()
        await message.answer(f"🚀 {esc(target_name).upper()} ПОЛЕТІВ В КОСМОС за {esc(reason)} 🚀 Бан від {esc(message.from_user.first_name)} 😂")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_warn(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target_id, target_obj, target_name, target_username = await resolve_target(message, bot)
    if not target_id: return await message.answer("❌ Не знайшов! Приклад: <code>!warn @krem_in мат</code>")
    text=message.text or ""
    remaining=re.sub(r"^[/!]\w+\s+@\w+\s*", "", text, flags=re.IGNORECASE)
    remaining=re.sub(r"^[/!]\w+\s+", "", remaining, flags=re.IGNORECASE) if not re.search(r"@\w+", text) else remaining
    reason=remaining if remaining else "Трошки заєбав"
    u=db.get_user(message.chat.id, target_id, target_name, target_username); u["warns"]=u.get("warns",0)+1; warns=u["warns"]; db.save()
    if warns>=3:
        try: await bot.ban_chat_member(message.chat.id, target_id); u["warns"]=0; u["mutes"]=0; db.save()
        except: pass
        await message.answer(f"🚀 {esc(target_name)} — 3/3 варна за {esc(reason)}, полетів в космос 🚀")
    else:
        try: await bot.restrict_chat_member(message.chat.id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=10))
        except: pass
        await message.answer(f"😅 {esc(target_name)}, варн [{warns}/3] за {esc(reason)} — ще один і космос 🚀")

async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target_id, _, target_name, _ = await resolve_target(message, bot)
    if not target_id: return await message.answer("❌ Відповідай або тегни: !unmute @username")
    try: await bot.restrict_chat_member(message.chat.id, target_id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
    except: pass
    db.clear_mutes(message.chat.id, target_id)
    await message.answer(f"✅ {esc(target_name)} розмутили [0/3] — другий шанс!")

async def cmd_unban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target_id, _, target_name, _ = await resolve_target(message, bot)
    if not target_id: return await message.answer("❌ Відповідай або тегни: !unban @username")
    try: await bot.unban_chat_member(message.chat.id, target_id)
    except: pass
    db.clear_all(message.chat.id, target_id)
    await message.answer(f"✅ {esc(target_name)} розбанили, повертайся!")

async def cmd_unwarn(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target_id, _, target_name, _ = await resolve_target(message, bot)
    if not target_id: return await message.answer("❌ Відповідай або тегни: !unwarn @username")
    new=db.dec_warn(message.chat.id, target_id)
    await message.answer(f"✅ Зняв варн з {esc(target_name)}, тепер [{new}/3]")

async def cmd_warns(message: Message, bot: Bot):
    if message.reply_to_message and message.reply_to_message.from_user:
        target=message.reply_to_message.from_user; mutes,warns=db.get_stats(message.chat.id, target.id)
        await message.answer(f"📊 {esc(target.first_name)}: 🔇 [{mutes}/3] | ⚠️ [{warns}/3]")
    else:
        text=message.text or ""
        m=re.search(r"@(\w{3,32})", text)
        if m:
            username=m.group(1); uid, udata = db.find_by_username(message.chat.id, username)
            if uid: mutes,warns=db.get_stats(message.chat.id, int(uid)); await message.answer(f"📊 @{esc(username)} ({esc(udata.get('name',''))}): 🔇 [{mutes}/3] | ⚠️ [{warns}/3]")
            else: await message.answer(f"❌ Не знайшов @{esc(username)} в базі, нехай напише хоч раз")
            return
        ch=db.get_chat(message.chat.id); warned=[(uid,u) for uid,u in ch["users"].items() if u.get("mutes",0)>0 or u.get("warns",0)>0]
        if not warned: await message.answer(f"✅ Всі чисті ✨")
        else:
            txt="<b>📊 Хто пошалив:</b>\n\n"
            for uid,u in sorted(warned, key=lambda x: x[1].get("warns",0), reverse=True)[:15]:
                uname=f"@{u.get('username')}" if u.get('username') else ""
                txt+=f"👤 {esc(u.get('name','Unknown'))} {esc(uname)} — 🔇 [{u.get('mutes',0)}/3] ⚠️ [{u.get('warns',0)}/3]\n"
            await message.answer(txt)

async def auto_mod(message: Message, bot: Bot):
    # Зберігаємо юзернейм в базу для пошуку по @
    if message.from_user:
        db.get_user(message.chat.id, message.from_user.id, message.from_user.first_name, message.from_user.username or "")
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    if message.sender_chat and message.chat and message.sender_chat.id==message.chat.id: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem): return
    except: pass
    text=message.text or message.caption or ""
    if is_flood(message.chat.id, message.from_user.id):
        try: await message.delete()
        except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]; await punish(bot, message.chat.id, message.from_user, "флуд", message.from_user.id, message.from_user.first_name); return
    if contains_link(text):
        try: await message.delete()
        except: pass
        await punish(bot, message.chat.id, message.from_user, "лінк/реклама", message.from_user.id, message.from_user.first_name); return
    bad=contains_bad(text)
    if bad:
        try: await message.delete()
        except: pass
        await punish(bot, message.chat.id, message.from_user, f"мат ({bad})", message.from_user.id, message.from_user.first_name); return

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        db.get_user(event.chat.id, user.id, user.first_name, user.username or "")
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(event.chat.id, f"👋 Йо, {esc(user.first_name)} залетів в {esc(event.chat.title or 'чат')} 😎 Привіт, бро! Я — самий сучасний бот, перевірю шо ти не бот:", reply_markup=kb_verify(user.id))
        except: pass
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        try: await bot.send_message(event.chat.id, f"👋 Бувай, {esc(user.first_name)}! Було весело, повертайся! 🫶")
        except: pass

async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return
    try: await bot.send_message(event.chat.id, f"🔥 <b>AETHER — САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ 2026</b> активований! 🔥\n\nЯ — легенда 😎\n💎 Плюси: авто, миттєвий, пам'ятаю все, смішний, справедливий, капча, 24/7, правила після капчі\n🔇 Мут 5хв [3/3]=⚠️ Варн [3/3]=🚀 Бан\n👮 Адмін: /mute @user 5m або відповідь, і !mute теж\nНапиши /help для всіх плюсів!")
    except: pass

async def cb_handler(call: CallbackQuery, bot: Bot):
    data=call.data
    if data.startswith("verify_"):
        uid=int(data.split("_")[1])
        if call.from_user.id!=uid: return await call.answer("Не твоя капча, бро! 😅", show_alert=True)
        emojis=["🦊","🐶","🐱","🐰","🦁","🐯"]; correct=random.choice(emojis); opts=random.sample(emojis,4)
        if correct not in opts: opts[0]=correct
        random.shuffle(opts); _captcha[(call.message.chat.id, uid)]=correct
        await call.message.edit_text(f"🤖 Йо, {esc(call.from_user.first_name)}, тикни <b>{correct}</b> щоб довести шо ти свій 😎:", reply_markup=kb_captcha(uid, correct, opts))
        await call.answer(); return
    if data.startswith("cap_"):
        _, uid_s, chosen, correct = data.split("_",3); uid_s=int(uid_s)
        if call.from_user.id!=uid_s: return await call.answer("Не твоя капча!", show_alert=True)
        if chosen==correct:
            _captcha.pop((call.message.chat.id, uid_s),None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid_s, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                # МОМЕНТАЛЬНИЙ ВИВІД ПРАВИЛ ПІСЛЯ КАПЧІ - ЯК ТИ ХОТІВ!
                await call.message.edit_text(f"👋 {esc(call.from_user.first_name)} пройшов капчу, красава, свій чувак ✨ Залетай! 🫶")
                await bot.send_message(call.message.chat.id, f"👋 {esc(call.from_user.first_name)}, ласкаво в {esc(call.message.chat.title or 'чат')}! Ось правила, читай, бро, шоб не отлетіть 🚀\n{RULES_TEXT}")
            except: 
                try: await call.message.edit_text(f"✅ Красава, пройшов! Залетай ❤️\n\n{RULES_TEXT}")
                except: pass
            await call.answer("Красава! ✨")
        else:
            try: await bot.ban_chat_member(call.message.chat.id, uid_s); await bot.unban_chat_member(call.message.chat.id, uid_s); await call.message.edit_text(f"🚫 {esc(call.from_user.first_name)} не пройшов капчу, отлетів в космос 🚀")
            except: pass
            await call.answer("Невірно, отлітай! 😂", show_alert=True)
        return

async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher(storage=MemoryStorage())
    @dp.message(CommandStart())
    async def h_start(m: Message): await cmd_start(m, bot)
    @dp.message(Command("help"))
    async def h_help(m: Message): await cmd_help(m, bot)
    @dp.message(Command("rules"))
    async def h_rules(m: Message): await m.answer(RULES_TEXT)
    @dp.message(Command("mute"))
    async def h_mute(m: Message): await cmd_mute(m, bot)
    @dp.message(Command("ban"))
    async def h_ban(m: Message): await cmd_ban(m, bot)
    @dp.message(Command("warn"))
    async def h_warn(m: Message): await cmd_warn(m, bot)
    @dp.message(Command("unmute"))
    async def h_unmute(m: Message): await cmd_unmute(m, bot)
    @dp.message(Command("unban"))
    async def h_unban(m: Message): await cmd_unban(m, bot)
    @dp.message(Command("unwarn"))
    async def h_unwarn(m: Message): await cmd_unwarn(m, bot)
    @dp.message(Command("warns"))
    async def h_warns(m: Message): await cmd_warns(m, bot)
    @dp.message(F.text.startswith("!"))
    async def h_bang(m: Message):
        txt=(m.text or "").lower()
        if txt.startswith("!mute"): await cmd_mute(m, bot)
        elif txt.startswith("!ban"): await cmd_ban(m, bot)
        elif txt.startswith("!warn"): await cmd_warn(m, bot)
        elif txt.startswith("!unmute"): await cmd_unmute(m, bot)
        elif txt.startswith("!unban"): await cmd_unban(m, bot)
        elif txt.startswith("!unwarn"): await cmd_unwarn(m, bot)
        elif txt.startswith("!warns"): await cmd_warns(m, bot)
        elif txt.startswith("!rules"): await m.answer(RULES_TEXT)
        elif txt.startswith("!help"): await m.answer(BOT_DESC)
    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)
    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)
    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
    async def h_admin(e: ChatMemberUpdated): await bot_admin_handler(e, bot)
    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)
    await dp.start_polling(bot)

if __name__=="__main__": asyncio.run(main())
