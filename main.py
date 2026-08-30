import os, re, json, asyncio, logging, random, time
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, ChatPermissions
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER, ADMINISTRATOR
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN missing!")
    exit(1)

DB_FILE = "database.json"

BAD_WORDS = ["бля","блять","блядь","сука","сучка","хуй","хуйня","хуйло","пизда","пиздец","єба","ебать","нахуй","похуй","охуел","заебал","долбоёб","уебок","мудак","гандон","пидор","шлюха","жопа","говно","fuck","shit","bitch","asshole","dick","cunt","whore","slut","bastard","faggot","nigger","motherfucker","дебил","дурак","тварь","мразь","ублюдок","сволочь","гнида","чмо","лох","курва","срака","лайно","мудила","підар","шмара","довбойоб","уйобок","єблан","єбало","нахуя","хулі","пиздобол","єбанутий","сраний","залупа","блядіна"]

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("V12_1")

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
        except Exception as e: logger.error(f"Save failed {e}")
    def get_chat(self,cid):
        cid=str(cid)
        if cid not in self.data["chats"]:
            self.data["chats"][cid]={"title":"", "users":{}}
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("users",{})
        return ch
    def get_user(self,cid,uid,name=""):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"name":name or "Unknown","mutes":0,"warns":0,"messages":0,"bans":0}
            self.save()
        u=ch["users"][uid]
        if name: u["name"]=name
        u.setdefault("mutes",0); u.setdefault("warns",0); u.setdefault("messages",0); u.setdefault("bans",0)
        return u
    def add_mute(self,cid,uid,name=""):
        """Додає мут, повертає (тип, мути, варни) - все зберігається в базу"""
        u=self.get_user(cid,uid,name)
        u["mutes"]+=1
        mutes=u["mutes"]
        warns=u["warns"]
        # 3/3 мута -> 1 варн
        if mutes>=3:
            u["mutes"]=0
            u["warns"]+=1
            mutes=0
            warns=u["warns"]
            self.save()
            # Перевірка чи варни досягли 3
            if warns>=3:
                return "ban", mutes, warns
            return "warn", mutes, warns
        self.save()
        return "mute", mutes, warns
    def add_warn_direct(self,cid,uid,name=""):
        """Прямий варн (для команди /warn)"""
        u=self.get_user(cid,uid,name)
        u["warns"]+=1
        warns=u["warns"]
        self.save()
        if warns>=3:
            return "ban", 0, warns
        return "warn", 0, warns
    def clear_mutes(self,cid,uid):
        u=self.get_user(cid,uid); u["mutes"]=0; self.save()
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()
    def clear_all(self,cid,uid):
        u=self.get_user(cid,uid); u["mutes"]=0; u["warns"]=0; self.save()
    def dec_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=max(0,u["warns"]-1); self.save(); return u["warns"]
    def dec_mute(self,cid,uid):
        u=self.get_user(cid,uid); u["mutes"]=max(0,u["mutes"]-1); self.save(); return u["mutes"]
    def get_stats(self,cid,uid):
        u=self.get_user(cid,uid); return u["mutes"], u["warns"]

db=Database()
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
    if len(re.findall(r"[😀-🙏🌀-🗿🚀-🛿]", text))>12: return "багато емодзі"
    return False

async def is_admin(bot, message):
    if message.sender_chat and message.chat and message.sender_chat.id==message.chat.id: return True
    if not message.from_user: return False
    try:
        m=await bot.get_chat_member(message.chat.id, message.from_user.id)
        return is_admin_obj(m)
    except: return False

def kb_verify(uid):
    b=InlineKeyboardBuilder(); b.button(text="✅ Я не бот — пройти перевірку", callback_data=f"verify_{uid}"); return b.as_markup()
def kb_captcha(uid, correct, opts):
    b=InlineKeyboardBuilder()
    for e in opts: b.button(text=e, callback_data=f"cap_{uid}_{e}_{correct}")
    b.adjust(2,2); return b.as_markup()

