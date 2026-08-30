import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, ChatPermissions
from aiogram.filters import CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER, ADMINISTRATOR
from aiogram.enums import ChatMemberStatus
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN missing!")
    exit(1)

DB_FILE = "database.json"

BAD_WORDS = ["бля","блять","блядь","сука","сучка","хуй","хуйня","хуйло","пизда","пиздец","єба","ебать","нахуй","похуй","охуел","заебал","долбоёб","уебок","мудак","гандон","пидор","шлюха","жопа","говно","fuck","shit","bitch","asshole","dick","cunt","whore","slut","bastard","faggot","nigger","motherfucker","дебил","дурак","тварь","мразь","ублюдок","сволочь","гнида","чмо","лох","курва","срака","лайно","мудила","підар","шмара","довбойоб","уйобок","єблан","єбало","нахуя","хулі","пиздобол","єбанутий","сраний","залупа"]

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AETHER_SIMPLE")

class DB:
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
            self.data["chats"][cid]={"title":"", "users":{}}
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("users",{})
        return ch
    def get_user(self,cid,uid, name=""):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"name":name,"mutes":0,"warns":0,"messages":0}
            self.save()
        u=ch["users"][uid]
        if name: u["name"]=name
        u.setdefault("mutes",0); u.setdefault("warns",0); u.setdefault("messages",0)
        return u
    def add_mute(self,cid,uid,name=""):
        u=self.get_user(cid,uid,name)
        u["mutes"]+=1
        # 3/3 мута -> 1 варн
        if u["mutes"]>=3:
            u["mutes"]=0
            u["warns"]+=1
            self.save()
            return "warn", u["warns"], u["mutes"]
        self.save()
        return "mute", u["warns"], u["mutes"]
    def get_stats(self,cid,uid):
        u=self.get_user(cid,uid)
        return u["mutes"], u["warns"]

db=DB()
_flood={}
_captcha={}

def esc(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} if m else False
def contains_bad(text):
    t=str(text or "").lower()
    for w in BAD_WORDS:
        if re.search(re.escape(w.lower()), t, re.IGNORECASE): return w
    return None
def contains_link(text):
    for p in LINK_PATTERNS:
        if re.search(p, str(text or ""), re.IGNORECASE): return True
    return False
def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); lst=_flood.get(key,[]); lst=[x for x in lst if now-x<=5]; lst.append(now); _flood[key]=lst; return len(lst)>=4
def is_spam(text):
    if not text: return False
    if len(text)>800: return "довге повідомлення"
    if re.search(r"(.)\1{7,}", text): return "спам символами"
    if len(text)>15 and sum(1 for c in text if c.isupper())/len(text)>0.8: return "капс"
    emoji_count=len(re.findall(r"[😀-🙏🌀-🗿🚀-🛿]", text))
    if emoji_count>12: return "багато емодзі"
    return False

async def is_admin(bot, msg):
    if msg.sender_chat and msg.chat and msg.sender_chat.id==msg.chat.id: return True
    if not msg.from_user: return False
    try:
        m=await bot.get_chat_member(msg.chat.id, msg.from_user.id)
        return is_admin_obj(m)
    except: return False

# ==================== КАПЧА ====================
def kb_verify(uid):
    b=InlineKeyboardBuilder()
    b.button(text="✅ Я не бот — пройти перевірку", callback_data=f"verify_{uid}")
    return b.as_markup()

def kb_captcha(uid, correct, opts):
    b=InlineKeyboardBuilder()
    for e in opts:
        b.button(text=e, callback_data=f"cap_{uid}_{e}_{correct}")
    b.adjust(2,2)
    return b.as_markup()

