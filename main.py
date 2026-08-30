
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
        if cid not in self.data["chats"]: self.data["chats"][cid]={"title":"","users":{}}; self.save()
        ch=self.data["chats"][cid]; ch.setdefault("users",{}); return ch
    def get_user(self,cid,uid,name=""):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]: ch["users"][uid]={"name":name or "Unknown","mutes":0,"warns":0,"bans":0}; self.save()
        u=ch["users"][uid]
        if name: u["name"]=name
        u.setdefault("mutes",0); u.setdefault("warns",0); u.setdefault("bans",0); return u
    def add_mute(self,cid,uid,name=""):
        u=self.get_user(cid,uid,name); u["mutes"]+=1
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

# ===== ОПИС БОТА - САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ =====
BOT_DESCRIPTION = """
<b>🔥 AETHER — САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ 2026 🔥</b>

Йо, я не просто бот, я — легенда чату, базарю з матами, але по-доброму і смішно 😎

<b>💎 МОЇ ПЛЮСИ:</b>
🤖 <b>Працюю сам</b> — без налаштувань, без кнопок, все авто
⚡ <b>Миттєвий</b> — видаляю мат, лінк, флуд за 0.1с
💾 <b>Пам'ятаю все</b> — база на 1000+ порушників, нічого не забуваю
😂 <b>Смішний</b> — пишу ржачно, з матами, але нікого не ображаю, всі ржуть
🎯 <b>Справедливий</b> — мут 5хв [1/3][2/3][3/3] → варн [1/3][2/3][3/3] → бан (отлітай в космос 🚀)
👋 <b>Ввічливий</b> — вітаю новеньких, прощаюсь з тими хто йде
🤖 <b>Капча-топ</b> — перевірка з емодзі, як в Google, але веселіша
🔇 <b>Не сплю</b> — 24/7 в чаті, слідкую за порядком
🎭 <b>Свій чувак</b> — базарю на молодьожному сленгу, з матами, але любя ❤️

<b>🎮 ЯК ПРАЦЮЮ:</b>
Пишеш мат/спам/флуд/рекламу → я видаляю і даю мут 5хв [1/3]
Ще раз → [2/3]
Ще раз → [3/3] = варн [1/3] + мут 15хв
3 варна → отлітаєш в космос (бан) 🚀

<b>👮 ДЛЯ АДМІНА:</b>
/mute 5m або !mute — замутити
/ban або !ban — забанити (отлітай маленький 🚀)
/warn або !warn — варн
/unmute /unban /unwarn /warns /stats — зняти і подивитись

Я — їбаний бот, але свій, не обіжайтесь, я просто так базарю 😂❤️
"""

async def punish(bot, chat_id, user, reason):
    cid=str(chat_id)
    result,mutes,warns = db.add_mute(cid, user.id, user.first_name)
    if result=="mute":
        try:
            await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=5))
            msgs=[
                f"😅 Опа, {esc(user.first_name)} попався на гарячому! За {esc(reason)} лови тайм-аут 5хв, сходи за чіпсами 🍿\n🔇 [{mutes}/3] | ⚠️ [{warns}/3] — я бот, я все бачу",
                f"🤭 {esc(user.first_name)}, ну ти даєш, за {esc(reason)} — мут 5хв 😂 Посиди, подумай, я тут поки мемчики покидаю\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]",
                f"🫣 {esc(user.first_name)}, бля, знову ти? За {esc(reason)} — мут 5хв, я не злий, просто порядок люблю\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]",
                f"😂 {esc(user.first_name)} — головний герой чату сьогодні! За {esc(reason)} — мут 5хв в куток 😅\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]",
                f"👀 {esc(user.first_name)} спалився! За {esc(reason)} — мут 5хв, відпочинь, бро, я посторожу чат\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]"
            ]
            await bot.send_message(chat_id, random.choice(msgs))
        except Exception as e: await bot.send_message(chat_id, f"😅 {esc(user.first_name)} мут {mutes}/3: {e}")
    elif result=="warn":
        try:
            await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=15))
            msgs=[
                f"😬 {esc(user.first_name)}, ти вже майже чемпіон! За {esc(reason)} + 3/3 мута — варн [{warns}/3] 🏆\n🔇 Мут 15хв, мути скинув [0/3] — ще один варн і буде фінальний бос — бан 🚀",
                f"🤦‍♂️ Бля, {esc(user.first_name)}, ну скільки можна? Варн [{warns}/3] за {esc(reason)} 😤 Посиди 15хв, я тут поки чат посторожу",
                f"🫠 {esc(user.first_name)}, братан, ти вже на волоску, варн [{warns}/3] за {esc(reason)} — ще один і полетиш в космос, я попереджав 😅",
                f"😅 {esc(user.first_name)} збирає варни як покемонів! [{warns}/3] за {esc(reason)} — ще один і буде еволюція в бан 🚀"
            ]
            await bot.send_message(chat_id, random.choice(msgs))
        except: await bot.send_message(chat_id, f"⚠️ {esc(user.first_name)} варн [{warns}/3] за {esc(reason)}")
    elif result=="ban":
        try:
            await bot.ban_chat_member(chat_id, user.id)
            u=db.get_user(cid, user.id); u["mutes"]=0; u["warns"]=0; u["bans"]=u.get("bans",0)+1; db.save()
            msgs=[
                f"🚀 {esc(user.first_name).upper()} ПОЛЕТІВ В КОСМОС! 🚀\n📛 За {esc(reason)} — 3/3 варна, ти легенда, але пора відпочити\n🔨 Бан назавжди, було весело, повернешся — обнімем ❤️",
                f"💥 {esc(user.first_name)} — НУ ВСЬО, ТИ ДОГРАВСЯ, ФІНАЛЬНИЙ БОС ПОВАЛЕНИЙ 😂💥\n📛 {esc(reason)} — 3/3 варна, отлітай маленький 🚀 Було прикольно, але правила є правила",
                f"😂 {esc(user.first_name)} офіційно чемпіон чату! 3/3 варна за {esc(reason)} 🏆\n🚀 Отлітає в бан, але було весело, повертайся потім!",
                f"🛸 {esc(user.first_name).upper()} ВІДПРАВЛЯЄТЬСЯ НА МАРС 🛸\n📛 {esc(reason)} — 3/3 варна, ну ти даєш, бро\n🔨 Бан, але ми тебе любим, повертайся коли охолонеш ❤️"
            ]
            await bot.send_message(chat_id, random.choice(msgs))
        except Exception as e: await bot.send_message(chat_id, f"💥 {esc(user.first_name)} мав полетіть, але помилка: {e}")

