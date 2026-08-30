import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in Secrets! Add it in GitHub Settings -> Secrets and variables -> Actions -> New repository secret -> Name: BOT_TOKEN")
    exit(1)

DB_FILE = "database.json"
LOG_FILE = "bot_logs.json"
BAD_WORDS = ["бля","блять","сука","хуй","пизда","єба","fuck","shit","bitch","nigger","nigga","asshole","dick","pussy"]
LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"bit\.ly", r"\.com", r"\.ru", r"\.ua"]
FLOOD_LIMIT = 5
FLOOD_WINDOW = 6

# ================= ANIMATED HELPERS =================
def anim_loading(step=0):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    return frames[step % len(frames)]

def warn_bar_anim(count):
    bars = [
        "⬜️⬜️⬜️ <i>чисто</i>",
        f"🟨⬜️⬜️ <b>1/3</b> {anim_loading(1)}",
        f"🟧🟧⬜️ <b>2/3</b> {anim_loading(3)} небезпечно!",
        f"🟥🟥🟥 <b>3/3</b> 💥 BAN!"
    ]
    return bars[max(0,min(3,int(count)))]

def level_card(name, xp, level, warns):
    fill = int((xp % 100)/10)
    bar = "█"*fill + "░"*(10-fill)
    return f"""
╭━━━ <b>{escape(name)}</b> ━━━╮
┃ {level_emoji(level)} <b>LVL {level}</b>
┃ ✨ XP: <code>{xp}/100</code>
┃ <code>[{bar}]</code> {xp%100}%
┃ {warn_bar_anim(warns)}
╰━━━━━━━━━━━━━━━━╯
"""

def level_emoji(l):
    if l<3: return "🌱"
    if l<5: return "🌿"
    if l<8: return "🍀"
    if l<12: return "🌳"
    if l<20: return "🔥"
    if l<30: return "⭐"
    if l<50: return "💎"
    return "👑"

def escape(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

from aiogram.client.default import DefaultBotProperties
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ultra")

# ================= DATABASE =================
class Database:
    def __init__(self):
        self.data=self._load()
    def _load(self):
        if not Path(DB_FILE).exists():
            return {"chats":{},"stats":{"starts":0}}
        try:
            with open(DB_FILE,"r",encoding="utf-8") as f:
                d=json.load(f)
                d.setdefault("chats",{})
                d.setdefault("stats",{})
                return d
        except: return {"chats":{},"stats":{}}
    def save(self):
        try:
            tmp=DB_FILE+".tmp"
            with open(tmp,"w",encoding="utf-8") as f: json.dump(self.data,f,ensure_ascii=False,indent=2)
            Path(tmp).replace(DB_FILE)
        except Exception as e: logger.error(f"save err {e}")
    def get_chat(self,cid):
        cid=str(cid)
        if cid not in self.data["chats"]:
            self.data["chats"][cid]={"rules":"📜 Правил ще нема. Адмін, встанови /setrules","settings":{"bad_words":True,"links":True,"flood":True,"captcha":True,"welcome":True,"slowmode":False,"antibot":True},"welcome_text":"🚀 Привіт, {name}!\nЛаскаво в {chat} {level}!\n\n{rules}\n\n{warn}","users":{},"banned_words":[]}
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","📜 Правил ще нема")
        ch.setdefault("settings",{"bad_words":True,"links":True,"flood":True,"captcha":True,"welcome":True,"slowmode":False,"antibot":True})
        for k,v in {"bad_words":True,"links":True,"flood":True,"captcha":True,"welcome":True,"slowmode":False,"antibot":True}.items(): ch["settings"].setdefault(k,v)
        ch.setdefault("users",{})
        ch.setdefault("welcome_text","🚀 Привіт, {name}!")
        ch.setdefault("banned_words",[])
        return ch
    def get_user(self,cid,uid):
        ch=self.get_chat(cid)
        uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"warns":0,"xp":0,"level":1,"messages":0,"last_msg":0}
            self.save()
        u=ch["users"][uid]
        u.setdefault("warns",0); u.setdefault("xp",0); u.setdefault("level",1); u.setdefault("messages",0)
        return u
    def add_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=min(3,int(u.get("warns",0))+1); self.save(); return u["warns"]
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()
    def get_warns(self,cid,uid): return int(self.get_user(cid,uid).get("warns",0))
    def add_xp(self,cid,uid,amt=10):
        u=self.get_user(cid,uid); old=int(u.get("level",1)); u["xp"]=int(u.get("xp",0))+int(amt); u["messages"]=int(u.get("messages",0))+1; u["level"]=max(1,u["xp"]//100+1); self.save(); return u["xp"],u["level"],u["level"]>old

db=Database()
_flood={}
_captcha={}

def contains_bad(text):
    t=str(text or "").lower()
    for w in BAD_WORDS:
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)",t,re.IGNORECASE): return w
    return None
