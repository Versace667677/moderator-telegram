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
BAD_WORDS = ["бля","блять","блядь","сука","сучка","хуй","хуйня","хуйло","пизда","пиздец","єба","ебать","нахуй","похуй","охуел","заебал","долбоёб","уебок","мудак","гандон","пидор","шлюха","жопа","говно","fuck","shit","bitch","asshole","dick","cunt","whore","slut","bastard","faggot","nigger","motherfucker","дебил","дурак","тварь","мразь","ублюдок","сволочь","гнида","чмо","лох","курва","срака","лайно","мудила","підар","шмара","довбойоб","уйобок","єблан","єбало","нахуя","хулі","пиздобол","єбанутий","сраний","залупа","блядіна","гондон","підор"]

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AETHER_V9")

class Database:
    def __init__(self):
        self.data=self._load()
    def _load(self):
        if not Path(DB_FILE).exists():
            return {"chats":{}, "active_chat": None}
        try:
            with open(DB_FILE,"r",encoding="utf-8") as f:
                d=json.load(f); d.setdefault("chats",{}); d.setdefault("active_chat", None); return d
        except: return {"chats":{}, "active_chat": None}
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
                "title":"", "owner_id": None, "is_active": False, "bot_is_admin": False,
                "rules":"1. Без мату та образ\n2. Без спаму та реклами\n3. Поважай інших\n4. Без 18+",
                "welcome_text":"Привіт, {name} 👋\nЛаскаво в {chat} ✨\nРаді тебе бачити!",
                "goodbye_text":"Бувай, {name} 👋 Сумуватимемо!",
                "settings":{"antimat":True,"antilink":True,"antiflood":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True},
                "users":{},"banned_words":[],"warn_limit":3,"mute_time":600,"ban_time":86400,"members_count":0
            }
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","Правила не встановлені"); ch.setdefault("welcome_text","Привіт, {name} 👋"); ch.setdefault("goodbye_text","Бувай, {name} 👋")
        ch.setdefault("settings",{"antimat":True,"antilink":True,"antiflood":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True})
        for k in ["antimat","antilink","antiflood","welcome","goodbye","captcha","autowarn","automute"]:
            ch["settings"].setdefault(k, True)
        ch.setdefault("users",{}); ch.setdefault("banned_words",[]); ch.setdefault("warn_limit",3)
        return ch

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

# ==================== КЛАВІАТУРИ ====================
def kb_private_start(bot_username, has_active=False):
    b=InlineKeyboardBuilder()
    if not has_active:
        b.button(text="➕ Додати AETHER в чат", url=f"https://t.me/{bot_username}?startgroup=true")
        b.button(text="📖 Як це працює?", callback_data="how_it_works")
        b.adjust(1,1)
    else:
        # Якщо вже активний - ЛС вимкнено
        b.button(text="⚙️ Керування вже в групі", callback_data="already_active")
        b.adjust(1)
    return b.as_markup()

def kb_admin_panel_group(cid):
    # Панель яка пишеться ТІЛЬКИ в групі для адмінів
    b=InlineKeyboardBuilder()
    b.button(text="⚙️ Налаштування", callback_data=f"panel_cfg_{cid}")
    b.button(text="🛡️ Модерація", callback_data=f"panel_mod_{cid}")
    b.button(text="🤖 Капча ON/OFF", callback_data=f"tgl_captcha_{cid}")
    b.button(text="👋 Вітання ON/OFF", callback_data=f"tgl_welcome_{cid}")
    b.button(text="📜 Правила", callback_data=f"panel_rules_{cid}")
    b.button(text="🧹 Очистити 20", callback_data=f"quick_clear_20_{cid}")
    b.button(text="🐢 Тихий режим 10с", callback_data=f"quick_silent_10_{cid}")
    b.button(text="🐢 Тихий OFF", callback_data=f"quick_silent_0_{cid}")
    b.adjust(2,2,2,2)
    return b.as_markup()

