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

LINK_PATTERNS = [r"t\.me/", r"https?://", r"www\.", r"discord\.gg"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AETHER_V11")

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
                "rules":"1️⃣ Без мату та образ\n2️⃣ Без спаму, реклами, лінків\n3️⃣ Поважай інших\n4️⃣ Без 18+",
                "welcome_text":"Привіт, {name} 👋\n✨ Ласкаво в {chat} ✨\n💫 Ми раді що ти з нами!",
                "goodbye_text":"Бувай, {name} 👋 Сумуватимемо!",
                "settings":{"antimat":True,"antilink":True,"antiflood":True,"antispam":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True},
                "users":{},"banned_words":[],"warn_limit":3,"mute_time":600,"ban_time":86400,
                "games_won":{}
            }
            self.save()
        ch=self.data["chats"][cid]
        ch.setdefault("rules","Правила не встановлені"); ch.setdefault("welcome_text","Привіт, {name} 👋"); ch.setdefault("goodbye_text","Бувай, {name} 👋")
        ch.setdefault("settings",{"antimat":True,"antilink":True,"antiflood":True,"antispam":True,"welcome":True,"goodbye":True,"captcha":True,"autowarn":True,"automute":True})
        for k in ["antimat","antilink","antiflood","antispam","welcome","goodbye","captcha","autowarn","automute"]:
            ch["settings"].setdefault(k, True)
        ch.setdefault("users",{}); ch.setdefault("banned_words",[]); ch.setdefault("warn_limit",3); ch.setdefault("games_won",{})
        return ch
    def get_user(self,cid,uid):
        ch=self.get_chat(cid); uid=str(uid)
        if uid not in ch["users"]:
            ch["users"][uid]={"warns":0,"messages":0}; self.save()
        return ch["users"][uid]
    def add_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=min(10,int(u.get("warns",0))+1); self.save(); return u["warns"]
    def dec_warn(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=max(0,int(u.get("warns",0))-1); self.save(); return u["warns"]
    def get_warns(self,cid,uid): return int(self.get_user(cid,uid).get("warns",0))
    def clear_warns(self,cid,uid):
        u=self.get_user(cid,uid); u["warns"]=0; self.save()

db=Database()
_flood={}
_captcha={}
_games={}  # game_id -> {board, players, turn, chat_id, message_id}
_game_counter=0

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

# ==================== ГРА ХРЕСТИКИ-НОЛИКИ ====================
def check_winner(board):
    # board 9 елементів: 0-8
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in wins:
        if board[a] and board[a]==board[b]==board[c]:
            return board[a]
    if all(board): return "draw"
    return None

def render_board(board):
    # board: ["", "X", "O"...]
    symbols = {"": "⬜", "X": "❌", "O": "⭕"}
    lines=[]
    for i in range(0,9,3):
        lines.append(f"{symbols.get(board[i],'⬜')}{symbols.get(board[i+1],'⬜')}{symbols.get(board[i+2],'⬜')}")
    return "\n".join(lines)

def kb_tictactoe(game_id, board):
    b=InlineKeyboardBuilder()
    for i in range(9):
        if board[i]=="":
            b.button(text="⬜", callback_data=f"ttt_move_{game_id}_{i}")
        else:
            txt="❌" if board[i]=="X" else "⭕"
            b.button(text=txt, callback_data=f"ttt_ignore_{game_id}")
    b.button(text="🚪 Вийти з гри", callback_data=f"ttt_leave_{game_id}")
    b.adjust(3,3,1)
    return b.as_markup()

def kb_game_lobby():
    b=InlineKeyboardBuilder()
    b.button(text="🎮 Створити гру (2 гравці)", callback_data="ttt_create")
    b.button(text="📊 Топ гравців", callback_data="ttt_top")
    b.adjust(1,1)
    return b.as_markup()

# ==================== КЛАВІАТУРИ ====================
def kb_private(bot_username):
    b=InlineKeyboardBuilder()
    b.button(text="➕ Додати AETHER в чат", url=f"https://t.me/{bot_username}?startgroup=true")
    b.button(text="📖 Що вміє?", callback_data="about")
    b.button(text="🎮 Гра в чаті", callback_data="about_game")
    b.adjust(1,1,1)
    return b.as_markup()

def kb_group_main(cid):
    b=InlineKeyboardBuilder()
    b.button(text="⚙️ Налаштування", callback_data=f"cfg_{cid}")
    b.button(text="🎮 Гра Хрестики-Нолики", callback_data=f"game_{cid}")
    b.button(text="🤖 Капча", callback_data=f"tgl_captcha_{cid}")
    b.button(text="👋 Вітання", callback_data=f"tgl_welcome_{cid}")
    b.button(text="📜 Правила", callback_data=f"rules_{cid}")
    b.button(text="🧹 Clear 20", callback_data=f"clear_20_{cid}")
    b.adjust(2,2,2,1)
    return b.as_markup()

def kb_settings(cid):
    ch=db.get_chat(cid); s=ch["settings"]
    def st(v): return "🟢 ON" if v else "🔴 OFF"
    b=InlineKeyboardBuilder()
    b.button(text=f"🤬 Мат {st(s['antimat'])}", callback_data=f"tgl_antimat_{cid}")
    b.button(text=f"🔗 Лінки {st(s['antilink'])}", callback_data=f"tgl_antilink_{cid}")
    b.button(text=f"🌊 Флуд {st(s['antiflood'])}", callback_data=f"tgl_antiflood_{cid}")
    b.button(text=f"🤖 Капча {st(s['captcha'])}", callback_data=f"tgl_captcha_{cid}")
    b.button(text=f"👋 Вітання {st(s['welcome'])}", callback_data=f"tgl_welcome_{cid}")
    b.button(text="◀️ Назад", callback_data=f"main_{cid}")
    b.adjust(2,2,2,1)
    return b.as_markup()

def kb_mod(cid, uid):
    b=InlineKeyboardBuilder()
    b.button(text="🔇 10хв", callback_data=f"act_mute_600_{cid}_{uid}")
    b.button(text="🔇 1год", callback_data=f"act_mute_3600_{cid}_{uid}")
    b.button(text="⚠️ Варн", callback_data=f"act_warn_{cid}_{uid}")
    b.button(text="🔨 Бан", callback_data=f"act_ban_{cid}_{uid}")
    b.button(text="🔊 Розмут", callback_data=f"act_unmute_{cid}_{uid}")
    b.adjust(2,2,1)
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
    info=await bot.get_me()
    if message.chat.type=="private":
        txt=f"""<b>AETHER GAME</b> — захист + ігри ✨

Я — модератор з іграми!

<b>🛡️ Захист:</b>
• Видаляю мати ({len(BAD_WORDS)}+), лінки, флуд
• Капча, вітання, прощання

<b>🎮 Гра:</b>
• Хрестики-Нолики на 2 гравців прямо в чаті!
• Поле оновлюється по черзі для кожного
• Топ гравців

<b>Як підключити:</b>
1. Додай в чат кнопкою
2. Дай адмінку
3. Я напишу панель в чаті

Все кнопками, з анімаціями!
"""
        await message.answer(txt, reply_markup=kb_private(info.username))
    else:
        ch=db.get_chat(message.chat.id); ch["title"]=message.chat.title or ""; db.save()
        try:
            bot_mem=await bot.get_chat_member(message.chat.id, info.id)
            if not is_admin_obj(bot_mem):
                await message.answer(f"👋 Я <b>AETHER GAME</b> ✨\nДай мені адмінку з усіма правами і я напишу панель!")
                return
        except: pass
        if not await is_admin(bot, message): return
        ch["bot_is_admin"]=True; db.save()
        txt=f"""<b>AETHER GAME активований</b> ✨

<b>Чат:</b> {escape(message.chat.title or '')}
<b>Матів:</b> {len(BAD_WORDS)}+

<b>Що є:</b>
🛡️ Авто-модерація з видаленням
🎮 Гра Хрестики-Нолики (2 гравці)
🤖 Капча, вітання, прощання

Керуй кнопками:
"""
        await message.answer(txt, reply_markup=kb_group_main(message.chat.id))

async def cmd_help(message: Message, bot: Bot):
    if message.chat.type!="private" and not await is_admin(bot, message): return
    if message.chat.type=="private":
        info=await bot.get_me()
        await message.answer("<b>AETHER</b> ✨ Натисни щоб додати:", reply_markup=kb_private(info.username))
    else:
        await message.answer(f"<b>AETHER GAME</b> ✨ Панель:", reply_markup=kb_group_main(message.chat.id))

async def cmd_game(message: Message, bot: Bot):
    # Команда для гри в чаті
    if message.chat.type=="private":
        return await message.answer("🎮 Гра працює тільки в групі! Додай бота в чат.")
    txt="""<b>🎮 Хрестики-Нолики</b> ✨

Гра для 2 гравців прямо в чаті!

<b>Як грати:</b>
1. Натисни «Створити гру»
2. Другий гравець натискає «Приєднатись»
3. Ходите по черзі, поле оновлюється автоматично!

Хто перший збере 3 в ряд — виграв! 🏆
"""
    await message.answer(txt, reply_markup=kb_game_lobby())

async def cmd_mute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай на повідомлення!")
    target=message.reply_to_message.from_user
    sec=parse_time(message.text.split()[1]) if len(message.text.split())>1 else 600
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
        await message.answer(f"🔇 {escape(target.first_name)} мут на {format_time(sec)} ✨", reply_markup=kb_mod(message.chat.id, target.id))
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_unmute(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
        await message.answer(f"🔊 {escape(target.first_name)} розмучений ✨")
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_ban(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.answer("❌ Відповідай!")
    target=message.reply_to_message.from_user
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 {escape(target.first_name)} забанений ✨")
        try: await message.reply_to_message.delete()
        except: pass
    except Exception as e: await message.answer(f"❌ {e}")

async def cmd_clear(message: Message, bot: Bot):
    if not await is_admin(bot, message): return await message.answer("❌ Тільки для адмінів!")
    args=message.text.split()
    try: num=int(args[1]) if len(args)>1 else 20
    except: num=20
    num=min(max(num,1),100)
    deleted=0
    for i in range(num+5):
        try:
            await bot.delete_message(message.chat.id, message.message_id - i)
            deleted+=1; await asyncio.sleep(0.05)
        except: continue
    try:
        m=await message.answer(f"🧹 Видалено {deleted} ✨")
        await asyncio.sleep(2)
        try: await m.delete()
        except: pass
    except: pass

# ==================== CALLBACKS ====================
async def cb_handler(call: CallbackQuery, bot: Bot):
    global _game_counter
    # Капча доступна всім, гра доступна всім, інше тільки адмінам
    if call.data.startswith("cap_") or call.data.startswith("verify_") or call.data.startswith("ttt_"):
        pass
    else:
        if call.message.chat.type!="private":
            if not await is_admin(bot, call.message):
                return await call.answer("❌ Тільки для адмінів!", show_alert=True)
    
    data=call.data
    
    # ===== ГРА ХРЕСТИКИ-НОЛИКИ =====
    if data=="ttt_create":
        _game_counter+=1
        game_id=_game_counter
        board=[""]*9
        _games[game_id]={"board":board, "players":[call.from_user.id], "player_names":[call.from_user.first_name], "turn":0, "chat_id":call.message.chat.id, "message_id":None, "status":"waiting"}
        b=InlineKeyboardBuilder()
        b.button(text="👋 Приєднатись як O", callback_data=f"ttt_join_{game_id}")
        b.button(text="🚪 Скасувати", callback_data=f"ttt_cancel_{game_id}")
        b.adjust(1,1)
        txt=f"""<b>🎮 Хрестики-Нолики #{game_id}</b> ✨

Гравець 1 (❌): {escape(call.from_user.first_name)}

Очікуємо гравця 2 (⭕)...
Натисни «Приєднатись»!

{render_board(board)}
"""
        try:
            msg=await call.message.answer(txt, reply_markup=b.as_markup())
            _games[game_id]["message_id"]=msg.message_id
            await call.answer("Гру створено! Очікуємо другого гравця")
        except Exception as e: await call.answer(f"Помилка: {e}", show_alert=True)
        return
    
    if data.startswith("ttt_join_"):
        game_id=int(data.split("_")[2])
        game=_games.get(game_id)
        if not game: return await call.answer("Гра не знайдена", show_alert=True)
        if game["status"]!="waiting": return await call.answer("Гра вже почалась", show_alert=True)
        if call.from_user.id in game["players"]: return await call.answer("Ти вже в грі!", show_alert=True)
        if len(game["players"])>=2: return await call.answer("Місця зайняті (макс 2)", show_alert=True)
        
        game["players"].append(call.from_user.id)
        game["player_names"].append(call.from_user.first_name)
        game["status"]="playing"
        
        # Анімація старту
        txt=f"""<b>🎮 Гра #{game_id} почалась!</b> ✨

❌ {escape(game['player_names'][0])} vs ⭕ {escape(game['player_names'][1])}

Хід: ❌ {escape(game['player_names'][0])}

{render_board(game['board'])}
"""
        try:
            await bot.edit_message_text(chat_id=game["chat_id"], message_id=game["message_id"], text=txt, reply_markup=kb_tictactoe(game_id, game["board"]))
            await call.answer(f"Ти приєднався як ⭕! Твій хід після {game['player_names'][0]}")
        except: await call.answer("Приєднався!")
        return
    
    if data.startswith("ttt_move_"):
        _, _, game_id_s, pos_s = data.split("_")
        game_id=int(game_id_s); pos=int(pos_s)
        game=_games.get(game_id)
        if not game: return await call.answer("Гра не знайдена", show_alert=True)
        if game["status"]!="playing": return await call.answer("Гра закінчена", show_alert=True)
        if call.from_user.id not in game["players"]: return await call.answer("Ти не учасник цієї гри!", show_alert=True)
        
        current_player_idx = game["turn"] % 2
        if game["players"][current_player_idx]!=call.from_user.id:
            return await call.answer(f"Зараз хід {game['player_names'][current_player_idx]}!", show_alert=True)
        
        if game["board"][pos]!="": return await call.answer("Клітинка зайнята!", show_alert=True)
        
        symbol = "X" if current_player_idx==0 else "O"
        game["board"][pos]=symbol
        game["turn"]+=1
        
        winner=check_winner(game["board"])
        if winner:
            if winner=="draw":
                txt=f"""<b>🎮 Гра #{game_id} — Нічия! 🤝</b>

{render_board(game["board'])}

{escape(game['player_names'][0])} (❌) vs {escape(game['player_names'][1])} (⭕)
Нічия! Спробуйте ще!

"""
                b=InlineKeyboardBuilder()
                b.button(text="🔄 Нова гра", callback_data="ttt_create")
                b.adjust(1)
            else:
                win_idx = 0 if winner=="X" else 1
                win_name = game["player_names"][win_idx]
                # Зберігаємо перемогу
                ch=db.get_chat(game["chat_id"])
                ch["games_won"][str(game["players"][win_idx])]=ch["games_won"].get(str(game["players"][win_idx]),0)+1
                db.save()
                txt=f"""<b>🎮 Гра #{game_id} — Перемога! 🏆</b>

{render_board(game["board'])}

🏆 Переміг: {escape(win_name)} ({'❌' if winner=='X' else '⭕'})!
{escape(game['player_names'][0])} (❌) vs {escape(game['player_names'][1])} (⭕)

Вітаємо! ✨
"""
                b=InlineKeyboardBuilder()
                b.button(text="🔄 Реванш", callback_data="ttt_create")
                b.button(text="📊 Топ", callback_data="ttt_top")
                b.adjust(1,1)
            game["status"]="finished"
            try:
                await bot.edit_message_text(chat_id=game["chat_id"], message_id=game["message_id"], text=txt, reply_markup=b.as_markup())
            except: pass
            await call.answer(f"{'Нічия!' if winner=='draw' else f'Переміг {win_name}!'}")
            # Видаляємо гру через 60с
            await asyncio.sleep(60)
            _games.pop(game_id, None)
            return
        else:
            next_idx = game["turn"] % 2
            txt=f"""<b>🎮 Гра #{game_id}</b> ✨

❌ {escape(game['player_names'][0])} vs ⭕ {escape(game['player_names'][1])}

Хід: {'❌' if next_idx==0 else '⭕'} {escape(game['player_names'][next_idx])}

{render_board(game['board'])}
"""
            try:
                await bot.edit_message_text(chat_id=game["chat_id"], message_id=game["message_id"], text=txt, reply_markup=kb_tictactoe(game_id, game["board"]))
                await call.answer(f"Ти поставив {'❌' if symbol=='X' else '⭕'}! Хід суперника")
            except Exception as e: await call.answer(f"Хід зроблено!")
        return
    
    if data.startswith("ttt_cancel_") or data.startswith("ttt_leave_"):
        game_id=int(data.split("_")[2])
        game=_games.get(game_id)
        if game:
            _games.pop(game_id, None)
            try:
                await bot.edit_message_text(chat_id=game["chat_id"], message_id=game["message_id"], text=f"🚪 Гра #{game_id} скасована")
            except: pass
        await call.answer("Гру скасовано")
        return
    
    if data=="ttt_top":
        ch=db.get_chat(call.message.chat.id)
        top=sorted(ch.get("games_won",{}).items(), key=lambda x: x[1], reverse=True)[:10]
        if not top:
            txt="<b>📊 Топ гравців</b>\n\nЩе нема перемог. Зіграй першим! 🎮"
        else:
            lines=[]
            for i,(uid,wins) in enumerate(top):
                # Спробуємо отримати ім'я з бази
                name = ch["users"].get(uid,{}).get("name", f"Гравець {uid[:4]}")
                # Краще взяти з player_names якщо є
                lines.append(f"{i+1}. {name} — {wins} перемог 🏆")
            txt="<b>📊 Топ гравців AETHER</b> 🏆\n\n" + "\n".join(lines)
        b=InlineKeyboardBuilder()
        b.button(text="🎮 Грати", callback_data="ttt_create")
        b.button(text="◀️ Назад", callback_data=f"main_{call.message.chat.id}")
        b.adjust(1,1)
        await call.message.edit_text(txt, reply_markup=b.as_markup())
        await call.answer()
        return
    
    if data=="ttt_ignore":
        await call.answer("Клітинка вже зайнята!", show_alert=True)
        return
    
    # ===== СТАРІ КНОПКИ =====
    if data=="about":
        await call.message.edit_text(f"<b>AETHER GAME</b> ✨\n\n🤬 {len(BAD_WORDS)}+ матів\n🔗 Лінки, флуд, спам\n🤖 Капча з емодзі\n🎮 Гра Хрестики-Нолики на 2 гравців\n👋 Вітання/прощання\n\nВсе кнопками!", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back").as_markup())
        await call.answer(); return
    if data=="about_game":
        await call.message.edit_text("<b>🎮 Гра Хрестики-Нолики</b>\n\n• 2 гравці\n• Поле 3x3 оновлюється по черзі\n• Кнопки ⬜ → ❌/⭕\n• Перемога 3 в ряд\n• Топ гравців\n\nПрацює тільки в групі! Напиши /game", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back").as_markup())
        await call.answer(); return
    if data=="back":
        info=await bot.get_me()
        await call.message.edit_text("<b>AETHER GAME</b> ✨ Натисни щоб додати:", reply_markup=kb_private(info.username))
        await call.answer(); return
    
    if data.startswith("main_"):
        cid=int(data.split("_")[1])
        ch=db.get_chat(cid)
        await call.message.edit_text(f"<b>AETHER GAME</b> ✨\nЧат: {escape(ch.get('title',''))}", reply_markup=kb_group_main(cid))
        await call.answer(); return
    
    if data.startswith("cfg_") or data.startswith("game_"):
        cid=int(data.split("_")[1])
        if data.startswith("cfg_"):
            await call.message.edit_text(f"<b>⚙️ Налаштування</b> ID: <code>{cid}</code>", reply_markup=kb_settings(cid))
        else:
            await call.message.edit_text(f"<b>🎮 Гра</b> ✨\nОбери дію:", reply_markup=InlineKeyboardBuilder().button(text="🎮 Створити гру", callback_data="ttt_create").button(text="📊 Топ", callback_data="ttt_top").button(text="◀️ Назад", callback_data=f"main_{cid}").adjust(1,1,1).as_markup())
        await call.answer(); return
    
    if data.startswith("rules_"):
        cid=int(data.split("_")[1]); ch=db.get_chat(cid)
        await call.message.edit_text(f"<b>📜 Правила</b> ✨\n\n{escape(ch['rules'])}", reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data=f"main_{cid}").as_markup())
        await call.answer(); return
    
    if data.startswith("tgl_"):
        parts=data.split("_"); key=parts[1]
        if len(parts)==4: key=parts[1]+"_"+parts[2]; cid=int(parts[3])
        else: cid=int(parts[2])
        ch=db.get_chat(cid)
        if key in ch["settings"]:
            ch["settings"][key]=not ch["settings"][key]; db.save()
            await call.answer(f"{key} {'ON' if ch['settings'][key] else 'OFF'} ✨")
            await call.message.edit_reply_markup(reply_markup=kb_settings(cid))
        return
    
    if data.startswith("clear_"):
        num=int(data.split("_")[1]); cid=int(data.split("_")[2])
        deleted=0
        for i in range(num+5):
            try: await bot.delete_message(cid, call.message.message_id - i); deleted+=1; await asyncio.sleep(0.05)
            except: continue
        await call.answer(f"Видалено {deleted} ✨"); return
    
    if data.startswith("act_"):
        parts=data.split("_"); action=parts[1]
        if action=="mute":
            sec=int(parts[2]); cid=int(parts[3]); uid=int(parts[4])
            try: await bot.restrict_chat_member(cid, uid, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec)); await call.message.edit_text(f"🔇 Мут {format_time(sec)} ✨")
            except Exception as e: await call.answer(f"{e}", show_alert=True)
        elif action=="warn":
            cid=int(parts[2]); uid=int(parts[3]); cnt=db.add_warn(cid, uid); await call.message.edit_text(f"⚠️ Варн {cnt}/3 ✨")
        elif action=="unwarn":
            cid=int(parts[2]); uid=int(parts[3]); new=db.dec_warn(cid, uid); await call.message.edit_text(f"✅ Знято {new}/3 ✨")
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
        if call.from_user.id!=uid: return await call.answer("Не твоя капча!", show_alert=True)
        emojis=["🦊","🐶","🐱","🐰","🦁","🐯"]; correct=random.choice(emojis); opts=random.sample(emojis,4)
        if correct not in opts: opts[0]=correct
        random.shuffle(opts)
        _captcha[(call.message.chat.id, uid)]=correct
        await call.message.edit_text(f"<b>Перевірка</b> ✨ Натисни <b>{correct}</b>:", reply_markup=kb_captcha(uid, correct, opts))
        await call.answer(); return
    
    if data.startswith("cap_"):
        _, uid_s, chosen, correct = data.split("_",3)
        uid_s=int(uid_s)
        if call.from_user.id!=uid_s: return await call.answer("Не твоя капча!", show_alert=True)
        if chosen==correct:
            _captcha.pop((call.message.chat.id, uid_s),None)
            try:
                await bot.restrict_chat_member(call.message.chat.id, uid_s, permissions=ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
                ch=db.get_chat(call.message.chat.id)
                welcome=ch["welcome_text"].format(name=escape(call.from_user.first_name), chat=escape(call.message.chat.title or "чат"))
                await call.message.edit_text(f"{welcome}\n\n✅ Ласкаво просимо! ✨")
            except: await call.message.edit_text("✅ Пройдено ✨")
            await call.answer("Вітаємо!")
        else:
            try:
                await bot.ban_chat_member(call.message.chat.id, uid_s)
                await bot.unban_chat_member(call.message.chat.id, uid_s)
                await call.message.edit_text(f"🚫 {escape(call.from_user.first_name)} не пройшов")
            except: pass
            await call.answer("Невірно!", show_alert=True)
        return

async def auto_mod(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot: return
    if message.chat.type not in {"group","supergroup"}: return
    if message.sender_chat and message.chat and message.sender_chat.id == message.chat.id: return
    try:
        mem=await bot.get_chat_member(message.chat.id, message.from_user.id)
        if is_admin_obj(mem): return
    except: pass
    ch=db.get_chat(message.chat.id); s=ch["settings"]; text=message.text or message.caption or ""
    uid=str(message.from_user.id)
    if uid not in ch["users"]: ch["users"][uid]={"warns":0,"messages":0}
    ch["users"][uid]["messages"]=ch["users"][uid].get("messages",0)+1
    db.save()
    if s.get("antiflood") and is_flood(message.chat.id, message.from_user.id):
        try: await message.delete()
        except: pass
        if s.get("automute"):
            try: await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=600))
            except: pass
        _flood[(message.chat.id, message.from_user.id)]=[]
        return
    if s.get("antilink") and contains_link(text):
        try: await message.delete()
        except: pass
        cnt=db.add_warn(message.chat.id, message.from_user.id) if s.get("autowarn") else 1
        if s.get("automute"):
            try: await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=300))
            except: pass
        return
    if s.get("antimat"):
        bad=contains_bad(text, ch.get("banned_words",[]))
        if bad:
            try: await message.delete()
            except: pass
            db.add_warn(message.chat.id, message.from_user.id)
            if s.get("automute"):
                try: await bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=ch["mute_time"]))
                except: pass
            return