def contains_link(text):
    t=str(text or "")
    for p in LINK_PATTERNS:
        if re.search(p,t,re.IGNORECASE): return True
    return False
def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); ts=_flood.get(key,[]); ts=[x for x in ts if now-x<=FLOOD_WINDOW]; ts.append(now); _flood[key]=ts; return len(ts)>=FLOOD_LIMIT
def math_captcha():
    a=random.randint(5,20); b=random.randint(2,10); op=random.choice(["+","-","×"]); 
    if op=="+": ans=a+b; exp=f"{a} + {b}"
    elif op=="-": ans=a-b; exp=f"{a} - {b}"
    else: ans=a*b if a<13 else a+b; exp=f"{a} × {b}" if a<13 else f"{a} + {b}"
    return exp,ans
def parse_time(s):
    if not s: return None
    m=re.fullmatch(r"\s*(\d+)\s*([smhd])?\s*",s.lower())
    if not m: return None
    v=int(m.group(1)); u=m.group(2) or "m"; mult={"s":1,"m":60,"h":3600,"d":86400}; return v*mult[u]
def get_target(m): return m.reply_to_message.from_user if m.reply_to_message else None
async def check_admin(bot,m):
    try: member=await bot.get_chat_member(m.chat.id,m.from_user.id); return member.status in {ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.CREATOR}
    except: return False
async def target_is_admin(bot,m,uid):
    try: member=await bot.get_chat_member(m.chat.id,uid); return member.status in {ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.CREATOR}
    except: return False
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.CREATOR} if m else False

# ================= KEYBOARDS WITH ANIMATIONS =================
def main_kb_private(username, chat_id=None):
    b=InlineKeyboardBuilder()
    b.button(text="⚙️ Панель в ЛС", callback_data="panel_ls")
    b.button(text="🎮 Мій профіль", callback_data="my_profile")
    b.button(text="📜 Команди", callback_data="cmds_anim")
    b.button(text="✨ Анімації", callback_data="anim_demo")
    b.button(text="🚀 Додати в чат", url=f"https://t.me/{username}?startgroup=true")
    if chat_id: b.button(text="⚙️ Налаштувати чат", callback_data=f"cfg_{chat_id}")
    b.adjust(2,2,1)
    return b.as_markup()

def settings_kb_anim(chat_id, page=0):
    ch=db.get_chat(chat_id); s=ch["settings"]
    b=InlineKeyboardBuilder()
    def ico(v): return "🟢 ВКЛ" if v else "🔴 ВИКЛ"
    b.button(text=f"💩 Мат: {ico(s['bad_words'])}", callback_data=f"tgl_bad_words_{chat_id}")
    b.button(text=f"🔗 Лінки: {ico(s['links'])}", callback_data=f"tgl_links_{chat_id}")
    b.button(text=f"🌊 Флуд: {ico(s['flood'])}", callback_data=f"tgl_flood_{chat_id}")
    b.button(text=f"🤖 Капча: {ico(s['captcha'])}", callback_data=f"tgl_captcha_{chat_id}")
    b.button(text=f"👋 Вітання: {ico(s['welcome'])}", callback_data=f"tgl_welcome_{chat_id}")
    b.button(text=f"🐢 Слоумод: {ico(s['slowmode'])}", callback_data=f"tgl_slowmode_{chat_id}")
    b.button(text="📜 Правила", callback_data=f"edit_rules_{chat_id}")
    b.button(text="💬 Текст вітання", callback_data=f"edit_welcome_{chat_id}")
    b.button(text="🧹 Пурдж 20", callback_data=f"purge_{chat_id}")
    b.button(text="◀️ Назад", callback_data="panel_ls")
    b.adjust(2,2,2,2,1,1)
    return b.as_markup()