def kb_settings_group(cid):
    ch=db.get_chat(cid); s=ch["settings"]
    b=InlineKeyboardBuilder()
    b.button(text=f"🤬 Мат {'ON' if s['antimat'] else 'OFF'}", callback_data=f"tgl_antimat_{cid}")
    b.button(text=f"🔗 Лінки {'ON' if s['antilink'] else 'OFF'}", callback_data=f"tgl_antilink_{cid}")
    b.button(text=f"🌊 Флуд {'ON' if s['antiflood'] else 'OFF'}", callback_data=f"tgl_antiflood_{cid}")
    b.button(text=f"🤖 Капча {'ON' if s['captcha'] else 'OFF'}", callback_data=f"tgl_captcha_{cid}")
    b.button(text=f"👋 Вітання {'ON' if s['welcome'] else 'OFF'}", callback_data=f"tgl_welcome_{cid}")
    b.button(text=f"👋 Прощання {'ON' if s['goodbye'] else 'OFF'}", callback_data=f"tgl_goodbye_{cid}")
    b.button(text="◀️ Назад до панелі", callback_data=f"panel_main_{cid}")
    b.adjust(2,2,2,1)
    return b.as_markup()

def kb_mod_actions(cid, uid):
    b=InlineKeyboardBuilder()
    b.button(text="🔇 10хв", callback_data=f"act_mute_600_{cid}_{uid}")
    b.button(text="🔇 1год", callback_data=f"act_mute_3600_{cid}_{uid}")
    b.button(text="⚠️ Варн", callback_data=f"act_warn_{cid}_{uid}")
    b.button(text="🔨 Бан", callback_data=f"act_ban_{cid}_{uid}")
    b.button(text="✅ -Варн", callback_data=f"act_unwarn_{cid}_{uid}")
    b.button(text="🔊 Розмут", callback_data=f"act_unmute_{cid}_{uid}")
    b.adjust(2,2,2)
    return b.as_markup()

def kb_captcha(uid, correct, opts):
    b=InlineKeyboardBuilder()
    for e in opts:
        b.button(text=e, callback_data=f"cap_{uid}_{e}_{correct}")
    b.adjust(2,2)
    return b.as_markup()

def kb_verify(uid):
    b=InlineKeyboardBuilder()
    b.button(text="✅ Я не бот", callback_data=f"verify_{uid}")
    b.adjust(1)
    return b.as_markup()

# ==================== КОМАНДИ ====================
async def cmd_start(message: Message, bot: Bot):
    bot_info = await bot.get_me()
    has_active = len(db.data["chats"])>0 and any([c.get("bot_is_admin") for c in db.data["chats"].values()])
    
    if message.chat.type=="private":
        if has_active:
            # ЛС ВИМКНЕНО після додавання в групу
            active_chat_id = db.data.get("active_chat") or list(db.data["chats"].keys())[0]
            ch=db.get_chat(active_chat_id)
            await message.answer(f"<b>AETHER вже активний</b> ✨\n\nЯ працюю тільки в групі <b>{escape(ch.get('title','')}</b>\n\n❌ ЛС вимкнено!\nВсі команди і керування тільки в групі для адмінів.\n\nЯкщо ти адмін — напиши в групі /help",
                                 reply_markup=kb_private_start(bot_info.username, has_active=True))
        else:
            # Перший запуск - тільки кнопка додати в чат
            txt=f"""<b>AETHER</b> — сучасний захист чату ✨

<b>Як підключити:</b>
1️⃣ Натисни <b>Додати AETHER в чат</b>
2️⃣ Обери свій чат / канал
3️⃣ Зайди в чат → Адміни → Додай мене адміном з усіма правами
4️⃣ Як тільки даси адмінку — я сам напишу в чаті панель для адмінів

Після цього я працюватиму тільки в групі. ЛС вимкнеться.
"""
            await message.answer(txt, reply_markup=kb_private_start(bot_info.username, has_active=False))
    else:
        # В групі
        ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
        # Якщо бот ще не адмін - просимо адмінку
        try:
            bot_member = await bot.get_chat_member(message.chat.id, bot_info.id)
            if not is_admin_obj(bot_member):
                await message.answer(f"👋 Привіт! Я <b>AETHER</b> ✨\n\nЩоб я запрацював, дай мені адмінку:\n\nЧат → Налаштування → Адміністратори → Додати → @{bot_info.username} → ✅ Всі права\n\nПісля цього я сам напишу панель керування для адмінів!")
                return
        except: pass
        
        # Бот адмін - перевіряємо чи адмін пише
        if not await is_admin(bot, message):
            return  # Ігноруємо не адмінів
        
        # Адмін в групі - показуємо панель
        ch["bot_is_admin"]=True; ch["is_active"]=True; db.data["active_chat"]=str(message.chat.id); db.save()
        txt=f"""<b>AETHER активований</b> ✨

<b>Чат:</b> {escape(message.chat.title or '')}
<b>ID:</b> <code>{message.chat.id}</code>
<b>Матів в базі:</b> {len(BAD_WORDS)}

Я постійно оновлюю список учасників і слідкую за порядком.
Всі команди — тільки для адмінів і тільки кнопками.

<b>Авто-модерація:</b>
🤬 Мат → видалення + мут + варн
🔗 Лінк → видалення + мут + варн
🌊 Флуд → мут

Натисни кнопку щоб керувати:
"""
        await message.answer(txt, reply_markup=kb_admin_panel_group(message.chat.id))

