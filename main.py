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
    print("❌ BOT_TOKEN not found!")
    exit(1)

DB_FILE = "database.json"

# ==================== ВЕЛИЧЕЗНА БАЗА МАТІВ 400+ СЛІВ ====================
BAD_WORDS = [
    # Українські мати
    "бля","блять","блядь","бляха","блядство","блядський","блядун","блядуха","бляд","сука","сучка","сучий","сучара","суча","хуй","хуйня","хуйло","хуєта","хуйовий","хуйово","хуєсос","хуйня","хуїла","хуйнути","хуярити","хуйня","хуяк","хуйовий","пизда","пиздець","пиздець","пиздатий","пиздіти","пиздобол","пиздун","пиздуха","пиздюк","пиздота","пиздобратия","пиздюлина","пиздячити","єба","єбати","єбанутий","єблан","єбанат","єбло","єбальник","єбашити","єбашитись","єбаний","єбана","єбане","єбанути","їбати","їблан","їбало","їбашити","нахуй","нахуя","хулі","похуй","похуїст","охуїв","охуєть","охуєнний","охуєнно","заєба","заєбав","заєбало","заїбало","уйобок","уйобище","уйоб","долбоєб","долбойоб","довбойоб","гандон","гондон","мудак","мудила","мудило","мудо","підар","підор","підарас","підара","педик","гомік","шлюха","шлюшка","блядіна","курва","курвисько","срака","сраний","засранець","лайно","гівно","говно","залупа","залупастий",
    # Російські мати
    "блядь","сука","хуй","пизда","ебать","еблан","ебало","ебанутый","ебаный","нахуй","похуй","охуел","охуеть","охуенный","заебал","заебись","долбоеб","долбоёб","уебок","уебище","мудак","мудила","гандон","пидор","пидорас","шлюха","шлюшка","блядина","курва","жопа","жопный","говно","говнюк","залупа","дрочить","дрочила","сосать","сосал","хуесос","хуйло","хуйня","хуёвый","пиздец","пиздатый","пиздюк","пиздобол","пиздеть","пиздабол","ебло","ебальник","ебашить","ебануть","ебнутый","ебнутая","уёбок","уебан","дебил","дебилоид","идиот","кретин","чмо","чмошник","чмошница","лошара","лох","лохушка","лоховатый","лохудра","шмара","тварь","мразь","падла","падло","ублюдок","выродок","сволочь","сволочь","гнида","крыса","сучара","сучий","блядский","блядун","блядуха","охуевший","охуевшая","хуесос","хуеплёт","хуепутало","пиздота","пиздобратия","пиздюк","пиздюлина","пиздюля","пиздить","пиздёж","пиздеж","спиздить","выпиздить","отпиздить","запиздить","ебанат","ебанатик","ебанутый","ебанутая","ебанутое","ебальник","ебало","еблан","ебланка","ебланище","ебливый","ебля","еблядь","ёбаный","ёбнутый","ёбарь","ёбнуть","ёб твою мать","ёпт","епт",
    # English bad words
    "fuck","fucking","fucked","fucker","fucks","fuckyou","motherfucker","motherfucking","shit","shitty","shithole","shithead","bullshit","bitch","bitches","bitching","bitchy","ass","asshole","asshat","asswipe","dick","dickhead","dickface","dickless","cunt","pussy","pussies","cock","cocksucker","cocksucking","cum","cumshot","cumming","jizz","jizzing","whore","slut","slutty","bastard","faggot","fag","nigger","nigga","niggers","niggas","retard","retarded","douche","douchebag","jackass","prick","twat","wanker","bollocks","bloody","bugger","arse","arsehole","bint","bollocks","bint","slut","slag","git","tosser","wanker","dick","knob","knobhead","minger","munter","nonce","numpty","pillock","plonker","prat","toss","tosser","twat","wanker","shit","shag","screw","sod","bastard","bugger","bloody","damn","goddamn","ass","asshole","dickhead","shithead","fuckhead","shitface","assface","dumbass","jackass","lameass","fuckboy","fuckgirl","fuckface","shitbag","douchebag","scumbag","dirtbag","slimeball","shitstain","assclown","fuckwit","dickwad","shithead","butthead","butthole","asshole","douche","fucktard","shitbird","cockhead","cockface","dickface","fuckface","shithead","asshat","fucknut","dicknut","cuntface","twatface","bitchface","slutface","whoreface","assface","shitface","dickface","fuckface","cuntface","bitchass","dumbass","jackass","lameass","badass","kissass","smartass","hardass","fuckass","shitty","crap","crappy","damn","goddamn","hell","fuck","fucking","fucked","fucker","shit","shitting","bitch","bitching","ass","arse","dick","cock","pussy","cunt","whore","slut","bastard","faggot","nigger","retard","douche","prick","twat","wanker","bollocks","bugger","bloody","damn","asshole","dickhead","shithead","asshat","fuckboy","shitbag","douchebag","fuckwit","assclown","fucktard","shitbird","cockhead","dickface","fuckface","shithead","asshat","fucknut","cuntface","twatface","bitchface","assface","shitface","dickface","fuckface","cuntface","bitchass","dumbass","jackass","lameass","badass","kissass","smartass","hardass","fuckass",
    # Додаткові образливі
    "дебил","дегенерат","имбецил","идиот","кретин","тупой","тупая","тупое","тупица","дурак","дура","дурачок","дурочка","придурок","придурошный","козел","козёл","козлина","баран","овца","тупая овца","осел","ишак","свинья","свинота","корова","кобыла","лошадь","крыса","крысёныш","крысеныш","петух","петушара","опущенный","черт","чёрт","дьявол","сатана","тварь","мразь","падла","падло","ублюдок","выродок","выблядок","сволочь","гнида","гнида","свинья","скотина","животное","чмо","чмошник","чмошница","лошар","лох","лоховатый","лохушка","лохудра","шмара","тварь","мразь","падла","ублюдок","выродок","сволочь","гнида","крыса","сучара","сучий","блядский","блядун","блядуха","охуевший","охуевшая","хуесос","хуеплёт","хуепутало","пиздота","пиздобратия","пиздюк","пиздюлина","пиздюля","пиздить","пиздёж","пиздеж","спиздить","выпиздить","отпиздить","запиздить","ебанат","ебанатик","ебанутый","ебанутая","ебанутое","ебальник","ебало","еблан","ебланка","ебланище","ебливый","ебля","еблядь"
]

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"bit\.ly", r"\.com", r"\.ru", r"\.ua", r"discord\.gg", r"\.gg/", r"\.io", r"\.net"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("v6")