async def cmd_start(message: Message, bot: Bot):
    if message.chat.type=="private":
        await message.answer(BOT_DESCRIPTION)
    else:
        db.get_chat(message.chat.id)["title"]=message.chat.title or ""; db.save()
        await message.answer(f"🔥 <b>AETHER — САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ 2026</b> активний в {esc(message.chat.title or 'чаті')}! 🔥\n\nЯ — легенда, базарю смішно з матами, але любя ❤️\n⚡ Видаляю мат/лінк/флуд за 0.1с\n💾 Пам'ятаю все в базу\n😂 Пишу ржачно\n🔇 Мут 5хв [3/3]=⚠️ Варн [3/3]=🚀 Бан\n\nНапиши /help щоб побачити всі плюси і команди!")

async def cmd_help(message: Message, bot: Bot):
    await message.answer(BOT_DESCRIPTION)

async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів, бро, ти шо 😅")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай на повідомлення того кого мутиш, бро!")
    args=message.text.split(); dur=300; reason="Трошки заєбав чат"
    if len(args)>=2:
        try:
            if 'm' in args[1] or 'h' in args[1] or args[1].isdigit():
                import re; m=re.fullmatch(r"(\d+)\s*([smhd])?", args[1].lower())
                if m: v=int(m.group(1)); u=m.group(2) or "m"; mult={"s":1,"m":60,"h":3600,"d":86400}; dur=v*mult[u]; reason=" ".join(args[2:]) if len(args)>2 else "Трошки заєбав"
                else: reason=" ".join(args[1:])
            else: reason=" ".join(args[1:])
        except: reason=" ".join(args[1:])
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=dur))
        u=db.get_user(message.chat.id, target.id, target.first_name); u["mutes"]=u.get("mutes",0)+1
        if u["mutes"]>=3: u["mutes"]=0; u["warns"]=u.get("warns",0)+1
        db.save(); mutes,warns=db.get_stats(message.chat.id, target.id)
        msgs=[
            f"😂 {esc(target.first_name)} лови мут {dur//60}хв за {esc(reason)} — посиди, подумай 😅\n🔇 [{mutes}/3] | ⚠️ [{warns}/3] | Адмін {esc(message.from_user.first_name)} так вирішив",
            f"🔇 {esc(target.first_name)} — тайм-аут {dur//60}хв за {esc(reason)}, відпочинь, бро\n🔇 [{mutes}/3] | ⚠️ [{warns}/3]"
        ]
        await message.answer(random.choice(msgs))
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай на повідомлення!")
    reason=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else "Ну ти даєш"
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        u=db.get_user(message.chat.id, target.id, target.first_name); u["bans"]=u.get("bans",0)+1; u["mutes"]=0; u["warns"]=0; db.save()
        await message.answer(f"🚀 {esc(target.first_name).upper()} ПОЛЕТІВ В КОСМОС за {esc(reason)} 🚀 Бан від {esc(message.from_user.first_name)}, було весело 😂")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_warn(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    reason=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else "Трошки заєбав"
    u=db.get_user(message.chat.id, target.id, target.first_name); u["warns"]=u.get("warns",0)+1; warns=u["warns"]; db.save()
    if warns>=3:
        try: await bot.ban_chat_member(message.chat.id, target.id); u["warns"]=0; u["mutes"]=0; db.save()
        except: pass
        await message.answer(f"🚀 {esc(target.first_name)} — 3/3 варна за {esc(reason)}, полетів в космос 🚀")
    else:
        try: await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=10))
        except: pass
        await message.answer(f"😅 {esc(target.first_name)}, варн [{warns}/3] за {esc(reason)} — ще один і буде космос 🚀")

