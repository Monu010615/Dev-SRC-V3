# batch.py
# ---------------------------
# Imports and Setup
# ---------------------------
import os, re, time, asyncio, json, signal, sys
from pyrogram import Client, filters
from pyrogram.types import Message
from utils import get_caption, get_msg, copy_msg, download_msg, upload_msg
from utils.func import get_user_data, get_user_data_key, process_text_with_rules, is_premium_user, E
from utils.encrypt import dcs
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress
from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_video_metadata, screenshot, thumbnail

Y = None if not STRING else __import__('shared_client').userbot
Z, P, UB, UC, emp = {}, {}, {}, {}, {}
ACTIVE_USERS = {}
ACTIVE_USERS_FILE = "active_users.json"

# ---------------------------
# Shutdown handler
# ---------------------------
def shutdown_handler(*_):
    print("[INFO] Shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ---------------------------
# File / Active Users Utilities
# ---------------------------
def sanitize(filename):
    return re.sub(r'[<>:"/\\|?*\']', '_', filename).strip(" .")[:255]

def load_active_users():
    try:
        if os.path.exists(ACTIVE_USERS_FILE):
            with open(ACTIVE_USERS_FILE, 'r') as f:
                data = json.load(f)
                print(f"[DEBUG] Loaded active users: {data}")
                return data
        return {}
    except Exception as e:
        print(f"[ERROR] Loading active users failed: {e}")
        return {}

async def save_active_users_to_file():
    try:
        with open(ACTIVE_USERS_FILE, 'w') as f:
            json.dump(ACTIVE_USERS, f)
        print("[DEBUG] Active users saved")
    except Exception as e:
        print(f"[ERROR] Saving active users failed: {e}")

async def add_active_batch(user_id: int, batch_info: dict):
    ACTIVE_USERS[str(user_id)] = batch_info
    await save_active_users_to_file()
    print(f"[DEBUG] Added active batch for user {user_id}")

def is_user_active(user_id: int) -> bool:
    return str(user_id) in ACTIVE_USERS

async def update_batch_progress(user_id: int, current: int, success: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["current"] = current
        ACTIVE_USERS[str(user_id)]["success"] = success
        await save_active_users_to_file()
        print(f"[DEBUG] Updated batch progress: user={user_id}, current={current}, success={success}")

async def request_batch_cancel(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["cancel_requested"] = True
        await save_active_users_to_file()
        print(f"[DEBUG] Batch cancel requested for user {user_id}")
        return True
    return False

def should_cancel(user_id: int) -> bool:
    user_str = str(user_id)
    return user_str in ACTIVE_USERS and ACTIVE_USERS[user_str].get("cancel_requested", False)

async def remove_active_batch(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        del ACTIVE_USERS[str(user_id)]
        await save_active_users_to_file()
        print(f"[DEBUG] Removed active batch for user {user_id}")

def get_batch_info(user_id: int):
    return ACTIVE_USERS.get(str(user_id))

ACTIVE_USERS = load_active_users()

# ---------------------------
# Pyrogram Helpers
# ---------------------------
async def upd_dlg(c):
    try:
        async for _ in c.get_dialogs(limit=100): pass
        print(f"[DEBUG] Dialogs updated for {c.me.username}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update dialogs: {e}")
        return False

# ---------------------------
# Get message function
# ---------------------------
async def get_msg(c, u, i, d, lt):
    try:
        print(f"[DEBUG] get_msg start: chat={i}, msg_id={d}, type={lt}")
        if lt == 'public':
            try:
                if str(i).lower().endswith('bot'):
                    emp[i] = False
                    xm = await u.get_messages(i, d)
                    emp[i] = getattr(xm, "empty", False)
                    if not emp[i]:
                        emp[i] = True
                        print(f"[DEBUG] Bot chat fetched: {xm}")
                        return xm
                if emp[i]:
                    xm = await c.get_messages(i, d)
                    emp[i] = getattr(xm, "empty", False)
                    print(f"[DEBUG] Public chat fetched by {c.me.username}")
                    if emp[i]:
                        try: await u.join_chat(i)
                        except: pass
                        xm = await u.get_messages((await u.get_chat(f'@{i}')).id, d)
                    return xm
            except Exception as e:
                print(f"[ERROR] Error fetching public message: {e}")
                return None
        else:
            if u:
                try:
                    async for _ in u.get_dialogs(limit=50): pass
                    chat_id_100, chat_id_dash = i, i
                    if str(i).startswith('-100'):
                        base_id = str(i)[4:]
                        chat_id_dash = f"-{base_id}"
                    elif i.isdigit():
                        chat_id_100 = f"-100{i}"
                        chat_id_dash = f"-{i}"
                    try:
                        result = await u.get_messages(chat_id_100, d)
                        if result and not getattr(result, "empty", False):
                            return result
                    except: pass
                    try:
                        result = await u.get_messages(chat_id_dash, d)
                        if result and not getattr(result, "empty", False):
                            return result
                    except: pass
                    try:
                        async for _ in u.get_dialogs(limit=200): pass
                        result = await u.get_messages(i, d)
                        if result and not getattr(result, "empty", False):
                            return result
                    except: pass
                    return None
                except Exception as e:
                    print(f"[ERROR] Private channel error: {e}")
                    return None
            return None
    except Exception as e:
        print(f"[ERROR] get_msg failed: {e}")
        return None

# ---------------------------
# Userbot / Bot helpers
# ---------------------------
async def get_ubot(uid):
    bt = await get_user_data_key(uid, "bot_token", None)
    if not bt: return None
    if uid in UB: return UB.get(uid)
    try:
        bot = Client(f"user_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH)
        await bot.start()
        UB[uid] = bot
        print(f"[DEBUG] Started user bot for {uid}")
        return bot
    except Exception as e:
        print(f"[ERROR] Error starting bot for user {uid}: {e}")
        return None

async def get_uclient(uid):
    ud = await get_user_data(uid)
    ubot = UB.get(uid)
    cl = UC.get(uid)
    if cl: return cl
    if not ud: return ubot if ubot else None
    xxx = ud.get('session_string')
    if xxx:
        try:
            ss = dcs(xxx)
            gg = Client(f'{uid}_client', api_id=API_ID, api_hash=API_HASH, device_model="v3saver", session_string=ss)
            await gg.start()
            await upd_dlg(gg)
            UC[uid] = gg
            print(f"[DEBUG] Started user client for {uid}")
            return gg
        except Exception as e:
            print(f"[ERROR] User client error: {e}")
            return ubot if ubot else Y
    return Y

# ---------------------------
# Progress helper
# ---------------------------
async def prog(c, t, C, h, m, st):
    global P
    p = c/t*100
    interval = 10 if t>=100*1024*1024 else 20 if t>=50*1024*1024 else 30 if t>=10*1024*1024 else 50
    step = int(p//interval)*interval
    if m not in P or P[m]!=step or p>=100:
        P[m]=step
        c_mb=t_mb=0
        try: c_mb=c/(1024*1024); t_mb=t/(1024*1024)
        except: pass
        bar='🟢'*int(p/10)+'🔴'*(10-int(p/10))
        speed=c/(time.time()-st)/(1024*1024) if time.time()>st else 0
        eta=time.strftime('%M:%S', time.gmtime((t-c)/(speed*1024*1024))) if speed>0 else '00:00'
        await C.edit_message_text(h, m, f"__**Pyro Handler...**__\n\n{bar}\n\n⚡**Completed**: {c_mb:.2f} MB / {t_mb:.2f} MB\n📊 **Done**: {p:.2f}%\n🚀 **Speed**: {speed:.2f} MB/s\n⏳ **ETA**: {eta}\n\n**Powered by Team SPY**")
        if p>=100: P.pop(m,None)

# ---------------------------
# Process single message
# ---------------------------
async def process_msg(c,u,m,d,lt,uid,i):
    try:
        print(f"[DEBUG] START process_msg | chat={d}, uid={uid}")
        tcid=d; rtmid=None
        cfg_chat = await get_user_data_key(d,'chat_id',None)
        if cfg_chat:
            if '/' in cfg_chat:
                parts = cfg_chat.split('/',1)
                tcid=int(parts[0])
                rtmid=int(parts[1]) if len(parts)>1 else None
            else:
                tcid=int(cfg_chat)
        if m.media:
            orig_text = m.caption.markdown if m.caption else ''
            proc_text = await process_text_with_rules(d, orig_text)
            user_cap = await get_user_data_key(d,'caption','')
            ft = f'{proc_text}\n\n{user_cap}' if proc_text and user_cap else user_cap if user_cap else proc_text
            st=time.time()
            p = await c.send_message(d,'Downloading...')
            c_name=f"{time.time()}"
            if m.video: file_name=m.video.file_name or f"{time.time()}.mp4"
            elif m.audio: file_name=m.audio.file_name or f"{time.time()}.mp3"
            elif m.document: file_name=m.document.file_name or f"{time.time()}"
            elif m.photo: file_name=f"{time.time()}.jpg"
            c_name = sanitize(file_name)
            f = await u.download_media(m,file_name=c_name,progress=prog,progress_args=(c,d,p.id,st))
            if not f: await c.edit_message_text(d,p.id,'Failed.'); return 'Failed.'
            await c.edit_message_text(d,p.id,'Renaming...')
            if ((m.video and m.video.file_name) or (m.audio and m.audio.file_name) or (m.document and m.document.file_name)):
                f = await rename_file(f,d,p)
            fsize = os.path.getsize(f)/(1024*1024*1024)
            th=None
            if fsize>2 and Y:
                st=time.time(); await c.edit_message_text(d,p.id,'File >2GB. Using alternative...')
                await upd_dlg(Y)
                mtd=await get_video_metadata(f)
                dur,h,w = mtd['duration'],mtd['width'],mtd['height']
                th = await screenshot(f,d)
                sent = await Y.send_document(LOG_GROUP,f,thumb=th,caption=ft if m.caption else None,reply_to_message_id=rtmid,progress=prog,progress_args=(c,d,p.id,st))
                await c.copy_message(d,LOG_GROUP,sent.id)
                os.remove(f); await c.delete_messages(d,p.id)
                return 'Done (Large file)'
            await c.edit_message_text(d,p.id,'Uploading...')
            st=time.time()
            try: await c.send_document(tcid,document=f,caption=ft if m.caption else None,reply_to_message_id=rtmid,progress=prog,progress_args=(c,d,p.id,st))
            except Exception as e:
                await c.edit_message_text(d,p.id,f'Upload failed: {str(e)[:30]}'); os.remove(f) if os.path.exists(f) else None; return 'Failed.'
            os.remove(f); await c.delete_messages(d,p.id)
            return 'Done.'
        elif m.text:
            await c.send_message(tcid,text=m.text.markdown,reply_to_message_id=rtmid)
            return 'Sent.'
    except Exception as e:
        print(f"[ERROR] process_msg failed: {e}")
        return f'Error: {str(e)[:50]}'

# ---------------------------
# Command Handlers
# ---------------------------
@X.on_message(filters.command(['batch','single']))
async def process_cmd(c,m):
    uid = m.from_user.id
    cmd = m.command[0]
    if FREEMIUM_LIMIT==0 and not await is_premium_user(uid):
        await m.reply_text("Bot does not provide free services, get subscription.")
        return
    if await sub(c,m)==1: return
    pro = await m.reply_text('Doing checks...')
    if is_user_active(uid):
        await pro.edit('Active task exists. Use /stop.')
        return
    ubot = await get_ubot(uid)
    if not ubot: await pro.edit('Add bot with /setbot first'); return
    Z[uid] = {'step':'start' if cmd=='batch' else 'start_single'}
    await pro.edit(f'Send {"start link..." if cmd=="batch" else "link to process"}.')

@X.on_message(filters.command(['cancel','stop']))
async def cancel_cmd(c,m):
    uid=m.from_user.id
    if is_user_active(uid):
        if await request_batch_cancel(uid):
            await m.reply_text('Cancellation requested. Batch will stop after current download.')
        else: await m.reply_text('Failed to request cancellation.')
    else: await m.reply_text('No active batch found.')

# ---------------------------
# Text handler
# ---------------------------
@X.on_message(filters.text & filters.private & ~login_in_progress & ~filters.command(['start','batch','cancel','login','logout','stop','set','pay','redeem','gencode','single','generate','keyinfo','encrypt','decrypt','keys','setbot','rembot']))
async def text_handler(c,m):
    uid=m.from_user.id
    if uid not in Z: return
    s=Z[uid].get('step')
    if s=='start':
        L=m.text; i,d,lt=E(L)
        if not i or not d: await m.reply_text('Invalid link.'); Z.pop(uid,None); return
        Z[uid].update({'step':'count','cid':i,'sid':d,'lt':lt})
        await m.reply_text('How many messages?')
    elif s=='start_single':
        L=m.text; i,d,lt=E(L)
        if not i or not d: await m.reply_text('Invalid link.'); Z.pop(uid,None); return
        Z[uid].update({'step':'process_single','cid':i,'sid':d,'lt':lt})
        i,s,lt=Z[uid]['cid'],Z[uid]['sid'],Z[uid]['lt']
        pt=await m.reply_text('Processing...')
        ubot=UB.get(uid)
        if not ubot: await pt.edit('Add bot with /setbot first'); Z.pop(uid,None); return
        uc=await get_uclient(uid)
        if not uc: await pt.edit('Cannot proceed without client'); Z.pop(uid,None); return
        if is_user_active(uid): await pt.edit('Active task exists. Use /stop'); Z.pop(uid,None); return
        try:
            msg = await get_msg(ubot,uc,i,s,lt)
            if msg:
                res = await process_msg(ubot,uc,msg,str(m.chat.id),lt,uid,i)
                await pt.edit(f'1/1: {res}')
            else: await pt.edit('Message not found')
        except Exception as e:
            print(f"[ERROR] process_msg failed: {str(e)}")
            await pt.edit(f'Error: {str(e)[:50]}')
        finally:
            Z.pop(uid,None)
