import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found!")
    exit(1)

DB_FILE = "database.json"

# Красива база 300 матів (оптимізована)
BAD_WORDS = ["бля","блять","блядь","сука","сучка","хуй","хуйня","хуйло","пизда","пиздец","єба","ебать","нахуй","похуй","охуел","заебал","долбоёб","уебок","мудак","гандон","пидор","шлюха","жопа","говно","залупа","fuck","shit","bitch","asshole","dick","cunt","whore","slut","bastard","faggot","nigger","retard","motherfucker","bullshit","dickhead","asshat","fuckboy","dumbass","scumbag","shithead","fuckface","assface","dickface","fuckwit","assclown","дебил","дурак","придурок","козел","баран","тварь","мразь","ублюдок","сволочь","гнида","чмо","лох","курва","срака","лайно","гівно","мудила","підар","шмара","довбойоб","уйобок","залупа","єблан","єбало","нахуя","хулі","похуїст","пиздобол","пиздун","пиздюк","єбанутий","їбати","їблан","сраний","засранець","блядіна","курвисько","гондон","підор","педик","гомік","шлюшка","блядун","блядуха","хуесос","хуйовий","хуєта","хуйнути","хуярити","пиздіти","пиздота","пиздюлина","охуєнний","заєбало","уйобище","долбоєб","мудило","срака","сраний"]

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AETHER")

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
                "title":"", 
                "rules":"1. Без мату та образ\n2. Без спаму та реклами\n3. Поважай інших\n4. Без 18+ контенту",
                "welcome_text":"Привіт, {name} 👋\nЛаскаво просимо в {chat} ✨\n\nМи раді що ти з нами! Будь активним і дотримуйся правил 🫶",
                "goodbye_text":"Бувайте, {name} 👋\nСумуватимемо! Повертайся знову 💫",
                "settings":{"antimat":True,"antilink":True,"antiflood":True,"antispam":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True},
                "users":{},"banned_words":[],"warn_limit":3,"mute_time":600,"ban_time":86400
            }
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","Правила не встановлені")
        ch.setdefault("welcome_text","Привіт, {name} 👋")
        ch.setdefault("goodbye_text","Бувай, {name} 👋")
        ch.setdefault("settings",{"antimat":True,"antilink":True,"antiflood":True,"antispam":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True})
        for k in ["antimat","antilink","antiflood","antispam","welcome","goodbye","captcha","autowarn","automute"]:
            ch["settings"].setdefault(k, True)
        ch.setdefault("users",{}); ch.setdefault("banned_words",[]); ch.setdefault("warn_limit",3); ch.setdefault("mute_time",600)
        return ch
    def get_user(self,cid,uid):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"warns":0,"messages":0}; self.save()
        return ch["users"][uid]
    def add_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=min(10,int(u.get("warns",0))+1); self.save(); return u["warns"]
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()
    def dec_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=max(0,int(u.get("warns",0))-1); self.save(); return u["warns"]
    def get_warns(self,cid,uid): return int(self.get_user(cid,uid).get("warns",0))

db=Database()
_flood={}
_captcha_data={}

def escape(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} if m else False

def warn_bar(c): 
    if c==0: return "○○○"
    if c==1: return "●○○"
    if c==2: return "●●○"
    return "●●●"

def contains_bad(text, extra=[]):
    t=str(text or "").lower()
    for w in BAD_WORDS+extra:
        if re.search(re.escape(w.lower()), t, re.IGNORECASE):
            return w
    return None

def contains_link(text):
    for p in LINK_PATTERNS:
        if re.search(p, str(text or ""), re.IGNORECASE): return True
    return False

def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); lst=_flood.get(key,[]); lst=[x for x in lst if now-x<=5]; lst.append(now); _flood[key]=lst; return len(lst)>=4

def parse_time(s):
    if not s: return 600
    s=str(s).lower().strip()
    m=re.fullmatch(r"(\d+)\s*([smhd])?", s)
    if not m: 
        try: return int(s)*60
        except: return 600
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

# ================= КРАСИВІ КЛАВІАТУРИ =================
def kb_main():
    b=InlineKeyboardBuilder()
    b.button(text="⚙️ Керування", callback_data="panel")
    b.button(text="🛡️ Модерація", callback_data="mod")
    b.button(text="✨ AETHER INFO", callback_data="info")
    b.adjust(2,1)
    return b.as_markup()

