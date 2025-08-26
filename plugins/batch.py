# ---------------------------
# IMPORTS
# ---------------------------
import os
import re
import time
import json
import asyncio
import signal
import sys
from typing import Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant

from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata
from utils.func import get_user_data_key, process_text_with_rules, is_premium_user, E
from utils.encrypt import dcs
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress

# ---------------------------
# GLOBALS
# ---------------------------
Y = None if not STRING else __import__('shared_client').userbot
Z, P, UB, UC, emp = {}, {}, {}, {}, {}
ACTIVE_USERS = {}
ACTIVE_USERS_FILE = "active_users.json"

# ---------------------------
# SHUTDOWN HANDLER
# ---------------------------
def shutdown_handler(*_):
    print("[INFO] Shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ---------------------------
# UTILITIES
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
        print(f"[ERROR] Failed to load active users: {e}")
        return {}

async def save_active_users_to_file():
    try:
        with open(ACTIVE_USERS_FILE, 'w') as f:
            json.dump(ACTIVE_USERS, f)
        print(f"[DEBUG] Active users saved successfully")
    except Exception as e:
        print(f"[ERROR] Saving active users failed: {e}")

async def add_active_batch(user_id: int, batch_info: Dict[str, Any]):
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
        print(f"[DEBUG] Batch progress updated for {user_id}: {current}/{ACTIVE_USERS[str(user_id)]['total']} success={success}")

async def request_batch_cancel(user_id: int):
    if str(user_id) in ACTIVE_USERS:
        ACTIVE_USERS[str(user_id)]["cancel_requested"] = True
        await save_active_users_to_file()
        print(f"[DEBUG] Cancellation requested for user {user_id}")
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

def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
    return ACTIVE_USERS.get(str(user_id))

ACTIVE_USERS = load_active_users()

# ---------------------------
# UPDATE DIALOGS (helper)
# ---------------------------
async def upd_dlg(c):
    try:
        async for _ in c.get_dialogs(limit=100):
            pass
        print(f"[DEBUG] Dialogs updated for client {c.me.username}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update dialogs: {e}")
        return False

# ---------------------------
# FETCH MESSAGE
# ---------------------------
async def get_msg(c, u, i, d, lt):
    try:
        print(f"[DEBUG] get_msg called | lt={lt} i={i} d={d}")
        if lt == 'public':
            try:
                if str(i).lower().endswith('bot'):
                    emp[i] = False
                    xm = await u.get_messages(i, d)
                    emp[i] = getattr(xm, "empty", False)
                    if not emp[i]:
                        emp[i] = True
                        print(f"[INFO] Bot chat found successfully, returning message {xm}")
                        return xm
                    
                if emp.get(i, True):
                    xm = await c.get_messages(i, d)
                    emp[i] = getattr(xm, "empty", False)
                    if emp[i]:
                        print(f"[WARNING] Not fetched by {c.me.username}, trying join")
                        try: await u.join_chat(i)
                        except: pass
                        xm = await u.get_messages((await u.get_chat(f'@{i}')).id, d)
                        print(f"[INFO] Returning message after join: {xm}")
                    return xm
            except Exception as e:
                print(f"[ERROR] Public message fetch error: {e}")
                return None
        else:
            if u:
                try:
                    async for _ in u.get_dialogs(limit=50): pass
                    chat_id_100, chat_id_dash = None, None
                    if str(i).startswith('-100'):
                        chat_id_100 = i
                        base_id = str(i)[4:]
                        chat_id_dash = f"-{base_id}"
                    elif i.isdigit():
                        chat_id_100 = f"-100{i}"
                        chat_id_dash = f"-{i}"
                    else:
                        chat_id_100 = i
                        chat_id_dash = i
                    
                    try:
                        result = await u.get_messages(chat_id_100, d)
                        if result and not getattr(result, "empty", False):
                            print(f"[INFO] get_msg returning result from chat_id_100")
                            return result
                    except Exception:
                        pass
                    try:
                        result = await u.get_messages(chat_id_dash, d)
                        if result and not getattr(result, "empty", False):
                            print(f"[INFO] get_msg returning result from chat_id_dash")
                            return result
                    except Exception:
                        pass
                    try:
                        async for _ in u.get_dialogs(limit=200): pass
                        result = await u.get_messages(i, d)
                        if result and not getattr(result, "empty", False):
                            print(f"[INFO] get_msg returning result from generic id")
                            return result
                    except Exception:
                        pass
                    print(f"[WARNING] get_msg returning None for {i}")
                    return None
                except Exception as e:
                    print(f"[ERROR] Private channel fetch error: {e}")
                    return None
            return None
    except Exception as e:
        print(f"[ERROR] get_msg general error: {e}")
        return None

# ---------------------------
# GET BOT AND USER CLIENT
# ---------------------------
async def get_ubot(uid):
    bt = await get_user_data_key(uid, "bot_token", None)
    if not bt:
        print(f"[WARNING] No bot token found for user {uid}")
        return None
    if uid in UB:
        return UB.get(uid)
    try:
        bot = Client(f"user_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH)
        await bot.start()
        UB[uid] = bot
        print(f"[INFO] Bot started for user {uid}")
        return bot
    except Exception as e:
        print(f"[ERROR] Starting bot failed for user {uid}: {e}")
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
            print(f"[INFO] User client started for {uid}")
            return gg
        except Exception as e:
            print(f"[ERROR] User client error: {e}")
            return ubot if ubot else Y
    return Y

# ---------------------------
# PROGRESS UPDATE
# ---------------------------
async def prog(c, t, C, h, m, st):
    global P
    p = c / t * 100
    interval = 10 if t >= 100 * 1024 * 1024 else 20 if t >= 50 * 1024 * 1024 else 30 if t >= 10 * 1024 * 1024 else 50
    step = int(p // interval) * interval
    if m not in P or P[m] != step or p >= 100:
        P[m] = step
        c_mb = c / (1024 * 1024)
        t_mb = t / (1024 * 1024)
        bar = '🟢' * int(p / 10) + '🔴' * (10 - int(p / 10))
        speed = c / (time.time() - st) / (1024 * 1024) if time.time() > st else 0
        eta = time.strftime('%M:%S', time.gmtime((t - c) / (speed * 1024 * 1024))) if speed > 0 else '00:00'
        await C.edit_message_text(h, m, f"__**Pyro Handler...**__\n\n{bar}\n\n⚡**__Completed__**: {c_mb:.2f} MB / {t_mb:.2f} MB\n📊 **__Done__**: {p:.2f}%\n🚀 **__Speed__**: {speed:.2f} MB/s\n⏳ **__ETA__**: {eta}\n\n**__Powered by Team SPY__**")
        print(f"[DEBUG] Progress updated: {p:.2f}% for message {m}")
        if p >= 100: P.pop(m, None)

# ---------------------------
# DIRECT SEND FUNCTION
# ---------------------------
async def send_direct(c, m, tcid, ft=None, rtmid=None):
    try:
        if m.video:
            await c.send_video(tcid, m.video.file_id, caption=ft, duration=m.video.duration, width=m.video.width, height=m.video.height, reply_to_message_id=rtmid)
        elif m.video_note:
            await c.send_video_note(tcid, m.video_note.file_id, reply_to_message_id=rtmid)
        elif m.voice:
            await c.send_voice(tcid, m.voice.file_id, reply_to_message_id=rtmid)
        elif m.sticker:
            await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
        elif m.audio:
            await c.send_audio(tcid, m.audio.file_id, caption=ft, duration=m.audio.duration, performer=m.audio.performer, title=m.audio.title, reply_to_message_id=rtmid)
        elif m.photo:
            photo_id = m.photo.file_id if hasattr(m.photo, 'file_id') else m.photo[-1].file_id
            await c.send_photo(tcid, photo_id, caption=ft, reply_to_message_id=rtmid)
        elif m.document:
            await c.send_document(tcid, m.document.file_id, caption=ft, file_name=m.document.file_name, reply_to_message_id=rtmid)
        else:
            return False
        print(f"[INFO] Sent directly to {tcid}")
        return True
    except Exception as e:
        print(f"[ERROR] Direct send failed: {e}")
        return False

  # ---------------------------
# PROCESS SINGLE MESSAGE
# ---------------------------
async def process_msg(c, u, m, d, lt, uid, i):
    try:
        print(f"[DEBUG] START process_msg | mid={d} uid={uid} | media={m.media}")
        cfg_chat = await get_user_data_key(d, 'chat_id', None)
        tcid = d
        rtmid = None
        if cfg_chat:
            if '/' in cfg_chat:
                parts = cfg_chat.split('/', 1)
                tcid = int(parts[0])
                rtmid = int(parts[1]) if len(parts) > 1 else None
            else:
                tcid = int(cfg_chat)
        
        if m.media:
            orig_text = m.caption.markdown if m.caption else ''
            proc_text = await process_text_with_rules(d, orig_text)
            user_cap = await get_user_data_key(d, 'caption', '')
            ft = f'{proc_text}\n\n{user_cap}' if proc_text and user_cap else user_cap if user_cap else proc_text
            
            if lt == 'public' and not emp.get(i, False):
                sent = await send_direct(c, m, tcid, ft, rtmid)
                print(f"[DEBUG] Sent directly: {sent}")
                return 'Sent directly.'
            
            st = time.time()
            p = await c.send_message(d, 'Downloading...')
            print(f"[DEBUG] Download message created | id={p.id}")

            # Determine filename
            c_name = f"{time.time()}"
            if m.video:
                file_name = m.video.file_name or f"{time.time()}.mp4"
            elif m.audio:
                file_name = m.audio.file_name or f"{time.time()}.mp3"
            elif m.document:
                file_name = m.document.file_name or f"{time.time()}"
            elif m.photo:
                file_name = f"{time.time()}.jpg"
            else:
                file_name = f"{time.time()}"
            c_name = sanitize(file_name)
            print(f"[DEBUG] File will be saved as {c_name}")

            f = await u.download_media(m, file_name=c_name, progress=prog, progress_args=(c, d, p.id, st))
            if not f:
                await c.edit_message_text(d, p.id, 'Failed.')
                print("[ERROR] Download failed")
                return 'Failed.'
            print(f"[INFO] Media downloaded: {f}")

            await c.edit_message_text(d, p.id, 'Renaming...')
            if (m.video and m.video.file_name) or (m.audio and m.audio.file_name) or (m.document and m.document.file_name):
                f = await rename_file(f, d, p)
                print(f"[DEBUG] File renamed to {f}")

            fsize = os.path.getsize(f) / (1024 * 1024 * 1024)
            th = thumbnail(d)

            # Large file handling
            if fsize > 2 and Y:
                st = time.time()
                await c.edit_message_text(d, p.id, 'File is larger than 2GB. Using alternative method...')
                await upd_dlg(Y)
                mtd = await get_video_metadata(f)
                dur, h, w = mtd['duration'], mtd['width'], mtd['height']
                th = await screenshot(f, dur, d)
                print("[INFO] Sending large file via alternative method")

                send_funcs = {'video': Y.send_video, 'video_note': Y.send_video_note, 'voice': Y.send_voice,
                              'audio': Y.send_audio, 'photo': Y.send_photo, 'document': Y.send_document}

                for mtype, func in send_funcs.items():
                    if f.endswith('.mp4'): mtype = 'video'
                    if getattr(m, mtype, None):
                        sent = await func(LOG_GROUP, f, thumb=th if mtype == 'video' else None, 
                                          duration=dur if mtype == 'video' else None,
                                          height=h if mtype == 'video' else None,
                                          width=w if mtype == 'video' else None,
                                          caption=ft if m.caption and mtype not in ['video_note', 'voice'] else None,
                                          reply_to_message_id=rtmid, progress=prog, progress_args=(c, d, p.id, st))
                        print(f"[DEBUG] Large file sent via Y: {sent}")
                        break
                else:
                    sent = await Y.send_document(LOG_GROUP, f, thumb=th, caption=ft if m.caption else None,
                                                 reply_to_message_id=rtmid, progress=prog, progress_args=(c, d, p.id, st))
                
                await c.copy_message(d, LOG_GROUP, sent.id)
                os.remove(f)
                await c.delete_messages(d, p.id)
                print("[INFO] Large file processing done")
                return 'Done (Large file).'
            
            # Normal upload
            await c.edit_message_text(d, p.id, 'Uploading...')
            st = time.time()
            try:
                if m.video or os.path.splitext(f)[1].lower() == '.mp4':
                    mtd = await get_video_metadata(f)
                    dur, h, w = mtd['duration'], mtd['width'], mtd['height']
                    th = await screenshot(f, dur, d)
                    await c.send_video(tcid, video=f, caption=ft if m.caption else None,
                                       thumb=th, width=w, height=h, duration=dur,
                                       progress=prog, progress_args=(c, d, p.id, st),
                                       reply_to_message_id=rtmid)
                elif m.video_note:
                    await c.send_video_note(tcid, video_note=f, progress=prog,
                                            progress_args=(c, d, p.id, st), reply_to_message_id=rtmid)
                elif m.voice:
                    await c.send_voice(tcid, f, progress=prog, progress_args=(c, d, p.id, st),
                                       reply_to_message_id=rtmid)
                elif m.sticker:
                    await c.send_sticker(tcid, m.sticker.file_id)
                elif m.audio:
                    await c.send_audio(tcid, audio=f, caption=ft if m.caption else None,
                                       thumb=th, progress=prog, progress_args=(c, d, p.id, st),
                                       reply_to_message_id=rtmid)
                elif m.photo:
                    await c.send_photo(tcid, photo=f, caption=ft if m.caption else None,
                                       progress=prog, progress_args=(c, d, p.id, st),
                                       reply_to_message_id=rtmid)
                else:
                    await c.send_document(tcid, document=f, caption=ft if m.caption else None,
                                          progress=prog, progress_args=(c, d, p.id, st),
                                          reply_to_message_id=rtmid)
                print(f"[INFO] File uploaded successfully: {f}")
            except Exception as e:
                await c.edit_message_text(d, p.id, f'Upload failed: {str(e)[:30]}')
                if os.path.exists(f): os.remove(f)
                print(f"[ERROR] Upload failed: {e}")
                return 'Failed.'
            
            os.remove(f)
            await c.delete_messages(d, p.id)
            print("[DEBUG] process_msg completed successfully")
            return 'Done.'
        
        elif m.text:
            await c.send_message(tcid, text=m.text.markdown, reply_to_message_id=rtmid)
            print("[DEBUG] Text message sent successfully")
            return 'Sent.'
    except Exception as e:
        print(f"[ERROR] process_msg failed: {str(e)}")
        return f'Error: {str(e)[:50]}'

  # ---------------------------
# PROCESS BATCH / SINGLE COMMAND
# ---------------------------
@X.on_message(filters.command(['batch', 'single']))
async def process_cmd(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    print(f"[DEBUG] process_cmd called | uid={uid} | cmd={cmd}")

    if FREEMIUM_LIMIT == 0 and not await is_premium_user(uid):
        await m.reply_text("[ERROR] Bot does not provide free services, get subscription from OWNER")
        print("[DEBUG] User is not premium, exiting")
        return

    if await sub(c, m) == 1:
        print("[DEBUG] Subscription check failed")
        return

    pro = await m.reply_text('Doing some checks, hold on...')
    print("[DEBUG] Initial checks message sent")

    if is_user_active(uid):
        await pro.edit('You have an active task. Use /stop to cancel it.')
        print("[DEBUG] User has active task, exiting")
        return

    ubot = await get_ubot(uid)
    if not ubot:
        await pro.edit('Add your bot with /setbot first')
        print("[DEBUG] User has no bot configured")
        return

    Z[uid] = {'step': 'start' if cmd == 'batch' else 'start_single'}
    await pro.edit(f'Send {"start link..." if cmd == "batch" else "link you want to process"}')
    print(f"[DEBUG] User step set: {Z[uid]['step']}")

# ---------------------------
# CANCEL / STOP COMMAND
# ---------------------------
@X.on_message(filters.command(['cancel', 'stop']))
async def cancel_cmd(c, m):
    uid = m.from_user.id
    print(f"[DEBUG] cancel_cmd called | uid={uid}")
    if is_user_active(uid):
        if await request_batch_cancel(uid):
            await m.reply_text('Cancellation requested. Current batch will stop after current download.')
            print("[DEBUG] Cancellation requested successfully")
        else:
            await m.reply_text('Failed to request cancellation. Please try again.')
            print("[ERROR] Cancellation request failed")
    else:
        await m.reply_text('No active batch process found.')
        print("[DEBUG] No active batch to cancel")

# ---------------------------
# TEXT HANDLER FOR STEPS
# ---------------------------
@X.on_message(filters.text & filters.private & ~login_in_progress & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set',
    'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo',
    'encrypt', 'decrypt', 'keys', 'setbot', 'rembot']))
async def text_handler(c, m):
    uid = m.from_user.id
    print(f"[DEBUG] text_handler called | uid={uid} | step={Z.get(uid, {}).get('step')}")
    if uid not in Z: return
    s = Z[uid].get('step')

    if s == 'start':
        L = m.text
        i, d, lt = E(L)
        if not i or not d:
            await m.reply_text('Invalid link format.')
            Z.pop(uid, None)
            print("[ERROR] Invalid link format in start")
            return
        Z[uid].update({'step': 'count', 'cid': i, 'sid': d, 'lt': lt})
        await m.reply_text('How many messages?')
        print(f"[DEBUG] User batch link accepted | cid={i} sid={d} lt={lt}")

    elif s == 'start_single':
        L = m.text
        i, d, lt = E(L)
        if not i or not d:
            await m.reply_text('Invalid link format.')
            Z.pop(uid, None)
            print("[ERROR] Invalid link format in start_single")
            return

        Z[uid].update({'step': 'process_single', 'cid': i, 'sid': d, 'lt': lt})
        i, s, lt = Z[uid]['cid'], Z[uid]['sid'], Z[uid]['lt']
        pt = await m.reply_text('Processing...')
        print(f"[DEBUG] Starting single message processing | cid={i} sid={s} lt={lt}")

        ubot = UB.get(uid)
        if not ubot:
            await pt.edit('Add bot with /setbot first')
            Z.pop(uid, None)
            print("[ERROR] No bot configured for single processing")
            return
        
        uc = await get_uclient(uid)
        if not uc:
            await pt.edit('Cannot proceed without user client.')
            Z.pop(uid, None)
            print("[ERROR] No user client for single processing")
            return

        if is_user_active(uid):
            await pt.edit('Active task exists. Use /stop first.')
            Z.pop(uid, None)
            print("[DEBUG] Active task exists, cancelling single processing")
            return

        try:
            msg = await get_msg(ubot, uc, i, s, lt)
            if msg:
                res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                await pt.edit(f'1/1: {res}')
                print(f"[DEBUG] Single message processed | result={res}")
            else:
                await pt.edit('Message not found')
                print("[ERROR] Message not found for single processing")
        except Exception as e:
            await pt.edit(f'Error: {str(e)[:50]}')
            print(f"[ERROR] process_msg failed in single: {e}")
        finally:
            Z.pop(uid, None)

      # ---------------------------
# BATCH COUNT / PROCESSING
# ---------------------------
    elif s == 'count':
        if not m.text.isdigit():
            await m.reply_text('Enter a valid number.')
            print("[ERROR] Non-numeric input for batch count")
            return
        
        count = int(m.text)
        maxlimit = PREMIUM_LIMIT if await is_premium_user(uid) else FREEMIUM_LIMIT
        print(f"[DEBUG] User batch count: {count} | Max limit: {maxlimit}")

        if count > maxlimit:
            await m.reply_text(f'Maximum limit is {maxlimit}.')
            print("[DEBUG] User exceeded max limit")
            return

        Z[uid].update({'step': 'process', 'did': str(m.chat.id), 'num': count})
        i, s, n, lt = Z[uid]['cid'], Z[uid]['sid'], Z[uid]['num'], Z[uid]['lt']
        success = 0

        pt = await m.reply_text('Processing batch...')
        print(f"[DEBUG] Batch processing started | total={n}")

        uc = await get_uclient(uid)
        ubot = UB.get(uid)
        if not uc or not ubot:
            await pt.edit('Missing client setup')
            print("[ERROR] Missing user client or bot for batch")
            Z.pop(uid, None)
            return

        if is_user_active(uid):
            await pt.edit('Active task exists')
            print("[DEBUG] User has active task, cannot start new batch")
            Z.pop(uid, None)
            return

        await add_active_batch(uid, {
            "total": n,
            "current": 0,
            "success": 0,
            "cancel_requested": False,
            "progress_message_id": pt.id
        })
        print("[DEBUG] Active batch registered for user")

        try:
            for j in range(n):
                if should_cancel(uid):
                    await pt.edit(f'Cancelled at {j}/{n}. Success: {success}')
                    print(f"[DEBUG] Batch cancelled by user at {j}/{n}")
                    break

                await update_batch_progress(uid, j, success)
                mid = int(s) + j
                print(f"[DEBUG] Processing message {j+1}/{n} | mid={mid}")

                try:
                    msg = await get_msg(ubot, uc, i, mid, lt)
                    if msg:
                        res = await process_msg(ubot, uc, msg, str(m.chat.id), lt, uid, i)
                        print(f"[DEBUG] process_msg result: {res}")
                        if any(x in res.lower() for x in ['done', 'copied', 'sent']):
                            success += 1
                    else:
                        print(f"[ERROR] Message {mid} not found")
                except Exception as e:
                    print(f"[ERROR] process_msg failed: {e}")
                    try:
                        await pt.edit(f'{j+1}/{n}: Error - {str(e)[:30]}')
                    except:
                        pass

                await asyncio.sleep(10)

            if j+1 == n:
                await m.reply_text(f'Batch Completed ✅ Success: {success}/{n}')
                print(f"[DEBUG] Batch completed | success={success}/{n}")

        finally:
            await remove_active_batch(uid)
            Z.pop(uid, None)
            print("[DEBUG] Cleaned up active batch and user step")