async def cmd_help(message: Message, bot: Bot):
    if message.chat.type=="private":
        # В ЛС після активації - кажемо що ЛС вимкнено
        if len(db.data["chats"])>0:
            return await message.answer("❌ ЛС вимкнено! Керування тільки в групі для адмінів. Напиши /help в групі.")
        else:
            bot_info = await bot.get_me()
            await message.answer("Натисни щоб додати бота в чат:", reply_markup=kb_private_start(bot_info.username))
        return
    
    # В групі - тільки для адмінів
    if not await is_admin(bot, message):
        return
    
    ch=db.get_chat(message.chat.id)
    txt=f"""<b>AETHER • Панель адміна</b> ✨

<b>Чат:</b> {escape(message.chat.title or '')}
<b>Учасників в базі:</b> {len(ch['users'])}
<b>Матів:</b> {len(BAD_WORDS)}

<b>Керуй кнопками:</b>
"""
    await message.answer(txt, reply_markup=kb_admin_panel_group(message.chat.id))

async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай на повідомлення порушника!")
    target=message.reply_to_message.from_user
    sec=parse_time(message.text.split()[1]) if len(message.text.split())>1 else 600
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
        await message.answer(f"🔇 {escape(target.first_name)} мут на {format_time(sec)}", reply_markup=kb_mod_actions(message.chat.id, target.id))
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await message.answer(f"🔊 {escape(target.first_name)} розмучений")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 {escape(target.first_name)} забанений")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_clear(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    args=message.text.split()
    try: num=int(args[1]) if len(args)>1 else 20
    except: num=20
    num=min(max(num,1),100)
    deleted=0
    for i in range(num+5):
        try:
            await bot.delete_message(message.chat.id, message.message_id - i)
            deleted+=1
            await asyncio.sleep(0.05)
        except: continue
    try:
        m=await message.answer(f"🧹 Видалено {deleted} повідомлень ✨")
        await asyncio.sleep(3)
        try: await m.delete()
        except: pass
    except: pass