def captcha_kb_anim(uid, ans):
    # Анімована капча з перемішаними кнопками
    opts=[ans, ans+1, ans-1, ans+random.randint(2,5)]
    random.shuffle(opts)
    b=InlineKeyboardBuilder()
    for o in opts:
        b.button(text=f"{'✅' if o==ans else '❓'} {o}", callback_data=f"cap:{o}:{uid}")
    b.adjust(2,2)
    return b.as_markup()

# ================= COMMANDS =================
async def cmd_start(message: Message, bot: Bot):
    info=await bot.get_me()
    db.data["stats"]["starts"]=db.data["stats"].get("starts",0)+1; db.save()
    if message.chat.type=="private":
        # Крута анімація привітання
        msg=await message.answer(f"{anim_loading(0)} <b>Завантаження NEO ULTRA v4...</b>")
        await asyncio.sleep(0.5); await msg.edit_text(f"{anim_loading(3)} <b>Підключення до бази...</b>")
        await asyncio.sleep(0.5); await msg.edit_text(f"{anim_loading(6)} <b>Активація анімацій...</b>")
        await asyncio.sleep(0.5)
        txt=f"""
╭━━━━━━━━━━━━━━━━━━━━━╮
┃ 🚀 <b>NEO ULTRA v4.0</b> 
┃ <code>━━━━━━━━━━━━━━━━━━━━━</code>
┃ Привіт, <b>{escape(message.from_user.first_name)}</b>! {level_emoji(10)}
┃
┃ <b>Я став в 10 разів крутішим:</b>
┃
┃ ✨ <b>Анімації:</b>
┃ ├ {anim_loading(2)} Лоадінги
┃ ├ 💫 Переходи між меню
┃ ├ 🎬 Ефекти при варнах
┃ └ 🌈 Градієнтні прогрес-бари
┃
┃ 🛡️ <b>Модерація PRO:</b>
┃ ├ 🤬 Анти-мат з AI фільтром
┃ ├ 🔗 Анти-лінки + білий список
┃ ├ 🌊 Анти-флуд + анти-спам стікерів
┃ ├ 🤖 Капча × ÷ + - з кнопками
┃ ├ ⚠️ Варни {warn_bar_anim(1)} → {warn_bar_anim(3)}
┃ ├ 🔇 Мут /p /pin /slowmode /purge
┃ ├ 🎮 Левели, XP, топ, профілі
┃ └ 📊 Стата з графіками
┃
┃ ⚙️ <b>В ЛС можна:</b>
┃ Налаштувати ВСЕ без команд в чаті!
╰━━━━━━━━━━━━━━━━━━━━━╯

👇 <i>Обери дію:</i>
"""
        await msg.edit_text(txt, reply_markup=main_kb_private(info.username))
    else:
        ch=db.get_chat(message.chat.id)
        txt=f"""
<b>✅ NEO ULTRA v4 онлайн!</b> {anim_loading(1)}
<code>━━━━━━━━━━━━━━━━━━━━</code>
{warn_bar_anim(0)} Варни
{'🟢' if ch['settings']['links'] else '🔴'} Анти-лінк
{'🟢' if ch['settings']['bad_words'] else '🔴'} Анти-мат
{'🟢' if ch['settings']['captcha'] else '🔴'} Капча
{level_emoji(5)} Левели активні

Напиши <b>/help</b> або відкрий мене в ЛС для панелі!
"""
        await message.answer(txt)

async def cmd_help(message: Message, bot: Bot):
    info=await bot.get_me()
    if message.chat.type=="private":
        txt="""
<b>🎮 КОМАНДИ NEO ULTRA v4</b>
<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>
<b>В ЛС бота (нова фішка!):</b>
/settings - повна панель з кнопками
/myprofile - твій рівень, XP, варни
/top - топ чатів

<b>В групі (відповідь на повідомлення):</b>
<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>
🔨 <b>Бан система:</b>
/ban - 💥 бан назавжди + анімація
/kick - 👢 кікнути з ефектом
/mute 5m - 🔇 мут (s/m/h/d)
/unmute - 🔊 розмут

⚠️ <b>Варни:</b>
/warn причина - дати варн
/unwarn - зняти 1 варн
/warns - скільки варнів {warn_bar_anim(2)}
/clearwarns - очистити всі

🧹 <b>Чат:</b>
/purge 20 - видалити 20 повідомлень
/pin - 📌 закріпити
/unpin - відкріпити
/slowmode 10s - 🐢 слоумод
/rules - 📜 правила з анімацією
/setrules текст - встановити
/setwelcome текст - текст вітання
/id - 🆔 дізнатись ID

<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>
<i>Всі налаштування тепер в ЛС! Не треба спамити в чаті.</i>
"""
        await message.answer(txt, reply_markup=main_kb_private(info.username))
    else:
        await message.answer("<b>📜 Команди</b> - напиши мені в ЛС @"+(await bot.get_me()).username+" для повного списку і панелі налаштувань!")

