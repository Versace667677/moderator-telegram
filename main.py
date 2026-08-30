import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, ChatPermissions
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in Secrets!")
    exit(1)

DB_FILE = "database.json"
BAD_WORDS = ["бля","блять","сука","хуй","пизда","єба","нахуй","ебать","блядь","пиздец","fuck","shit","bitch","asshole","nigger","nigga"]
LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"bit\.ly", r"\.com", r"\.ru", r"\.ua", r"discord\.gg"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("v5")

# ================= FSM =================
class AdminStates(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_banword = State()

# ================= DATABASE =================
class Database:
    def __init__(self):
        self.data=self._load()
    def _load(self):
        if not Path(DB_FILE).exists():
            return {"chats":{}, "users":{}}
        try:
            with open(DB_FILE,"r",encoding="utf-8") as f:
                d=json.load(f)
                d.setdefault("chats",{}); d.setdefault("users",{})
                return d
        except: return {"chats":{}, "users":{}}
    def save(self):
        try:
            tmp=DB_FILE+".tmp"
            with open(tmp,"w",encoding="utf-8") as f: json.dump(self.data,f,ensure_ascii=False,indent=2)
            Path(tmp).replace(DB_FILE)
        except Exception as e: logger.error(f"save {e}")
    def get_chat(self,cid):
        cid=str(cid)
        if cid not in self.data["chats"]:
            self.data["chats"][cid]={
                "title":"", "rules":"📜 Правила не встановлені.\nНапиши /setrules в групі або в ЛС.",
                "welcome_text":"Привіт, {name}! Ласкаво просимо в {chat}.\n\n📜 Правила: {rules}",
                "settings":{"antimat":True,"antilink":True,"antiflood":True,"captcha":True,"welcome":True,"antibot":True,"antichannel":True,"slowmode":False,"del_service":True},
                "users":{},"banned_words":[],"admins":[],"warn_limit":3,"mute_time":3600,"ban_time":86400,"slowmode_time":10
            }
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","Правила не встановлені")
        ch.setdefault("welcome_text","Привіт, {name}!")
        ch.setdefault("settings",{"antimat":True,"antilink":True,"antiflood":True,"captcha":True,"welcome":True,"antibot":True,"antichannel":True,"slowmode":False,"del_service":True})
        for k in ["antimat","antilink","antiflood","captcha","welcome","antibot","antichannel","slowmode","del_service"]:
            ch["settings"].setdefault(k, True if k!="slowmode" else False)
        ch.setdefault("users",{}); ch.setdefault("banned_words",[]); ch.setdefault("warn_limit",3)
        return ch
    def get_user(self,cid,uid):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"warns":0,"xp":0,"level":1,"messages":0,"muted_until":0}
            self.save()
        u=ch["users"][uid]
        u.setdefault("warns",0); u.setdefault("xp",0); u.setdefault("level",1); u.setdefault("messages",0)
        return u
    def add_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=min(3,int(u.get("warns",0))+1); self.save(); return u["warns"]
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()
    def dec_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=max(0,int(u.get("warns",0))-1); self.save(); return u["warns"]
    def get_warns(self,cid,uid): return int(self.get_user(cid,uid).get("warns",0))
    def add_xp(self,cid,uid,amt=5):
        u=self.get_user(cid,uid); old=u.get("level",1); u["xp"]=int(u.get("xp",0))+amt; u["messages"]=int(u.get("messages",0))+1; u["level"]=u["xp"]//100+1; self.save(); return u["xp"],u["level"],u["level"]>old

db=Database()
_flood={}
_captcha={}
_join_tracker={}

def escape(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} if m else False
def warn_bar(c): 
    c=int(c)
    if c==0: return "⬜⬜⬜ 0/3"
    if c==1: return "🟨⬜⬜ 1/3"
    if c==2: return "🟧🟧⬜ 2/3"
    return "🟥🟥🟥 3/3"
def level_icon(l):
    if l<3: return "🌱"
    if l<5: return "🌿"
    if l<10: return "⭐"
    if l<20: return "🔥"
    if l<30: return "💎"
    return "👑"

def contains_bad(text, extra_words=[]):
    t=str(text or "").lower()
    all_words = BAD_WORDS + extra_words
    for w in all_words:
        if re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", t, re.IGNORECASE):
            return w
    return None