# ==================== ОСНОВНА ЛОГІКА ПОКАРАННЯ ====================
async def punish_user(bot, chat_id, user, reason, punish_type="мут"):
    """
    Ланцюжок: мут 1/3 -> 2/3 -> 3/3 -> варн 1/3 -> 2/3 -> 3/3 -> бан
    """
    cid=str(chat_id)
    mutes_before, warns_before = db.get_stats(cid, user.id)
    
    # Додаємо мут
    result, warns_after, mutes_after = db.add_mute(cid, user.id, user.first_name)
    
    # Видаляємо повідомлення порушника якщо є
    # (видалення робиться в auto_mod, тут тільки покарання)
    
    if result=="mute":
        # Просто мут
        try:
            await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=10))
            await bot.send_message(chat_id, f"🔇 <b>Авто-покарання</b> ✨\n👤 {esc(user.first_name)} | ID: <code>{user.id}</code>\n📛 Причина: {esc(reason)}\n🔇 Покарання: мут 10хв [{mutes_after}/3]\n⚠️ Варни: [{warns_after}/3]\n\n<i>3/3 мута = 1 варн, 3/3 варна = бан</i>")
        except Exception as e:
            await bot.send_message(chat_id, f"🔇 {esc(user.first_name)} порушив: {esc(reason)} — мут {mutes_after}/3, варн {warns_after}/3, але не вдалося замутити: {e}")
    
    elif result=="warn":
        # 3 мута превратились в варн
        if warns_after>=3:
            # 3/3 варна = бан
            try:
                await bot.ban_chat_member(chat_id, user.id)
                # Скидаємо
                u=db.get_user(cid, user.id)
                u["mutes"]=0; u["warns"]=0; db.save()
                await bot.send_message(chat_id, f"💥 <b>Авто-бан</b> ✨\n👤 {esc(user.first_name)} | ID: <code>{user.id}</code>\n📛 Причина: {esc(reason)}\n🔨 Покарання: бан назавжди\n⚠️ Досяг {warns_after}/3 варнів (3/3 мута = 1 варн)\n\n<i>Ланцюжок: мут 3/3 → варн, варн 3/3 → бан</i>")
            except Exception as e:
                await bot.send_message(chat_id, f"💥 {esc(user.first_name)} мав отримати бан за {esc(reason)}, але помилка: {e}")
        else:
            # Варн видано
            try:
                await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=30))
                await bot.send_message(chat_id, f"⚠️ <b>Авто-варн</b> ✨\n👤 {esc(user.first_name)} | ID: <code>{user.id}</code>\n📛 Причина: {esc(reason)} + 3/3 мута\n🔇 Покарання: мут 30хв + варн\n🔇 Мути: [0/3] (скинуто)\n⚠️ Варни: [{warns_after}/3]\n\n<i>3/3 варна = бан</i>")
            except:
                await bot.send_message(chat_id, f"⚠️ {esc(user.first_name)} отримав варн {warns_after}/3 за {esc(reason)} (3/3 мута)")

# ==================== КОМАНДИ ====================
async def cmd_start(message: Message, bot: Bot):
    if message.chat.type=="private":
        await message.answer(f"<b>AETHER SIMPLE</b> ✨\n\nЯ працюю тільки в групі і все роблю автоматично:\n\n🤬 Мат → мут 10хв\n🔗 Лінк → мут 5хв\n🌊 Флуд 4 повід/5с → мут 10хв\n📢 Спам → мут\n\n<b>Ланцюжок:</b>\n🔇 Мут [1/3] → [2/3] → [3/3] = ⚠️ Варн [1/3]\n⚠️ Варн [1/3] → [2/3] → [3/3] = 🔨 Бан\n\n👋 Вітання + прощання + капча з емодзі\n\nДодай мене в групу і дай адмінку — я сам все зроблю!")
    else:
        ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
        await message.answer(f"✨ <b>AETHER SIMPLE</b> активний в {esc(message.chat.title or 'чаті')}!\n\nЯ працюю автоматично:\n🔇 Мут → ⚠️ Варн → 🔨 Бан\n3/3 мута = 1 варн, 3/3 варна = бан\n\n👋 Вітання/прощання + 🤖 Капча\n\nВ чаті пишу хто що порушив.")

# ==================== АВТО-МОДЕРАЦІЯ - ГОЛОВНЕ ====================
async def auto_mod(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    if message.sender_chat and message.chat and message.sender_chat.id==message.chat.id: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem): return
    except: pass

    text=message.text or message.caption or ""
    user=message.from_user
    cid=str(message.chat.id)
    
    # Оновлюємо лічильник повідомлень
    u=db.get_user(cid, user.id, user.first_name)
    u["messages"]=u.get("messages",0)+1
    db.save()

    # 1. ФЛУД
    if is_flood(message.chat.id, user.id):
        try: await message.delete()
        except: pass
        _flood[(message.chat.id, user.id)]=[]
        await punish_user(bot, message.chat.id, user, "флуд (4 повід. за 5с)", "мут")
        return

    # 2. СПАМ
    spam_reason=is_spam(text)
    if spam_reason:
        try: await message.delete()
        except: pass
        await punish_user(bot, message.chat.id, user, f"спам ({spam_reason})", "мут")
        return

    # 3. ЛІНКИ
    if contains_link(text):
        try: await message.delete()
        except: pass
        await punish_user(bot, message.chat.id, user, "лінк / реклама", "мут")
        return

    # 4. МАТИ / ОБРАЗИ
    bad=contains_bad(text)
    if bad:
        try: await message.delete()
        except: pass
        await punish_user(bot, message.chat.id, user, f"мат / образа ({bad})", "мут")
        return