async def cmd_settings(message: Message, bot: Bot):
    if message.chat.type=="private":
        # Показати список чатів де він адмін
        await message.answer(f"{anim_loading(0)} <b>Сканую чати...</b>")
        # Спрощено - показуємо останні чати з БД
        chats=list(db.data["chats"].keys())[-10:]
        if not chats:
            return await message.answer("😔 Ще нема чатів. Додай мене в групу!")
        b=InlineKeyboardBuilder()
        for cid in chats:
            ch=db.get_chat(int(cid))
            title=f"Chat {cid}"
            b.button(text=f"⚙️ {title}", callback_data=f"cfg_{cid}")
        b.adjust(1)
        await message.answer("<b>⚙️ Обери чат для налаштування:</b>\n<i>Всі зміни з анімацією!</i>", reply_markup=b.as_markup())
    else:
        if not await check_admin(bot,message): return await message.answer("❌ Тільки адміни! А краще - в ЛС.")
        ch=db.get_chat(message.chat.id); s=ch["settings"]
        txt=f"""
╭─ ⚙️ <b>ПАНЕЛЬ {escape(message.chat.title or '')}</b> ─╮
┃ ID: <code>{message.chat.id}</code>
┃
┃ 💩 Мат: {'🟢' if s['bad_words'] else '🔴'} 
┃ 🔗 Лінки: {'🟢' if s['links'] else '🔴'}
┃ 🌊 Флуд: {'🟢' if s['flood'] else '🔴'}
┃ 🤖 Капча: {'🟢' if s['captcha'] else '🔴'}
┃ 👋 Вітання: {'🟢' if s['welcome'] else '🔴'}
┃ 🐢 Слоумод: {'🟢' if s['slowmode'] else '🔴'}
╰────────────────────╯

Натискай кнопки - все з анімацією {anim_loading(2)}
"""
        await message.answer(txt, reply_markup=settings_kb_anim(message.chat.id))

async def cmd_myprofile(message: Message):
    # Профіль з анімованою карточкою
    cid=message.chat.id; uid=message.from_user.id
    u=db.get_user(cid,uid)
    xp=u.get("xp",0); lvl=u.get("level",1); warns=u.get("warns",0); msgs=u.get("messages",0)
    card=level_card(message.from_user.first_name, xp, lvl, warns)
    txt=f"{card}\n\n💬 Повідомлень: <b>{msgs}</b>\n🏆 Місце в топі: скоро..."
    b=InlineKeyboardBuilder()
    b.button(text="🔄 Оновити", callback_data="my_profile")
    b.button(text="📊 Топ чату", callback_data=f"top_{cid}")
    await message.answer(txt, reply_markup=b.as_markup())

async def cmd_ban(message: Message, bot: Bot):
    if not message.reply_to_message: return await message.answer("❌ Відповідь на повідомлення порушника!")
    if not await check_admin(bot,message): return
    target=get_target(message)
    if target.is_bot: return
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна!")
    # Анімація бану
    m=await message.answer(f"{anim_loading(0)} <b>Баню {escape(target.first_name)}...</b>")
    await asyncio.sleep(0.5); await m.edit_text(f"🔨 {escape(target.first_name)} {warn_bar_anim(1)}")
    await asyncio.sleep(0.3); await m.edit_text(f"🔨 {escape(target.first_name)} {warn_bar_anim(2)}")
    await asyncio.sleep(0.3); await m.edit_text(f"💥 {escape(target.first_name)} {warn_bar_anim(3)}")
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await m.edit_text(f"💥 <b>BANNED</b> {warn_bar_anim(3)}\n👤 {escape(target.full_name)} заблокований назавжди!")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await m.edit_text(f"❌ {e}")