async def punish_chain(bot, chat_id, user, reason):
    """Основна функція покарання - мут 5хв, все в базу, бан працює!"""
    cid=str(chat_id)
    result, mutes, warns = db.add_mute(cid, user.id, user.first_name)
    
    if result=="mute":
        # Мут 5хв як ти просив
        try:
            await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=5))
            await bot.send_message(chat_id, f"🔇 <b>Покарання</b>\n👤 {esc(user.first_name)} | <code>{user.id}</code>\n📛 Причина: {esc(reason)}\n🔇 Мут: 5хв [{mutes}/3]\n⚠️ Варн: [{warns}/3]\n💾 Збережено в базу\n<i>3/3 мута → 1 варн, 3/3 варна → бан</i>")
        except Exception as e:
            await bot.send_message(chat_id, f"🔇 {esc(user.first_name)} — {esc(reason)} — мут {mutes}/3, варн {warns}/3 (не вдалося замутити: {e})")
    
    elif result=="warn":
        # 3/3 мута -> варн
        try:
            await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=15))
            await bot.send_message(chat_id, f"⚠️ <b>Варн</b>\n👤 {esc(user.first_name)} | <code>{user.id}</code>\n📛 Причина: {esc(reason)} + 3/3 мута\n🔇 Мут: 15хв + варн\n🔇 Мути: [0/3] скинуто\n⚠️ Варни: [{warns}/3]\n💾 Збережено в базу\n<i>3/3 варна → бан</i>")
        except Exception as e:
            await bot.send_message(chat_id, f"⚠️ {esc(user.first_name)} варн {warns}/3 за {esc(reason)}")
    
    elif result=="ban":
        # 3/3 варна -> бан - ТЕПЕР ПРАЦЮЄ!
        try:
            await bot.ban_chat_member(chat_id, user.id)
            u=db.get_user(cid, user.id)
            u["bans"]=u.get("bans",0)+1
            u["mutes"]=0; u["warns"]=0
            db.save()
            await bot.send_message(chat_id, f"💥 <b>БАН</b>\n👤 {esc(user.first_name)} | <code>{user.id}</code>\n📛 Причина: {esc(reason)} — досяг {warns}/3 варнів\n🔨 Покарання: бан назавжди\n💾 Збережено в базу (банив: {u['bans']} раз)\n\nЛанцюжок: мут [3/3] → варн, варн [3/3] → бан")
        except Exception as e:
            logger.error(f"Ban failed {e}")
            await bot.send_message(chat_id, f"💥 {esc(user.first_name)} мав отримати бан за {esc(reason)} (3/3 варна), але помилка: {e} — перевір чи бот адмін!")

def parse_duration(s):
    if not s: return 5*60
    s=str(s).lower().strip()
    import re
    m=re.fullmatch(r"(\d+)\s*([smhd])?", s)
    if not m: return 5*60
    v=int(m.group(1)); u=m.group(2) or "m"
    mult={"s":1,"m":60,"h":3600,"d":86400}
    return v*mult[u]

def format_dur(sec):
    sec=int(sec)
    if sec<60: return f"{sec}с"
    if sec<3600: return f"{sec//60}хв"
    if sec<86400: return f"{sec//3600}год"
    return f"{sec//86400}д"

async def cmd_start(message: Message, bot: Bot):
    if message.chat.type=="private":
        await message.answer("<b>AETHER</b> ✨\n\n<b>Авто:</b> мут 5хв [1/3][2/3][3/3] → варн [1/3][2/3][3/3] → бан\nВсе в базу, в чат пише хто порушив\n\n<b>Адмін-команди (відповідь на юзера):</b>\n/mute 5m причина або !mute 5m — мут\n/ban причина або !ban — бан\n/warn причина або !warn — варн\n/unmute або !unmute — зняти мут\n/unban або !unban — розбан\n/unwarn або !unwarn — зняти варн\n/clearwarns /clearmutes /clearall\n/warns /stats\n\nПідтримує / і ! префікс!\n\nДодай в групу і дай адмінку!")
    else:
        ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
        await message.answer(f"✨ <b>AETHER</b> активний!\n\nАвто: мут 5хв [1/3]→[2/3]→[3/3]=варн→[3/3]=бан\nВсе в базу\n\nАдмін: /mute /ban /warn /unmute /unban /unwarn + з ! теж працює\nПриклад: відповідь на порушника /mute 10m спам або !ban")

# ===== РУЧНІ КОМАНДИ АДМІНА /mute /ban /warn =====
async def cmd_mute_manual(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай на повідомлення того кого мутиш!\nПриклад: /mute 5m спам або !mute 10m")
    args=message.text.split()
    # /mute 5m причина або /mute причина
    dur=5*60
    reason="Порушення правил"
    if len(args)>=2:
        # Перевіряємо чи другий аргумент це час
        try:
            # Спробуємо парсити як час
            if any(c.isdigit() for c in args[1]):
                dur=parse_duration(args[1])
                reason=" ".join(args[2:]) if len(args)>2 else "Порушення правил"
            else:
                reason=" ".join(args[1:])
        except:
            reason=" ".join(args[1:])
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=dur))
        # Зберігаємо в базу як мут
        u=db.get_user(message.chat.id, target.id, target.first_name)
        u["mutes"]=u.get("mutes",0)+1
        if u["mutes"]>=3:
            u["mutes"]=0
            u["warns"]=u.get("warns",0)+1
        db.save()
        mutes,warns=db.get_stats(message.chat.id, target.id)
        await message.answer(f"🔇 <b>Мут видано адміном</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n📛 Причина: {esc(reason)}\n🔇 Покарання: мут {format_dur(dur)}\n🔇 Мути: [{mutes}/3] | ⚠️ Варни: [{warns}/3]\n👮 Адмін: {esc(message.from_user.first_name)}\n💾 Збережено в базу")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ Не вдалося: {e}")