# ==================== ВІТАННЯ / ПРОЩАННЯ / КАПЧА ====================
async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    ch=db.get_chat(event.chat.id)
    
    # ХТОСЬ ЗАЙШОВ
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        
        # Додаємо в базу
        db.get_user(event.chat.id, user.id, user.first_name)
        
        # Капча - красива
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(event.chat.id, f"👋 Привіт, {esc(user.first_name)}! Ласкаво просимо в {esc(event.chat.title or 'чат')} ✨\n\nЩоб довести що ти не бот, пройди перевірку:", reply_markup=kb_verify(user.id))
        except Exception as e:
            logger.warning(f"captcha failed: {e}")
            # Якщо не вдалося пройти капчу - просто вітаємо
            try:
                await bot.send_message(event.chat.id, f"👋 Привіт, {esc(user.first_name)}! Ласкаво просимо в {esc(event.chat.title or 'чат')} ✨ Раді тебе бачити! 🫶")
            except: pass
    
    # ХТОСЬ ВИЙШОВ
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        try:
            await bot.send_message(event.chat.id, f"👋 Бувай, {esc(user.first_name)}! Сумуватимемо 💫 Повертайся знову ✨")
        except: pass

async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return
    try:
        await bot.send_message(event.chat.id, f"✨ <b>AETHER</b> активований в {esc(event.chat.title or 'чаті')}!\n\nЯ працюю автоматично без налаштувань:\n🔇 Мут [1/3] [2/3] [3/3] → ⚠️ Варн [1/3]\n⚠️ Варн [1/3] [2/3] [3/3] → 🔨 Бан\n\n🤬 Мат, 🔗 Лінк, 🌊 Флуд, 📢 Спам → мут\n👋 Вітання + прощання + 🤖 Капча\n\nВ чаті пишу хто що порушив ✨")
    except: pass

async def cb_handler(call: CallbackQuery, bot: Bot):
    data=call.data
    
    if data.startswith("verify_"):
        uid=int(data.split("_")[1])
        if call.from_user.id!=uid:
            return await call.answer("Киш киш,це не твоя капча!", show_alert=True)
        emojis=["🦊","🐶","🐱","🐰","🦁","🐯","🐻","🐼","🦄","🐙"]
        correct=random.choice(emojis); opts=random.sample(emojis,4)
        if correct not in opts: opts[0]=correct
        random.shuffle(opts)
        _captcha[(call.message.chat.id, uid)]=correct
        await call.message.edit_text(f"<b>🤖 Перевірка AETHER</b> ✨\n\n{esc(call.from_user.first_name)}, доведи що ти не бот — натисни <b>{correct}</b>:", reply_markup=kb_captcha(uid, correct, opts))
        await call.answer()
        return
    
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
                await call.message.edit_text(f"👋 Привіт, {esc(call.from_user.first_name)}! Ласкаво просимо в {esc(call.message.chat.title or 'чат')} ✨\n\n✅ Перевірку пройдено! Раді тебе бачити 🫶")
            except:
                await call.message.edit_text("✅ Перевірку пройдено! Ласкаво просимо ✨")
            await call.answer("Вітаємо! ✨")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_s)
                await bot.unban_chat_member(call.message.chat.id, uid_s)
                await call.message.edit_text(f"🚫 {esc(call.from_user.first_name)} не пройшов перевірку і кікнутий")
            except: pass
            await call.answer("Невірно! ❌", show_alert=True)
        return

async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def h_start(m: Message): await cmd_start(m, bot)

    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
    async def h_bot_admin(e: ChatMemberUpdated): await bot_admin_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)

    logger.info("AETHER SIMPLE v12 started - mute->warn->ban chain!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