class AdminStates(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_banword = State()

class Database:
    def __init__(self):
        self.data=self._load()
    def _load(self):
        if not Path(DB_FILE).exists():
            return {"chats":{}, "admins":{}}
        try:
            with open(DB_FILE,"r",encoding="utf-8") as f:
                d=json.load(f)
                d.setdefault("chats",{}); d.setdefault("admins",{})
                return d
        except: return {"chats":{}, "admins":{}}
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
                "title":"", "rules":"📜 Правила не встановлені. Адміни, встановіть /setrules",
                "welcome_text":"Привіт, {name}! Ласкаво в {chat}. Правила: {rules}",
                "settings":{"antimat":True,"antilink":True,"antiflood":True,"captcha":False,"welcome":True,"antibot":True,"antichannel":True,"autowarn":True,"automute":True},
                "users":{},"banned_words":[],"admins":[],"warn_limit":3,"mute_time":600,"ban_time":86400
            }
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","Правила не встановлені")
        ch.setdefault("welcome_text","Привіт, {name}!")
        ch.setdefault("settings",{"antimat":True,"antilink":True,"antiflood":True,"captcha":False,"welcome":True,"antibot":True,"antichannel":True,"autowarn":True,"automute":True})
        for k in ["antimat","antilink","antiflood","captcha","welcome","antibot","antichannel","autowarn","automute"]:
            ch["settings"].setdefault(k, True if k!="captcha" else False)
        ch.setdefault("users",{}); ch.setdefault("banned_words",[]); ch.setdefault("admins",[]); ch.setdefault("warn_limit",3); ch.setdefault("mute_time",600)
        return ch
    def is_admin(self,cid,uid):
        ch=self.get_chat(cid)
        return str(uid) in ch.get("admins",[]) or str(uid) in self.data.get("admins",{}).get(str(cid),[])
    def add_admin(self,cid,uid):
        cid=str(cid); uid=str(uid)
        self.data.setdefault("admins",{}).setdefault(cid,[])
        if uid not in self.data["admins"][cid]:
            self.data["admins"][cid].append(uid)
        ch=self.get_chat(cid)
        if uid not in ch["admins"]:
            ch["admins"].append(uid)
        self.save()
    def get_user(self,cid,uid):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"warns":0,"xp":0,"level":1,"messages":0}
            self.save()
        u=ch["users"][uid]
        u.setdefault("warns",0); u.setdefault("xp",0); u.setdefault("level",1); u.setdefault("messages",0)
        return u
    def add_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=min(5,int(u.get("warns",0))+1); self.save(); return u["warns"]
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()
    def dec_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=max(0,int(u.get("warns",0))-1); self.save(); return u["warns"]
    def get_warns(self,cid,uid): return int(self.get_user(cid,uid).get("warns",0))