def kb_panel(cid):
    ch=db.get_chat(cid); s=ch["settings"]
    b=InlineKeyboardBuilder()
    def ico(v): return "ON" if v else "OFF"
    b.button(text=f"🤬 Мат {ico(s['antimat'])}", callback_data=f"tgl_antimat_{cid}")
    b.button(text=f"🔗 Лінки {ico(s['antilink'])}", callback_data=f"tgl_antilink_{cid}")
    b.button(text=f"🌊 Флуд {ico(s['antiflood'])}", callback_data=f"tgl_antiflood_{cid}")
    b.button(text=f"👋 Вітання {ico(s['welcome'])}", callback_data=f"tgl_welcome_{cid}")
    b.button(text=f"👋 Прощання {ico(s['goodbye'])}", callback_data=f"tgl_goodbye_{cid}")
    b.button(text=f"🤖 Капча {ico(s['captcha'])}", callback_data=f"tgl_captcha_{cid}")
    b.button(text=f"📜 Правила", callback_data=f"rules_{cid}")
    b.button(text=f"💬 Вітання", callback_data=f"edit_welcome_{cid}")
    b.button(text=f"👋 Прощання", callback_data=f"edit_goodbye_{cid}")
    b.button(text="◀️ Назад", callback_data="main")
    b.adjust(2,2,2,1,1,1,1)
    return b.as_markup()

def kb_mod_actions(cid, uid, name):
    b=InlineKeyboardBuilder()
    b.button(text="🔇 Мут 10хв", callback_data=f"act_mute_600_{cid}_{uid}")
    b.button(text="🔇 Мут 1год", callback_data=f"act_mute_3600_{cid}_{uid}")
    b.button(text="⚠️ Варн", callback_data=f"act_warn_{cid}_{uid}")
    b.button(text="🔨 Бан", callback_data=f"act_ban_{cid}_{uid}")
    b.button(text="✅ Зняти варн", callback_data=f"act_unwarn_{cid}_{uid}")
    b.button(text="🔊 Розмут", callback_data=f"act_unmute_{cid}_{uid}")
    b.adjust(2,2,2)
    return b.as_markup()

def kb_captcha_modern(uid, correct_emoji, options):
    # Сучасна капча - обери правильний емодзі
    b=InlineKeyboardBuilder()
    for emoji in options:
        b.button(text=emoji, callback_data=f"cap_{uid}_{emoji}_{correct_emoji}")
    b.adjust(2,2)
    return b.as_markup()

def kb_welcome_verify(uid):
    b=InlineKeyboardBuilder()
    b.button(text="✅ Я не бот, пропустити", callback_data=f"verify_start_{uid}")
    b.adjust(1)
    return b.as_markup()

# ================= КОМАНДИ =================
async def cmd_start(message: Message, bot: Bot):
    if message.chat.type=="private":
        txt=f"""<b>AETHER</b> — сучасний захист твого чату

Привіт, {escape(message.from_user.first_name)} ✨

Я не просто бот-модератор. Я — <b>AETHER</b>, твій невидимий щит.

<b>Що я вмію:</b>
• Автоматично видаляю мати, лінки, спам і флуд
• Зустрічаю новачків красивою капчею і вітанням
• Проводжаю тих хто йде
• Працюю кнопками, а не скучними командами

<b>Дизайн:</b>
Мінімалізм, швидкість, без рамок. Як має бути у 2026.

Натисни <b>Керування</b> щоб налаштувати свій чат.
"""
        await message.answer(txt, reply_markup=kb_main())
    else:
        ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
        await message.answer(f"<b>AETHER</b> активований в <b>{escape(message.chat.title or 'чаті')}</b> ✨\n\nЯ слідкую за порядком. Матів в базі: {len(BAD_WORDS)}\nНалаштуй мене в ЛС: @{ (await bot.get_me()).username }")

async def cmd_help(message: Message, bot: Bot):
    if message.chat.type!="private" and not await is_admin(bot,message):
        return
    await message.answer("""<b>AETHER • Команди</b>

<b>Кнопками (в ЛС):</b>
Всі налаштування кнопками, без команд

<b>В чаті (тільки адміни):</b>
/mute 10 — мут на 10хв (відповідь на юзера)
/unmute — розмут
/ban — бан
/unban — розбан
/warn — варн
/unwarn — зняти варн
/warns — варни
/clear 20 — очистити 20 повідомлень
/silent 10s / off — тихий режим
/pin — закріпити
/rules — правила
/setrules текст — встановити правила

<b>Авто:</b>
Мат → видалення + мут + варн
Лінк → видалення + мут + варн
Флуд → мут
""")

