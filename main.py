import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, ChatPermissions
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER, ADMINISTRATOR
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found!")
    exit(1)

DB_FILE = "database.json"

BAD_WORDS = ["бля","блять","блядь","сука","сучка","хуй","хуйня","хуйло","пизда","пиздец","єба","ебать","нахуй","похуй","охуел","заебал","долбоёб","уебок","мудак","гандон","пидор","шлюха","жопа","говно","fuck","shit","bitch","asshole","dick","cunt","whore","slut","bastard","faggot","nigger","motherfucker","дебил","дурак","тварь","мразь","ублюдок","сволочь","гнида","чмо","лох","курва","срака","лайно","мудила","підар","шмара","довбойоб","уйобок","єблан","єбало","нахуя","хулі","пиздобол","єбанутий","сраний","залупа","блядіна","гондон","підор","хуесос","хуйовий","пиздун","пиздюк","охуєнний","заєбало","уйобище","мудило"]

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg", r"bit\.ly"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AETHER_V10")

class Database:
    def __init__(self):
        self.data=self._load()
    def _load(self):
        if not Path(DB_FILE).exists():
            return {"chats":{}}
        try:
            with open(DB_FILE,"r",encoding="utf-8") as f:
                d=json.load(f); d.setdefault("chats",{}); return d
        except: return {"chats":{}}
    def save(self):
        try:
            tmp=DB_FILE+".tmp"
            with open(tmp,"w",encoding="utf-8") as f: json.dump(self.data,f,ensure_ascii=False,indent=2)
            Path(tmp).replace(DB_FILE)
        except: pass
    def get_chat(self,cid):
        cid=str(cid)
        if cid not in self.data["chats"]:
            self.data["chats"][cid]={
                "title":"", "bot_is_admin": False,
                "rules":"1️⃣ Без мату та образ\n2️⃣ Без спаму, реклами, лінків\n3️⃣ Поважай інших\n4️⃣ Без 18+ та політики",
                "welcome_text":"Привіт, {name} 👋\n✨ Ласкаво просимо в {chat} ✨\n\n💫 Ми раді що ти з нами! Читай правила і будь активним 🫶",
                "goodbye_text":"Бувай, {name} 👋\n💫 Сумуватимемо! Повертайся ✨",
                "settings":{"antimat":True,"antilink":True,"antiflood":True,"antispam":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True,"del_service":True},
                "users":{},"banned_words":[],"warn_limit":3,"mute_time":600,"ban_time":86400,"slowmode":0
            }
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","Правила не встановлені"); ch.setdefault("welcome_text","Привіт, {name} 👋"); ch.setdefault("goodbye_text","Бувай, {name} 👋")
        ch.setdefault("settings",{"antimat":True,"antilink":True,"antiflood":True,"antispam":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True,"del_service":True})
        for k in ["antimat","antilink","antiflood","antispam","welcome","goodbye","captcha","autowarn","automute","del_service"]:
            ch["settings"].setdefault(k, True if k!="del_service" else False)
        ch.setdefault("users",{}); ch.setdefault("banned_words",[]); ch.setdefault("warn_limit",3); ch.setdefault("mute_time",600)
        return ch
    def get_user(self,cid,uid):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"warns":0,"messages":0,"level":1,"xp":0}; self.save()
        return ch["users"][uid]
    def add_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=min(10,int(u.get("warns",0))+1); self.save(); return u["warns"]
    def dec_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=max(0,int(u.get("warns",0))-1); self.save(); return u["warns"]
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()
    def get_warns(self,cid,uid): return int(self.get_user(cid,uid).get("warns",0))

db=Database()
_flood={}
_captcha={}

def escape(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} if m else False

def contains_bad(text, extra=[]):
    t=str(text or "").lower()
    for w in BAD_WORDS+extra:
        if re.search(re.escape(w.lower()), t, re.IGNORECASE): return w
    return None
def contains_link(text):
    for p in LINK_PATTERNS:
        if re.search(p, str(text or ""), re.IGNORECASE): return True
    return False