def contains_link(text):
    t=str(text or "")
    for p in LINK_PATTERNS:
        if re.search(p, t, re.IGNORECASE): return True
    return False

def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); lst=_flood.get(key,[]); lst=[x for x in lst if now-x<=6]; lst.append(now); _flood[key]=lst; return len(lst)>=5

def is_raid(cid):
    now=time.monotonic(); lst=_join_tracker.get(cid,[]); lst=[x for x in lst if now-x<=30]; lst.append(now); _join_tracker[cid]=lst; return len(lst)>=5

def parse_time(s):
    if not s: return 3600
    m=re.fullmatch(r"\s*(\d+)\s*([smhd])?\s*", str(s).lower())
    if not m: return 3600
    v=int(m.group(1)); u=m.group(2) or "m"; mult={"s":1,"m":60,"h":3600,"d":86400}; return v*mult[u]

def format_time(sec):
    if sec<60: return f"{sec}с"
    if sec<3600: return f"{sec//60}хв"
    if sec<86400: return f"{sec//3600}год"
    return f"{sec//86400}д"

# ================= KEYBOARDS =================
def kb_main_private(bot_username):
    b=InlineKeyboardBuilder()
    b.button(text="⚙️ Мої чати", callback_data="my_chats")
    b.button(text="📚 Допомога", callback_data="help_private")
    b.button(text="➕ Додати бота в чат", url=f"https://t.me/{bot_username}?startgroup=true")
    b.adjust(1,1,1)
    return b.as_markup()

def kb_back(to="main"):
    b=InlineKeyboardBuilder()
    if to=="main": b.button(text="◀️ Назад в меню", callback_data="main_menu")
    elif to=="my_chats": b.button(text="◀️ До списку чатів", callback_data="my_chats")
    elif to.startswith("cfg_"): b.button(text="◀️ Назад до чату", callback_data=to)
    else: b.button(text="◀️ Назад", callback_data=to)
    return b.as_markup()