async def cmd_ban_manual(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай на повідомлення! Приклад: /ban спам або !ban")
    reason=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else "Порушення правил"
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        u=db.get_user(message.chat.id, target.id, target.first_name)
        u["bans"]=u.get("bans",0)+1
        u["mutes"]=0; u["warns"]=0
        db.save()
        await message.answer(f"🔨 <b>Бан видано адміном</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n📛 Причина: {esc(reason)}\n🔨 Покарання: бан назавжди\n👮 Адмін: {esc(message.from_user.first_name)}\n💾 Збережено в базу (банів: {u['bans']})")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_warn_manual(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай! Приклад: /warn спам або !warn")
    reason=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else "Порушення правил"
    result,mutes,warns=db.add_warn_direct(message.chat.id, target.id, target.first_name) if hasattr(db, 'add_warn_direct') else db.add_mute(message.chat.id, target.id, target.first_name)
    # Використаємо прямий варн
    if result!="ban":
        # Якщо не бан, додаємо варн через add_warn_direct
        # Перезапишемо логіку: прямий варн
        u=db.get_user(message.chat.id, target.id, target.first_name)
        # Вже додали вище, перевіримо
        if result=="mute":
            # add_mute додав мут, а нам треба варн - виправимо
            u["mutes"]=max(0,u.get("mutes",1)-1)
            u["warns"]=u.get("warns",0)+1
            db.save()
            mutes,warns=db.get_stats(message.chat.id, target.id)
            result="warn"
    
    if result=="ban" or warns>=3:
        try:
            await bot.ban_chat_member(message.chat.id, target.id)
            u=db.get_user(message.chat.id, target.id)
            u["mutes"]=0; u["warns"]=0; db.save()
            await message.answer(f"💥 <b>Бан за варни</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n📛 Причина: {esc(reason)} — {warns}/3 варна\n🔨 Бан назавжди\n👮 Адмін: {esc(message.from_user.first_name)}")
        except Exception as e:
            await message.answer(f"⚠️ {esc(target.first_name)} варн {warns}/3, мав бути бан, але помилка: {e}")
    else:
        try:
            await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=10))
            await message.answer(f"⚠️ <b>Варн видано адміном</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n📛 Причина: {esc(reason)}\n⚠️ Варни: [{warns}/3] | 🔇 Мути: [{mutes}/3]\n👮 Адмін: {esc(message.from_user.first_name)}\n💾 Збережено в базу")
        except:
            await message.answer(f"⚠️ Варн {warns}/3 видано {esc(target.first_name)} за {esc(reason)}")