async def cmd_silent(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    args=message.text.split()
    if len(args)<2 or args[1].lower()=="off": sec=0
    else: sec=parse_time(args[1])
    try:
        await bot.set_chat_slow_mode_delay(chat_id=message.chat.id, slow_mode_delay=sec)
        if sec==0: await message.answer("🐢 Тихий режим вимкнено ✨")
        else: await message.answer(f"🐢 Тихий режим {sec}с ✨")
    except Exception as e: await message.answer(f"❌ {e}")

# ==================== CALLBACKS - ТІЛЬКИ ДЛЯ АДМІНІВ ====================
async def cb_handler(call: CallbackQuery, bot: Bot):
    # Перевірка - тільки адміни можуть натискати кнопки (крім капчі)
    if not call.data.startswith("cap_") and not call.data.startswith("verify_"):
        # В групі перевіряємо адмінку
        if call.message.chat.type!="private":
            try:
                mem=await bot.get_chat_member(call.message.chat.id, call.from_user.id)
                if not is_admin_obj(mem) and not (call.message.sender_chat and call.message.chat and call.message.sender_chat.id == call.message.chat.id):
                    # Перевірка анонімного адміна - якщо sender_chat == chat, то адмін
                    if call.message.chat.type in {"group","supergroup"}:
                        # Додаткова перевірка для callback від анонімного адміна - дозволяємо якщо юзер адмін в кеші
                        is_anon=False
                        # Для спрощення - перевіряємо чи юзер взагалі адмін в цьому чаті через get
                        try:
                            m=await bot.get_chat_member(call.message.chat.id, call.from_user.id)
                            if not is_admin_obj(m):
                                return await call.answer("❌ Тільки для адмінів!", show_alert=True)
                        except:
                            return await call.answer("❌ Тільки для адмінів!", show_alert=True)
            except:
                return await call.answer("❌ Тільки для адмінів!", show_alert=True)
    
    data=call.data
    
    if data=="how_it_works":
        await call.message.edit_text("<b>Як працює AETHER:</b>\n\n1️⃣ Додаєш бота в чат кнопкою\n2️⃣ Даєш адмінку\n3️⃣ Бот пише в чаті панель для адмінів\n4️⃣ ЛС вимикається, все в групі\n5️⃣ Не адміни не можуть керувати\n6️⃣ Бот оновлює список учасників", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back_to_start").as_markup())
        await call.answer(); return
    
    if data=="back_to_start":
        bot_info=await bot.get_me()
        await call.message.edit_text("<b>AETHER</b> — сучасний захист чату ✨\n\nНатисни щоб додати в чат:", reply_markup=kb_private_start(bot_info.username))
        await call.answer(); return
    
    if data=="already_active":
        await call.answer("Я вже працюю в групі! Керування тільки там.", show_alert=True)
        return
    
    if data.startswith("panel_main_") or data.startswith("panel_cfg_") or data.startswith("cfg_") or data.startswith("panel_"):
        # Панель в групі
        if "_" in data:
            parts=data.split("_")
            cid=int(parts[-1])
            if data.startswith("panel_cfg_") or data.startswith("cfg_"):
                await call.message.edit_text(f"<b>AETHER • Налаштування</b>\nID: <code>{cid}</code>", reply_markup=kb_settings_group(cid))
            elif data.startswith("panel_main_"):
                ch=db.get_chat(cid)
                await call.message.edit_text(f"<b>AETHER активований</b> ✨\nЧат: {escape(ch.get('title',''))}", reply_markup=kb_admin_panel_group(cid))
            elif data.startswith("panel_mod_"):
                await call.message.edit_text(f"<b>Модерація</b>\nУчасників: {len(db.get_chat(cid)['users'])}\nВарнів: {sum([u['warns'] for u in db.get_chat(cid)['users'].values()])}", reply_markup=kb_admin_panel_group(cid))
            elif data.startswith("panel_rules_"):
                ch=db.get_chat(cid)
                await call.message.edit_text(f"<b>Правила</b>\n\n{escape(ch['rules'])}", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data=f"panel_main_{cid}").as_markup())
            await call.answer(); return
    
    if data.startswith("tgl_"):
        parts=data.split("_"); key=parts[1]
        if len(parts)==4: key=parts[1]+"_"+parts[2]; cid=int(parts[3])
        else: cid=int(parts[2])
        ch=db.get_chat(cid)
        if key in ch["settings"]:
            ch["settings"][key]=not ch["settings"][key]; db.save()
            await call.answer(f"{key} {'ON' if ch['settings'][key] else 'OFF'} ✨")
            await call.message.edit_reply_markup(reply_markup=kb_settings_group(cid) if "panel" in call.message.text or "Налаштування" in call.message.text else kb_admin_panel_group(cid))
        return
    
    if data.startswith("quick_silent_"):
        parts=data.split("_"); sec=int(parts[2]); cid=int(parts[3])
        try:
            await bot.set_chat_slow_mode_delay(chat_id=cid, slow_mode_delay=sec)
            await call.answer(f"Тихий режим {sec}с" if sec>0 else "Тихий режим OFF")
        except Exception as e: await call.answer(f"Помилка: {e}", show_alert=True)
        return
    
    if data.startswith("quick_clear_"):
        cid=int(data.split("_")[3]); num=int(data.split("_")[2])
        deleted=0
        for i in range(num+5):
            try:
                await bot.delete_message(cid, call.message.message_id - i)
                deleted+=1; await asyncio.sleep(0.05)
            except: continue
        await call.answer(f"Видалено {deleted}")
        return
    
    if data.startswith("act_"):
        parts=data.split("_"); action=parts[1]
        if action=="mute":
            sec=int(parts[2]); cid=int(parts[3]); uid=int(parts[4])
            try:
                await bot.restrict_chat_member(cid, uid, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
                await call.message.edit_text(f"🔇 Мут на {format_time(sec)} ✨")
            except Exception as e: await call.answer(f"{e}", show_alert=True)
        elif action=="warn":
            cid=int(parts[2]); uid=int(parts[3]); cnt=db.add_warn(cid, uid); await call.message.edit_text(f"⚠️ Варн {cnt}/3")
        elif action=="unwarn":
            cid=int(parts[2]); uid=int(parts[3]); new=db.dec_warn(cid, uid); await call.message.edit_text(f"✅ Варн знято {new}/3")
        elif action=="ban":
            cid=int(parts[2]); uid=int(parts[3])
            try: await bot.ban_chat_member(cid, uid); await call.message.edit_text("🔨 Забанений")
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
        emojis=["🦊","🐶","🐱","🐰","🦁","🐯"]; correct=random.choice(emojis); opts=random.sample(emojis,4)
        if correct not in opts: opts[0]=correct
        random.shuffle(opts)
        _captcha[(call.message.chat.id, uid)]=correct
        await call.message.edit_text(f"<b>AETHER • Перевірка</b> ✨\n\n{escape(call.from_user.first_name)}, натисни <b>{correct}</b> щоб довести що ти не бот:", reply_markup=kb_captcha(uid, correct, opts))
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
                # Оновлюємо список учасників
                ch["users"][str(uid_s)]=ch["users"].get(str(uid_s),{"warns":0,"messages":0})
                ch["members_count"]=len(ch["users"])
                db.save()
                await call.message.edit_text(f"{welcome}\n\n✅ Перевірку пройдено ✨")
            except: await call.message.edit_text("✅ Перевірку пройдено ✨")
            await call.answer("Вітаємо!")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_s)
                await bot.unban_chat_member(call.message.chat.id, uid_s)
                await call.message.edit_text(f"🚫 {escape(call.from_user.first_name)} не пройшов перевірку")
            except: pass
            await call.answer("Невірно!", show_alert=True)
        return

# ==================== АВТО-МОДЕРАЦІЯ ====================
async def auto_mod(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    if message.sender_chat and message.chat and message.sender_chat.id == message.chat.id: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem): return
    except: pass

    ch=db.get_chat(message.chat.id); s=ch["settings"]; text=message.text or message.caption or ""
    # Оновлюємо список учасників постійно
    uid=str(message.from_user.id)
    if uid not in ch["users"]:
        ch["users"][uid]={"warns":0,"messages":0}
    ch["users"][uid]["messages"]=ch["users"][uid].get("messages",0)+1
    ch["members_count"]=len(ch["users"])
    db.save()

    if s.get("antiflood") and is_flood(message.chat.id, message.from_user.id):
        try: await message.delete()
        except: pass
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=600))
                await bot.send_message(message.chat.id, f"🌊 Авто-мут — {escape(message.from_user.first_name)} флуд, 10хв")
            except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return

    if s.get("antilink") and contains_link(text):
        try: await message.delete()
        except: pass
        cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300))
                await bot.send_message(message.chat.id, f"🔗 Авто-мут — {escape(message.from_user.first_name)} лінк, 5хв")
            except: pass
        if cnt>=ch["warn_limit"]:
            try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"])); db.clear_warns(message.chat.id, message.from_user.id)
            except: pass
        return

    if s.get("antimat"):
        bad=contains_bad(text, ch.get("banned_words",[]))
        if bad:
            try: await message.delete()
            except Exception as e: logger.warning(f"Delete failed {e}")
            cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
            if s.get("automute"):
                try:
                    await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=ch["mute_time"]))
                    await bot.send_message(message.chat.id, f"🤬 Авто-мут — {escape(message.from_user.first_name)} мат, {format_time(ch['mute_time'])}")
                except: pass
            if cnt>=ch["warn_limit"]:
                try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"])); db.clear_warns(message.chat.id, message.from_user.id)
                except: pass
            return

