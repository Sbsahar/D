import telebot
import os
import random
import threading
import requests
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
import json
from telebot.types import BotCommand
# توكن البوت ومفتاح API
TOKEN = '7588670003:AAEJSTkUqMYiNdjL17UsoM5O4a87YPiHhsc'
api_key = "sk_b34dcf68d51bee17991c066ead5eeb94fd72b26d5e73267d096f851420397bfaa1ac6a2482a141cdc8e07565b7a6ca0ddec607f8f5df31c3bc7be55cb6d14ffa024RooBLphN0iXkbKBufH"
CHANNEL_URL = 'https://t.me/SYR_SB'
CHANNEL_USERNAME = 'SYR_SB' 
DEVELOPER_CHAT_ID = '6789179634'
DEVELOPER_CHAT_ID = 6789179634
VIDEO_URL = "https://t.me/srevbo67/5" 
bot = telebot.TeleBot(TOKEN)
# تخزين عمليات الحظر لكل مشرف
ban_tracker = {}
# تخزين المشرفين اللي رفعهم البوت
group_detection_status = {}
pending_replies = {} 
bot_promoted_admins = {}
pending_promotions = {}
users = set()
warnings = {}
groups = set()
user_violations = {}
activated_groups = {}  # {group_id: report_chat_id}
daily_reports = {}     # {group_id: {"banned": [], "muted": [], "deleted_content": [], "manual_actions": []}}
REPLIES_FILE = "replies.json"
# قائمة الصلاحيات الافتراضية مع أسمائها بالعربية
PERMISSION_NAMES = {
    "can_delete_messages": "حذف الرسائل",
    "can_restrict_members": "تقييد الأعضاء",
    "can_invite_users": "إضافة أعضاء",
    "can_pin_messages": "تثبيت الرسائل",
    "can_change_info": "تغيير معلومات المجموعة",
    "can_manage_chat": "إدارة المجموعة"
}

DEFAULT_PERMISSIONS = {perm: False for perm in PERMISSION_NAMES}

gbt_enabled = False
commands = [
    BotCommand('gbt', 'استخدام الذكاء الاصطناعي (GPT)'),
    BotCommand('opengbt', 'تفعيل الذكاء الاصطناعي (للمشرفين فقط)'),
    BotCommand('closegbt', 'تعطيل الذكاء الاصطناعي (للمشرفين فقط)')
]
bot.set_my_commands(commands)
def get_blackbox_response(user_input):
    """ إرسال استفسار إلى Blackbox AI واسترجاع الرد """
    url = "https://api.blackbox.ai/api/chat"
    headers = {
        "Content-Type": "application/json"
    }
    json_data = json.dumps({
        "messages": [{"content": user_input, "role": "user"}],
        "model": "deepseek-ai/DeepSeek-V3",
        "max_tokens": "1024"
    })
    max_retries = 3  
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, data=json_data, timeout=10)  # زيادة المهلة
            print(f"Response Status: {response.status_code}")
            print(f"Response Text: {response.text}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Parsed Response: {data}")
                    return data.get("response", "⚠️ لا يوجد رد متاح.")
                except json.JSONDecodeError:
                    if response.text.strip():
                        return response.text
                    else:
                        return "⚠️ لا يوجد رد متاح."
            else:
                return f"⚠️ خطأ: {response.status_code} - {response.text}"     
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  
            else:
                return "الخدمة مشغولة حاليًا، يرجى المحاولة مرة أخرى لاحقًا."
def load_replies():
    if os.path.exists(REPLIES_FILE):
        with open(REPLIES_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}  # إذا ما كان الملف موجود، يرجّع قاموس فارغ

# حفظ الردود إلى الملف
def save_replies():
    with open(REPLIES_FILE, "w", encoding="utf-8") as file:
        json.dump(group_replies, file, ensure_ascii=False, indent=4)


group_replies = load_replies()        


def split_message(message, max_length=4096):
    """ تقسيم الرسالة إلى أجزاء إذا كانت طويلة """
    return [message[i:i + max_length] for i in range(0, len(message), max_length)]
def check_gbt_status(chat_id):
    """ التحقق من حالة الذكاء الاصطناعي وإرسال رسالة إذا كان معطلًا """
    global gbt_enabled
    if not gbt_enabled:
        bot.send_message(chat_id, "للأسف، قام المشرفون بتعطيل الذكاء الاصطناعي. يرجى طلب تفعيله من أحد المشرفين.")
        return False
    return True
# ------ دوال تفعيل التقارير ------



def check_image_safety(image_url):
    """فحص إذا كانت الصورة غير مناسبة باستخدام API خارجي"""
    api_url = "https://api.jigsawstack.com/v1/validate/nsfw"
    headers = {
        "x-api-key": api_key
    }
    params = {
        "url": image_url
    }
    try:
        response = requests.get(api_url, headers=headers, params=params)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('nudity', False):
                return 'nude'
            return 'ok'
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"An error occurred: {e}")
        return 'error'
def is_user_admin(bot, chat_id, user_id):
    chat_member = bot.get_chat_member(chat_id, user_id)
    return chat_member.status in ['administrator', 'creator']        
def is_admin(chat_id, user_id):
    """التحقق من صلاحية المشرف"""
    try:
        admins = bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False 
        
                
                                
def is_user_admin(bot, chat_id, user_id):
    """
    التحقق مما إذا كان المستخدم مشرفًا في المجموعة.
    """
    try:
        admins = bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.id == user_id:
                return True
        return False
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False
def extract_user_info(bot, message):
    """
    استخراج الأيدي أو اليوزرنيم من الرسالة.
    """
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.username
    elif len(message.text.split()) > 1:
        target = message.text.split()[1]
        if target.startswith("@"): 
            try:
                user_info = bot.get_chat(target)
                return user_info.id, user_info.username 
            except Exception as e:
                print(f"Error getting user info: {e}")
                return None, None
        else: 
            try:
                user_id = int(target) 
                return user_id, None  
            except ValueError:
                print("Invalid user ID format")
                return None, None
    else:
        return None, None
def is_user_subscribed(user_id):
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        chat_member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False
@bot.message_handler(content_types=['left_chat_member'])
def handle_manual_ban(message):
    """تسجيل عمليات الطرد أو الحظر اليدوي وحفظها في التقرير اليومي"""
    chat_id = message.chat.id
    removed_user = message.left_chat_member

    if chat_id in activated_groups:
        user_info = f"👤 الاسم: {removed_user.first_name}\n" \
                    f"📎 اليوزر: @{removed_user.username if removed_user.username else 'لا يوجد'}\n" \
                    f"🆔 الآيدي: <code>{removed_user.id}</code>"

        event = f"🚷 <b>تم طرد أو حظر عضو يدويًا:</b>\n\n{user_info}"

        # ✅ التأكد من وجود سجل للمجموعة
        if chat_id not in daily_reports:
            daily_reports[chat_id] = {
                "banned": [],
                "muted": [],
                "deleted_content": [],
                "manual_actions": []
            }

        # ✅ تسجيل الحدث في التقرير اليومي تحت قسم "الإجراءات اليدوية"
        daily_reports[chat_id]["manual_actions"].append(event)

        # ✅ إرسال إشعار فوري إلى مجموعة التقارير
        report_chat_id = activated_groups[chat_id]
        bot.send_message(report_chat_id, event, parse_mode="HTML")

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    """تسجيل انضمام الأعضاء الجدد (اختياري)"""
    chat_id = message.chat.id
    for member in message.new_chat_members:
        if chat_id in activated_groups:
            user_info = f"👤 الاسم: {member.first_name}\n" \
                        f"📎 اليوزر: @{member.username if member.username else 'لا يوجد'}\n" \
                        f"🆔 الآيدي: <code>{member.id}</code>"

            event = f"✅ <b>انضمام عضو جديد:</b>\n\n{user_info}"
            
            # حفظ الحدث في التقرير اليومي
            daily_reports[chat_id]["manual_actions"].append(event)

            # إرسال إشعار إلى مجموعة التقارير
            report_chat_id = activated_groups[chat_id]
            bot.send_message(report_chat_id, event, parse_mode="HTML")        
        
@bot.message_handler(commands=['enable_reports'])
def activate_reports(message):
    # التحقق من كون المستخدم مشرف
    if not is_user_admin(bot, message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "❌ يجب أن تكون مشرفًا في المجموعة لتفعيل التقارير.")
        return

    msg = bot.send_message(message.chat.id, "📝 أرسل ID المجموعة المراد تفعيل التقارير لها.")
    bot.register_next_step_handler(msg, process_group_id_step)