async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай на повідомлення того кого треба розмутити!")
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        db.clear_mutes(message.chat.id, target.id)
        await message.answer(f"🔊 <b>Розмут</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n✅ Мут знято, мути очищені в базі [0/3]\n👮 Адмін: {esc(message.from_user.first_name)}")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        db.clear_all(message.chat.id, target.id)
        await message.answer(f"✅ <b>Розбан</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n✅ Бан знято, всі покарання очищені в базі\n👮 Адмін: {esc(message.from_user.first_name)}")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unwarn(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    new=db.dec_warn(message.chat.id, target.id)
    await message.answer(f"✅ <b>Знято варн</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n⚠️ Варни: [{new}/3] (було більше)\n💾 Оновлено в базі\n👮 Адмін: {esc(message.from_user.first_name)}")

async def cmd_clearwarns(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    db.clear_warns(message.chat.id, target.id)
    await message.answer(f"✅ <b>Варни очищені</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n⚠️ Варни: [0/3]\n💾 Збережено в базу")

async def cmd_clearmutes(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    db.clear_mutes(message.chat.id, target.id)
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
    except: pass
    await message.answer(f"✅ <b>Мути очищені</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n🔇 Мути: [0/3]\n💾 Збережено в базу")

async def cmd_clearall(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    db.clear_all(message.chat.id, target.id)
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await bot.unban_chat_member(message.chat.id, target.id)
    except: pass
    await message.answer(f"✅ <b>Всі покарання очищені</b>\n👤 {esc(target.first_name)} | <code>{target.id}</code>\n🔇 Мути: [0/3] | ⚠️ Варни: [0/3]\n💾 Збережено в базу")

async def cmd_warns(message: Message, bot: Bot):
    if message.reply_to_message and message.reply_to_message.from_user:
        target=message.reply_to_message.from_user
        mutes,warns=db.get_stats(message.chat.id, target.id)
        await message.answer(f"📊 <b>Статистика {esc(target.first_name)}</b>\n👤 ID: <code>{target.id}</code>\n🔇 Мути: [{mutes}/3]\n⚠️ Варни: [{warns}/3]\n💾 В базі")
    else:
        ch=db.get_chat(message.chat.id)
        warned=[(uid,u) for uid,u in ch["users"].items() if u.get("mutes",0)>0 or u.get("warns",0)>0]
        if not warned:
            await message.answer("✅ Нема покараних користувачів — всі чисті ✨")
        else:
            txt="<b>📊 Список покарань</b>\n\n"
            for uid,u in sorted(warned, key=lambda x: (x[1].get("warns",0), x[1].get("mutes",0)), reverse=True)[:20]:
                txt+=f"👤 {esc(u.get('name','Unknown'))} | <code>{uid}</code>\n   🔇 Мути: [{u.get('mutes',0)}/3] | ⚠️ Варни: [{u.get('warns',0)}/3]\n"
            txt+="\n💾 Все з бази"
            await message.answer(txt)

async def cmd_stats(message: Message):
    ch=db.get_chat(message.chat.id)
    total=len(ch["users"])
    total_mutes=sum([u.get("mutes",0) for u in ch["users"].values()])
    total_warns=sum([u.get("warns",0) for u in ch["users"].values()])
    await message.answer(f"<b>📊 Статистика {esc(ch.get('title','чату'))}</b>\n\n👥 Юзерів в базі: {total}\n🔇 Всього мутів: {total_mutes}\n⚠️ Всього варнів: {total_warns}\n\nЛанцюжок: мут 5хв [3/3] → варн, варн [3/3] → бан\n💾 Все зберігається в базу")

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
    u=db.get_user(message.chat.id, user.id, user.first_name)
    u["messages"]=u.get("messages",0)+1
    db.save()

    if is_flood(message.chat.id, user.id):
        try: await message.delete()
        except: pass
        _flood[(message.chat.id, user.id)]=[]
        await punish_chain(bot, message.chat.id, user, "флуд (4 повід. за 5с)")
        return
    spam=is_spam(text)
    if spam:
        try: await message.delete()
        except: pass
        await punish_chain(bot, message.chat.id, user, f"спам ({spam})")
        return
    if contains_link(text):
        try: await message.delete()
        except: pass
        await punish_chain(bot, message.chat.id, user, "лінк / реклама")
        return
    bad=contains_bad(text)
    if bad:
        try: await message.delete()
        except: pass
        await punish_chain(bot, message.chat.id, user, f"мат / образа ({bad})")
        return

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        db.get_user(event.chat.id, user.id, user.first_name)
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(event.chat.id, f"👋 Привіт, {esc(user.first_name)}! Ласкаво в {esc(event.chat.title or 'чат')} ✨\n\nПройди перевірку:", reply_markup=kb_verify(user.id))
        except:
            try: await bot.send_message(event.chat.id, f"👋 Привіт, {esc(user.first_name)}! Ласкаво в {esc(event.chat.title or 'чат')} ✨")
            except: pass
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        try: await bot.send_message(event.chat.id, f"👋 Бувай, {esc(user.first_name)}! Сумуватимемо 💫")
        except: pass

async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return
    try:
        await bot.send_message(event.chat.id, f"✨ <b>AETHER</b> активований!\n\n🔇 Мут 5хв [1/3][2/3][3/3] → ⚠️ Варн [1/3][2/3][3/3] → 🔨 Бан\n💾 Все в базу\n🤬 Мат, 🔗 Лінк, 🌊 Флуд, 📢 Спам → авто-покарання\n👋 Вітання/прощання + 🤖 Капча\n\nАдмін-команди:\n/unmute /unban /unwarn /clearwarns /clearmutes /clearall /warns /stats")
    except: pass

async def cb_handler(call: CallbackQuery, bot: Bot):
    data=call.data
    if data.startswith("verify_"):
        uid=int(data.split("_")[1])
        if call.from_user.id!=uid: return await call.answer("Не твоя капча!", show_alert=True)
        emojis=["🦊","🐶","🐱","🐰","🦁","🐯"]; correct=random.choice(emojis); opts=random.sample(emojis,4)
        if correct not in opts: opts[0]=correct
        random.shuffle(opts)
        _captcha[(call.message.chat.id, uid)]=correct
        await call.message.edit_text(f"<b>🤖 Перевірка</b> ✨ {esc(call.from_user.first_name)}, натисни <b>{correct}</b>:", reply_markup=kb_captcha(uid, correct, opts))
        await call.answer(); return
    if data.startswith("cap_"):
        _, uid_s, chosen, correct = data.split("_",3)
        uid_s=int(uid_s)
        if call.from_user.id!=uid_s: return await call.answer("Не твоя капча!", show_alert=True)
        if chosen==correct:
            _captcha.pop((call.message.chat.id, uid_s),None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid_s, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                await call.message.edit_text(f"👋 Привіт, {esc(call.from_user.first_name)}! Ласкаво в {esc(call.message.chat.title or 'чат')} ✨ ✅ Перевірку пройдено! 🫶")
            except: await call.message.edit_text("✅ Перевірку пройдено ✨")
            await call.answer("Вітаємо!")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_s)
                await bot.unban_chat_member(call.message.chat.id, uid_s)
                await call.message.edit_text(f"🚫 {esc(call.from_user.first_name)} не пройшов капчу")
            except: pass
            await call.answer("Невірно!", show_alert=True)
        return

async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def h_start(m: Message): await cmd_start(m, bot)
    
    # Адмін-команди з / префіксом
    @dp.message(Command("mute"))
    async def h_mute(m: Message): await cmd_mute_manual(m, bot)
    @dp.message(Command("ban"))
    async def h_ban(m: Message): await cmd_ban_manual(m, bot)
    @dp.message(Command("warn"))
    async def h_warn(m: Message): await cmd_warn_manual(m, bot)
    @dp.message(Command("unmute"))
    async def h_unmute(m: Message): await cmd_unmute(m, bot)
    @dp.message(Command("unban"))
    async def h_unban(m: Message): await cmd_unban(m, bot)
    @dp.message(Command("unwarn"))
    async def h_unwarn(m: Message): await cmd_unwarn(m, bot)
    @dp.message(Command("clearwarns"))
    async def h_cwarn(m: Message): await cmd_clearwarns(m, bot)
    @dp.message(Command("clearmutes"))
    async def h_cmutes(m: Message): await cmd_clearmutes(m, bot)
    @dp.message(Command("clearall"))
    async def h_call(m: Message): await cmd_clearall(m, bot)
    @dp.message(Command("warns"))
    async def h_warns(m: Message): await cmd_warns(m, bot)
    @dp.message(Command("mutes"))
    async def h_mutes(m: Message): await cmd_warns(m, bot)
    @dp.message(Command("stats"))
    async def h_stats(m: Message): await cmd_stats(m)

    # Адмін-команди з ! префіксом (!ban !mute !warn !unmute !unban !unwarn)
    @dp.message(F.text.startswith("!"))
    async def h_bang(m: Message):
        txt=m.text or ""
        if not txt.startswith("!"): return
        cmd=txt.split()[0].lower()
        # Переписуємо в / формат
        if cmd in ["!mute"]:
            await cmd_mute_manual(m, bot)
        elif cmd in ["!ban"]:
            await cmd_ban_manual(m, bot)
        elif cmd in ["!warn"]:
            await cmd_warn_manual(m, bot)
        elif cmd in ["!unmute"]:
            await cmd_unmute(m, bot)
        elif cmd in ["!unban"]:
            await cmd_unban(m, bot)
        elif cmd in ["!unwarn"]:
            await cmd_unwarn(m, bot)
        elif cmd in ["!clearwarns"]:
            await cmd_clearwarns(m, bot)
        elif cmd in ["!clearmutes"]:
            await cmd_clearmutes(m, bot)
        elif cmd in ["!clearall"]:
            await cmd_clearall(m, bot)
        elif cmd in ["!warns","!mutes"]:
            await cmd_warns(m, bot)
        elif cmd in ["!stats"]:
            await cmd_stats(m)

    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)
    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)
    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
    async def h_admin(e: ChatMemberUpdated): await bot_admin_handler(e, bot)
    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)

    logger.info("V12.1 SIMPLE FIXED - mute 5min, ban works, all in DB!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