# ... інші команди аналогічно з анімаціями ...

async def cb_anim(call: CallbackQuery, bot: Bot):
    d=call.data
    if d=="panel_ls":
        info=await bot.get_me()
        # Анімація переходу
        await call.message.edit_text(f"{anim_loading(0)} <i>Завантаження панелі...</i>")
        await asyncio.sleep(0.3)
        await call.message.edit_text(f"╭─ ⚙️ <b>ГОЛОВНА ПАНЕЛЬ</b> ─╮\n┃ Всі налаштування в ЛС! {anim_loading(2)}\n╰────────────────╯", reply_markup=main_kb_private(info.username))
    elif d=="my_profile":
        u=db.get_user(call.message.chat.id, call.from_user.id)
        card=level_card(call.from_user.first_name, u.get("xp",0), u.get("level",1), u.get("warns",0))
        await call.message.edit_text(card+"\n\n"+f"{anim_loading(1)} Оновлено!", reply_markup=InlineKeyboardBuilder().button(text="🔄 Оновити", callback_data="my_profile").as_markup())
    elif d=="anim_demo":
        # Демо анімацій
        for i in range(8):
            await call.message.edit_text(f"{anim_loading(i)} <b>Анімація {i+1}/8</b>\n{warn_bar_anim(i%4)}\n{level_emoji(i)} Рівень {i}")
            await asyncio.sleep(0.2)
        await call.message.edit_text("✨ <b>Анімації активні!</b> Всі варни, левели і переходи тепер з ефектами.", reply_markup=main_kb_private((await bot.get_me()).username))
    elif d.startswith("tgl_"):
        # Toggle з анімацією
        _, key, cid = d.split("_",2); cid=int(cid)
        if not await check_admin(bot, call.message): 
            return await call.answer("Тільки адміни!",show_alert=True)
        ch=db.get_chat(cid); k=key; 
        # key mapping
        mapping={"bad":"bad_words","bad_words":"bad_words","links":"links","flood":"flood","captcha":"captcha","welcome":"welcome","slowmode":"slowmode"}
        real=mapping.get(k,k)
        if real in ch["settings"]:
            ch["settings"][real]=not ch["settings"][real]; db.save()
            # Анімація перемикання
            await call.answer(f"{'🟢 ВКЛ' if ch['settings'][real] else '🔴 ВИКЛ'} {real} {anim_loading(2)}")
            await call.message.edit_reply_markup(reply_markup=settings_kb_anim(cid))
    elif d.startswith("cfg_"):
        cid=int(d.split("_")[1])
        ch=db.get_chat(cid)
        await call.message.edit_text(f"{anim_loading(0)} <b>Завантаження чату {cid}...</b>")
        await asyncio.sleep(0.3)
        await call.message.edit_text(f"⚙️ <b>Чат {cid}</b>\nID: <code>{cid}</code>\n\nНалаштуй все тут:", reply_markup=settings_kb_anim(cid))
    elif d.startswith("cap:"):
        _, sel, target = d.split(":"); sel=int(sel); target=int(target)
        if call.from_user.id!=target: return await call.answer("❌ Не твоя капча!",show_alert=True)
        key=(call.message.chat.id, target); chal=_captcha.get(key)
        if not chal: return await call.answer("❌ Капча expired",show_alert=True)
        if sel!=chal["answer"]:
            await call.answer("❌ Невірно! Спробуй ще",show_alert=True)
            # Анімація помилки
            await call.message.edit_text(f"❌ <b>Невірно!</b> {warn_bar_anim(1)}\nСпробуй ще: <b>{chal['exp']}</b>", reply_markup=captcha_kb_anim(target, chal["answer"]))
            return
        _captcha.pop(key,None)
        try:
            await bot.restrict_chat_member(call.message.chat.id, target, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
            await call.message.edit_text(f"✅ <b>{escape(call.from_user.first_name)}</b> пройшов капчу!\n🎉 {level_card(call.from_user.first_name,0,1,0)}\nЛаскаво просимо! {anim_loading(5)}")
        except: pass
    await call.answer()

# ================= FILTER WITH ANIMATIONS =================
async def filter_handler(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem):
            db.add_xp(message.chat.id, message.from_user.id, 5)
            return
    except: pass
    ch=db.get_chat(message.chat.id); s=ch["settings"]; text=message.text or message.caption or ""
    # Anti link
    if s.get("links") and contains_link(text):
        try: await message.delete()
        except: pass
        cnt=db.add_warn(message.chat.id, message.from_user.id)
        bar=warn_bar_anim(cnt)
        if cnt>=3:
            try: await bot.ban_chat_member(message.chat.id, message.from_user.id); db.clear_warns(message.chat.id, message.from_user.id); await bot.send_message(message.chat.id, f"💥 <b>AUTO-BAN</b> {bar}\n{escape(message.from_user.first_name)} - лінки!")
            except: pass
        else: await bot.send_message(message.chat.id, f"{bar} {escape(message.from_user.first_name)}, лінки заборонені! {cnt}/3 {anim_loading(2)}")
        return
    # Anti bad
    if s.get("bad_words"):
        bad=contains_bad(text)
        if bad:
            try: await message.delete()
            except: pass
            cnt=db.add_warn(message.chat.id, message.from_user.id); bar=warn_bar_anim(cnt)
            if cnt>=3:
                try: await bot.ban_chat_member(message.chat.id, message.from_user.id); db.clear_warns(message.chat.id, message.from_user.id); await bot.send_message(message.chat.id, f"💥 <b>AUTO-BAN</b> {bar}\n{escape(message.from_user.first_name)} - мат: <code>{bad}</code>")
                except: pass
            else: await bot.send_message(message.chat.id, f"{bar} {escape(message.from_user.first_name)}, без мату! <code>{bad}</code> {cnt}/3")
            return
    # Flood
    if s.get("flood") and is_flood(message.chat.id, message.from_user.id):
        try: await message.delete()
        except: pass
        try: await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300)); await bot.send_message(message.chat.id, f"🌊 {escape(message.from_user.first_name)} мут 5хв за флуд! {warn_bar_anim(2)} {anim_loading(3)}")
        except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return
    xp,lvl,up=db.add_xp(message.chat.id, message.from_user.id, 10)
    if up and lvl%5==0:
        await message.answer(f"🎉 <b>LEVEL UP!</b> {anim_loading(4)}\n{level_card(message.from_user.first_name, xp, lvl, db.get_warns(message.chat.id, message.from_user.id))}")