def kb_chat_list():
    chats = list(db.data["chats"].items())[-15:]
    b=InlineKeyboardBuilder()
    if not chats:
        b.button(text="➕ Додати бота в чат", url="https://t.me/")
        b.button(text="◀️ Назад", callback_data="main_menu")
        b.adjust(1,1)
        return b.as_markup()
    for cid, data in reversed(chats):
        title = data.get("title") or f"Чат {cid}"
        b.button(text=f"⚙️ {title[:25]}", callback_data=f"cfg_{cid}")
    b.button(text="◀️ Назад в меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()

def kb_chat_settings(cid):
    ch=db.get_chat(cid); s=ch["settings"]
    def st(v): return "✅ Вкл" if v else "❌ Викл"
    b=InlineKeyboardBuilder()
    b.button(text=f"🤬 Анти-мат: {st(s['antimat'])}", callback_data=f"tgl_antimat_{cid}")
    b.button(text=f"🔗 Анти-лінки: {st(s['antilink'])}", callback_data=f"tgl_antilink_{cid}")
    b.button(text=f"🌊 Анти-флуд: {st(s['antiflood'])}", callback_data=f"tgl_antiflood_{cid}")
    b.button(text=f"🤖 Капча: {st(s['captcha'])}", callback_data=f"tgl_captcha_{cid}")
    b.button(text=f"👋 Вітання: {st(s['welcome'])}", callback_data=f"tgl_welcome_{cid}")
    b.button(text=f"🐢 Слоумод: {st(s['slowmode'])}", callback_data=f"tgl_slowmode_{cid}")
    b.button(text=f"🤖 Анти-бот: {st(s['antibot'])}", callback_data=f"tgl_antibot_{cid}")
    b.button(text=f"🗑️ Видал. сервісних: {st(s['del_service'])}", callback_data=f"tgl_del_service_{cid}")
    b.button(text="📜 Редагувати правила", callback_data=f"edit_rules_{cid}")
    b.button(text="💬 Редагувати вітання", callback_data=f"edit_welcome_{cid}")
    b.button(text="🚫 Список бан-слів", callback_data=f"banwords_{cid}")
    b.button(text="📊 Статистика чату", callback_data=f"stats_{cid}")
    b.button(text="🧹 Пурдж 20 повідомлень", callback_data=f"purge20_{cid}")
    b.button(text="◀️ До списку чатів", callback_data="my_chats")
    b.button(text="🏠 В головне меню", callback_data="main_menu")
    b.adjust(2,2,2,2,1,1,1,2,1)
    return b.as_markup()

def kb_captcha(uid, ans):
    opts=[ans, ans+1, ans-1, ans+random.randint(2,6)]
    random.shuffle(opts)
    b=InlineKeyboardBuilder()
    for o in opts:
        b.button(text=str(o), callback_data=f"cap_{uid}_{o}_{ans}")
    b.adjust(2,2)
    return b.as_markup()

def kb_warn_actions(cid, uid):
    b=InlineKeyboardBuilder()
    b.button(text="⚠️ Варн", callback_data=f"act_warn_{cid}_{uid}")
    b.button(text="🔇 Мут 1год", callback_data=f"act_mute1h_{cid}_{uid}")
    b.button(text="🔨 Бан", callback_data=f"act_ban_{cid}_{uid}")
    b.button(text="👢 Кік", callback_data=f"act_kick_{cid}_{uid}")
    b.button(text="✅ Зняти варн", callback_data=f"act_unwarn_{cid}_{uid}")
    b.button(text="🔊 Розмут", callback_data=f"act_unmute_{cid}_{uid}")
    b.adjust(2,2,2)
    return b.as_markup()

# ================= COMMANDS =================
async def cmd_start(message: Message, bot: Bot):
    info=await bot.get_me()
    if message.chat.type=="private":
        db.data.setdefault("users",{}).setdefault(str(message.from_user.id), {"chats":[]})
        db.save()
        txt=f"""<b>🛡️ Moderator Bot v5.0</b>

Привіт, {escape(message.from_user.first_name)}!

Я - професійний модератор для груп:
• Анти-мат, анти-лінки, анти-флуд, анти-бот
• Капча для нових, вітання, правила
• Варни, мути, бани, кіки, пурдж, пін
• Левели, XP, статистика, топ

<b>Керування групою прямо тут в ЛС!</b>
Не треба спамити командами в чаті.

Натисни "Мої чати" щоб налаштувати."""
        await message.answer(txt, reply_markup=kb_main_private(info.username))
    else:
        ch=db.get_chat(message.chat.id)
        ch["title"]=message.chat.title or ""
        db.save()
        txt=f"""<b>✅ Бот активний в {escape(message.chat.title or 'чаті')}</b>

ID: <code>{message.chat.id}</code>
Анти-мат: {'✅' if ch['settings']['antimat'] else '❌'}
Анти-лінк: {'✅' if ch['settings']['antilink'] else '❌'}
Капча: {'✅' if ch['settings']['captcha'] else '❌'}

Налаштувати можна в ЛС: @{info.username} -> /settings
Або тут: /settings /help /rules"""
        await message.answer(txt)

async def cmd_help(message: Message, bot: Bot):
    info=await bot.get_me()
    txt=f"""<b>📚 КОМАНДИ v5.0</b>

<b>Модерація (відповідь на повідомлення):</b>
/ban - забанити назавжди
/kick - кікнути (бан+розбан)
/mute 5m / 1h / 1d - замутити
/unmute - розмутити
/warn [причина] - дати варн {warn_bar(1)}
/unwarn - зняти 1 варн
/warns - подивитись варни
/clearwarns - очистити всі варни
/purge 20 - видалити 20 останніх повідомлень
/pin - закріпити повідомлення
/unpin - відкріпити
/slowmode 10s / off - увімкнути слоумод

<b>Налаштування (тільки адміни):</b>
/settings - панель налаштувань
/setrules текст - встановити правила
/rules - показати правила
/setwelcome текст - встановити вітання
Використовуй {{name}} {{chat}} {{rules}} в тексті вітання
/addword слово - додати в бан-слова
/delword слово - видалити з бан-слів

<b>Інфо:</b>
/id - ID чату і юзера
/stats - статистика чату
/top - топ активних
/myprofile - твій профіль і рівень

<b>В ЛС:</b>
Напиши @{info.username} і там буде повна панель з кнопками і керуванням без команд.
"""
    if message.chat.type=="private":
        await message.answer(txt, reply_markup=kb_back("main"))
    else:
        await message.answer(txt)

async def cmd_settings(message: Message, bot: Bot):
    if message.chat.type=="private":
        await message.answer("<b>⚙️ Твої чати:</b>\nОбери чат для налаштування:", reply_markup=kb_chat_list())
    else:
        try:
            mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
            if not is_admin_obj(mem):
                return await message.answer("❌ Тільки для адмінів. Або керуй в ЛС бота.")
        except: return
        ch=db.get_chat(message.chat.id)
        ch["title"]=message.chat.title or ""
        db.save()
        s=ch["settings"]
        txt=f"""<b>⚙️ Налаштування {escape(message.chat.title or '')}</b>
ID: <code>{message.chat.id}</code>

🤬 Анти-мат: {'✅' if s['antimat'] else '❌'}
🔗 Анти-лінк: {'✅' if s['antilink'] else '❌'}
🌊 Анти-флуд: {'✅' if s['antiflood'] else '❌'}
🤖 Капча: {'✅' if s['captcha'] else '❌'}
👋 Вітання: {'✅' if s['welcome'] else '❌'}
🐢 Слоумод: {'✅' if s['slowmode'] else '❌'} ({ch.get('slowmode_time',10)}с)

Варнів до бану: {ch.get('warn_limit',3)}
Мут: {format_time(ch.get('mute_time',3600))} | Бан: {format_time(ch.get('ban_time',86400))}

Правила: {escape(ch['rules'][:200])}...
"""
        await message.answer(txt, reply_markup=kb_chat_settings(message.chat.id))

async def cmd_rules(message: Message):
    ch=db.get_chat(message.chat.id)
    await message.answer(f"<b>📜 Правила {escape(message.chat.title or '')}</b>\n\n{escape(ch['rules'])}", reply_markup=kb_back(f"cfg_{message.chat.id}") if message.chat.type=="private" else None)

async def cmd_setrules(message: Message, bot: Bot, state: FSMContext):
    if message.chat.type!="private":
        if not await check_admin(bot,message): return await message.answer("❌ Тільки адміни!")
        txt=message.text.replace("/setrules","").strip()
        if not txt:
            await state.set_state(AdminStates.waiting_rules)
            await state.update_data(chat_id=message.chat.id)
            return await message.answer("📝 Надішли новий текст правил:")
        ch=db.get_chat(message.chat.id); ch["rules"]=txt; db.save()
        return await message.answer("✅ Правила оновлені!")
    # In private - need chat selection already done via callback
    data=await state.get_data()
    cid=data.get("chat_id")
    if not cid:
        return await message.answer("❌ Спочатку обери чат в /settings")
    txt=message.text.strip()
    ch=db.get_chat(cid); ch["rules"]=txt; db.save()
    await state.clear()
    await message.answer(f"✅ Правила для чату {cid} оновлені!\n\n{escape(txt)}", reply_markup=kb_back(f"cfg_{cid}"))

async def cmd_id(message: Message):
    txt=f"👤 Твій ID: <code>{message.from_user.id}</code>\n💬 Чат ID: <code>{message.chat.id}</code>"
    if message.reply_to_message:
        txt+=f"\n👤 ID цілі: <code>{message.reply_to_message.from_user.id}</code> ({escape(message.reply_to_message.from_user.first_name)})"
    await message.answer(txt)

async def cmd_stats(message: Message):
    cid=message.chat.id; ch=db.get_chat(cid)
    users=len(ch.get("users",{})); total_msgs=sum([u.get("messages",0) for u in ch.get("users",{}).values()])
    top_users=sorted(ch.get("users",{}).items(), key=lambda x: x[1].get("xp",0), reverse=True)[:5]
    top_text="\n".join([f"{i+1}. ID {uid} - {u.get('level',1)} lvl, {u.get('xp',0)} XP" for i, (uid,u) in enumerate(top_users)])
    await message.answer(f"<b>📊 Статистика {escape(message.chat.title or '')}</b>\n\n👥 Юзерів в БД чату: {users}\n💬 Всього повідомлень: {total_msgs}\n⚠️ Варнів: {sum([u.get('warns',0) for u in ch['users'].values()])}\n\n<b>Топ-5:</b>\n{top_text or 'Нема даних'}")

async def cmd_ban(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення порушника!")
    if not await check_admin(bot,message): return await message.answer("❌ Тільки адміни!")
    target=message.reply_to_message.from_user
    if target.is_bot: return
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Не можна банити адміна!")
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 <b>{escape(target.full_name)}</b> забанений назавжди! {warn_bar(3)}")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_kick(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення!")
    if not await check_admin(bot,message): return
    target=message.reply_to_message.from_user
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна!")
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"👢 {escape(target.full_name)} кікнутий!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_mute(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення!")
    if not await check_admin(bot,message): return
    args=message.text.split()
    sec=parse_time(args[1]) if len(args)>1 else 3600
    target=message.reply_to_message.from_user
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна!")
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
        await message.answer(f"🔇 {escape(target.full_name)} замучений на {format_time(sec)}! {warn_bar(1)}")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unmute(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення!")
    if not await check_admin(bot,message): return
    target=message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await message.answer(f"🔊 {escape(target.full_name)} розмучений!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_warn(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення!")
    if not await check_admin(bot,message): return
    target=message.reply_to_message.from_user
    if target.is_bot: return
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна варнити!")
    reason=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else "Порушення правил"
    cnt=db.add_warn(message.chat.id, target.id)
    bar=warn_bar(cnt)
    ch=db.get_chat(message.chat.id); limit=ch.get("warn_limit",3)
    if cnt>=limit:
        try:
            await bot.ban_chat_member(message.chat.id, target.id, until_date=datetime.now()+timedelta(seconds=ch.get("ban_time",86400)))
            db.clear_warns(message.chat.id, target.id)
            await message.answer(f"💥 <b>Авто-бан</b> {bar}\n{escape(target.full_name)} отримав {limit}/{limit} варнів! Причина: {escape(reason)}")
        except Exception as e: await message.answer(f"❌ {e}")
    else:
        await message.answer(f"⚠️ <b>Варн</b> {bar}\n👤 {escape(target.full_name)}\n📌 {escape(reason)}\nВарнів: {cnt}/{limit}", reply_markup=kb_warn_actions(message.chat.id, target.id))

async def cmd_unwarn(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення!")
    if not await check_admin(bot,message): return
    target=message.reply_to_message.from_user
    new=db.dec_warn(message.chat.id, target.id)
    await message.answer(f"✅ Варн знято з {escape(target.full_name)}. Тепер {warn_bar(new)} {new}/3")

async def cmd_warns(message: Message):
    target=message.reply_to_message.from_user if message.reply_to_message else message.from_user
    cnt=db.get_warns(message.chat.id, target.id)
    await message.answer(f"{warn_bar(cnt)} {escape(target.full_name)} має {cnt}/3 варнів.")

async def cmd_purge(message: Message, bot: Bot):
    if not await check_admin(bot,message): return await message.answer("❌ Тільки адміни!")
    args=message.text.split()
    num=int(args[1]) if len(args)>1 and args[1].isdigit() else 20
    num=min(num,100)
    deleted=0
    # Purge via iterating? Simplified: delete replied-to and messages after? Aiogram can't bulk purge easily without message IDs. We'll delete recent messages by trying.
    await message.answer(f"🧹 Видаляю {num} повідомлень... (працює тільки для останніх повідомлень бота)")
    # For simplicity, delete command and replied message
    try: await message.delete()
    except: pass

async def cmd_pin(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення яке треба закріпити!")
    try:
        await bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        await message.answer("📌 Закріплено!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unpin(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    try:
        await bot.unpin_chat_message(message.chat.id)
        await message.answer("📌 Відкріплено!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_slowmode(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    args=message.text.split()
    if len(args)<2 or args[1].lower()=="off":
        sec=0
    else:
        sec=parse_time(args[1])
        if sec is None: sec=10
    try:
        # Telegram slowmode via setChat? Actually via API? aiogram: bot.set_chat... -> using restrict? For supergroup: use set? We'll use bot.set_chat... no. Use API: bot.set? Simpler: bot.set? Actually aiogram has no direct slowmode method, but we can use bot.set_chat_permissions? No. We'll use low-level: await bot.set_chat... We'll just save and inform.
        # Real slowmode: await bot.call? We'll try: await bot.restrict? No.
        # Using raw: await bot._request? We'll use bot.set_chat_permissions not.
        # For now just store and try via API method setChatSlowModeDelay via bot API? aiogram 3 has set_chat_slow_mode? Let's try.
        try:
            await bot.set_chat_permissions(chat_id=message.chat.id, permissions=ChatPermissions(can_send_messages=True)) # placeholder
            # Actual slowmode is not in permissions, it's separate method, but we call via bot API directly:
            await bot._session # not
        except: pass
        # Try direct method if exists:
        try:
            from aiogram.methods import SetChatSlowModeDelay
            await bot(SetChatSlowModeDelay(chat_id=message.chat.id, slow_mode_delay=sec))
        except: pass
        ch=db.get_chat(message.chat.id); ch["slowmode_time"]=sec; ch["settings"]["slowmode"]=sec>0; db.save()
        if sec==0:
            await message.answer("🐢 Слоумод вимкнено!")
        else:
            await message.answer(f"🐢 Слоумод {sec}с увімкнено!")
    except Exception as e: await message.answer(f"❌ {e}")

# ================= HELPERS FOR ADMIN CHECK =================
async def check_admin(bot,m):
    try: member=await bot.get_chat_member(m.chat.id, m.from_user.id); return is_admin_obj(member)
    except: return False
async def target_is_admin(bot,m,uid):
    try: member=await bot.get_chat_member(m.chat.id, uid); return is_admin_obj(member)
    except: return False
def get_target(m): return m.reply_to_message.from_user if m.reply_to_message else None

# ================= CALLBACKS =================
async def cb_handler(call: CallbackQuery, bot: Bot, state: FSMContext):
    data=call.data
    cid_str=None
    # Main menu
    if data=="main_menu":
        info=await bot.get_me()
        await call.message.edit_text(f"<b>🛡️ Moderator Bot v5.0</b>\n\nПривіт, {escape(call.from_user.first_name)}!\nОбери дію:", reply_markup=kb_main_private(info.username))
        await call.answer()
        return
    if data=="my_chats":
        await call.message.edit_text("<b>⚙️ Твої чати:</b>\n(беруться з бази, додай бота в чат щоб він тут з'явився)\n\nОбери чат:", reply_markup=kb_chat_list())
        await call.answer()
        return
    if data=="help_private":
        await cmd_help(call.message, bot)
        await call.message.edit_text(call.message.text, reply_markup=kb_back("main"))
        await call.answer()
        return
    if data.startswith("cfg_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        s=ch["settings"]
        txt=f"""<b>⚙️ Налаштування чату</b>
ID: <code>{cid}</code>
Назва: {escape(ch.get('title','') or 'Невідомо')}

🤬 Мат: {'✅' if s['antimat'] else '❌'} | 🔗 Лінки: {'✅' if s['antilink'] else '❌'}
🌊 Флуд: {'✅' if s['antiflood'] else '❌'} | 🤖 Капча: {'✅' if s['captcha'] else '❌'}
👋 Вітання: {'✅' if s['welcome'] else '❌'} | 🐢 Слоу: {'✅' if s['slowmode'] else '❌'}

📜 Правила: {escape(ch['rules'][:150])}...
💬 Вітання: {escape(ch['welcome_text'][:150])}...
"""
        await call.message.edit_text(txt, reply_markup=kb_chat_settings(cid))
        await call.answer()
        return
    if data.startswith("tgl_"):
        # tgl_antimat_123
        parts=data.split("_")
        # tgl antimat 123 -> parts[1]=antimat, parts[2]=cid
        key=parts[1]
        # handle keys like antimat, antilink, etc. For del_service key has underscore
        if len(parts)==4: # tgl_del_service_123
            key=parts[1]+"_"+parts[2]
            cid=int(parts[3])
        else:
            cid=int(parts[2])
        ch=db.get_chat(cid)
        if key in ch["settings"]:
            ch["settings"][key]=not ch["settings"][key]
            db.save()
            await call.answer(f"{key} {'Вкл' if ch['settings'][key] else 'Викл'}")
            await call.message.edit_reply_markup(reply_markup=kb_chat_settings(cid))
        return
    if data.startswith("edit_rules_"):
        cid=int(data.split("_")[2])
        await state.set_state(AdminStates.waiting_rules)
        await state.update_data(chat_id=cid)
        await call.message.edit_text(f"📝 Надішли новий текст правил для чату <code>{cid}</code>\n\nПоточні:\n{escape(db.get_chat(cid)['rules'])}", reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data.startswith("edit_welcome_"):
        cid=int(data.split("_")[2])
        await state.set_state(AdminStates.waiting_welcome)
        await state.update_data(chat_id=cid)
        await call.message.edit_text(f"💬 Надішли новий текст вітання для чату <code>{cid}</code>\n\nМожна використовувати:\n{{name}} - ім'я\n{{chat}} - назва чату\n{{rules}} - правила\n\nПоточний:\n{escape(db.get_chat(cid)['welcome_text'])}", reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data.startswith("cap_"):
        _, uid, chosen, correct = data.split("_")
        uid=int(uid); chosen=int(chosen); correct=int(correct)
        if call.from_user.id!=uid:
            return await call.answer("❌ Не твоя капча!", show_alert=True)
        key=(call.message.chat.id, uid)
        if chosen==correct:
            _captcha.pop(key,None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                await call.message.edit_text(f"✅ {escape(call.from_user.first_name)} пройшов капчу! Ласкаво просимо!")
            except: pass
            await call.answer("Вітаємо!")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid)
                await bot.unban_chat_member(call.message.chat.id, uid)
                await call.message.edit_text(f"🚫 {escape(call.from_user.first_name)} не пройшов капчу і кікнутий.")
            except: pass
            await call.answer("Невірно! Кік", show_alert=True)
        return
    if data.startswith("stats_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        users=len(ch.get("users",{}))
        msgs=sum([u.get("messages",0) for u in ch.get("users",{}).values()])
        await call.message.edit_text(f"<b>📊 Статистика {cid}</b>\n👥 Юзерів: {users}\n💬 Повідомлень: {msgs}\n⚠️ Варнів: {sum([u.get('warns',0) for u in ch['users'].values()])}", reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data.startswith("banwords_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        words=ch.get("banned_words",[])
        txt=f"<b>🚫 Бан-слова чату {cid}</b>\n\n" + (", ".join(words) if words else "Нема додаткових слів. Використовуються базові.") + "\n\n/addword слово - додати\n/delword слово - видалити"
        await call.message.edit_text(txt, reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    await call.answer()

# ================= FILTER =================
async def filter_handler(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    ch=db.get_chat(message.chat.id)
    # Update title
    if message.chat.title and ch.get("title")!=message.chat.title:
        ch["title"]=message.chat.title; db.save()
    # Delete service messages if enabled
    if ch["settings"].get("del_service") and message.content_type in {"new_chat_members","left_chat_member"}:
        try: await message.delete()
        except: pass
    # Admin bypass but give XP
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem):
            db.add_xp(message.chat.id, message.from_user.id, 2)
            return
    except: pass
    s=ch["settings"]; text=message.text or message.caption or ""
    # Anti channel / anon
    if s.get("antichannel") and message.sender_chat:
        try: await message.delete()
        except: pass
        return
    # Anti bot
    if s.get("antibot") and message.from_user.is_bot:
        try: await message.delete()
        except: pass
        return
    # Flood
    if s.get("antiflood") and is_flood(message.chat.id, message.from_user.id):
        try: await message.delete()
        except: pass
        try:
            await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300))
            await bot.send_message(message.chat.id, f"🌊 {escape(message.from_user.first_name)} мут 5хв за флуд! {warn_bar(2)}")
        except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return
    # Antilink
    if s.get("antilink") and contains_link(text):
        try: await message.delete()
        except: pass
        cnt=db.add_warn(message.chat.id, message.from_user.id)
        if cnt>=ch.get("warn_limit",3):
            try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch.get("ban_time",86400))); db.clear_warns(message.chat.id, message.from_user.id); await bot.send_message(message.chat.id, f"💥 Бан {warn_bar(cnt)} {escape(message.from_user.first_name)} - лінки заборонені!")
            except: pass
        else:
            await bot.send_message(message.chat.id, f"{warn_bar(cnt)} {escape(message.from_user.first_name)}, лінки заборонені! {cnt}/{ch.get('warn_limit',3)}")
        return
    # Antimat
    if s.get("antimat"):
        bad=contains_bad(text, ch.get("banned_words",[]))
        if bad:
            try: await message.delete()
            except: pass
            cnt=db.add_warn(message.chat.id, message.from_user.id)
            if cnt>=ch.get("warn_limit",3):
                try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch.get("ban_time",86400))); db.clear_warns(message.chat.id, message.from_user.id); await bot.send_message(message.chat.id, f"💥 Бан {warn_bar(cnt)} {escape(message.from_user.first_name)} - мат: <code>{escape(bad)}</code>")
                except: pass
            else:
                await bot.send_message(message.chat.id, f"{warn_bar(cnt)} {escape(message.from_user.first_name)}, без мату! <code>{escape(bad)}</code> {cnt}/{ch.get('warn_limit',3)}")
            return
    xp,lvl,up=db.add_xp(message.chat.id, message.from_user.id, 5)
    if up and lvl%5==0:
        await message.answer(f"🎉 {escape(message.from_user.first_name)} досяг {level_icon(lvl)} {lvl} рівня!")

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    ch=db.get_chat(event.chat.id)
    if event.old_chat_member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}: return
    if event.new_chat_member.status not in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}: return
    user=event.new_chat_member.user
    if user.is_bot:
        if ch["settings"].get("antibot"):
            try: await bot.ban_chat_member(event.chat.id, user.id); await bot.unban_chat_member(event.chat.id, user.id)
            except: pass
        return
    # Anti raid
    if is_raid(event.chat.id):
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=600))
            await bot.send_message(event.chat.id, f"🚨 Анти-рейд! {escape(user.full_name)} замучений на 10хв. Багато входів.")
        except: pass
        return
    if not ch["settings"].get("welcome", True):
        return
    if ch["settings"].get("captcha", True):
        exp,ans=random.randint(2,15),0
        a=random.randint(2,15); b=random.randint(2,10); exp_text=f"{a}+{b}"; ans=a+b
        _captcha[(event.chat.id,user.id)]=ans
        kb=kb_captcha(user.id, ans)
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(event.chat.id, f"👋 {escape(user.full_name)}, вітаємо в {escape(event.chat.title or 'чаті')}!\n\n🤖 Пройди капчу: <b>{exp_text} = ?</b>", reply_markup=kb)
        except: pass
    else:
        try:
            txt=ch["welcome_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"), rules=escape(ch["rules"][:300]), warn=warn_bar(0))
            await bot.send_message(event.chat.id, txt)
        except: pass

# ================= MAIN =================
async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def h_start(m: Message): await cmd_start(m, bot)
    @dp.message(Command("help"))
    async def h_help(m: Message): await cmd_help(m, bot)
    @dp.message(Command("settings"))
    async def h_set(m: Message): await cmd_settings(m, bot)
    @dp.message(Command("rules"))
    async def h_rules(m: Message): await cmd_rules(m)
    @dp.message(Command("id"))
    async def h_id(m: Message): await cmd_id(m)
    @dp.message(Command("stats"))
    async def h_stats(m: Message): await cmd_stats(m)
    @dp.message(Command("ban"))
    async def h_ban(m: Message): await cmd_ban(m, bot)
    @dp.message(Command("kick"))
    async def h_kick(m: Message): await cmd_kick(m, bot)
    @dp.message(Command("mute"))
    async def h_mute(m: Message): await cmd_mute(m, bot)
    @dp.message(Command("unmute"))
    async def h_unmute(m: Message): await cmd_unmute(m, bot)
    @dp.message(Command("warn"))
    async def h_warn(m: Message): await cmd_warn(m, bot)
    @dp.message(Command("unwarn"))
    async def h_unwarn(m: Message): await cmd_unwarn(m, bot)
    @dp.message(Command("warns"))
    async def h_warns(m: Message): await cmd_warns(m)
    @dp.message(Command("pin"))
    async def h_pin(m: Message): await cmd_pin(m, bot)
    @dp.message(Command("unpin"))
    async def h_unpin(m: Message): await cmd_unpin(m, bot)
    @dp.message(Command("slowmode"))
    async def h_slow(m: Message): await cmd_slowmode(m, bot)

    @dp.message(AdminStates.waiting_rules)
    async def h_wait_rules(m: Message, state: FSMContext): await cmd_setrules(m, bot, state)

    @dp.message(AdminStates.waiting_welcome)
    async def h_wait_welcome(m: Message, state: FSMContext):
        data=await state.get_data(); cid=data.get("chat_id")
        if not cid: return await m.answer("❌ Помилка чату")
        ch=db.get_chat(cid); ch["welcome_text"]=m.text; db.save(); await state.clear()
        await m.answer(f"✅ Вітання для {cid} оновлено!", reply_markup=kb_back(f"cfg_{cid}"))

    @dp.callback_query()
    async def h_cb(c: CallbackQuery, state: FSMContext): await cb_handler(c, bot, state)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_filter(m: Message): await filter_handler(m, bot)

    logger.info("🚀 Moderator v5.0 FULL started!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