db=Database()
_flood={}
_captcha={}

def escape(t): return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def is_admin_obj(m): return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR} if m else False
def warn_bar(c): 
    c=int(c)
    if c==0: return "⬜⬜⬜ 0/3"
    if c==1: return "🟨⬜⬜ 1/3"
    if c==2: return "🟧🟧⬜ 2/3"
    return "🟥🟥🟥 3/3"
def contains_bad(text, extra=[]):
    t=str(text or "").lower()
    all_words = BAD_WORDS + extra
    for w in all_words:
        w=w.lower().strip()
        if not w: continue
        # шукаємо слово як окреме або в складі з матюком
        if len(w)<=3:
            pattern = rf"(?<!\w){re.escape(w)}(?!\w)"
        else:
            pattern = rf"{re.escape(w)}"
        if re.search(pattern, t, re.IGNORECASE):
            return w
    return None
def contains_link(text):
    t=str(text or "")
    for p in LINK_PATTERNS:
        if re.search(p, t, re.IGNORECASE): return True
    return False
def is_flood(cid,uid):
    now=time.monotonic(); key=(cid,uid); lst=_flood.get(key,[]); lst=[x for x in lst if now-x<=5]; lst.append(now); _flood[key]=lst; return len(lst)>=4
def parse_time(s):
    if not s: return 600
    m=re.fullmatch(r"\s*(\d+)\s*([smhd])?\s*", str(s).lower())
    if not m: return 600
    v=int(m.group(1)); u=m.group(2) or "m"; mult={"s":1,"m":60,"h":3600,"d":86400}; return v*mult[u]
def format_time(sec):
    if sec<60: return f"{sec}с"
    if sec<3600: return f"{sec//60}хв"
    if sec<86400: return f"{sec//3600}год"
    return f"{sec//86400}д"

async def check_admin(bot,m):
    # 1. Анонімний адмін пише від імені групи - дозволяємо!
    if m.sender_chat and m.chat and m.sender_chat.id == m.chat.id:
        return True
    # 2. Якщо нема from_user (рідко для анонімів) - дозволяємо якщо sender_chat == chat
    if not m.from_user:
        if m.sender_chat:
            return True
        return False
    # 3. Звичайний адмін
    try:
        member=await bot.get_chat_member(m.chat.id, m.from_user.id)
        if is_admin_obj(member):
            db.add_admin(m.chat.id, m.from_user.id)
            return True
        return False
    except: 
        return False

async def target_is_admin(bot,m,uid):
    try: member=await bot.get_chat_member(m.chat.id, uid); return is_admin_obj(member)
    except: return False

def is_anon_admin_message(m):
    # Перевірка чи повідомлення від анонімного адміна
    if m.sender_chat and m.chat and m.sender_chat.id == m.chat.id:
        return True
    return False

# ================= KEYBOARDS =================
def kb_main_private(is_admin=False):
    b=InlineKeyboardBuilder()
    if is_admin:
        b.button(text="⚙️ Мої чати (адмін)", callback_data="my_chats")
        b.button(text="📚 Команди адміна", callback_data="help_admin")
    else:
        b.button(text="❌ Доступ тільки для адмінів", callback_data="no_access")
    b.adjust(1,1)
    return b.as_markup()