async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    ch=db.get_chat(event.chat.id)
    if event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        user=event.new_chat_member.user
        if user.is_bot: return
        uid=str(user.id); ch["users"][uid]=ch["users"].get(uid,{"warns":0,"messages":0}); db.save()
        if ch["settings"].get("captcha", True):
            try:
                await bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
                await bot.send_message(event.chat.id, f"Привіт, {escape(user.first_name)} 👋 Ласкаво! Пройди перевірку:", reply_markup=kb_verify(user.id))
            except: pass
        else:
            if ch["settings"].get("welcome", True):
                try: await bot.send_message(event.chat.id, ch["welcome_text"].format(name=escape(user.first_name), chat=escape(event.chat.title or "чат")))
                except: pass

async def bot_admin_handler(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.user.id != bot.id: return
    if not is_admin_obj(event.new_chat_member): return
    if is_admin_obj(event.old_chat_member): return
    ch=db.get_chat(event.chat.id)
    ch["bot_is_admin"]=True; ch["title"]=event.chat.title or ""; db.save()
    txt=f"""<b>AETHER GAME активований</b> ✨

Чат: {escape(event.chat.title or '')}

🛡️ Авто-видалення мату, лінків, флуду
🎮 Гра Хрестики-Нолики — /game
🤖 Капча, вітання, прощання

Керуй кнопками (тільки адміни):
"""
    try: await bot.send_message(event.chat.id, txt, reply_markup=kb_group_main(event.chat.id))
    except: pass

async def main():
    bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    dp=Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def h_start(m: Message): await cmd_start(m, bot)
    @dp.message(Command("help"))
    async def h_help(m: Message): await cmd_help(m, bot)
    @dp.message(Command("game"))
    async def h_game(m: Message): await cmd_game(m, bot)
    @dp.message(Command("mute"))
    async def h_mute(m: Message): await cmd_mute(m, bot)
    @dp.message(Command("unmute"))
    async def h_unmute(m: Message): await cmd_unmute(m, bot)
    @dp.message(Command("ban"))
    async def h_ban(m: Message): await cmd_ban(m, bot)
    @dp.message(Command("clear"))
    async def h_clear(m: Message): await cmd_clear(m, bot)

    @dp.callback_query()
    async def h_cb(c: CallbackQuery): await cb_handler(c, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER | IS_NOT_MEMBER))
    async def h_join(e: ChatMemberUpdated): await welcome_handler(e, bot)

    @dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
    async def h_bot_admin(e: ChatMemberUpdated): await bot_admin_handler(e, bot)

    @dp.message(F.chat.type.in_({"group","supergroup"}))
    async def h_auto(m: Message): await auto_mod(m, bot)

    logger.info("AETHER v11 GAME started!")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