async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай на повідомлення того кого треба замутити і напиши /mute 10")
    target=message.reply_to_message.from_user
    try:
        if await is_admin(bot, message.reply_to_message):
            return await message.answer("Не можна мутити адміна")
    except: pass
    sec=parse_time(message.text.split()[1]) if len(message.text.split())>1 else 600
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
        await message.answer(f"🔇 <b>{escape(target.first_name)}</b> замучений на {format_time(sec)}", reply_markup=kb_mod_actions(message.chat.id, target.id, target.first_name))
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e:
        await message.answer(f"Не вдалося: {e}")

async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай на повідомлення!")
    target=message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await message.answer(f"🔊 {escape(target.first_name)} розмучений!")
    except Exception as e: await message.answer(f"Не вдалося: {e}")

async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай на повідомлення порушника!")
    target=message.reply_to_message.from_user
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 {escape(target.first_name)} забанений")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"Не вдалося: {e}")

async def cmd_unban(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"✅ {escape(target.first_name)} розбанений")
    except Exception as e: await message.answer(f"Не вдалося: {e}")

async def cmd_warn(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай на повідомлення!")
    target=message.reply_to_message.from_user
    cnt=db.add_warn(message.chat.id, target.id)
    ch=db.get_chat(message.chat.id)
    if cnt>=ch["warn_limit"]:
        try:
            await bot.ban_chat_member(message.chat.id, target.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"]))
            db.clear_warns(message.chat.id, target.id)
            await message.answer(f"💥 {escape(target.first_name)} отримав {ch['warn_limit']}/{ch['warn_limit']} і забанений!")
        except: await message.answer(f"{warn_bar(cnt)} {escape(target.first_name)} {cnt}/{ch['warn_limit']}")
    else:
        await message.answer(f"⚠️ {warn_bar(cnt)} {escape(target.first_name)} — варн {cnt}/{ch['warn_limit']}", reply_markup=kb_mod_actions(message.chat.id, target.id, target.first_name))

async def cmd_unwarn(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("Відповідай!")
    target=message.reply_to_message.from_user
    new=db.dec_warn(message.chat.id, target.id)
    await message.answer(f"✅ Варн знято. {escape(target.first_name)} — {warn_bar(new)} {new}/3")

async def cmd_clear(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    args=message.text.split()
    try: num=int(args[1]) if len(args)>1 else 10
    except: num=10
    num=min(max(num,1),100)
    deleted=0
    # Видаляємо останні повідомлення - шукаємо ID від поточного назад
    for i in range(num+1):
        try:
            await bot.delete_message(message.chat.id, message.message_id - i)
            deleted+=1
            await asyncio.sleep(0.05)
        except: continue
    try:
        msg=await message.answer(f"🧹 Видалено {deleted} повідомлень")
        await asyncio.sleep(3)
        try: await msg.delete()
        except: pass
    except: pass

async def cmd_silent(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    args=message.text.split()
    if len(args)<2 or args[1].lower()=="off": sec=0
    else: sec=parse_time(args[1])
    try:
        from aiogram.methods import SetChatSlowModeDelay
        await bot(SetChatSlowModeDelay(chat_id=message.chat.id, slow_mode_delay=sec))
        if sec==0: await message.answer("Тихий режим вимкнено")
        else: await message.answer(f"Тихий режим: {sec}с")
    except Exception as e: await message.answer(f"Не вдалося: {e}")

async def cmd_rules(message: Message):
    ch=db.get_chat(message.chat.id)
    await message.answer(f"<b>Правила {escape(message.chat.title or '')}</b>\n\n{escape(ch['rules'])}")

async def cmd_setrules(message: Message, bot: Bot):
    if not await is_admin(bot,message): return
    txt=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else None
    if not txt: return await message.answer("Напиши: /setrules Текст правил")
    ch=db.get_chat(message.chat.id); ch["rules"]=txt; db.save()
    await message.answer("✅ Правила оновлені")

# ================= CALLBACKS =================
async def cb_handler(call: CallbackQuery, bot: Bot):
    data=call.data
    uid=call.from_user.id

    if data=="main":
        await call.message.edit_text("<b>AETHER</b> — сучасний захист\n\nОбери розділ:", reply_markup=kb_main())
        await call.answer(); return

    if data=="panel":
        # Показати чати
        chats=list(db.data["chats"].items())[-10:]
        b=InlineKeyboardBuilder()
        for cid, ch in reversed(chats):
            title=ch.get("title") or f"Чат {cid}"
            b.button(text=title[:30], callback_data=f"cfg_{cid}")
        b.button(text="◀️ Назад", callback_data="main")
        b.adjust(1)
        await call.message.edit_text("<b>AETHER • Твої чати</b>\nОбери чат для керування:", reply_markup=b.as_markup())
        await call.answer(); return

    if data.startswith("cfg_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        txt=f"<b>AETHER • {escape(ch.get('title','') or str(cid))}</b>\nID: <code>{cid}</code>\n\nНалаштуй захист кнопками:"
        await call.message.edit_text(txt, reply_markup=kb_panel(cid))
        await call.answer(); return

    if data.startswith("tgl_"):
        parts=data.split("_")
        key=parts[1]
        if len(parts)==4: key=parts[1]+"_"+parts[2]; cid=int(parts[3])
        else: cid=int(parts[2])
        ch=db.get_chat(cid)
        if key in ch["settings"]:
            ch["settings"][key]=not ch["settings"][key]; db.save()
            await call.answer(f"{key} {'ON' if ch['settings'][key] else 'OFF'}")
            await call.message.edit_reply_markup(reply_markup=kb_panel(cid))
        return

    if data.startswith("rules_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        await call.message.edit_text(f"<b>Правила</b>\n\n{escape(ch['rules'])}", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data=f"cfg_{cid}").as_markup())
        await call.answer(); return

    if data.startswith("act_"):
        # act_mute_600_cid_uid
        parts=data.split("_")
        action=parts[1]
        if action=="mute":
            sec=int(parts[2]); cid=int(parts[3]); target_id=int(parts[4])
            try:
                await bot.restrict_chat_member(cid, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
                await call.message.edit_text(f"🔇 Замучений на {format_time(sec)}")
            except Exception as e: await call.answer(f"Помилка: {e}", show_alert=True)
        elif action=="warn":
            cid=int(parts[2]); target_id=int(parts[3])
            cnt=db.add_warn(cid, target_id)
            await call.message.edit_text(f"⚠️ Варн {warn_bar(cnt)} {cnt}/3")
        elif action=="unwarn":
            cid=int(parts[2]); target_id=int(parts[3])
            new=db.dec_warn(cid, target_id)
            await call.message.edit_text(f"✅ Варн знято {warn_bar(new)}")
        elif action=="ban":
            cid=int(parts[2]); target_id=int(parts[3])
            try: await bot.ban_chat_member(cid, target_id); await call.message.edit_text("🔨 Забанений")
            except Exception as e: await call.answer(f"Помилка: {e}", show_alert=True)
        elif action=="unmute":
            cid=int(parts[2]); target_id=int(parts[3])
            try: await bot.restrict_chat_member(cid, target_id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True)); await call.message.edit_text("🔊 Розмучений")
            except Exception as e: await call.answer(f"Помилка: {e}", show_alert=True)
        await call.answer(); return

    if data.startswith("verify_start_"):
        target_id=int(data.split("_")[2])
        if call.from_user.id!=target_id:
            return await call.answer("Не твоя капча!", show_alert=True)
        # Генеруємо сучасну капчу - обери правильний емодзі
        emojis = ["🦊","🐶","🐱","🐰","🦁","🐯","🐻","🐼"]
        correct = random.choice(emojis)
        options = random.sample(emojis, 4)
        if correct not in options: options[0]=correct
        random.shuffle(options)
        _captcha_data[(call.message.chat.id, target_id)] = correct
        await call.message.edit_text(f"<b>Перевірка AETHER</b>\n\n{escape(call.from_user.first_name)}, доведи що ти не бот ✨\n\nНатисни <b>{correct}</b>", reply_markup=kb_captcha_modern(target_id, correct, options))
        await call.answer(); return

    if data.startswith("cap_"):
        _, uid_s, chosen, correct = data.split("_",3)
        uid_s=int(uid_s)
        if call.from_user.id!=uid_s:
            return await call.answer("Не твоя капча!", show_alert=True)
        key=(call.message.chat.id, uid_s)
        if chosen==correct:
            _captcha_data.pop(key,None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid_s, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                ch=db.get_chat(call.message.chat.id)
                welcome = ch["welcome_text"].format(name=escape(call.from_user.first_name), chat=escape(call.message.chat.title or "чат"))
                await call.message.edit_text(f"{welcome}\n\n✅ Перевірку пройдено! Ласкаво просимо ✨")
            except: await call.message.edit_text("✅ Перевірку пройдено!")
            await call.answer("Вітаємо!")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_s)
                await bot.unban_chat_member(call.message.chat.id, uid_s)
                await call.message.edit_text(f"🚫 {escape(call.from_user.first_name)} не пройшов перевірку")
            except: pass
            await call.answer("Невірно!", show_alert=True)
        return

    await call.answer()

# ================= АВТО-МОДЕРАЦІЯ + ВИДАЛЕННЯ =================
async def auto_mod(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    if message.sender_chat and message.chat and message.sender_chat.id == message.chat.id: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem): return
    except: pass

    ch=db.get_chat(message.chat.id); s=ch["settings"]; text=message.text or message.caption or ""

    # Флуд
    if s.get("antiflood") and is_flood(message.chat.id, message.from_user.id):
        try: 
            await message.delete()
            logger.info(f"Deleted flood from {message.from_user.id}")
        except Exception as e: logger.warning(f"Delete flood failed: {e}")
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=600))
                await bot.send_message(message.chat.id, f"🌊 Авто-мут — {escape(message.from_user.first_name)} флудить, мут 10хв")
            except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return

    # Лінки
    if s.get("antilink") and contains_link(text):
        try: await message.delete(); logger.info(f"Deleted link from {message.from_user.id}")
        except Exception as e: logger.warning(f"Delete link failed: {e}")
        cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300))
                await bot.send_message(message.chat.id, f"🔗 Авто-мут — {escape(message.from_user.first_name)} за лінк, мут 5хв {warn_bar(cnt)}")
            except: pass
        if cnt>=ch["warn_limit"]:
            try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"])); db.clear_warns(message.chat.id, message.from_user.id)
            except: pass
        return

    # Мати
    if s.get("antimat"):
        bad=contains_bad(text, ch.get("banned_words",[]))
        if bad:
            try: await message.delete(); logger.info(f"Deleted bad word {bad} from {message.from_user.id}")
            except Exception as e: logger.warning(f"Delete bad failed: {e} - bot not admin?")
            cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
            if s.get("automute"):
                try:
                    await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=ch["mute_time"]))
                    await bot.send_message(message.chat.id, f"🤬 Авто-мут — {escape(message.from_user.first_name)} за мат, мут {format_time(ch['mute_time'])} {warn_bar(cnt)}")
                except: pass
            if cnt>=ch["warn_limit"]:
                try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch["ban_time"])); db.clear_warns(message.chat.id, message.from_user.id)
                except: pass
            return

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    ch=db.get_chat(event.chat.id)
    # Хтось зайшов
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        if not ch["settings"].get("captcha", True) and not ch["settings"].get("welcome", True): return
        if ch["settings"].get("captcha", True):
            # Сучасна капча - спочатку кнопка верифікації
            try:
                await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
                await bot.send_message(event.chat.id, f"Привіт, {escape(user.first_name)} 👋\nЛаскаво просимо в {escape(event.chat.title or 'чат')} ✨\n\nЩоб увійти, пройди перевірку:", reply_markup=kb_welcome_verify(user.id))
            except Exception as e: logger.warning(f"captcha send failed {e}")
        else:
            if ch["settings"].get("welcome", True):
                try:
                    txt=ch["welcome_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"))
                    await bot.send_message(event.chat.id, txt)
                except: pass
    # Хтось вийшов
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        if ch["settings"].get("goodbye", True):
            try:
                txt=ch["goodbye_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат"))
                await bot.send_message(event.chat.id, txt)
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
    @dp.message(Command("unwarn"))
    async def h_unwarn(m: Message): await cmd_unwarn(m, bot)
    @dp.message(Command("clear"))
    async def h_clear(m: Message): await cmd_clear(m, bot)
    @dp.message(Command("purge"))
    async def h_purge2(m: Message): await cmd_clear(m, bot)
    @dp.message(Command("silent"))
    async def h_silent(m: Message): await cmd_silent(m, bot)
    @dp.message(Command("rules"))
    async def h_rules(m: Message): await cmd_rules(m)
    @dp.message(Command("setrules"))
    async def h_setrules(m: Message): await cmd_setrules(m, bot)
    @dp.message(Command("pin"))
    async def h_pin(m: Message): 
        if not await is_admin(bot,m): return
        if not m.reply_to_message: return await m.answer("Відповідай на повідомлення!")
        try: await bot.pin_chat_message(m.chat.id, m.reply_to_message.message_id); await m.answer("📌 Закріплено")
        except Exception as e: await m.answer(f"Не вдалося: {e}")

    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)

    logger.info(f"AETHER v8.0 MODERN started! Bad words: {len(BAD_WORDS)}")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