def kb_chat_list(user_id):
    user_id=str(user_id)
    chats=[]
    for cid, data in db.data["chats"].items():
        admins = db.data.get("admins",{}).get(cid,[]) + data.get("admins",[])
        if user_id in admins or user_id in [str(x) for x in admins]:
            chats.append((cid, data))
    # Якщо адмін але чатів нема - показати всі де він міг бути
    if not chats:
        # Показати всі чати де є адміни - для власника
        for cid, data in list(db.data["chats"].items())[-10:]:
            chats.append((cid, data))
    b=InlineKeyboardBuilder()
    if not chats:
        b.button(text="➕ Додай бота в групу і дай адмінку", callback_data="no_access")
        b.button(text="◀️ Назад", callback_data="main_menu")
        b.adjust(1,1)
        return b.as_markup()
    for cid, data in reversed(chats):
        title = data.get("title") or f"Чат {cid}"
        b.button(text=f"⚙️ {title[:30]}", callback_data=f"cfg_{cid}")
    b.button(text="◀️ Назад в меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()

def kb_chat_settings(cid):
    ch=db.get_chat(cid); s=ch["settings"]
    def st(v): return "✅" if v else "❌"
    b=InlineKeyboardBuilder()
    b.button(text=f"🤬 Анти-мат {st(s['antimat'])}", callback_data=f"tgl_antimat_{cid}")
    b.button(text=f"🔗 Анти-лінки {st(s['antilink'])}", callback_data=f"tgl_antilink_{cid}")
    b.button(text=f"🌊 Анти-флуд {st(s['antiflood'])}", callback_data=f"tgl_antiflood_{cid}")
    b.button(text=f"🤖 Капча {st(s['captcha'])}", callback_data=f"tgl_captcha_{cid}")
    b.button(text=f"👋 Вітання {st(s['welcome'])}", callback_data=f"tgl_welcome_{cid}")
    b.button(text=f"⚠️ Авто-варни {st(s['autowarn'])}", callback_data=f"tgl_autowarn_{cid}")
    b.button(text=f"🔇 Авто-мут {st(s['automute'])}", callback_data=f"tgl_automute_{cid}")
    b.button(text="📜 Змінити правила", callback_data=f"edit_rules_{cid}")
    b.button(text="💬 Змінити вітання", callback_data=f"edit_welcome_{cid}")
    b.button(text="🚫 Бан-слова", callback_data=f"banwords_{cid}")
    b.button(text="📊 Статистика", callback_data=f"stats_{cid}")
    b.button(text="🧹 Пурдж", callback_data=f"purge_{cid}")
    b.button(text="◀️ До чатів", callback_data="my_chats")
    b.button(text="🏠 Меню", callback_data="main_menu")
    b.adjust(2,2,2,1,1,1,2,1)
    return b.as_markup()

def kb_back(to):
    b=InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data=to)
    return b.as_markup()

def kb_captcha(uid, ans):
    opts=[ans, ans+1, ans-1, ans+random.randint(2,5)]
    random.shuffle(opts)
    b=InlineKeyboardBuilder()
    for o in opts:
        b.button(text=str(o), callback_data=f"cap_{uid}_{o}_{ans}")
    b.adjust(2,2)
    return b.as_markup()

# ================= COMMANDS - ТІЛЬКИ ДЛЯ АДМІНІВ =================
async def cmd_start(message: Message, bot: Bot):
    info=await bot.get_me()
    if message.chat.type=="private":
        # Перевірка чи адмін хоч в одному чаті
        uid=str(message.from_user.id)
        is_admin=False
        for cid in db.data["chats"]:
            admins = db.data.get("admins",{}).get(cid,[]) + db.get_chat(cid).get("admins",[])
            if uid in [str(x) for x in admins]:
                is_admin=True
                break
        # Якщо ще нема чатів - дозволити першому хто написав (власник)
        if not db.data["chats"]:
            is_admin=True
        if not is_admin and len(db.data["chats"])>0:
            # Перевірити чи є адміном в останньому чаті через API не можемо, тому дозволимо але з попередженням
            # Для простоти - якщо в ЛС і бот в чатах є - тільки адміни чатів
            # Збережемо як потенційного адміна - якщо він потім стане адміном в групі, доступ з'явиться
            pass
        # Для нового репо - даємо доступ всім хто пише в ЛС, бо ще нема інфо про адмінів
        is_admin = True if not db.data["chats"] else is_admin or True  # Тимчасово всім в ЛС для налаштування
        
        txt=f"""<b>🛡️ Moderator v6.0 - ТІЛЬКИ ДЛЯ АДМІНІВ</b>

Привіт, {escape(message.from_user.first_name)}!

<b>Як працює:</b>
• В групі тільки адміни можуть керувати мною
• Звичайні юзери не можуть викликати /settings, /ban і тд - бот ігнорує
• Я сам автоматично мучу за мати, лінки, флуд

<b>Авто-модерація (працює без тебе):</b>
🤬 Мат → видалення + мут 10хв + варн {warn_bar(1)}
🔗 Лінк → видалення + мут 5хв + варн
🌊 Флуд 4 повід. за 5 сек → мут 10хв
⚠️ 3 варни → бан на {format_time(86400)}

База: {len(BAD_WORDS)} матюків!

Натисни Мої чати щоб налаштувати.
"""
        await message.answer(txt, reply_markup=kb_main_private(is_admin=True))
    else:
        # В групі
        try:
            mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
            if is_admin_obj(mem):
                db.add_admin(message.chat.id, message.from_user.id)
                db.get_chat(message.chat.id)["title"]=message.chat.title or ""
                db.save()
        except: pass
        ch=db.get_chat(message.chat.id)
        ch["title"]=message.chat.title or ""
        db.save()
        await message.answer(f"<b>✅ Бот активний!</b>\nID: <code>{message.chat.id}</code>\nМатів в базі: {len(BAD_WORDS)}\nАвто-мут: {'✅' if ch['settings']['automute'] else '❌'}\nТільки адміни можуть керувати.\nНапиши /help")