def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); lst=_flood.get(key,[]); lst=[x for x in lst if now-x<=5]; lst.append(now); _flood[key]=lst; return len(lst)>=4
def parse_time(s):
    if not s: return 600
    s=str(s).lower().strip(); m=re.fullmatch(r"(\d+)\s*([smhd])?", s)
    if not m: return 600
    v=int(m.group(1)); u=m.group(2) or "m"; mult={"s":1,"m":60,"h":3600,"d":86400}; return v*mult[u]
def format_time(sec):
    sec=int(sec)
    if sec<60: return f"{sec}с"
    if sec<3600: return f"{sec//60}хв"
    if sec<86400: return f"{sec//3600}год"
    return f"{sec//86400}д"

async def is_admin(bot, message):
    if message.sender_chat and message.chat and message.sender_chat.id == message.chat.id:
        return True
    if not message.from_user: return False
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return is_admin_obj(member)
    except: return False

# ==================== ЄБЄЙШІ АНІМАЦІЇ ====================
async def animate_loading(message, bot, text="Завантаження"):
    # Анімація як в сучасних ботах - змінює текст
    frames = [f"{text} ⠋", f"{text} ⠙", f"{text} ⠹", f"{text} ⠸", f"{text} ⠼", f"{text} ⠴", f"{text} ⠦", f"{text} ⠧"]
    msg = await message.answer(frames[0])
    for i in range(1, len(frames)):
        await asyncio.sleep(0.15)
        try: await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text=frames[i])
        except: break
    return msg

async def animate_action(bot, chat_id, target_name, action="мут"):
    # Єбєйша анімація для муту/бану
    frames = [
        f"⚡ <b>AETHER</b> аналізує {escape(target_name)}...",
        f"⚡ <b>AETHER</b> аналізує {escape(target_name)}... 🔍",
        f"⚡ <b>AETHER</b> виявлено порушення! ⚠️",
        f"🔨 Застосовую {action} до {escape(target_name)}... ⠋",
        f"🔨 Застосовую {action} до {escape(target_name)}... ⠙",
        f"✅ {escape(target_name)} — {action} виконано! ✨"
    ]
    msg = await bot.send_message(chat_id, frames[0])
    for f in frames[1:]:
        await asyncio.sleep(0.4)
        try: await bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f)
        except: break
    await asyncio.sleep(2)
    try: await bot.delete_message(chat_id, msg.message_id)
    except: pass

# ==================== КЛАВІАТУРИ СУЧАСНІ ====================
def kb_private(bot_username):
    b=InlineKeyboardBuilder()
    b.button(text="➕ Додати в мій чат", url=f"https://t.me/{bot_username}?startgroup=true")
    b.button(text="📖 Що вміє AETHER?", callback_data="about")
    b.button(text="✨ Дизайн і фішки", callback_data="features")
    b.adjust(1,1,1)
    return b.as_markup()

def kb_group_main(cid):
    b=InlineKeyboardBuilder()
    b.button(text="⚙️ Налаштування", callback_data=f"cfg_{cid}")
    b.button(text="🛡️ Модерація", callback_data=f"mod_{cid}")
    b.button(text="🤖 Капча", callback_data=f"tgl_captcha_{cid}")
    b.button(text="👋 Вітання", callback_data=f"tgl_welcome_{cid}")
    b.button(text="📜 Правила", callback_data=f"rules_{cid}")
    b.button(text="🧹 Clear 20", callback_data=f"clear_20_{cid}")
    b.button(text="🐢 Slow 10s", callback_data=f"slow_10_{cid}")
    b.button(text="🐢 Slow OFF", callback_data=f"slow_0_{cid}")
    b.adjust(2,2,2,2)
    return b.as_markup()