def process_group_id_step(message):
    try:
        group_id = int(message.text.strip())  # تحويل الإدخال إلى رقم
        if not is_user_admin(bot, group_id, message.from_user.id):  # تحقق من المشرف في المجموعة
            bot.send_message(message.chat.id, "❌ يجب أن تكون مشرفًا في المجموعة لتفعيل التقارير.")
            return

        activated_groups[group_id] = message.chat.id
        daily_reports[group_id] = {"banned": [], "muted": [], "deleted_content": [], "manual_actions": []}
        bot.send_message(message.chat.id, f"✅ تم تفعيل التقارير للمجموعة (ID: {group_id})")
        schedule_daily_report(group_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال ID صحيح للمجموعة.")        
        
@bot.message_handler(commands=['gbt'])
def handle_gbt_command(message):
    """ التعامل مع الأمر /gbt """
    if not check_gbt_status(message.chat.id):
        return
    
    user_input = message.text.split('/gbt', 1)[-1].strip()
    if not user_input:
        bot.send_message(message.chat.id, "يرجى إرسال سؤال بعد /gbt")
        return
    
    thinking_message = bot.send_message(message.chat.id, "جاري الاتصال بالذكاء، انتظر قليلًا...", parse_mode="Markdown")
    response = get_blackbox_response(user_input)
    bot.delete_message(message.chat.id, thinking_message.message_id)
    
    message_parts = split_message(response)
    for part in message_parts:
        bot.send_message(message.chat.id, part, parse_mode="Markdown")        
@bot.message_handler(commands=['opengbt'])
def handle_opengbt_command(message):
    """ تفعيل الذكاء الاصطناعي """
    global gbt_enabled
    try:
        # التحقق من أن المستخدم مشرف أو مالك المجموعة
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ["administrator", "creator"]:
            gbt_enabled = True
            bot.send_message(message.chat.id, "تم تفعيل الذكاء الاصطناعي بنجاح.✓")
        else:
            bot.send_message(message.chat.id, "عذرًا، فقط المشرفون يمكنهم تفعيل الذكاء الاصطناعي.")
    except Exception as e:
        print(f"Error checking admin status: {e}")
        bot.send_message(message.chat.id, "حدث خطأ أثناء التحقق من الصلاحيات.")   
       
@bot.message_handler(commands=['detection'])
def smart_detector(message):
    if message.chat.type == 'private':
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        bot.send_message(chat_id, "❌ هذا الأمر متاح للمشرفين فقط!")
        return

    # إنشاء لوحة المفاتيح التفاعلية
    markup = InlineKeyboardMarkup()
    
    current_status = group_detection_status.get(chat_id, 'disabled')
    
    btn_text = "✅ مفعل" if current_status == 'enabled' else "☑️ معطل"
    markup.row(
        InlineKeyboardButton(f"التفعيل {btn_text}", callback_data=f"detector_toggle_{chat_id}")
    )
    markup.row(
        InlineKeyboardButton("🗑 إغلاق القائمة", callback_data="detector_close")
    )

    welcome_msg = (
        "🛡️ *مرحبا بك في لوحة تحكم الكاشف الذكي*\n\n"
        "• فحص الصور والملصقات تلقائياً\n"
        "• لفحص الفيديو والمتحركات أضف البوت المساعد @Masaeeddbot \n"
        "• البوت المساعد يساعد على تخفيف الضغط وضمان فحص كل أنواع الميديا في مجموعتك✓\n\n"
        f"*الحالة الحالية:* {'مفعل 🟢' if current_status == 'enabled' else 'معطل 🔴'}"
    )

    bot.send_message(
        chat_id,
        welcome_msg,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('detector_'))
def handle_detector_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id

    if not is_admin(chat_id, user_id):
        bot.answer_callback_query(call.id, "❌ أنت لست مشرفاً!", show_alert=True)
        return

    if call.data == 'detector_close':
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
        return

    if 'toggle' in call.data:
        current_status = group_detection_status.get(chat_id, 'disabled')
        new_status = 'disabled' if current_status == 'enabled' else 'enabled'
        group_detection_status[chat_id] = new_status

        # تحديث الزر مع العلامة الجديدة
        markup = InlineKeyboardMarkup()
        btn_text = "✅ مفعل" if new_status == 'enabled' else "☑️ معطل"
        markup.row(
            InlineKeyboardButton(f"التفعيل {btn_text}", callback_data=f"detector_toggle_{chat_id}")
        )
        markup.row(
            InlineKeyboardButton("🗑 إغلاق القائمة", callback_data="detector_close")
        )

        # تحديث الرسالة الأصلية
        updated_text = (
            f"🛡️ **تم تحديث الحالة بنجاح!**\n\n"
            f"• الحالة الجديدة: {'مفعل 🟢' if new_status == 'enabled' else 'معطل 🔴'}\n"
            "• سيتم تطبيق التغييرات فورياً\n"
            "• يمكنك تعديل الإعدادات في أي وقت"
        )

        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=updated_text,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except:
            pass

        # إرسال إشعار التفعيل/التعطيل
        status_msg = " *تـم تفـعيل نظـام الحمايـة الذكيـة*✓" if new_status == 'enabled' else "❌ *تـم تعطيل نظام الحمايـة الذكية*"
        bot.send_message(chat_id, status_msg, parse_mode="Markdown")
        
        bot.answer_callback_query(call.id, "✓ تم حفظ الإعدادات")                
                
          
@bot.message_handler(commands=['closegbt'])
def handle_closegbt_command(message):
    """ تعطيل الذكاء الاصطناعي """
    global gbt_enabled
    try:
        # التحقق من أن المستخدم مشرف أو مالك المجموعة
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ["administrator", "creator"]:
            gbt_enabled = False
            bot.send_message(message.chat.id, "تم تعطيل الذكاء الاصطناعي بنجاح.✓")
        else:
            bot.send_message(message.chat.id, "عذرًا، فقط المشرفون يمكنهم تعطيل الذكاء الاصطناعي.")
    except Exception as e:
        print(f"Error checking admin status: {e}")
        bot.send_message(message.chat.id, "حدث خطأ أثناء التحقق من الصلاحيات.")
                
        
@bot.message_handler(commands=['ban'])
def ban_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق من أن المستخدم مشرف
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "⚠️ <b>عذرًا!</b>\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير!", parse_mode="HTML")
        return

    # استخراج معلومات الهدف
    target_id, target_username = extract_user_info(bot, message)
    
    # إذا كان الرد على الرسالة، أخذ الاسم الكامل للمستخدم
    if message.reply_to_message:
        target_full_name = message.reply_to_message.from_user.first_name or target_username  # استخدم الاسم الأول أو اليوزر
    else:
        target_full_name = target_username  # في حال لم يكن هناك رد على رسالة

    if not target_id:
        bot.reply_to(message, "📌 <b>كيفية استخدام الأمر:</b>\n"
                              "1️⃣ بالرد على رسالة العضو: <code>/ban</code>\n"
                              "2️⃣ باستخدام الآيدي: <code>/ban 12345</code>", parse_mode="HTML")
        return

    # منع حظر المشرفين الآخرين
    if is_user_admin(bot, chat_id, target_id):
        bot.reply_to(message, "⚠️ <b>عذرًا!</b>\nلا يمكنك حظر مشرف آخر.\n❌ دعك من هذا المزاح!", parse_mode="HTML")
        return

    try:
        bot.ban_chat_member(chat_id, target_id)

        # ------ التعديل الجديد ------
        if chat_id in activated_groups:
            event = f"تم حظر العضو: {target_full_name} (ID: {target_id})"
            daily_reports[chat_id]["banned"].append(event)
        # ------ نهاية التعديل ------

        # تنسيق رسالة الحظر
        banned_message = (
            f"👤 <b>الـحـلـو:</b> <a href='tg://user?id={target_id}'>{target_full_name}</a>\n"
            "✅ <b>تـم حظـره بنجـاح</b> 🚫"
        )

        bot.reply_to(message, banned_message, parse_mode="HTML")

    except Exception as e:
        bot.reply_to(message, f"❌ <b>حدث خطأ أثناء محاولة حظر العضو:</b> {e}", parse_mode="HTML")	
@bot.message_handler(commands=['unban'])
def unban_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق من أن المستخدم مشرف
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "⚠️ <b>عذرًا!</b>\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير!", parse_mode="HTML")
        return

    # استخراج معلومات الهدف
    target_id, target_username = extract_user_info(bot, message)
    
    # إذا كان الرد على الرسالة، أخذ الاسم الكامل للمستخدم
    if message.reply_to_message:
        target_full_name = message.reply_to_message.from_user.first_name or target_username  # استخدم الاسم الأول أو اليوزر
    else:
        target_full_name = target_username  # في حال لم يكن هناك رد على رسالة

    if not target_id:
        bot.reply_to(message, "📌 <b>كيفية استخدام الأمر:</b>\n"
                              "1️⃣ بالرد على رسالة العضو: <code>/unban</code>\n"
                              "2️⃣ باستخدام الآيدي: <code>/unban 12345</code>", parse_mode="HTML")
        return

    try:
        bot.unban_chat_member(chat_id, target_id)

        # تنسيق رسالة إلغاء الحظر
        unbanned_message = (
            f"✓ <b>تـم الغاء حظـره</b> <a href='tg://user?id={target_id}'>{target_full_name}</a>\n"
            "👀 <b>يستطـيع الأن العـودة بسـلام</b>"
        )

        bot.reply_to(message, unbanned_message, parse_mode="HTML")

    except Exception as e:
        bot.reply_to(message, f"❌ <b>حدث خطأ أثناء محاولة إلغاء حظر العضو:</b> {e}", parse_mode="HTML")
