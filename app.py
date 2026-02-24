import os
import time
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from openai import OpenAI
import redis

app = Flask(__name__)

# 從環境變數讀取金鑰 (更安全)
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', '758691ddb63dabf3711a807297dcabd7')
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'XbOeNFRjnqp0jKPZuX4aMgJJGsJ9IcHAGsiT925Zq8qgb9lT6AdP0OAeAM613QejMfep/+NkW+i18G9rMof++aIE1tjG4vDKYACF/CQAYcHqmekqRKvdI6Xr2KL7ClYQ3D8YNHJRrz3v2qOp0ZC6uwdB04t89/1O/w1cDnyilFU=')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# AI 回覆冷卻期（秒）
AI_COOLDOWN_PERIOD = 3600  # 1 小時

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# 初始化 Redis
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()
    print("[Redis] Connected successfully")
except Exception as e:
    print(f"[Redis] Connection failed: {e}")
    redis_client = None

def is_in_human_reply_cooldown(user_id: str) -> bool:
    """檢查使用者是否在人工回覆冷卻期內"""
    if not redis_client:
        return False
    
    key = f"human_reply:{user_id}"
    last_reply_time = redis_client.get(key)
    
    if last_reply_time:
        return True
    return False

def set_human_reply_cooldown(user_id: str):
    """設定人工回覆冷卻期"""
    if not redis_client:
        return
    
    key = f"human_reply:{user_id}"
    redis_client.setex(key, AI_COOLDOWN_PERIOD, str(int(time.time())))
    print(f"[Redis] Set cooldown for user {user_id} for {AI_COOLDOWN_PERIOD} seconds")

@app.route("/line/webhook", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/line/webhook2", methods=['POST'])
def callback_webhook2():
    """陳醫師的 Webhook 端點"""
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    
    # 檢查是否在人工回覆冷卻期內
    if is_in_human_reply_cooldown(user_id):
        print(f"[AI] User {user_id} is in cooldown period, skipping AI reply")
        # 在冷卻期內不回覆，或回覆固定訊息
        ai_reply = "感謝您的訊息，我們已收到。專人將盡快為您服務。"
    else:
        # 調用 OpenAI API
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "你是一位專業的 LINE 官方帳號小幫手，請用親切、專業且簡潔的語氣回覆客戶。"},
                    {"role": "user", "content": user_message}
                ]
            )
            ai_reply = response.choices[0].message.content
            print(f"[AI] Generated reply for user {user_id}")
        except Exception as e:
            print(f"[AI] Error: {e}")
            ai_reply = "收到您的訊息！我們將盡快由專人為您服務。"

    # 回覆訊息
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        try:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=ai_reply)]
                )
            )
            print(f"[LINE] Replied to user {user_id}")
        except Exception as e:
            print(f"[LINE] Reply error: {e}")

@app.route("/line/manual-reply/<user_id>", methods=['POST'])
def manual_reply(user_id: str):
    """
    人工回覆端點
    POST /line/manual-reply/<user_id>
    設定該使用者的 AI 回覆冷卻期
    """
    set_human_reply_cooldown(user_id)
    return {
        "status": "success",
        "message": f"AI reply cooldown set for user {user_id} for {AI_COOLDOWN_PERIOD} seconds"
    }

@app.route("/line/check-cooldown/<user_id>", methods=['GET'])
def check_cooldown(user_id: str):
    """檢查使用者是否在冷卻期內"""
    in_cooldown = is_in_human_reply_cooldown(user_id)
    return {
        "user_id": user_id,
        "in_cooldown": in_cooldown,
        "cooldown_period": AI_COOLDOWN_PERIOD
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