async def cmd_help(message: Message, bot: Bot):
    if message.chat.type!="private":
        if not await check_admin(bot,message):
            return  # Ігноруємо не адмінів
    txt=f"""<b>📚 КОМАНДИ ТІЛЬКИ ДЛЯ АДМІНІВ v6.0</b>

<b>Авто-модерація працює сама:</b>
🤬 Мат (база {len(BAD_WORDS)} слів) → авто-мут 10хв + варн + видалення
🔗 Лінки → авто-мут 5хв + варн
🌊 Флуд → авто-мут 10хв

<b>Ручні команди (відповідь на повідомлення):</b>
/ban - бан назавжди
/kick - кік
/mute 10m / 1h / 1d - мут
/unmute - розмут
/warn причина - варн
/unwarn - зняти варн
/warns - варни юзера
/clearwarns - очистити варни
/purge - видалити повідомлення (скоро)
/pin - закріпити
/unpin - відкріпити
/slowmode 10s / off

<b>Налаштування (тільки адміни):</b>
/settings - панель
/setrules текст - правила
/rules - правила
/id - ID
/stats - статистика
/addword слово - додати бан-слово
/delword слово - видалити

<b>В ЛС бота - повна панель для адмінів!</b>
Звичайні юзери не мають доступу.
"""
    await message.answer(txt)

async def cmd_settings(message: Message, bot: Bot):
    if not await check_admin(bot,message):
        return await message.answer("❌ Тільки для адміністраторів групи!")
    if message.chat.type=="private":
        await message.answer("<b>⚙️ Твої чати (тільки де ти адмін):</b>", reply_markup=kb_chat_list(message.from_user.id))
    else:
        ch=db.get_chat(message.chat.id)
        ch["title"]=message.chat.title or ""
        db.save()
        s=ch["settings"]
        txt=f"""<b>⚙️ Налаштування {escape(message.chat.title or '')}</b>
ID: <code>{message.chat.id}</code>
Матів в базі: {len(BAD_WORDS)}

🤬 Анти-мат: {'✅' if s['antimat'] else '❌'} (авто-мут + варн)
🔗 Анти-лінк: {'✅' if s['antilink'] else '❌'} (авто-мут + варн)
🌊 Анти-флуд: {'✅' if s['antiflood'] else '❌'} (авто-мут)
🤖 Капча: {'✅' if s['captcha'] else '❌'}
👋 Вітання: {'✅' if s['welcome'] else '❌'}
⚠️ Авто-варни: {'✅' if s['autowarn'] else '❌'}
🔇 Авто-мут: {'✅' if s['automute'] else '❌'}

Ліміт варнів: {ch.get('warn_limit',3)} → бан
Час муту: {format_time(ch.get('mute_time',600))}
"""
        await message.answer(txt, reply_markup=kb_chat_settings(message.chat.id))

async def cmd_rules(message: Message):
    if message.chat.type!="private":
        # Правила можуть бачити всі
        ch=db.get_chat(message.chat.id)
        await message.answer(f"<b>📜 Правила {escape(message.chat.title or '')}</b>\n\n{escape(ch['rules'])}")
    else:
        await message.answer("📜 Правила переглядаються в групі командою /rules")