@bot.message_handler(commands=['mute'])
def mute_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # التحقق من أن المستخدم مشرف
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "⚠️ <b>عذرًا!</b>\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير!", parse_mode="HTML")
        return
    
    # استخراج معلومات العضو المستهدف
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(message, "📌 <b>كيفية استخدام الأمر:</b>\n"
                              "1️⃣ بالرد على رسالة العضو: <code>/mute</code>\n"
                              "2️⃣ باستخدام الأيدي: <code>/mute 12345</code>\n"
                              "3️⃣ لتقييد مؤقت: <code>/mute 12345 30</code> (30 دقيقة مثال)", parse_mode="HTML")
        return
    
    command_parts = message.text.split()
    
    # إذا كان الأمر بالرد على رسالة العضو
    if message.reply_to_message:
        if len(command_parts) > 1:
            try:
                mute_duration = int(command_parts[1])
            except ValueError:
                bot.reply_to(message, "❌ <b>خطأ!</b>\nالمدة الزمنية يجب أن تكون رقمًا صحيحًا.", parse_mode="HTML")
                return
        else:
            mute_duration = None
    else:
        if len(command_parts) > 2:
            try:
                mute_duration = int(command_parts[2])
            except ValueError:
                bot.reply_to(message, "❌ <b>خطأ!</b>\nالمدة الزمنية يجب أن تكون رقمًا صحيحًا.", parse_mode="HTML")
                return
        else:
            mute_duration = None
    
    # تطبيق الكتم
    if mute_duration:
        until_date = int(time.time()) + mute_duration * 60
        bot.restrict_chat_member(chat_id, target_id, until_date=until_date, can_send_messages=False)
        
        # رسالة التقيد المؤقت مع ذكر المدة
        mute_message = (
            f"🕛 <b>تـم تقـييـد الحـلـو</b> <a href='tg://user?id={target_id}'>{target_username or 'المستخدم'}</a> <b>المدة</b>: {mute_duration} دقيقة\n"
            f"<b>بعـد أنتهـاء الوقت ⌛ سيعـود لأزعـاجنـا</b>"
        )
        bot.reply_to(message, mute_message, parse_mode="HTML")
    else:
        bot.restrict_chat_member(chat_id, target_id, can_send_messages=False)

        # رسالة التقيد الدائم
        mute_message = (
            f"🔇 <b>تـم تقـييـد الحـلـو</b> <a href='tg://user?id={target_id}'>{target_username or 'المستخدم'}</a> <b>بشكل دائـم</b>"
        )
        bot.reply_to(message, mute_message, parse_mode="HTML")
