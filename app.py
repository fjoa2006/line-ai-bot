import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from openai import OpenAI

app = Flask(__name__)

# =============================================
# OpenAI 客戶端
# =============================================
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)

# =============================================
# 管理員 LINE User ID（接收通知）
# =============================================
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', 'U29a37d4b6161a881428be1770ce098d5')

# =============================================
# 帳號 1：角落整合 官方 LINE（Assistants API 長期記憶版）
# =============================================
CHANNEL_SECRET_1 = os.getenv('LINE_CHANNEL_SECRET', '758691ddb63dabf3711a807297dcabd7')
CHANNEL_ACCESS_TOKEN_1 = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'XbOeNFRjnqp0jKPZuX4aMgJJGsJ9IcHAGsiT925Zq8qgb9lT6AdP0OAeAM613QejMfep/+NkW+i18G9rMof++aIE1tjG4vDKYACF/CQAYcHqmekqRKvdI6Xr2KL7ClYQ3D8YNHJRrz3v2qOp0ZC6uwdB04t89/1O/w1cDnyilFU=')
ASSISTANT_ID_1 = os.getenv('OPENAI_ASSISTANT_ID_1', 'asst_xUr3Fsf9IXMxZ85tTNVyFRis')

configuration_1 = Configuration(access_token=CHANNEL_ACCESS_TOKEN_1)
handler_1 = WebhookHandler(CHANNEL_SECRET_1)

# =============================================
# 帳號 2：陳宣位醫師 官方 LINE（Assistants API 長期記憶版）
# =============================================
CHANNEL_SECRET_2 = os.getenv('LINE_CHANNEL_SECRET_2', 'fc6b23caa737ae9b6967f892f5e2c553')
CHANNEL_ACCESS_TOKEN_2 = os.getenv('LINE_CHANNEL_ACCESS_TOKEN_2', 'mQfneQs6JkSPQ5jcGELeH0gWRKfJLiBUpTVinUwLwJB7g3teldp3J8QPFgJnt4didHsa2ryBG74THOpzvIQhVNN7I0lHoT5i9NWD5pFRyFwm9raWjcqEtbR/9XFu/TvYJyyfMDw33P0MWRrFhDpQKAdB04t89/1O/w1cDnyilFU=')
ASSISTANT_ID_2 = os.getenv('OPENAI_ASSISTANT_ID_2', 'asst_W3kzXbACu2kdabmBofmKoUIK')

configuration_2 = Configuration(access_token=CHANNEL_ACCESS_TOKEN_2)
handler_2 = WebhookHandler(CHANNEL_SECRET_2)

# 用於儲存每位使用者的 Thread ID（以帳號區分）
user_threads_1 = {}
user_threads_2 = {}


# =============================================
# 取得使用者 LINE 顯示名稱
# =============================================
def get_user_display_name(user_id, configuration):
    """透過 LINE API 取得使用者的顯示名稱"""
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            profile = line_bot_api.get_profile(user_id)
            return profile.display_name
    except Exception as e:
        print(f"[WARN] Failed to get user profile: {e}")
        return "（無法取得名稱）"


# =============================================
# 從對話中擷取掛號相關資訊
# =============================================
def extract_booking_info(user_message, ai_reply):
    """嘗試從病患訊息與機器人回覆中擷取掛號相關資訊"""
    booking_keywords = [
        '掛號', '預約', '掛好', '完成', '時間', '日期', '星期', '週',
        '上午', '下午', '診', '院區', '汀洲', '內湖'
    ]
    combined = user_message + ' ' + ai_reply
    found = any(kw in combined for kw in booking_keywords)
    if found:
        # 回傳病患訊息中可能含有的掛號資訊
        return user_message
    return None


# =============================================
# 傳送通知給管理員
# =============================================
def notify_admin(user_id, user_message, ai_reply, configuration):
    """當偵測到 [NOTIFY_ADMIN] 標記時，推播通知給管理員"""
    try:
        # 取得病患 LINE 顯示名稱
        display_name = get_user_display_name(user_id, configuration)

        # 嘗試擷取掛號資訊
        booking_info = extract_booking_info(user_message, ai_reply)

        notify_text = (
            f"🔔 【需要您關注的訊息】\n\n"
            f"病患姓名：{display_name}\n"
            f"病患訊息：{user_message}\n"
        )

        if booking_info:
            notify_text += f"\n📋 掛號資訊：{booking_info}\n"

        notify_text += (
            f"\n機器人回覆：{ai_reply[:200]}{'...' if len(ai_reply) > 200 else ''}"
        )

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=ADMIN_USER_ID,
                    messages=[TextMessage(text=notify_text)]
                )
            )
    except Exception as e:
        print(f"[WARN] Failed to notify admin: {e}")


# =============================================
# 共用的 Assistants API 長期記憶回覆函式
# =============================================
def generate_reply_with_memory(user_id, user_message, assistant_id, user_threads):
    try:
        # 取得或建立該使用者的 Thread
        if user_id not in user_threads:
            thread = client.beta.threads.create()
            user_threads[user_id] = thread.id

        thread_id = user_threads[user_id]

        # 新增使用者訊息到 Thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # 執行 Assistant 並等待完成
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id
        )

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            for msg in messages.data:
                if msg.role == 'assistant':
                    return msg.content[0].text.value

        return "收到您的訊息！我們將盡快由專人為您服務，謝謝您的耐心等待。"
    except Exception:
        return "收到您的訊息！我們將盡快由專人為您服務，謝謝您的耐心等待。"


def send_reply(reply_token, reply_text, configuration):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


# =============================================
# Webhook 路由：帳號 1（角落整合，長期記憶版）
# =============================================
@app.route("/line/webhook", methods=['POST'])
def callback_1():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler_1.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler_1.add(MessageEvent, message=TextMessageContent)
def handle_message_1(event):
    user_id = event.source.user_id
    user_message = event.message.text
    ai_reply = generate_reply_with_memory(user_id, user_message, ASSISTANT_ID_1, user_threads_1)
    send_reply(event.reply_token, ai_reply, configuration_1)


# =============================================
# Webhook 路由：帳號 2（陳宣位醫師，長期記憶版）
# =============================================
@app.route("/line/webhook2", methods=['POST'])
def callback_2():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler_2.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler_2.add(MessageEvent, message=TextMessageContent)
def handle_message_2(event):
    user_id = event.source.user_id
    user_message = event.message.text
    ai_reply = generate_reply_with_memory(user_id, user_message, ASSISTANT_ID_2, user_threads_2)

    # 偵測是否需要通知管理員
    needs_notify = '[NOTIFY_ADMIN]' in ai_reply

    # 移除標記，避免病患看到
    clean_reply = ai_reply.replace('[NOTIFY_ADMIN]', '').strip()

    # 回覆病患（乾淨版本）
    send_reply(event.reply_token, clean_reply, configuration_2)

    # 若需要，推播通知給管理員
    if needs_notify:
        notify_admin(user_id, user_message, clean_reply, configuration_2)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