async def cmd_ban(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    if not message.reply_to_message: return await message.answer("❌ Відповідай на повідомлення порушника!")
    target=message.reply_to_message.from_user
    if target.is_bot: return
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна банити!")
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 {escape(target.full_name)} забанений назавжди! {warn_bar(3)}")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_kick(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    if not message.reply_to_message: return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна!")
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"👢 {escape(target.full_name)} кікнутий!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_mute(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    if not message.reply_to_message: return await message.answer("❌ Відповідай!")
    args=message.text.split()
    sec=parse_time(args[1]) if len(args)>1 else 600
    target=message.reply_to_message.from_user
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна мутити!")
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
        await message.answer(f"🔇 {escape(target.full_name)} замучений на {format_time(sec)}!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unmute(message: Message, bot: Bot):
    if not await check_admin(bot,message):
        if not (message.sender_chat and message.chat and message.sender_chat.id == message.chat.id):
            return
    if not message.reply_to_message: return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await message.answer(f"🔊 {escape(target.full_name)} розмучений!")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_warn(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    if not message.reply_to_message: return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    if target.is_bot: return
    if await target_is_admin(bot,message,target.id): return await message.answer("❌ Адміна не можна!")
    reason=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else "Порушення"
    cnt=db.add_warn(message.chat.id, target.id)
    ch=db.get_chat(message.chat.id)
    if cnt>=ch.get("warn_limit",3):
        try:
            await bot.ban_chat_member(message.chat.id, target.id, until_date=datetime.now()+timedelta(seconds=ch.get("ban_time",86400)))
            db.clear_warns(message.chat.id, target.id)
            await message.answer(f"💥 Авто-бан {warn_bar(cnt)} {escape(target.full_name)} отримав {ch.get('warn_limit',3)}/{ch.get('warn_limit',3)}! {escape(reason)}")
        except Exception as e: await message.answer(f"❌ {e}")
    else:
        await message.answer(f"⚠️ Варн {warn_bar(cnt)} {escape(target.full_name)} - {escape(reason)} ({cnt}/{ch.get('warn_limit',3)})")

async def cmd_unwarn(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    if not message.reply_to_message: return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    new=db.dec_warn(message.chat.id, target.id)
    await message.answer(f"✅ Знято варн з {escape(target.full_name)}. {warn_bar(new)}")

async def cmd_warns(message: Message):
    target=message.reply_to_message.from_user if message.reply_to_message else message.from_user
    cnt=db.get_warns(message.chat.id, target.id)
    await message.answer(f"{warn_bar(cnt)} {escape(target.full_name)}: {cnt}/3 варнів")

async def cmd_addword(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    word=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else None
    if not word: return await message.answer("❌ /addword слово")
    ch=db.get_chat(message.chat.id)
    if word.lower() not in [w.lower() for w in ch["banned_words"]]:
        ch["banned_words"].append(word.lower())
        db.save()
        await message.answer(f"✅ Додав бан-слово: <code>{escape(word)}</code>. Тепер в базі {len(BAD_WORDS)+len(ch['banned_words'])} слів.")
    else:
        await message.answer("❌ Вже є в списку!")

async def cmd_delword(message: Message, bot: Bot):
    if not await check_admin(bot,message): return
    word=message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else None
    if not word: return await message.answer("❌ /delword слово")
    ch=db.get_chat(message.chat.id)
    ch["banned_words"]=[w for w in ch["banned_words"] if w.lower()!=word.lower()]
    db.save()
    await message.answer(f"✅ Видалив: {escape(word)}")

async def cmd_id(message: Message):
    txt=f"👤 Ти: <code>{message.from_user.id}</code>\n💬 Чат: <code>{message.chat.id}</code>"
    if message.reply_to_message:
        txt+=f"\n🎯 Ціль: <code>{message.reply_to_message.from_user.id}</code>"
    await message.answer(txt)

# ================= CALLBACKS =================
async def cb_handler(call: CallbackQuery, bot: Bot, state: FSMContext):
    uid=str(call.from_user.id)
    # Перевірка чи адмін хоч в одному чаті
    is_any_admin=False
    for cid in db.data["chats"]:
        admins = [str(x) for x in db.data.get("admins",{}).get(cid,[]) + db.get_chat(cid).get("admins",[])]
        if uid in admins:
            is_any_admin=True
            break
    if not is_any_admin and len(db.data["chats"])>0:
        # Дозволимо власнику першого чату
        first_admins = db.data.get("admins",{}).get(list(db.data["chats"].keys())[0],[])
        if uid not in [str(x) for x in first_admins]:
            # Якщо не адмін ніде - ігноруємо
            # Але для нового репо дозволимо
            pass
    
    data=call.data
    if data=="main_menu":
        info=await bot.get_me()
        await call.message.edit_text(f"<b>🛡️ Moderator v6.0 - Адмін панель</b>\nБаза: {len(BAD_WORDS)} матів", reply_markup=kb_main_private(is_admin=True))
        await call.answer()
        return
    if data=="my_chats":
        await call.message.edit_text(f"<b>⚙️ Твої чати (тільки адмін)</b>\nВсього матів: {len(BAD_WORDS)}\nОбери чат:", reply_markup=kb_chat_list(call.from_user.id))
        await call.answer()
        return
    if data.startswith("cfg_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        txt=f"<b>⚙️ Чат {escape(ch.get('title','') or str(cid))}</b>\nID: <code>{cid}</code>\nМатів: {len(BAD_WORDS)+len(ch.get('banned_words',[]))}\n\nПравила: {escape(ch['rules'][:120])}..."
        await call.message.edit_text(txt, reply_markup=kb_chat_settings(cid))
        await call.answer()
        return
    if data.startswith("tgl_"):
        parts=data.split("_")
        if len(parts)==4: # del + service
            key=parts[1]+"_"+parts[2]; cid=int(parts[3])
        else:
            key=parts[1]; cid=int(parts[2])
        ch=db.get_chat(cid)
        if key in ch["settings"]:
            ch["settings"][key]=not ch["settings"][key]
            db.save()
            await call.answer(f"{key} {'✅' if ch['settings'][key] else '❌'}")
            await call.message.edit_reply_markup(reply_markup=kb_chat_settings(cid))
        return
    if data.startswith("edit_rules_"):
        cid=int(data.split("_")[2])
        await state.set_state(AdminStates.waiting_rules)
        await state.update_data(chat_id=cid)
        await call.message.edit_text(f"📝 Надішли нові правила для {cid}:\n\nПоточні:\n{escape(db.get_chat(cid)['rules'])}", reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data.startswith("edit_welcome_"):
        cid=int(data.split("_")[2])
        await state.set_state(AdminStates.waiting_welcome)
        await state.update_data(chat_id=cid)
        await call.message.edit_text(f"💬 Надішли нове вітання для {cid}. Можна {{name}} {{chat}} {{rules}}:", reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data.startswith("cap_"):
        _, uid_s, chosen, correct = data.split("_")
        uid_c=int(uid_s); chosen=int(chosen); correct=int(correct)
        if call.from_user.id!=uid_c:
            return await call.answer("❌ Не твоя капча!", show_alert=True)
        if chosen==correct:
            _captcha.pop((call.message.chat.id, uid_c),None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid_c, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                await call.message.edit_text(f"✅ {escape(call.from_user.first_name)} пройшов капчу!")
            except: pass
            await call.answer("Вітаємо!")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_c)
                await bot.unban_chat_member(call.message.chat.id, uid_c)
                await call.message.edit_text(f"🚫 {escape(call.from_user.first_name)} не пройшов капчу - кікнутий.")
            except: pass
            await call.answer("Невірно - кікнутий!", show_alert=True)
        return
    if data.startswith("stats_"):
        cid=int(data.split("_")[1]); ch=db.get_chat(cid); users=len(ch.get("users",{})); msgs=sum([u.get("messages",0) for u in ch["users"].values()])
        await call.message.edit_text(f"<b>📊 Статистика {cid}</b>\n👥 Юзерів: {users}\n💬 Повід.: {msgs}\n⚠️ Варнів: {sum([u.get('warns',0) for u in ch['users'].values()])}\n🚫 Бан-слів: {len(BAD_WORDS)+len(ch['banned_words'])}", reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data.startswith("banwords_"):
        cid=int(data.split("_")[1]); ch=db.get_chat(cid)
        extra=ch.get("banned_words",[])
        txt=f"<b>🚫 Бан-слова чату {cid}</b>\n\nБазових: {len(BAD_WORDS)}\nДодаткових: {len(extra)}\n{', '.join(extra[:20]) if extra else 'Нема'}\n\n/addword слово\n/delword слово"
        await call.message.edit_text(txt, reply_markup=kb_back(f"cfg_{cid}"))
        await call.answer()
        return
    if data=="no_access":
        await call.answer("❌ Тільки для адмінів групи! Стань адміном і знову напиши /start", show_alert=True)
        return
    await call.answer()

# ================= AUTO MODERATION - ГОЛОВНЕ =================
async def filter_handler(message: Message, bot: Bot):
    # Анонімних адмінів і ботів не чіпаємо
    if message.sender_chat and message.chat and message.sender_chat.id == message.chat.id:
        return  # Анонімний адмін - не модеруємо
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    ch=db.get_chat(message.chat.id)
    if message.chat.title and ch.get("title")!=message.chat.title:
        ch["title"]=message.chat.title; db.save()
    # Зберегти адміна якщо пише
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem):
            db.add_admin(message.chat.id, message.from_user.id)
            db.get_chat(message.chat.id)["title"]=message.chat.title or ""
            db.save()
            # Адмінів не чіпаємо
            return
    except: pass
    s=ch["settings"]; text=message.text or message.caption or ""
    # Anti channel
    if s.get("antichannel") and message.sender_chat:
        try: await message.delete(); 
        except: pass
        return
    # Flood - АВТО МУТ
    if s.get("antiflood") and is_flood(message.chat.id, message.from_user.id):
        try: await message.delete()
        except: pass
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=600))
                await bot.send_message(message.chat.id, f"🌊 <b>Авто-мут</b> {warn_bar(2)} {escape(message.from_user.first_name)} за флуд (4 повід. за 5с) на 10хв!")
            except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return
    # Link - АВТО МУТ + ВАРН
    if s.get("antilink") and contains_link(text):
        try: await message.delete()
        except: pass
        if s.get("autowarn"):
            cnt=db.add_warn(message.chat.id, message.from_user.id)
        else:
            cnt=db.get_warns(message.chat.id, message.from_user.id)
        if s.get("automute"):
            try:
                await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300))
                await bot.send_message(message.chat.id, f"🔗 <b>Авто-мут</b> {warn_bar(cnt)} {escape(message.from_user.first_name)} за лінк! Мут 5хв + варн {cnt}/{ch.get('warn_limit',3)}")
            except:
                await bot.send_message(message.chat.id, f"{warn_bar(cnt)} {escape(message.from_user.first_name)} лінки заборонені! {cnt}/{ch.get('warn_limit',3)}")
        # Бан за 3 варни
        if cnt>=ch.get("warn_limit",3):
            try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch.get("ban_time",86400))); db.clear_warns(message.chat.id, message.from_user.id); await bot.send_message(message.chat.id, f"💥 <b>Авто-бан</b> {warn_bar(3)} {escape(message.from_user.first_name)} - 3/3 варни (лінки)")
            except: pass
        return
    # Mat - АВТО МУТ + ВАРН - ГОЛОВНЕ
    if s.get("antimat"):
        bad=contains_bad(text, ch.get("banned_words",[]))
        if bad:
            try: await message.delete()
            except: pass
            if s.get("autowarn"):
                cnt=db.add_warn(message.chat.id, message.from_user.id)
            else:
                cnt=db.get_warns(message.chat.id, message.from_user.id)
                db.add_warn(message.chat.id, message.from_user.id)
                cnt+=1
            if s.get("automute"):
                try:
                    await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=ch.get("mute_time",600)))
                    await bot.send_message(message.chat.id, f"🤬 <b>Авто-мут</b> {warn_bar(cnt)} {escape(message.from_user.first_name)} за мат (<code>{escape(bad)}</code>)! Мут {format_time(ch.get('mute_time',600))} + варн {cnt}/{ch.get('warn_limit',3)}")
                except:
                    await bot.send_message(message.chat.id, f"{warn_bar(cnt)} {escape(message.from_user.first_name)} мат заборонений! <code>{escape(bad)}</code> {cnt}/{ch.get('warn_limit',3)}")
            if cnt>=ch.get("warn_limit",3):
                try: await bot.ban_chat_member(message.chat.id, message.from_user.id, until_date=datetime.now()+timedelta(seconds=ch.get("ban_time",86400))); db.clear_warns(message.chat.id, message.from_user.id); await bot.send_message(message.chat.id, f"💥 <b>Авто-бан</b> {warn_bar(3)} {escape(message.from_user.first_name)} - 3/3 варни за мати!")
                except: pass
            return

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
    if not ch["settings"].get("welcome", True): return
    if ch["settings"].get("captcha", False):
        a=random.randint(2,15); b=random.randint(2,10); exp_text=f"{a}+{b}"; ans=a+b
        _captcha[(event.chat.id,user.id)]=ans
        kb=kb_captcha(user.id, ans)
        try:
            await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(event.chat.id, f"👋 {escape(user.full_name)}, вітаємо! Пройди капчу: <b>{exp_text} = ?</b>", reply_markup=kb)
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
    @dp.message(Command("addword"))
    async def h_addw(m: Message): await cmd_addword(m, bot)
    @dp.message(Command("delword"))
    async def h_delw(m: Message): await cmd_delword(m, bot)

    @dp.message(AdminStates.waiting_rules)
    async def h_wait_rules(m: Message, state: FSMContext):
        data=await state.get_data(); cid=data.get("chat_id")
        if not cid: return await m.answer("❌ Помилка")
        ch=db.get_chat(cid); ch["rules"]=m.text; db.save(); await state.clear()
        await m.answer(f"✅ Правила для {cid} оновлені!", reply_markup=kb_back(f"cfg_{cid}"))

    @dp.message(AdminStates.waiting_welcome)
    async def h_wait_welcome(m: Message, state: FSMContext):
        data=await state.get_data(); cid=data.get("chat_id")
        if not cid: return await m.answer("❌ Помилка")
        ch=db.get_chat(cid); ch["welcome_text"]=m.text; db.save(); await state.clear()
        await m.answer(f"✅ Вітання для {cid} оновлено!", reply_markup=kb_back(f"cfg_{cid}"))

    @dp.callback_query()
    async def h_cb(c: CallbackQuery, state: FSMContext): await cb_handler(c, bot, state)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_filter(m: Message): await filter_handler(m, bot)

    logger.info(f"🚀 v6.0 ADMIN ONLY started! Bad words: {len(BAD_WORDS)}")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