@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "⚠️ <b>عذرًا!</b>\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير!", parse_mode="HTML")
        return

    # استخراج معلومات المستخدم
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(message, "📌 <b>كيفية استخدام الأمر:</b>\n"
                              "1️⃣ بالرد على رسالة العضو: <code>/unmute</code>\n"
                              "2️⃣ باستخدام الأيدي: <code>/unmute 12345</code>\n", parse_mode="HTML")
        return

    try:
        # إلغاء تقييد المستخدم
        bot.restrict_chat_member(chat_id, target_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)

        # إنشاء التاك بناءً على اسم المستخدم أو نص افتراضي
        mention = f'<a href="tg://user?id={target_id}">{target_username or "المستخدم"}</a>'

        # الرد مع التاك
        bot.reply_to(message, f"<b>تـم إلغاء تقييد الحـلـو</b> {mention}.\n"
                              f"🎉 <b>الآن يمكنه التحدث بحرية مرة أخرى!</b>", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء محاولة إلغاء تقييد العضو: {e}")
              
@bot.message_handler(commands=['help'])
def help_user(message):
    help_message = """
<b>اهلا بك في بوت شاهين لحماية المجموعة</b>
<b>استطيع حماية مجموعتك من كل خطر عن طريق فحص الميديا بواسطة الذكاء الأصطناعي 🦅 في مجموعتك بشكل كامل</b>
<b>فقط اضفني الى مجموعتك واعطني صلاحيات</b>

<b>ويمكنك أيضا تفعيل التقارير لمجموعتك من خلالي</b>
<b>وحظر الأعضاء والتقيد وكثير أشياء</b>
<b>والتحدث مع الذكاء الأصطناعي أيضا</b>

<b>لمتابعة أخر تحديثاتي تابع قناة المطور لكل جديد</b>
<b>تحياتي شاهين 🦅</b>
    """
    bot.reply_to(message, help_message, parse_mode="HTML")   
@bot.message_handler(commands=['pr'])
def promote_handler(message):
    if not message.reply_to_message and len(message.text.split()) < 2:
        bot.reply_to(message, "⚠️ استخدم الأمر بالرد على المستخدم أو إدخال الـ ID.")
        return
    
    user_id = message.reply_to_message.from_user.id if message.reply_to_message else message.text.split()[1]
    chat_id = message.chat.id

    if not bot.get_chat_member(chat_id, message.from_user.id).status in ['administrator', 'creator']:
        bot.reply_to(message, "⚠️ هذا الأمر للمشرفين فقط.")
        return

    pending_promotions[chat_id] = {
        "user_id": int(user_id),
        "permissions": DEFAULT_PERMISSIONS.copy(),
        "admin_id": message.from_user.id  # لحماية القائمة من التعديل من قبل غير المشرف الذي أنشأها
    }

    send_permissions_menu(chat_id, message)

def send_permissions_menu(chat_id, message):
    data = pending_promotions.get(chat_id, {})
    if not data:
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    for perm, value in data["permissions"].items():
        btn_text = f"✅ {PERMISSION_NAMES[perm]}" if value else f"❌ {PERMISSION_NAMES[perm]}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"toggle_{perm}"))

    markup.add(
        InlineKeyboardButton("✔️ تأكيد", callback_data="confirm_promotion"),
        InlineKeyboardButton("❌ إلغاء", callback_data="cancel_promotion")
    )

    if isinstance(message, int):  
        bot.edit_message_text("⚙️ <b>اختر صلاحيات المشرف:</b>", chat_id, message, reply_markup=markup, parse_mode="HTML")
    else:
        sent_message = bot.send_message(chat_id, "⚙️ <b>اختر صلاحيات المشرف:</b>", reply_markup=markup, parse_mode="HTML")
        pending_promotions[chat_id]["message_id"] = sent_message.message_id

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle_permission(call):
    chat_id = call.message.chat.id
    data = pending_promotions.get(chat_id, {})

    if not data:
        return

    # إذا الشخص اللي ضغط الزر مش نفسه اللي أنشأ القائمة، نمنعه
    if call.from_user.id != data["admin_id"]:
        bot.answer_callback_query(call.id, "🚫 هذا الأمر لا يخصك!", show_alert=True)
        return
    
    perm = call.data.split("_", 1)[1]
    data["permissions"][perm] = not data["permissions"][perm]

    send_permissions_menu(chat_id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_promotion", "cancel_promotion"])
def confirm_or_cancel_promotion(call):
    chat_id = call.message.chat.id
    data = pending_promotions.pop(chat_id, None)

    if not data:
        return

    if call.data == "confirm_promotion":
        bot.promote_chat_member(chat_id, data["user_id"], **data["permissions"])

        bot_promoted_admins.setdefault(chat_id, []).append(data["user_id"])

        bot.edit_message_text(
            f"✅ <b>تم رفع المستخدم كمشرف بالصلاحيات المحددة.</b>", 
            chat_id, call.message.message_id, parse_mode="HTML"
        )
    else:
        bot.edit_message_text("❌ <b>تم إلغاء العملية.</b>", chat_id, call.message.message_id, parse_mode="HTML")

@bot.message_handler(commands=['dt'])
def demote_handler(message):
    if not message.reply_to_message and len(message.text.split()) < 2:
        bot.reply_to(message, "⚠️ استخدم الأمر بالرد على المشرف أو إدخال الـ ID.")
        return
    
    user_id = message.reply_to_message.from_user.id if message.reply_to_message else message.text.split()[1]
    
    chat_id = message.chat.id
    if not bot.get_chat_member(chat_id, message.from_user.id).status in ['administrator', 'creator']:
        bot.reply_to(message, "⚠️ هذا الأمر للمشرفين فقط.")
        return

    bot.promote_chat_member(
        chat_id, 
        int(user_id),
        can_delete_messages=False,
        can_restrict_members=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_change_info=False,
        can_manage_chat=False
    )
    
    bot.reply_to(message, "✅ تم تنزيل المشرف وإلغاء جميع صلاحياته.")

@bot.message_handler(content_types=['new_chat_members', 'left_chat_member'])
def track_bans(message):
    chat_id = message.chat.id
    user = message.left_chat_member

    if not user:
        return

    admin = bot.get_chat_member(chat_id, message.from_user.id)
    if admin.status not in ["administrator", "creator"]:
        return  

    admin_id = message.from_user.id
    current_time = time.time()

    if chat_id not in ban_tracker:
        ban_tracker[chat_id] = {}

    if admin_id not in ban_tracker[chat_id]:
        ban_tracker[chat_id][admin_id] = []

    ban_tracker[chat_id][admin_id].append(current_time)

    ban_tracker[chat_id][admin_id] = [
        t for t in ban_tracker[chat_id][admin_id] if current_time - t < 3600
    ]

    if len(ban_tracker[chat_id][admin_id]) > 20:
        handle_abusive_admin(chat_id, admin_id)

def handle_abusive_admin(chat_id, admin_id):
    admin_info = bot.get_chat_member(chat_id, admin_id)
    username = f"@{admin_info.user.username}" if admin_info.user.username else "بدون معرف"
    full_name = admin_info.user.first_name
    user_id = admin_info.user.id

    if user_id in bot_promoted_admins.get(chat_id, []):
        bot.promote_chat_member(
            chat_id, user_id,
            can_delete_messages=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_change_info=False,
            can_manage_chat=False
        )
        
        bot.send_message(
            chat_id,
            f"<b>🚨 تم تنزيل المشرف من منصبه!</b>\n\n"
            f"👤 <b>الاسم:</b> {full_name}\n"
            f"📎 <b>المعرف:</b> {username}\n"
            f"🆔 <b>الآيدي:</b> {user_id}\n\n"
            f"⚠️ <b>السبب:</b> قام بطرد أكثر من 20 عضو في أقل من ساعة!",
            parse_mode="HTML"
        )
        
        bot_promoted_admins[chat_id].remove(user_id)
    else:
        admins = bot.get_chat_administrators(chat_id)
        admin_mentions = " ".join(
            [f"@{admin.user.username}" for admin in admins if admin.user.username]
        )

        bot.send_message(
            chat_id,
            f"🚨 <b>تنبيه للمشرفين:</b>\n\n"
            f"👤 <b>الاسم:</b> {full_name}\n"
            f"📎 <b>المعرف:</b> {username}\n"
            f"🆔 <b>الآيدي:</b> {user_id}\n\n"
            f"⚠️ <b>هذا المشرف قام بطرد أكثر من 20 عضو خلال ساعة!</b>\n"
            f"❌ <b>ليس لدي صلاحيات لتنزيله، يرجى التعامل معه!</b>\n\n"
            f"{admin_mentions}",
            parse_mode="HTML"
        )

# دالة إضافة الردود
@bot.message_handler(commands=['ad'])
def add_reply_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type == "private":
        return bot.send_message(chat_id, "❌ هذا الأمر للجروبات فقط")

    if not is_admin(chat_id, user_id):
        return bot.reply_to(message, "❌ للمشرفين فقط")

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        return bot.reply_to(message, "❌ استخدم: `/ad كلمة`", parse_mode="Markdown")

    keyword = command_parts[1].strip().lower()
    pending_replies[user_id] = {'chat_id': chat_id, 'keyword': keyword}
    bot.reply_to(message, "✅ أرسل الرد الآن (نص/صورة/ملف/إلخ)")

# دالة حفظ الردود بأنواعها
@bot.message_handler(func=lambda m: m.from_user.id in pending_replies, content_types=['text', 'photo', 'video', 'sticker', 'voice', 'audio', 'document', 'animation'])
def save_reply(message):
    user_data = pending_replies.pop(message.from_user.id, None)
    if not user_data: return

    chat_id = user_data['chat_id']
    keyword = user_data['keyword']
    reply_data = None

    if message.content_type == 'text':
        reply_data = {'type': 'text', 'content': message.text}
    elif message.content_type == 'photo':
        reply_data = {'type': 'photo', 'content': message.photo[-1].file_id}
    elif message.content_type == 'video':
        reply_data = {'type': 'video', 'content': message.video.file_id}
    elif message.content_type == 'sticker':
        reply_data = {'type': 'sticker', 'content': message.sticker.file_id}
    elif message.content_type == 'voice':
        reply_data = {'type': 'voice', 'content': message.voice.file_id}
    elif message.content_type == 'audio':
        reply_data = {'type': 'audio', 'content': message.audio.file_id}
    elif message.content_type == 'document':
        reply_data = {'type': 'document', 'content': message.document.file_id}
    elif message.content_type == 'animation':
        reply_data = {'type': 'animation', 'content': message.animation.file_id}

    if reply_data:
        group_replies.setdefault(chat_id, {})[keyword] = reply_data
        save_replies()
        bot.reply_to(message, f"✅ تم ربط الرد بــ `{keyword}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ نوع غير مدعوم")
@bot.message_handler(commands=['setting1'])
def setting1(message):
    """ عرض خيارات إضافية مع شرح عن نظام الردود """
    setting1_msg = (
        "🔧 **خيارات إضافية - نظام الردود**\n\n"
        "هذا النظام يتيح لك إضافة ردود مخصصة تعتمد على الكلمات المفتاحية.\n\n"
        "• `/ad كلمة` - لإضافة رد مخصص لكلمة معينة. بعد استخدام هذا الأمر، ستتمكن من إرسال الرد الذي تريده (نص، صورة، فيديو، إلخ).\n"
        "• الرد سيكون تلقائيًا عندما يكتب أحد الأعضاء الكلمة في المجموعة.\n\n"
        "⚠️ **تنويه:** يمكن للمشرفين فقط إضافة أو تعديل هذه الردود.\n\n"
        "لإضافة رد مخصص، استخدم الأمر `/ad` كما تم شرحه سابقًا.\n"
        "📌 لمزيد من التعليمات يمكنك الرجوع إلى الإعدادات السابقة عبر الأمر /settings."
    )

    bot.send_message(message.chat.id, setting1_msg, parse_mode="Markdown")
                                                                                                                                                
              
@bot.message_handler(commands=['settings'])
def settings(message):
    """عرض إعدادات البوت للمشرفين"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "❌ هذا الأمر متاح للمشرفين فقط.")
        return

    # رسالة الإعدادات
    settings_msg = (
    "⚙️ **إعدادات البوت**\n\n"
    "• `/pp` - لتثبيت رسالة بالرد عليها.\n"
    "• `/de` - لحذف رسالة معينة بالرد عليها.\n"
    "• `/wwa` - لإرسال إنذار إلى عضو معين بالرد على رسالته (3 إنذارات = تقييد).\n"
    "• `/unwa` - لإزالة الإنذارات عن مستخدم معين.\n"
    "• `/pr` - لرفع عضو كمشرف بالرد عليه أو بإدخال الـ ID.\n"
    "• `/dt` - لتنزيل مشرف وإزالة جميع صلاحياته.\n"
    "• `/detection` - لتفعيل أو إيقاف الكاشف الذكي ليفحص ويراقب الميديا والوسائط في مجموعتك بواسطة الذكاء الأصطناعي.\n\n"
    "⚠️ هذه الأوامر متاحة للمشرفين فقط.\n\n"
    "🔹 لمزيد من الخيارات والأوامر اضغط على /setting1"
)
    bot.reply_to(message, settings_msg, parse_mode="Markdown")

# الأمر /pp لتثبيت رسالة

@bot.message_handler(commands=['pp'])
def pin_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "<b>❌ هذا الأمر متاح للمشرفين فقط.</b>", parse_mode='HTML')
        return

    # التحقق مما إذا كان هناك رد على رسالة
    if not message.reply_to_message:
        bot.reply_to(message, "<b>❌ الرجاء الرد على رسالة لتثبيتها.</b>", parse_mode='HTML')
        return

    # الرد أولاً بأننا بصدد تثبيت الرسالة
    try:
        # إرسال رسالة "جاري التثبيت"
        progress_message = bot.reply_to(message, "<b>🔃 جاري تثبيت الرسالة...</b>", parse_mode='HTML')

        # تثبيت الرسالة
        bot.pin_chat_message(chat_id, message.reply_to_message.message_id)

        # تأخير لمدة ثانيتين ثم إرسال رسالة جديدة بتثبيت الرسالة بنجاح
        time.sleep(2)
        bot.edit_message_text(
            "<b>✔️ تم تثبيت الرسالة بنجاح.</b>",
            chat_id=chat_id,
            message_id=progress_message.message_id,
            parse_mode='HTML'
        )
    except Exception as e:
        bot.reply_to(message, f"<b>❌ حدث خطأ أثناء تثبيت الرسالة: {e}</b>", parse_mode='HTML')

# الأمر /delete لحذف رسال

@bot.message_handler(commands=['de'])
def delete_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "❌ هذا الأمر متاح للمشرفين فقط.")
        return

    # التحقق مما إذا كان هناك رد على رسالة
    if not message.reply_to_message:
        bot.reply_to(message, "❌ الرجاء الرد على رسالة لحذفها.")
        return

    # حذف الرسالة التي تم الرد عليها
    try:
        bot.delete_message(chat_id, message.reply_to_message.message_id)
        success_message = bot.reply_to(message, "🗑️ تم حذف الرسالة بنجاح.")
        
        # تأخير لمدة ثانيتين ثم حذف رسالة البوت
        time.sleep(2)
        bot.delete_message(chat_id, success_message.message_id)

        # تأخير لمدة ثانيتين أخرى ثم حذف الرسالة التي أرسلت أمر /delete
        time.sleep(2)
        bot.delete_message(chat_id, message.message_id)
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء حذف الرسالة: {e}")

# الأمر /wwa لإرسال إنذار
@bot.message_handler(commands=['wwa'])
def warn_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "❌ هذا الأمر متاح للمشرفين فقط.")
        return

    # التحقق مما إذا كان هناك رد على رسالة
    if not message.reply_to_message:
        bot.reply_to(message, "❌ الرجاء الرد على رسالة لإرسال إنذار.")
        return

    target_user_id = message.reply_to_message.from_user.id
    target_user_name = message.reply_to_message.from_user.first_name

    # تحديث الإنذارات
    if chat_id not in warnings:
        warnings[chat_id] = {}
    if target_user_id not in warnings[chat_id]:
        warnings[chat_id][target_user_id] = 0

    warnings[chat_id][target_user_id] += 1
    current_warnings = warnings[chat_id][target_user_id]

    # الرد على الإنذار
    if current_warnings >= 3:
        try:
            bot.restrict_chat_member(chat_id, target_user_id, until_date=time.time() + 86400)  # تقييد لمدة يوم
            bot.reply_to(message, f"🚫 {target_user_name} تم تقييده بسبب تلقي 3 إنذارات.")
            warnings[chat_id][target_user_id] = 0  # إعادة تعيين الإنذارات
        except Exception as e:
            bot.reply_to(message, f"❌ حدث خطأ أثناء تقييد المستخدم: {e}")
    else:
        bot.reply_to(message, f"⚠️ {target_user_name} تلقى إنذارًا جديدًا ({current_warnings}/3).")

# الأمر /unwa لإزالة الإنذارات
@bot.message_handler(commands=['unwa'])
def un_warn_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "❌ هذا الأمر متاح للمشرفين فقط.")
        return

    # التحقق مما إذا كان هناك رد على رسالة
    if not message.reply_to_message:
        bot.reply_to(message, "❌ الرجاء الرد على رسالة لإزالة الإنذارات.")
        return

    target_user_id = message.reply_to_message.from_user.id
    target_user_name = message.reply_to_message.from_user.first_name

    # إزالة الإنذارات
    if chat_id in warnings and target_user_id in warnings[chat_id]:
        warnings[chat_id][target_user_id] = 0
        bot.reply_to(message, f"✅ تم إزالة جميع الإنذارات عن {target_user_name}.")
    else:
        bot.reply_to(message, f"ℹ️ {target_user_name} لا يملك أي إنذارات.")  
        
                    
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    users.add(user_id)

    # التحقق من الاشتراك بالقناة  
    if not is_user_subscribed(user_id):  
        markup = types.InlineKeyboardMarkup()  
        subscribe_button = types.InlineKeyboardButton("اشترك الآن", url=CHANNEL_URL)  
        check_button = types.InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")  
        markup.add(subscribe_button, check_button)  

        bot.send_message(  
            message.chat.id,  
            "⚠️ <b>يجب عليك الاشتراك في القناة أولاً لاستخدام البوت:</b>\n\n"  
            f"👉 <a href='{CHANNEL_URL}'>اضغط هنا للاشتراك</a>",  
            parse_mode="HTML",  
            reply_markup=markup  
        )  
        return  

    # إرسال إشعار للمطور عن المستخدم الجديد  
    notification_message = (  
        f"<b>📢 مستخدم جديد بدأ استخدام البوت!</b>\n\n"  
        f"<b>👤 الاسم:</b> {message.from_user.first_name}\n"  
        f"<b>📎 اليوزر:</b> @{message.from_user.username or 'بدون'}\n"  
        f"<b>🆔 الآيدي:</b> {user_id}"  
    )  
    bot.send_message(DEVELOPER_CHAT_ID, notification_message, parse_mode="HTML")  

    # رسالة الترحيب الرسمية مع الرابط  
    welcome_message = (  
        f"🔹 <a href='https://t.me/SYR_SB'>𝐒𝐎𝐔𝐑𝐂𝐄 𝐒𝐁</a>\n\n"  # <-- هذه هي الإضافة المطلوبة  
        "✨ <b>أهلاً وسهلاً بك في بوت شاهين المتطور!</b> ✨\n\n"  
        "🛡️ <b>هذا البوت مُصمم لحماية المجموعات بأحدث التقنيات.</b>\n"  
        "⚡ <b>سريع – ذكي – موثوق</b>\n\n"  
        "📌 <b>لمزيد من المعلومات اضغط:</b> /help\n\n"  
        "🚀 <b>استمتع بتجربة الحماية المتكاملة مع شاهين! 🦅</b>"  
    )  

    # أزرار التفاعل  
    markup = types.InlineKeyboardMarkup()  
    button_add_group = types.InlineKeyboardButton("➕ أضفني إلى مجموعتك", url=f"https://t.me/{bot.get_me().username}?startgroup=true")  
    button_channel = types.InlineKeyboardButton("📢 قناة المطور", url=CHANNEL_URL)  
    markup.add(button_add_group, button_channel)  

    # إرسال الفيديو مع رسالة الترحيب  
    bot.send_video(message.chat.id, VIDEO_URL, caption=welcome_message, parse_mode="HTML", reply_markup=markup)
@bot.message_handler(content_types=['left_chat_member'])
def handle_manual_ban(message):
    chat_id = message.chat.id
    if chat_id in activated_groups:
        user = message.left_chat_member
        event = f"تم طرد العضو يدويًا: @{user.username if user.username else user.id}"
        daily_reports[chat_id]["manual_actions"].append(event)        


@bot.message_handler(commands=['info'])
def get_user_info(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # استخراج معلومات المستخدم المستهدف
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(
            message, 
            "🔎 <b>كيفية استخدام الأمر:</b>\n"
            "1️⃣ <b>بالرد على رسالة العضو:</b> <code>/info</code>\n"
            "2️⃣ <b>باستخدام الآيدي:</b> <code>/info 12345</code>", 
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(target_id)
        print(f"target_id: {target_id}, DEVELOPER_CHAT_ID: {DEVELOPER_CHAT_ID}")

        # إذا كان المستخدم هو المطور
        if target_id == DEVELOPER_CHAT_ID:
            role = "👑 <b>المطور الأساسي</b>"
            header = "👑 <b>معلومات المطور:</b>\n"
            # محاولة استخدام الرسالة المردود عليها إذا كانت موجودة
            if message.reply_to_message:
                user = message.reply_to_message.from_user
            else:
                user = bot.get_chat(target_id)
        else:
            header = "📌 <b>معلومات العضو</b>\n"
            if chat_id < 0:  # داخل مجموعة
                chat_member = bot.get_chat_member(chat_id, target_id)
                user = chat_member.user
                status = chat_member.status
                role = "🔰 <b>مشرف</b>" if status in ["creator", "administrator"] else "👤 <b>عضو</b>"
            else:
                user = bot.get_chat(target_id)
                role = "👤 <b>عضو</b>"

        is_premium = "💎 <b>بريميوم</b>" if getattr(user, "is_premium", False) else "👤 <b>عادي</b>"
        violation_count = user_violations.get(target_id, 0)

        info_message = (
            header +
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>الاسم:</b> {user.first_name}\n"
            f"📎 <b>اليوزر:</b> @{user.username if user.username else '🚫 لا يوجد'}\n"
            f"🆔 <b>الآيدي:</b> <code>{target_id}</code>\n"
            f"🏅 <b>الرتبة:</b> {role}\n"
            f"⚠️ <b>المخالفات:</b> {violation_count}\n"
            f"🏆 <b>النوع:</b> {is_premium}\n"
            "━━━━━━━━━━━━━━━━━━"
        )

        bot.send_message(chat_id, info_message, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(
            message, 
            f"🚫 <b>خطأ:</b>\n<code>{e}</code>", 
            parse_mode="HTML"
        )

def extract_user_info(bot, message):
    # إذا تم الرد على رسالة
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        return user.id, user.username
    # إذا تم استخدام الآيدي مع الأمر
    elif len(message.text.split()) > 1:
        target_id = message.text.split()[1]
        return target_id, None
    else:
        return None, None
@bot.message_handler(commands=['info_group'])
def get_group_info(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "🚫 هذا الأمر يعمل فقط داخل المجموعات.")
        return

    try:
        chat = bot.get_chat(chat_id)
        members_count = bot.get_chat_member_count(chat_id)  # تم التصحيح هنا
        admins = bot.get_chat_administrators(chat_id)
        admins_count = len(admins)
        
        # إزالة الجزء الخاص بالمحظورين لعدم وجود دالة مناسبة
        # إزالة عد البوتات لعدم وجود طريقة مباشرة
        
        group_link = chat.invite_link if chat.invite_link else "🚫 لا يوجد رابط، هذه مجموعة خاصة"

        group_info = (
            "<b>📌 معلومات المجموعة:</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>اسم المجموعة:</b> {chat.title}\n"
            f"🆔 <b>آيدي المجموعة:</b> <code>{chat_id}</code>\n"
            f"🔗 <b>رابط المجموعة:</b> {group_link}\n"
            f"👥 <b>عدد الأعضاء:</b> {members_count}\n"
            f"🔰 <b>عدد المشرفين:</b> {admins_count}\n"
            "━━━━━━━━━━━━━━━━━━"
        )

        bot.send_message(chat_id, group_info, parse_mode="HTML")
    
    except Exception as e:
        bot.reply_to(
            message, 
            f"🚫 <b>خطأ:</b>\n<code>{e}</code>", 
            parse_mode="HTML"
        )
        
                        
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """التعامل مع الصور المرسلة والتحقق من محتواها"""
    # التحقق من حالة الكاشف الذكي في المجموعة
    if group_detection_status.get(message.chat.id, 'disabled') == 'enabled':
        # الحصول على الـ file_id والصورة
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_link = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
        
        # فحص الصورة
        res = check_image_safety(file_link)
        
        if res == 'nude':
            bot.delete_message(message.chat.id, message.message_id)
            warning_message = (
                f"🚫 <b>لا تبعت صور غير لائقة ياا {message.from_user.first_name}!</b>\n"
                f"🥷🏻 @{message.from_user.username or str(message.from_user.id)}، <b>هذا تنبيه لك!</b>\n"
                "<b>🤖 البوت يراقب ويمنع المحتوى غير الملائم 🛂</b>"
            )
            bot.send_message(message.chat.id, warning_message, parse_mode="HTML")
            update_violations(message.from_user.id, message.chat.id)
@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    """التعامل مع الملصقات المرسلة والتحقق من محتواها"""
    # التحقق من حالة الكاشف الذكي في المجموعة
    if group_detection_status.get(message.chat.id, 'disabled') == 'enabled':
        if message.sticker.thumb:
            file_info = bot.get_file(message.sticker.thumb.file_id)
            sticker_url = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
            
            # فحص الملصق
            res = check_image_safety(sticker_url)
            
            if res == 'nude':
                bot.delete_message(message.chat.id, message.message_id)
                warning_message = (
                    f"🚫 <b>لا تبعت ملصقات غير لائقة يا {message.from_user.first_name}!</b>\n"
                    f"🥷🏻 @{message.from_user.username or str(message.from_user.id)}، <b>هذا تنبيه لك!</b>\n"
                    "<b>🤖 البوت يراقب ويمنع المحتوى غير الملائم 🛂</b>"
                )
                bot.send_message(message.chat.id, warning_message, parse_mode="HTML")
                update_violations(message.from_user.id, message.chat.id)
                
@bot.message_handler(func=lambda message: message.entities and any(entity.type == 'custom_emoji' for entity in message.entities))
def handle_custom_emoji_message(message):
    """التعامل مع الرموز التعبيرية الخاصة والتحقق من محتواها"""
    # التحقق من حالة الكاشف الذكي في المجموعة
    if group_detection_status.get(message.chat.id, 'disabled') == 'enabled':
        custom_emoji_ids = [entity.custom_emoji_id for entity in message.entities if entity.type == 'custom_emoji']
        if custom_emoji_ids:
            sticker_links = get_premium_sticker_info(custom_emoji_ids)  
            if sticker_links:
                for link in sticker_links:
                    res = check_image_safety(link)
                    if res == 'nude':
                        bot.delete_message(message.chat.id, message.message_id)
                        warning_message = (
                            f"🚫 <b>لا تبعت ملصقات مميز غير لائقة يا {message.from_user.first_name}!</b>\n"
                            f"🥷🏻 @{message.from_user.username or str(message.from_user.id)}، <b>هذا تنبيه لك!</b>\n"
                            "<b>🤖 البوت يراقب ويمنع المحتوى غير الملائم 🛂</b>"
                        )
                        bot.send_message(message.chat.id, warning_message, parse_mode="HTML")
                        update_violations(message.from_user.id, message.chat.id)

def get_premium_sticker_info(custom_emoji_ids):
    """استخراج الروابط الخاصة بالرموز التعبيرية"""
    try:
        sticker_set = bot.get_custom_emoji_stickers(custom_emoji_ids)
        sticker_links = []
        for sticker in sticker_set:
            if sticker.thumb:
                file_info = bot.get_file(sticker.thumb.file_id)
                file_link = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
                sticker_links.append(file_link)
        return sticker_links
    except Exception as e:
        print(f"Error retrieving sticker info: {e}")
        return []



@bot.edited_message_handler(content_types=['text'])
def handle_edited_custom_emoji_message(message):
    """التعامل مع الرسائل المعدلة وفحص الرموز التعبيرية المميزة"""
    # التحقق من حالة الكاشف الذكي في المجموعة
    if group_detection_status.get(message.chat.id, 'disabled') == 'enabled':
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_name = f"@{message.from_user.username}" if message.from_user.username else f"({user_id})"

        if message.entities:
            custom_emoji_ids = [entity.custom_emoji_id for entity in message.entities if entity.type == 'custom_emoji']
            if custom_emoji_ids:
                sticker_links = get_premium_sticker_info(custom_emoji_ids)
                if sticker_links:
                    for link in sticker_links:
                        res = check_image_safety(link)
                        if res == 'nude':
                            bot.delete_message(chat_id, message.message_id)
                            alert_message = (
                                f"🚨 <b>تنبيه:</b>\n"
                                f"🔗 المستخدم {user_name} <b>عدل رسالة وأضاف ملصق مميز غير لائق!</b>\n\n"
                                "⚠️ <b>يجب على المشرفين اتخاذ الإجراءات اللازمة.</b>"
                            )
                            bot.send_message(chat_id, alert_message, parse_mode="HTML")
                            update_violations(user_id, chat_id)       
        
@bot.edited_message_handler(content_types=['text', 'photo', 'sticker'])
def handle_edited_message(message):
    """التعامل مع الرسائل المعدلة وفحص محتواها"""
    # التحقق من حالة الكاشف الذكي في المجموعة
    if group_detection_status.get(message.chat.id, 'disabled') == 'enabled':
        user_id = message.from_user.id
        chat_id = message.chat.id
        user_name = f"@{message.from_user.username}" if message.from_user.username else f"({user_id})"

        # فحص الصور المعدلة
        if message.content_type == 'photo':  
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            file_link = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
            res = check_image_safety(file_link)    

            if res == 'nude':  
                bot.delete_message(chat_id, message.message_id)
                alert_message = (
                    f"🚨 <b>تنبيه:</b>\n"
                    f"🔗 المستخدم {user_name} <b>حاول تعديل رسالة قديمة إلى صورة غير لائقة!</b>\n\n"
                    "⚠️ <b>وجب على المشرفين التعامل معه فورًا بحظره أو تحذيره.</b>"
                )
                bot.send_message(chat_id, alert_message, parse_mode="HTML")
                update_violations(user_id, chat_id)

        # فحص الملصقات المعدلة
        elif message.content_type == 'sticker': 
            if message.sticker.thumb:  
                file_info = bot.get_file(message.sticker.thumb.file_id)
                sticker_url = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
                res = check_image_safety(sticker_url)    

                if res == 'nude':  
                    bot.delete_message(chat_id, message.message_id)
                    alert_message = (
                        f"🚨 <b>تنبيه:</b>\n"
                        f"🔗 المستخدم {user_name} <b>حاول تعديل رسالة قديمة إلى ملصق غير لائق!</b>\n\n"
                        "⚠️ <b>وجب على المشرفين التعامل معه فورًا بحظره أو تحذيره.</b>"
                    )
                    bot.send_message(chat_id, alert_message, parse_mode="HTML")
                    update_violations(user_id, chat_id)


def update_violations(user_id, chat_id):
    global user_violations

    # زيادة عدد مخالفات المستخدم
    if user_id not in user_violations:
        user_violations[user_id] = 0
    user_violations[user_id] += 1

    # جلب معلومات المستخدم
    try:
        chat_member = bot.get_chat_member(chat_id, user_id)
        user = chat_member.user
        user_name = user.first_name or "غير معروف"
        user_username = f"@{user.username}" if user.username else "لا يوجد"
        user_id_text = f"<code>{user_id}</code>"  # لجعل الآيدي يظهر بشكل واضح
        violation_count = user_violations[user_id]

        # تقرير المخالفة
        violation_report = (
            f"🚨 <b>تنبيه بمخالفة جديدة!</b>\n\n"
            f"👤 <b>الاسم:</b> {user_name}\n"
            f"📎 <b>اليوزر:</b> {user_username}\n"
            f"🆔 <b>الآيدي:</b> {user_id_text}\n"
            f"🔢 <b>عدد المخالفات:</b> {violation_count}"
        )

        # إرسال التقرير إلى المجموعة المفعلة إذا كانت التقارير مفعلة
        if chat_id in activated_groups:
            report_chat_id = activated_groups[chat_id]
            daily_reports[chat_id]["deleted_content"].append(violation_report)
            bot.send_message(report_chat_id, violation_report, parse_mode="HTML")

    except Exception as e:
        print(f"❌ خطأ أثناء جلب معلومات المستخدم: {e}")
        return

    # تقييد المستخدم تلقائيًا إذا تجاوز 10 مخالفات (باستثناء المشرفين)
    if violation_count >= 10:
        try:
            if chat_member.status in ['administrator', 'creator']:
                warning_message = (
                    f"🚨 <b>تحذير!</b>\n"
                    f"👤 <b>المستخدم:</b> {user_name}\n"
                    f"📎 <b>اليوزر:</b> {user_username}\n"
                    f"🆔 <b>الآيدي:</b> {user_id_text}\n"
                    f"⚠️ <b>قام بارتكاب مخالفات كثيرة، لكنه مشرف ولا يمكن تقييده.</b>\n"
                    "⚠️ <b>يرجى التعامل معه يدويًا.</b>"
                )
                bot.send_message(chat_id, warning_message, parse_mode="HTML")
            else:
                bot.restrict_chat_member(chat_id, user_id, until_date=None, can_send_messages=False)
                restriction_message = (
                    f"🚫 <b>تم تقييد المستخدم بسبب تجاوز الحد المسموح به من المخالفات!</b>\n\n"
                    f"👤 <b>الاسم:</b> {user_name}\n"
                    f"📎 <b>اليوزر:</b> {user_username}\n"
                    f"🆔 <b>الآيدي:</b> {user_id_text}\n"
                    f"🔢 <b>عدد المخالفات:</b> {violation_count}\n\n"
                    "⚠️ <b>تم تقييده تلقائيًا.</b>"
                )
                bot.send_message(chat_id, restriction_message, parse_mode="HTML")

        except Exception as e:
            print(f"❌ خطأ أثناء محاولة تقييد المستخدم: {e}")
@bot.message_handler(content_types=['new_chat_members'])
def on_user_joins(message):
    """التعامل مع انضمام أعضاء جدد للمجموعة"""
    for member in message.new_chat_members:
        groups.add(message.chat.id) 
        added_by = message.from_user
        try:
            if bot.get_chat_member(message.chat.id, added_by.id).can_invite_users:
                group_link = bot.export_chat_invite_link(message.chat.id)
                welcome_message = (
                    f"🤖 <b>تم إضافة البوت بواسطة:</b>\n"
                    f"👤 <b>الاسم:</b> {added_by.first_name}\n"
                    f"📎 <b>اليوزر:</b> @{added_by.username or 'بدون'}\n"
                    f"🆔 <b>الآيدي:</b> {added_by.id}\n"
                )                
                if group_link:
                    welcome_message += f"\n🔗 <b>رابط الدعوة للمجموعة:</b> {group_link}"
                bot.send_message(message.chat.id, welcome_message, parse_mode="HTML")
        except Exception as e:
            print(f"Error while exporting chat invite link: {e}")
def broadcast_message(message_text):
    for user_id in users:
        try:
            bot.send_message(user_id, message_text)
        except Exception as e:
            print(f"Error sending message to user {user_id}: {e}")    
    for group_id in groups:
        try:
            bot.send_message(group_id, message_text)
        except Exception as e:
            print(f"Error sending message to group {group_id}: {e}")
@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    """إرسال رسالة جماعية للمستخدمين والمجموعات"""
    if str(message.chat.id) == DEVELOPER_CHAT_ID:
        msg_text = message.text.split(maxsplit=1)
        if len(msg_text) > 1:
            broadcast_message(msg_text[1])
            bot.send_message(message.chat.id, "📢 تم إرسال الرسالة بنجاح إلى جميع المستخدمين والمجموعات!")
        else:
            bot.send_message(message.chat.id, "🚫 يرجى كتابة الرسالة بعد الأمر /broadcast.")
    else:
        bot.send_message(message.chat.id, "🚫 هذا الأمر مخصص للمطور فقط.")
@bot.message_handler(commands=['sb'])
def handle_sb_command(message):
    """رد خاص للمطور عند إرسال أمر /sb"""
    if str(message.from_user.id) == DEVELOPER_CHAT_ID:
        bot.reply_to(message, "نعم عزيزي المطور البوت يعمل بنجاح 💪")
    else:
        bot.reply_to(message, "🚫 هذا الأمر مخصص للمطور فقط.")


def schedule_daily_report(group_id):
    """جدولة إرسال التقرير اليومي تلقائيًا كل 24 ساعة"""
    def send_report():
        send_group_report(group_id)  # إرسال التقرير
        threading.Timer(86400, send_report).start()  # إعادة التشغيل بعد 24 ساعة
    
    threading.Timer(86400, send_report).start()

@bot.message_handler(commands=['report'])
def manual_daily_report(message):
    """عرض التقرير اليومي عند الطلب"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "❌ هذا الأمر متاح للمشرفين فقط.")
        return

    # إرسال التقرير يدويًا
    send_group_report(chat_id)

def send_group_report(group_id):
    """تجميع وإرسال التقرير للمجموعة"""
    if group_id in daily_reports and any(daily_reports[group_id].values()):  # التأكد أن هناك بيانات
        report = daily_reports[group_id]
        report_chat_id = activated_groups.get(group_id, group_id)  # تحديد مجموعة الإشعارات أو نفس المجموعة

        msg = "📅 **التقرير اليومي**\n\n"
        msg += f"🔨 الأعضاء المحظورين:\n" + ("\n".join(report["banned"]) if report["banned"] else "لا يوجد") + "\n\n"
        msg += f"🔇 الأعضاء المكتمين:\n" + ("\n".join(report["muted"]) if report["muted"] else "لا يوجد") + "\n\n"
        msg += f"🚮 المحتوى المحذوف:\n" + ("\n".join(report["deleted_content"]) if report["deleted_content"] else "لا يوجد") + "\n\n"
        msg += f"👥 الإجراءات اليدوية:\n" + ("\n".join(report["manual_actions"]) if report["manual_actions"] else "لا يوجد")

        bot.send_message(report_chat_id, msg, parse_mode="Markdown")

    else:
        bot.send_message(group_id, "📢 لا يوجد سجل للمخالفات اليوم.", parse_mode="Markdown")

def reset_daily_reports():
    """إعادة تصفير السجلات كل 24 ساعة"""
    global daily_reports
    daily_reports = {group_id: {"banned": [], "muted": [], "deleted_content": [], "manual_actions": []} for group_id in activated_groups}
    print("✅ تم إعادة تصفير السجلات اليومية.")
    threading.Timer(86400, reset_daily_reports).start()  # إعادة التصغير بعد 24 ساعة


@bot.chat_member_handler(func=lambda message: message.new_chat_member is not None)
def notify_developer(message):
    """إعلام المطور عند إضافة البوت إلى مجموعة جديدة ورفعه كمشرف"""
    if message.new_chat_member.user.id == bot.id:  # التأكد أن البوت هو الذي تمت إضافته
        user_id = message.from_user.id
        username = message.from_user.username
        chat_id = message.chat.id
        chat_title = message.chat.title
        invite_link = f'https://t.me/{message.chat.username}' if message.chat.username else 'رابط المجموعة غير متوفر'

        # إرسال الرسالة للمطور
        bot.send_message(DEVELOPER_CHAT_ID, f"✅ تم إضافة البوت إلى مجموعة جديدة!\n\n"
                                           f"• **اسم المجموعة**: {chat_title}\n"
                                           f"• **ايدي المجموعة**: {chat_id}\n"
                                           f"• **الشخص الذي أضاف البوت**: {username} (ID: {user_id})\n"
                                           f"• **رابط المجموعة**: {invite_link}")
                
commands = [
telebot.types.BotCommand("settings", "عرض اعدادات المجموعة"),
    telebot.types.BotCommand("ban", "حظر عضو (بالرد، الأيدي، أو اليوزرنيم)"),
    telebot.types.BotCommand("unban", "إلغاء حظر عضو (بالرد، الأيدي، أو اليوزرنيم)"),
    telebot.types.BotCommand("mute", "تقييد عضو من الكتابة (بالرد، الأيدي، أو اليوزرنيم)"),
    telebot.types.BotCommand("unmute", "إلغاء تقييد عضو (بالرد، الأيدي، أو اليوزرنيم)"),
     telebot.types.BotCommand("opengbt", "للمشرف فقط (تفعيل الذكاء بلمجموعة)"),
      telebot.types.BotCommand("closegbt", "للمشرف فقط (تعطيل الذكاء بلمجموعة)"),
       telebot.types.BotCommand("gbt", "الذكاء الأصطناعي gbt-4 (ارسل رسالتك للذكاء مع الأمر)"),
telebot.types.BotCommand("enable_reports", "تفعيل إرسال التقارير اليومية لمجموعتك"),
           
]
bot.set_my_commands(commands)



# 5️⃣ دوال الرد التلقائي (الردود العشوائية)
shahin_replies = [
    "🥷🏻 <b>شاهين معك</b>",
    "🦅 <b>الشاهين فخر الثورة السورية</b>",
    "👀 <b>شاهين بالأجواء</b>",
    "🦾 <b>شاهين لديك لا خوف عليك</b>",
    "✨ <b>نعم صديقي، معك شاهين</b>",
    "🦦 <b>ماني فاضي عندي شغل</b>",
    "🗿 <b>مشغول شوي، بعدين برد</b>"
]

#bot_replies = [
 #   "🥷🏻 <b>اسمي شاهين، شو بقدر ساعدك؟</b>",
#    "🧑🏻‍💻 <b>مشغول</b>",
#    "⌛ <b>بعدين مو هلق</b>",
#    "🤯 <b>صرعتني ها، حاج تصيح بوت!</b>",
#    "🎤 <b>أي أي، كمان صيح بوت بوت</b>",
#    "🦅 <b>واحد متلك بوت، بتجي KD عندي 10</b>",
#    "🎮 <b>عم العب ببجي، ماني فاضي</b>"
#]

revolution_replies = [
    "💚 <b>الثورة عز والشهادة فخر</b>",
    "💚 <b>الثورة مالها حل غير النصر، إرادة الشعوب دائمًا تنتصر</b>"
]

deterrence_replies = [
    "🦅 <b>ردع العدوان</b>"
]

syria_replies = [
    "<b>سوريا أرض العز</b>"
]

syrian_replies = [
    "🦅 <b>أرفع راسك فوق أنت سوري حر</b>"
]

# دوال الرد على الكلمات
@bot.message_handler(func=lambda message: "شاهين" in message.text.lower())
def shahin_reply(message):
    bot.reply_to(message, random.choice(shahin_replies), parse_mode="HTML")

#@bot.message_handler(func=lambda message: "بوت" in message.text.lower())
#def bot_reply(message):
#    bot.reply_to(message, random.choice(bot_replies), parse_mode="HTML")

@bot.message_handler(func=lambda message: "ثورة" in message.text.lower())
def revolution_reply(message):
    bot.reply_to(message, random.choice(revolution_replies), parse_mode="HTML")

@bot.message_handler(func=lambda message: "ردع" in message.text.lower())
def deterrence_reply(message):
    bot.reply_to(message, random.choice(deterrence_replies), parse_mode="HTML")

@bot.message_handler(func=lambda message: "سوريا" in message.text.lower())
def syria_reply(message):
    bot.reply_to(message, random.choice(syria_replies), parse_mode="HTML")

@bot.message_handler(func=lambda message: "سوري" in message.text.lower())
def syrian_reply(message):
    bot.reply_to(message, random.choice(syrian_replies), parse_mode="HTML")
@bot.message_handler(func=lambda message: 'يلعن روحه' in message.text)
def send_audio(message):
    audio_file_id = 'https://t.me/srevbo67/6' 
    bot.send_audio(message.chat.id, audio_file_id, caption="يلعن روحه بقبره")    
# دالة إضافة الردود
@bot.message_handler(commands=['ad'])
def add_reply_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type == "private":
        return bot.send_message(chat_id, "❌ هذا الأمر للجروبات فقط")

    if not is_admin(chat_id, user_id):
        return bot.reply_to(message, "❌ للمشرفين فقط")

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        return bot.reply_to(message, "❌ استخدم: `/ad كلمة`", parse_mode="Markdown")

    keyword = command_parts[1].strip().lower()
    pending_replies[user_id] = {'chat_id': chat_id, 'keyword': keyword}
    bot.reply_to(message, "✅ أرسل الرد الآن (نص/صورة/ملف/إلخ)")

# دالة حفظ الردود بأنواعها
@bot.message_handler(func=lambda m: m.from_user.id in pending_replies, content_types=['text', 'photo', 'video', 'sticker', 'voice', 'audio', 'document', 'animation'])
def save_reply(message):
    user_data = pending_replies.pop(message.from_user.id, None)
    if not user_data: return

    chat_id = user_data['chat_id']
    keyword = user_data['keyword']
    reply_data = None

    if message.content_type == 'text':
        reply_data = {'type': 'text', 'content': message.text}
    elif message.content_type == 'photo':
        reply_data = {'type': 'photo', 'content': message.photo[-1].file_id}
    elif message.content_type == 'video':
        reply_data = {'type': 'video', 'content': message.video.file_id}
    elif message.content_type == 'sticker':
        reply_data = {'type': 'sticker', 'content': message.sticker.file_id}
    elif message.content_type == 'voice':
        reply_data = {'type': 'voice', 'content': message.voice.file_id}
    elif message.content_type == 'audio':
        reply_data = {'type': 'audio', 'content': message.audio.file_id}
    elif message.content_type == 'document':
        reply_data = {'type': 'document', 'content': message.document.file_id}
    elif message.content_type == 'animation':
        reply_data = {'type': 'animation', 'content': message.animation.file_id}

    if reply_data:
        group_replies.setdefault(chat_id, {})[keyword] = reply_data
        save_replies()
        bot.reply_to(message, f"✅ تم ربط الرد بــ `{keyword}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ نوع غير مدعوم")

# دالة معالجة الردود على الرسائل
@bot.message_handler(func=lambda m: True)
def handle_messages(message):
    chat_id = message.chat.id
    text = get_message_text(message).strip().lower()
    
    # إذا كانت الرسالة ردًا على رسالة أخرى
    if message.reply_to_message:
        replied_text = get_message_text(message.reply_to_message).strip().lower()
        if replied_text in group_replies.get(chat_id, {}):
            send_auto_reply(message.reply_to_message, original_message=message)
    
    # إذا كانت الرسالة عادية (ليست ردًا)
    elif text in group_replies.get(chat_id, {}):
        send_auto_reply(message)

def get_message_text(msg):
    """استخراج النص من الرسالة حتى لو كانت وسائط"""
    if msg.text: 
        return msg.text
    if msg.caption: 
        return msg.caption
    return ""

def send_auto_reply(target_msg, original_message=None):
    chat_id = target_msg.chat.id
    keyword = get_message_text(target_msg).strip().lower()
    reply_data = group_replies.get(chat_id, {}).get(keyword)

    if reply_data:
        try:
            # تحديد الشخص الذي يجب الرد عليه
            reply_to_user = original_message.from_user.id if original_message else target_msg.from_user.id
            reply_to_message_id = original_message.message_id if original_message else target_msg.message_id

            # إرسال الرد
            if reply_data["type"] == "text":
                bot.send_message(chat_id, reply_data["content"], reply_to_message_id=reply_to_message_id)
            else:
                send_func = getattr(bot, f'send_{reply_data["type"]}', None)
                if send_func:
                    send_func(chat_id, reply_data["content"], reply_to_message_id=reply_to_message_id)
                else:
                    bot.send_message(chat_id, "❌ لا يمكن إرسال هذا النوع من الردود.", reply_to_message_id=reply_to_message_id)
            
            # إضافة علامة إشارة (@) للشخص الذي تم الرد عليه
            if original_message:
                bot.send_message(chat_id, f"@{original_message.from_user.username}", reply_to_message_id=reply_to_message_id)
        except Exception as e:
            print(f"Error sending: {e}")       
        
         
          
reset_daily_reports()        
try:
    print("أي أنا شغال أموري تمام ")
    bot.infinity_polling()
except Exception as e:
    print(f"🚫 في غلط مارح اقدر أشتغل")