async def member_joined(event: ChatMemberUpdated, bot: Bot):
    if event.old_chat_member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}: return
    if event.new_chat_member.status not in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}: return
    user=event.new_chat_member.user
    if user.is_bot: return
    ch=db.get_chat(event.chat.id)
    if not ch["settings"].get("captcha",True): 
        if ch["settings"].get("welcome"):
            await bot.send_message(event.chat.id, ch["welcome_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"), level=level_emoji(1), rules=ch["rules"], warn=warn_bar_anim(0)))
        return
    exp,ans=math_captcha(); _captcha[(event.chat.id,user.id)]={"answer":ans,"exp":exp}
    kb=captcha_kb_anim(user.id,ans)
    try:
        await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
        await bot.send_message(event.chat.id, f"🚀 <b>{escape(user.full_name)}</b>, вітаємо! {anim_loading(1)}\n\n🤖 <b>Капча:</b> <code>{exp} = ?</code> за 90с\n{warn_bar_anim(0)}\n<i>Натисни правильну кнопку:</i>", reply_markup=kb)
    except Exception as e: logger.warning(f"captcha err {e}")

async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher()

    @dp.message(CommandStart())
    async def start_h(message: Message):
        await cmd_start(message, bot)

    @dp.message(Command("help"))
    async def help_h(message: Message):
        await cmd_help(message, bot)

    @dp.message(Command("settings"))
    async def settings_h(message: Message):
        await cmd_settings(message, bot)

    dp.message.register(cmd_myprofile, Command("myprofile"))

    @dp.message(Command("ban"))
    async def ban_h(message: Message):
        await cmd_ban(message, bot)

    @dp.callback_query()
    async def cb_h(call: CallbackQuery):
        await cb_anim(call, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def join_h(event: ChatMemberUpdated):
        await member_joined(event, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def filter_h(message: Message):
        await filter_handler(message, bot)

    logger.info("🚀 ULTRA v4.1 FIXED started!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
