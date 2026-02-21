import os
import json
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
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
# 帳號 1：角落整合 官方 LINE（普通 AI 回覆）
# =============================================
CHANNEL_SECRET_1 = os.getenv('LINE_CHANNEL_SECRET', '758691ddb63dabf3711a807297dcabd7')
CHANNEL_ACCESS_TOKEN_1 = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'XbOeNFRjnqp0jKPZuX4aMgJJGsJ9IcHAGsiT925Zq8qgb9lT6AdP0OAeAM613QejMfep/+NkW+i18G9rMof++aIE1tjG4vDKYACF/CQAYcHqmekqRKvdI6Xr2KL7ClYQ3D8YNHJRrz3v2qOp0ZC6uwdB04t89/1O/w1cDnyilFU=')
SYSTEM_PROMPT_1 = "你是一位專業的 LINE 官方帳號小幫手，請用親切、專業且簡潔的語氣回覆客戶。"

configuration_1 = Configuration(access_token=CHANNEL_ACCESS_TOKEN_1)
handler_1 = WebhookHandler(CHANNEL_SECRET_1)

# =============================================
# 帳號 2：陳宣位醫師 官方 LINE（Assistants API 長期記憶版）
# =============================================
CHANNEL_SECRET_2 = os.getenv('LINE_CHANNEL_SECRET_2', 'fc6b23caa737ae9b6967f892f5e2c553')
CHANNEL_ACCESS_TOKEN_2 = os.getenv('LINE_CHANNEL_ACCESS_TOKEN_2', 'mQfneQs6JkSPQ5jcGELeH0gWRKfJLiBUpTVinUwLwJB7g3teldp3J8QPFgJnt4didHsa2ryBG74THOpzvIQhVNN7I0lHoT5i9NWD5pFRyFwm9raWjcqEtbR/9XFu/TvYJyyfMDw33P0MWRrFhDpQKAdB04t89/1O/w1cDnyilFU=')
ASSISTANT_ID_2 = os.getenv('OPENAI_ASSISTANT_ID', 'asst_W3kzXbACu2kdabmBofmKoUIK')

configuration_2 = Configuration(access_token=CHANNEL_ACCESS_TOKEN_2)
handler_2 = WebhookHandler(CHANNEL_SECRET_2)

# 用於儲存每位使用者的 Thread ID（記憶體版，重啟後清空）
# 若需要永久記憶，可改用資料庫
user_threads = {}


# =============================================
# 帳號 1 的普通 AI 回覆
# =============================================
def generate_reply_simple(user_message, system_prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content
    except Exception:
        return "收到您的訊息！我們將盡快由專人為您服務，謝謝您的耐心等待。"


# =============================================
# 帳號 2 的 Assistants API 長期記憶回覆
# =============================================
def generate_reply_with_memory(user_id, user_message):
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

        # 執行 Assistant
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID_2
        )

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            # 取得最新的助理回覆
            for msg in messages.data:
                if msg.role == 'assistant':
                    return msg.content[0].text.value
        return "收到您的訊息！我們將盡快由專人為您服務，謝謝您的耐心等待。"
    except Exception as e:
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
# Webhook 路由：帳號 1（角落整合）
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
    user_message = event.message.text
    ai_reply = generate_reply_simple(user_message, SYSTEM_PROMPT_1)
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
    ai_reply = generate_reply_with_memory(user_id, user_message)
    send_reply(event.reply_token, ai_reply, configuration_2)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