def kb_settings(cid):
    ch=db.get_chat(cid); s=ch["settings"]
    def st(v): return "🟢 ON" if v else "🔴 OFF"
    b=InlineKeyboardBuilder()
    b.button(text=f"🤬 Мат {st(s['antimat'])}", callback_data=f"tgl_antimat_{cid}")
    b.button(text=f"🔗 Лінки {st(s['antilink'])}", callback_data=f"tgl_antilink_{cid}")
    b.button(text=f"🌊 Флуд {st(s['antiflood'])}", callback_data=f"tgl_antiflood_{cid}")
    b.button(text=f"📢 Спам {st(s['antispam'])}", callback_data=f"tgl_antispam_{cid}")
    b.button(text=f"🤖 Капча {st(s['captcha'])}", callback_data=f"tgl_captcha_{cid}")
    b.button(text=f"👋 Вітання {st(s['welcome'])}", callback_data=f"tgl_welcome_{cid}")
    b.button(text=f"👋 Прощання {st(s['goodbye'])}", callback_data=f"tgl_goodbye_{cid}")
    b.button(text="📝 Змінити правила", callback_data=f"edit_rules_{cid}")
    b.button(text="💬 Змінити вітання", callback_data=f"edit_welcome_{cid}")
    b.button(text="👋 Змінити прощання", callback_data=f"edit_goodbye_{cid}")
    b.button(text="◀️ Назад", callback_data=f"main_{cid}")
    b.adjust(2,2,2,2,1,1,1)
    return b.as_markup()

def kb_mod(cid, uid, name):
    b=InlineKeyboardBuilder()
    b.button(text="🔇 10хв", callback_data=f"act_mute_600_{cid}_{uid}")
    b.button(text="🔇 1год", callback_data=f"act_mute_3600_{cid}_{uid}")
    b.button(text="🔇 1д", callback_data=f"act_mute_86400_{cid}_{uid}")
    b.button(text="⚠️ Варн", callback_data=f"act_warn_{cid}_{uid}")
    b.button(text="🔨 Бан", callback_data=f"act_ban_{cid}_{uid}")
    b.button(text="✅ -Варн", callback_data=f"act_unwarn_{cid}_{uid}")
    b.button(text="🔊 Розмут", callback_data=f"act_unmute_{cid}_{uid}")
    b.button(text="🗑️ Видалити", callback_data=f"act_del_{cid}_{uid}")
    b.adjust(3,2,3)
    return b.as_markup()

def kb_captcha_modern(uid, correct, opts):
    b=InlineKeyboardBuilder()
    for e in opts:
        b.button(text=e, callback_data=f"cap_{uid}_{e}_{correct}")
    b.adjust(2,2)
    return b.as_markup()

def kb_verify(uid):
    b=InlineKeyboardBuilder()
    b.button(text="✅ Я не бот — пройти перевірку", callback_data=f"verify_{uid}")
    b.adjust(1)
    return b.as_markup()

# ==================== КОМАНДИ ====================
async def cmd_start(message: Message, bot: Bot):
    info=await bot.get_me()
    if message.chat.type=="private":
        txt=f"""<b>AETHER</b> — твій щит ✨

Я — найсучасніший модератор 2026 року.

<b>Що я роблю:</b>
• Видаляю мати ({len(BAD_WORDS)} слів в базі)
• Видаляю лінки, спам, флуд — сам, без тебе
• Зустрічаю новачків єбєйшою капчею
• Проводжаю тих хто йде
• Оновлюю список учасників 24/7

<b>Як підключити:</b>
1. Натисни «Додати в мій чат»
2. Дай мені адмінку
3. Я сам напишу в чаті панель для адмінів

Все керування — кнопками, з анімаціями!
"""
        await message.answer(txt, reply_markup=kb_private(info.username))
    else:
        ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
        # Перевірка чи бот адмін
        try:
            bot_mem=await bot.get_chat_member(message.chat.id, info.id)
            if not is_admin_obj(bot_mem):
                # Анімація прохання адмінки
                msg=await message.answer("⚡ AETHER ініціалізується... ⠋")
                await asyncio.sleep(0.5)
                try: await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text="⚡ AETHER потребує права адміна... ⠙")
                except: pass
                await asyncio.sleep(0.5)
                try: await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text=f"👋 Привіт! Я <b>AETHER</b> ✨\n\nЩоб я запрацював, дай мені адмінку:\n<b>Всі права</b> → Видаляти, Блокувати, Закріплювати\n\nПісля цього я сам напишу панель для адмінів з анімаціями!")
                except: pass
                return
        except: pass
        
        if not await is_admin(bot, message):
            return
        
        # Анімація активації
        loading=await message.answer("⚡ <b>AETHER</b> активується... ⠋")
        for t in ["⚡ <b>AETHER</b> активується... ⠙", "⚡ <b>AETHER</b> сканує чат... ⠹", "✨ <b>AETHER</b> готовий! ✨"]:
            await asyncio.sleep(0.4)
            try: await bot.edit_message_text(chat_id=loading.chat.id, message_id=loading.message_id, text=t)
            except: break
        await asyncio.sleep(0.5)
        try: await bot.delete_message(message.chat.id, loading.message_id)
        except: pass
        
        ch["bot_is_admin"]=True; db.save()
        txt=f"""<b>AETHER активований</b> ✨

<b>Чат:</b> {escape(message.chat.title or '')}
<b>ID:</b> <code>{message.chat.id}</code>
<b>Матів:</b> {len(BAD_WORDS)}+
<b>Учасників в базі:</b> {len(ch['users'])}

Я постійно оновлюю список і слідкую за порядком з анімаціями!

<b>Авто:</b>
🤬 Мат → видалення + мут 10хв
🔗 Лінк → видалення + мут 5хв
🌊 Флуд → мут 10хв

Керуй кнопками — тільки для адмінів:
"""
        await message.answer(txt, reply_markup=kb_group_main(message.chat.id))