# Коли бота роблять адміном - він сам пише панель
async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    # Перевіряємо чи бота зробили адміном
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return  # Вже був адміном
    
    ch=db.get_chat(event.chat.id)
    ch["bot_is_admin"]=True; ch["is_active"]=True; ch["title"]=event.chat.title or ""; db.data["active_chat"]=str(event.chat.id); db.save()
    
    txt=f"""<b>AETHER активований</b> ✨

Вітаю, адміністратори! Я отримав права адміна і готовий захищати чат.

<b>Чат:</b> {escape(event.chat.title or '')}
<b>ID:</b> <code>{event.chat.id}</code>

<b>Я вмію:</b>
🤬 Авто-видалення мату + мут
🔗 Авто-видалення лінків + мут
🌊 Захист від флуду
👋 Вітання і прощання
🤖 Капча для новачків

<b>Керування — тільки для адмінів і тільки тут в групі!</b>
ЛС тепер вимкнено. Всі кнопки нижче — тільки адміни можуть натискати.

Натисни щоб налаштувати:
"""
    try:
        await bot.send_message(event.chat.id, txt, reply_markup=kb_admin_panel_group(event.chat.id))
    except Exception as e: logger.warning(f"Send admin panel failed {e}")

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    # Оновлюємо список
    ch=db.get_chat(event.chat.id)
    if event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED} and event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        # Додаємо в базу
        uid=str(user.id)
        ch["users"][uid]=ch["users"].get(uid,{"warns":0,"messages":0})
        ch["members_count"]=len(ch["users"])
        db.save()
        
        if ch["settings"].get("captcha", True):
            try:
                await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
                await bot.send_message(event.chat.id, f"Привіт, {escape(user.first_name)} 👋\nЛаскаво в {escape(event.chat.title or 'чат')} ✨\n\nПройди перевірку:", reply_markup=kb_verify(user.id))
            except: pass
        else:
            if ch["settings"].get("welcome", True):
                try:
                    txt=ch["welcome_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"))
                    await bot.send_message(event.chat.id, txt)
                except: pass
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        if ch["settings"].get("goodbye", True):
            try:
                txt=ch["goodbye_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"))
                await bot.send_message(event.chat.id, txt)
            except: pass
        # Видаляємо з активних? Залишаємо в базі але можна відмітити
        ch["members_count"]=len([u for u in ch["users"]])  # оновлюємо
        db.save()