async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    try: await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
    except: pass
    db.clear_mutes(message.chat.id, target.id)
    await message.answer(f"✅ {esc(target.first_name)} розмутили, повезло 😅 [0/3] — другий шанс, не просри!")

async def cmd_unban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    try: await bot.unban_chat_member(message.chat.id, target.id)
    except: pass
    db.clear_all(message.chat.id, target.id)
    await message.answer(f"✅ {esc(target.first_name)} розбанили, повертайся, бро! Було скучно без тебе ❤️")

async def cmd_unwarn(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if not target: return await message.answer("❌ Відповідай!")
    new=db.dec_warn(message.chat.id, target.id)
    await message.answer(f"✅ Зняв варн з {esc(target.first_name)}, тепер [{new}/3], повезло 😅")

async def cmd_warns(message: Message, bot: Bot):
    if message.reply_to_message and message.reply_to_message.from_user:
        target=message.reply_to_message.from_user; mutes,warns=db.get_stats(message.chat.id, target.id)
        await message.answer(f"📊 {esc(target.first_name)}: 🔇 [{mutes}/3] | ⚠️ [{warns}/3] — я все пам'ятаю, бро 😎")
    else:
        ch=db.get_chat(message.chat.id); warned=[(uid,u) for uid,u in ch["users"].items() if u.get("mutes",0)>0 or u.get("warns",0)>0]
        if not warned: await message.answer(f"✅ Всі чисті, чат — топ, ніхто не заєбував ✨ Я пильную!")
        else:
            txt="<b>📊 Хто трошки пошалив:</b>\n\n"
            for uid,u in sorted(warned, key=lambda x: x[1].get("warns",0), reverse=True)[:15]:
                txt+=f"👤 {esc(u.get('name','Unknown'))} — 🔇 [{u.get('mutes',0)}/3] ⚠️ [{u.get('warns',0)}/3]\n"
            await message.answer(txt)

async def auto_mod(message: Message, bot: Bot):
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
        _flood[(message.chat.id, message.from_user.id)]=[]; await punish(bot, message.chat.id, message.from_user, "флуд")
        return
    if contains_link(text):
        try: await message.delete()
        except: pass
        await punish(bot, message.chat.id, message.from_user, "лінк/реклама"); return
    bad=contains_bad(text)
    if bad:
        try: await message.delete()
        except: pass
        await punish(bot, message.chat.id, message.from_user, f"мат ({bad})"); return

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        db.get_user(event.chat.id, user.id, user.first_name)
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(event.chat.id, f"👋 Йо, {esc(user.first_name)} залетів в {esc(event.chat.title or 'чат')} 😎 Привіт, бро! Я — самий сучасний бот, перевірю шо ти не бот:", reply_markup=kb_verify(user.id))
        except: pass
    elif event.old_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} and event.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        user=event.old_chat_member.user
        if user.is_bot: return
        try: await bot.send_message(event.chat.id, f"👋 Бувай, {esc(user.first_name)}! Було весело, повертайся, бро! 🫶")
        except: pass

async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return
    try: await bot.send_message(event.chat.id, f"🔥 <b>AETHER — САМИЙ СУЧАСНИЙ ЖОСКИЙ БОТ 2026</b> активований! 🔥\n\nЙо, пацани, я — легенда 😎\n💎 Плюси: працюю сам, миттєвий, пам'ятаю все, смішний, справедливий, не сплю 24/7\n🔇 Мут 5хв [3/3]=⚠️ Варн [3/3]=🚀 Бан\nНапиши /help щоб побачити всі плюси!")
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
                await call.message.edit_text(f"👋 {esc(call.from_user.first_name)} пройшов капчу, красава, свій чувак ✨ Залетай, будь пацаном 🫶")
            except: await call.message.edit_text(f"✅ Красава, пройшов! Залетай ❤️")
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