async def cmd_help(message: Message, bot: Bot):
    if message.chat.type!="private" and not await is_admin(bot, message):
        return
    if message.chat.type=="private":
        info=await bot.get_me()
        await message.answer("<b>AETHER • Допомога</b> ✨\nНатисни щоб додати в чат:", reply_markup=kb_private(info.username))
    else:
        ch=db.get_chat(message.chat.id)
        txt=f"""<b>AETHER • Панель адміна</b> ✨

<b>Чат:</b> {escape(message.chat.title or '')}
<b>Учасників:</b> {len(ch['users'])}
<b>Матів в базі:</b> {len(BAD_WORDS)}

<b>Керуй кнопками:</b> (тільки адміни)
"""
        await message.answer(txt, reply_markup=kb_group_main(message.chat.id))

async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай на повідомлення порушника! Приклад: /mute 10")
    target=message.reply_to_message.from_user
    sec=parse_time(message.text.split()[1]) if len(message.text.split())>1 else 600
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
        await animate_action(bot, message.chat.id, target.first_name, f"мут на {format_time(sec)}")
        await message.answer(f"🔇 <b>{escape(target.first_name)}</b> замучений на {format_time(sec)} ✨", reply_markup=kb_mod(message.chat.id, target.id, target.first_name))
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай на повідомлення!")
    target=message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await message.answer(f"🔊 <b>{escape(target.first_name)}</b> розмучений ✨")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await animate_action(bot, message.chat.id, target.first_name, "бан")
        await message.answer(f"🔨 <b>{escape(target.first_name)}</b> забанений ✨")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"✅ <b>{escape(target.first_name)}</b> розбанений ✨")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_warn(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    cnt=db.add_warn(message.chat.id, target.id)
    ch=db.get_chat(message.chat.id)
    if cnt>=ch["warn_limit"]:
        try:
            await bot.ban_chat_member(message.chat.id, target.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"]))
            db.clear_warns(message.chat.id, target.id)
            await message.answer(f"💥 <b>{escape(target.first_name)}</b> отримав {ch['warn_limit']}/{ch['warn_limit']} і забанений! ✨")
        except Exception as e: await message.answer(f"⚠️ Варн {cnt}/{ch['warn_limit']} {escape(target.first_name)}")
    else:
        await message.answer(f"⚠️ Варн {cnt}/{ch['warn_limit']} <b>{escape(target.first_name)}</b> ✨", reply_markup=kb_mod(message.chat.id, target.id, target.first_name))

async def cmd_clear(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    args=message.text.split()
    try: num=int(args[1]) if len(args)>1 else 20
    except: num=20
    num=min(max(num,1),100)
    
    # Анімація очищення
    loading=await message.answer(f"🧹 AETHER очищає чат... 0/{num} ⠋")
    deleted=0
    for i in range(num+5):
        try:
            await bot.delete_message(message.chat.id, message.message_id - i)
            deleted+=1
            if deleted%5==0:
                try: await bot.edit_message_text(chat_id=loading.chat.id, message_id=loading.message_id, text=f"🧹 AETHER очищає... {deleted}/{num} ⠙")
                except: pass
            await asyncio.sleep(0.05)
        except: continue
    
    try:
        await bot.edit_message_text(chat_id=loading.chat.id, message_id=loading.message_id, text=f"✅ Видалено {deleted} повідомлень ✨")
        await asyncio.sleep(2)
        try: await bot.delete_message(loading.chat.id, loading.message_id)
        except: pass
    except: pass

async def cmd_silent(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    args=message.text.split()
    if len(args)<2 or args[1].lower()=="off": sec=0
    else: sec=parse_time(args[1])
    try:
        await bot.set_chat_slow_mode_delay(chat_id=message.chat.id, slow_mode_delay=sec)
        ch=db.get_chat(message.chat.id); ch["slowmode"]=sec; db.save()
        if sec==0: await message.answer("🐢 Тихий режим вимкнено ✨")
        else: await message.answer(f"🐢 Тихий режим {sec}с увімкнено ✨")
    except Exception as e: await message.answer(f"❌ {e} — дай боту право 'Змінювати інфо про групу'")

async def cmd_rules(message: Message):
    ch=db.get_chat(message.chat.id)
    await message.answer(f"<b>📜 Правила {escape(message.chat.title or '')}</b> ✨\n\n{escape(ch['rules'])}")

async def cmd_setrules(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    txt=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else None
    if not txt: return await message.answer("❌ /setrules Текст правил")
    ch=db.get_chat(message.chat.id); ch["rules"]=txt; db.save()
    await message.answer(f"✅ Правила оновлені ✨\n\n{escape(txt)}")

# ==================== CALLBACKS ====================
async def cb_handler(call: CallbackQuery, bot: Bot):
    # Капча доступна всім
    if call.data.startswith("cap_") or call.data.startswith("verify_"):
        pass
    else:
        # Все інше тільки для адмінів
        if call.message.chat.type!="private":
            if not await is_admin(bot, call.message):
                return await call.answer("❌ Тільки для адмінів!", show_alert=True)
    
    data=call.data
    
    if data=="about":
        await call.message.edit_text(f"<b>AETHER</b> — топ бот 2026 ✨\n\n🤬 {len(BAD_WORDS)}+ матів в базі\n🔗 Авто-видалення лінків\n🌊 Анти-флуд\n🤖 Єбєйша капча з емодзі\n👋 Вітання і прощання з анімаціями\n🧹 Очищення чату\n🐢 Тихий режим\n\nВсе кнопками, все з анімаціями!", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back").as_markup())
        await call.answer(); return
    
    if data=="features":
        await call.message.edit_text("<b>✨ Фішки AETHER:</b>\n\n• Анімація завантаження ⠋⠙⠹\n• Анімація муту/бану ⚡🔨\n• Капча як на сайтах 🤖\n• Вітання з емодзі 👋✨\n• Кнопки замість команд\n• Авто-оновлення учасників\n• Працює як годинник", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back").as_markup())
        await call.answer(); return
    
    if data=="back":
        info=await bot.get_me()
        await call.message.edit_text("<b>AETHER</b> — твій щит ✨\n\nНатисни щоб додати в чат:", reply_markup=kb_private(info.username))
        await call.answer(); return
    
    if data.startswith("main_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        await call.message.edit_text(f"<b>AETHER активований</b> ✨\nЧат: {escape(ch.get('title',''))}", reply_markup=kb_group_main(cid))
        await call.answer(); return
    
    if data.startswith("cfg_") or data.startswith("mod_"):
        cid=int(data.split("_")[1])
        if data.startswith("cfg_"):
            await call.message.edit_text(f"<b>⚙️ Налаштування</b>\nID: <code>{cid}</code>", reply_markup=kb_settings(cid))
        else:
            ch=db.get_chat(cid)
            await call.message.edit_text(f"<b>🛡️ Модерація</b>\nУчасників: {len(ch['users'])}", reply_markup=kb_group_main(cid))
        await call.answer(); return
    
    if data.startswith("rules_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        await call.message.edit_text(f"<b>📜 Правила</b> ✨\n\n{escape(ch['rules'])}", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data=f"main_{cid}").as_markup())
        await call.answer(); return
    
    if data.startswith("tgl_"):
        parts=data.split("_"); key=parts[1]
        if len(parts)==4: key=parts[1]+"_"+parts[2]; cid=int(parts[3])
        else: cid=int(parts[2])
        ch=db.get_chat(cid)
        if key in ch["settings"]:
            ch["settings"][key]=not ch["settings"][key]; db.save()
            # Анімація перемикання
            await call.answer(f"{key} {'🟢 ON' if ch['settings'][key] else '🔴 OFF'} ✨")
            try:
                await call.message.edit_reply_markup(reply_markup=kb_settings(cid))
            except:
                await call.message.edit_reply_markup(reply_markup=kb_group_main(cid))
        return
    
    if data.startswith("clear_"):
        num=int(data.split("_")[1]); cid=int(data.split("_")[2])
        loading=await call.message.answer(f"🧹 Очищаю... ⠋")
        deleted=0
        for i in range(num+5):
            try:
                await bot.delete_message(cid, call.message.message_id - i)
                deleted+=1; await asyncio.sleep(0.05)
            except: continue
        try: await bot.edit_message_text(chat_id=loading.chat.id, message_id=loading.message_id, text=f"✅ Видалено {deleted} ✨")
        except: pass
        await asyncio.sleep(2)
        try: await bot.delete_message(loading.chat.id, loading.message_id)
        except: pass
        await call.answer(f"Видалено {deleted}"); return
    
    if data.startswith("slow_"):
        sec=int(data.split("_")[1]); cid=int(data.split("_")[2])
        try:
            await bot.set_chat_slow_mode_delay(chat_id=cid, slow_mode_delay=sec)
            ch=db.get_chat(cid); ch["slowmode"]=sec; db.save()
            await call.answer(f"Тихий режим {sec}с ✨" if sec>0 else "Тихий OFF ✨")
        except Exception as e: await call.answer(f"Помилка: {e}", show_alert=True)
        return
    
    if data.startswith("act_"):
        parts=data.split("_"); action=parts[1]
        if action=="mute":
            sec=int(parts[2]); cid=int(parts[3]); uid=int(parts[4])
            try:
                await bot.restrict_chat_member(cid, uid, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
                await call.message.edit_text(f"🔇 Мут на {format_time(sec)} ✨")
                # Анімація
                await asyncio.sleep(1)
                try: await call.message.delete()
                except: pass
            except Exception as e: await call.answer(f"{e}", show_alert=True)
        elif action=="warn":
            cid=int(parts[2]); uid=int(parts[3]); cnt=db.add_warn(cid, uid); await call.message.edit_text(f"⚠️ Варн {cnt}/3 ✨")
        elif action=="unwarn":
            cid=int(parts[2]); uid=int(parts[3]); new=db.dec_warn(cid, uid); await call.message.edit_text(f"✅ Варн знято {new}/3 ✨")
        elif action=="ban":
            cid=int(parts[2]); uid=int(parts[3])
            try: await bot.ban_chat_member(cid, uid); await call.message.edit_text("🔨 Забанений ✨")
            except Exception as e: await call.answer(f"{e}", show_alert=True)
        elif action=="unmute":
            cid=int(parts[2]); uid=int(parts[3])
            try: await bot.restrict_chat_member(cid, uid, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True)); await call.message.edit_text("🔊 Розмучений ✨")
            except Exception as e: await call.answer(f"{e}", show_alert=True)
        await call.answer(); return
    
    if data.startswith("verify_"):
        uid=int(data.split("_")[1])
        if call.from_user.id!=uid:
            return await call.answer("Не твоя капча!", show_alert=True)
        emojis=["🦊","🐶","🐱","🐰","🦁","🐯","🐻","🐼","🦄","🐙"]
        correct=random.choice(emojis); opts=random.sample(emojis,4)
        if correct not in opts: opts[0]=correct
        random.shuffle(opts)
        _captcha[(call.message.chat.id, uid)]=correct
        # Анімація капчі
        await call.message.edit_text("🤖 <b>AETHER перевіряє...</b> ⠋")
        await asyncio.sleep(0.5)
        await call.message.edit_text(f"<b>AETHER • Перевірка</b> ✨\n\n{escape(call.from_user.first_name)}, доведи що ти не бот:\nНатисни <b>{correct}</b>", reply_markup=kb_captcha_modern(uid, correct, opts))
        await call.answer(); return
    
    if data.startswith("cap_"):
        _, uid_s, chosen, correct = data.split("_",3)
        uid_s=int(uid_s)
        if call.from_user.id!=uid_s:
            return await call.answer("Не твоя капча!", show_alert=True)
        key=(call.message.chat.id, uid_s)
        if chosen==correct:
            _captcha.pop(key,None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid_s, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                ch=db.get_chat(call.message.chat.id)
                welcome=ch["welcome_text"].format(name=escape(call.from_user.first_name), chat=escape(call.message.chat.title or "чат"))
                # Анімація успіху
                await call.message.edit_text("✅ Перевірка пройдена... ✨ ⠋")
                await asyncio.sleep(0.5)
                await call.message.edit_text(f"{welcome}\n\n✅ Ласкаво просимо! ✨")
                # Оновлюємо базу
                ch["users"][str(uid_s)]=ch["users"].get(str(uid_s),{"warns":0,"messages":0})
                db.save()
            except: await call.message.edit_text("✅ Перевірку пройдено ✨")
            await call.answer("Вітаємо! ✨")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_s)
                await bot.unban_chat_member(call.message.chat.id, uid_s)
                await call.message.edit_text(f"🚫 {escape(call.from_user.first_name)} не пройшов перевірку")
            except: pass
            await call.answer("Невірно! Кік!", show_alert=True)
        return

# ==================== АВТО-МОДЕРАЦІЯ З ВИДАЛЕННЯМ ====================
async def auto_mod(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    if message.sender_chat and message.chat and message.sender_chat.id == message.chat.id: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem): return
    except: pass

    ch=db.get_chat(message.chat.id); s=ch["settings"]; text=message.text or message.caption or ""
    # Оновлюємо учасників постійно
    uid=str(message.from_user.id)
    if uid not in ch["users"]:
        ch["users"][uid]={"warns":0,"messages":0}
    ch["users"][uid]["messages"]=ch["users"][uid].get("messages",0)+1
    db.save()

    # Флуд
    if s.get("antiflood") and is_flood(message.chat.id, message.from_user.id):
        try: 
            await message.delete()
            logger.info(f"Deleted flood from {uid}")
        except Exception as e: logger.warning(f"Delete flood failed {e} - check bot admin rights")
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=600))
                await bot.send_message(message.chat.id, f"🌊 Авто-мут — {escape(message.from_user.first_name)} флудить, мут 10хв ✨")
            except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return

    # Лінки
    if s.get("antilink") and contains_link(text):
        try: 
            await message.delete()
            logger.info(f"Deleted link from {uid}")
        except Exception as e: logger.warning(f"Delete link failed {e}")
        cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300))
                await bot.send_message(message.chat.id, f"🔗 Авто-мут — {escape(message.from_user.first_name)} за лінк, мут 5хв ✨")
            except: pass
        if cnt>=ch["warn_limit"]:
            try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"])); db.clear_warns(message.chat.id, message.from_user.id)
            except: pass
        return

    # Мати - ГОЛОВНЕ, ВИДАЛЕННЯ ПРАЦЮЄ
    if s.get("antimat"):
        bad=contains_bad(text, ch.get("banned_words",[]))
        if bad:
            try: 
                await message.delete()
                logger.info(f"Deleted bad word {bad} from {uid}")
            except Exception as e: 
                logger.error(f"DELETE FAILED - bot needs admin Delete messages right! Error: {e}")
                # Пробуємо ще раз через 0.5с
                await asyncio.sleep(0.5)
                try: await message.delete()
                except: pass
            cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
            if s.get("automute"):
                try:
                    await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=ch["mute_time"]))
                    await bot.send_message(message.chat.id, f"🤬 Авто-мут — {escape(message.from_user.first_name)} за мат <code>{escape(bad)}</code>, мут {format_time(ch['mute_time'])} ✨")
                except: pass
            if cnt>=ch["warn_limit"]:
                try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"])); db.clear_warns(message.chat.id, message.from_user.id)
                except: pass
            return

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    ch=db.get_chat(event.chat.id)
    # Зайшов
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        uid=str(user.id)
        ch["users"][uid]=ch["users"].get(uid,{"warns":0,"messages":0})
        db.save()
        if ch["settings"].get("captcha", True):
            try:
                await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
                await bot.send_message(event.chat.id, f"Привіт, {escape(user.first_name)} 👋\nЛаскаво в {escape(event.chat.title or 'чат')} ✨\n\nПройди перевірку щоб довести що ти не бот:", reply_markup=kb_verify(user.id))
            except Exception as e: logger.warning(f"captcha failed {e}")
        else:
            if ch["settings"].get("welcome", True):
                try:
                    # Анімація вітання
                    msg=await bot.send_message(event.chat.id, f"✨ Зустрічаємо {escape(user.first_name)}... ⠋")
                    await asyncio.sleep(0.8)
                    txt=ch["welcome_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"))
                    await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text=f"{txt} ✨")
                except: pass
    # Вийшов
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        if ch["settings"].get("goodbye", True):
            try:
                txt=ch["goodbye_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"))
                # Анімація прощання
                msg=await bot.send_message(event.chat.id, f"💫 {escape(user.first_name)} йде... ⠋")
                await asyncio.sleep(0.5)
                await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text=f"{txt} 💫")
            except: pass