async def check_new_chat_member(message: Message, bot: Bot):
    # Коли бота додають в чат
    if bot.id in [u.id for u in message.new_chat_members]:
        # Хто додав?
        adder = message.from_user
        if not adder:
            return
        # Перевіряємо чи додав адмін? Якщо чат новий - дозволяємо першому
        if len(db.data["chats"])==0 or str(message.chat.id) not in db.data["chats"]:
            # Перший чат - дозволяємо
            ch=db.get_chat(message.chat.id); ch["owner_id"]=adder.id; ch["title"]=message.chat.title or ""; db.save()
            await message.answer(f"👋 Привіт! Я <b>AETHER</b> ✨\n\nДякую що додав мене в <b>{escape(message.chat.title or 'чат')}</b>!\n\nЩоб я запрацював:\n1️⃣ Дай мені адмінку з усіма правами\n2️⃣ Я сам напишу панель для адмінів\n\nПісля цього ЛС вимкнеться і все буде тільки в групі.")
        else:
            # Вже є активний чат - перевіряємо чи це той самий власник?
            # Якщо хтось інший хоче додати собі - не дозволяємо
            existing_owner = None
            for cid, cdata in db.data["chats"].items():
                if cdata.get("bot_is_admin"):
                    existing_owner = cdata.get("owner_id")
                    break
            if existing_owner and str(adder.id)!=str(existing_owner):
                # Чужий хоче додати - бот виходить
                try:
                    await message.answer("❌ AETHER вже працює в іншому чаті і налаштований тільки для одного власника. Я не можу працювати в двох чатах одночасно.")
                    await bot.leave_chat(message.chat.id)
                except: pass
                return
            else:
                ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
                await message.answer(f"👋 Привіт! Я <b>AETHER</b> ✨\n\nДай мені адмінку щоб я запрацював!")

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
    @dp.message(Command("clear"))
    async def h_clear(m: Message): await cmd_clear(m, bot)
    @dp.message(Command("silent"))
    async def h_silent(m: Message): await cmd_silent(m, bot)

    @dp.message(F.new_chat_members)
    async def h_new_chat(m: Message): await check_new_chat_member(m, bot)

    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER | IS_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
    async def h_bot_admin(e: ChatMemberUpdated): await bot_admin_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)

    logger.info("AETHER v9.0 PURE GROUP MODE started!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