async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return
    ch=db.get_chat(event.chat.id)
    ch["bot_is_admin"]=True; ch["title"]=event.chat.title or ""; db.save()
    txt=f"""<b>AETHER активований</b> ✨

Вітаю, адміни! Я отримав права і готовий.

<b>Чат:</b> {escape(event.chat.title or '')}
<b>Матів в базі:</b> {len(BAD_WORDS)}+

Я буду:
• Видаляти мати, лінки, флуд — з анімаціями
• Зустрічати новачків капчею
• Проводжати тих хто йде
• Оновлювати список учасників

Керування — тільки для адмінів, тільки кнопками ✨
"""
    try:
        await bot.send_message(event.chat.id, txt, reply_markup=kb_group_main(event.chat.id))
    except: pass

async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def h_start(m: Message): await cmd_start(m, bot)
    @dp.message(Command("help"))
    async def h_help(m: Message): await cmd_help(m, bot)
    @dp.message(Command("mute"))
    async def h_mute(m: Message): await cmd_mute(m, bot)
    @dp.message(Command("unmute"))
    async def h_unmute(m: Message): await cmd_unmute(m, bot)
    @dp.message(Command("ban"))
    async def h_ban(m: Message): await cmd_ban(m, bot)
    @dp.message(Command("unban"))
    async def h_unban(m: Message): await cmd_unban(m, bot)
    @dp.message(Command("warn"))
    async def h_warn(m: Message): await cmd_warn(m, bot)
    @dp.message(Command("clear"))
    async def h_clear(m: Message): await cmd_clear(m, bot)
    @dp.message(Command("purge"))
    async def h_purge(m: Message): await cmd_clear(m, bot)
    @dp.message(Command("silent"))
    async def h_silent(m: Message): await cmd_silent(m, bot)
    @dp.message(Command("rules"))
    async def h_rules(m: Message): await cmd_rules(m)
    @dp.message(Command("setrules"))
    async def h_setrules(m: Message): await cmd_setrules(m, bot)

    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
    async def h_bot_admin(e: ChatMemberUpdated): await bot_admin_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)

    logger.info(f"AETHER v10 ULTRA started! Bad words: {len(BAD_WORDS)} - animations ON!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
