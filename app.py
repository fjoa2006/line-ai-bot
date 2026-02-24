import os
import time
import json
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, UnfollowEvent
from openai import OpenAI

app = Flask(__name__)

# 從環境變數讀取金鑰 (更安全)
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', '758691ddb63dabf3711a807297dcabd7')
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'XbOeNFRjnqp0jKPZuX4aMgJJGsJ9IcHAGsiT925Zq8qgb9lT6AdP0OAeAM613QejMfep/+NkW+i18G9rMof++aIE1tjG4vDKYACF/CQAYcHqmekqRKvdI6Xr2KL7ClYQ3D8YNHJRrz3v2qOp0ZC6uwdB04t89/1O/w1cDnyilFU=')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# AI 回覆冷卻期（秒）
AI_COOLDOWN_PERIOD = 3600  # 1 小時

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# 記憶體快取：存放「最後人工回覆時間」
# 格式：{user_id: timestamp}
human_reply_cache = {}

def is_in_human_reply_cooldown(user_id: str) -> bool:
    """檢查使用者是否在人工回覆冷卻期內"""
    if user_id not in human_reply_cache:
        return False
    
    last_reply_time = human_reply_cache[user_id]
    current_time = time.time()
    
    # 檢查是否超過冷卻期
    if current_time - last_reply_time < AI_COOLDOWN_PERIOD:
        return True
    else:
        # 冷卻期已過，刪除記錄
        del human_reply_cache[user_id]
        return False

def set_human_reply_cooldown(user_id: str):
    """設定人工回覆冷卻期"""
    human_reply_cache[user_id] = time.time()
    print(f"[Cache] Set cooldown for user {user_id} for {AI_COOLDOWN_PERIOD} seconds")

@app.route("/line/webhook", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    
    # 調試：列印接收到的事件
    try:
        events = json.loads(body)
        for event in events.get('events', []):
            print(f"[Webhook] Received event: {event.get('type')}")
            
            # 檢查是否是人工回覆事件（officialAccountLinkEvent）
            if event.get('type') == 'officialAccountLinkEvent':
                print("[Webhook] Detected official account link event")
            
            # 檢查是否是文字訊息（可能來自人工回覆）
            if event.get('type') == 'message' and event.get('message', {}).get('type') == 'text':
                # 檢查訊息是否來自官方帳號（人工回覆）
                # LINE 的人工回覆會有特殊的 source 類型
                source = event.get('source', {})
                if source.get('type') == 'user':
                    # 這是使用者的訊息，不是人工回覆
                    pass
    except Exception as e:
        print(f"[Webhook] Debug error: {e}")
    
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
    
    # 調試：列印接收到的事件
    try:
        events = json.loads(body)
        for event in events.get('events', []):
            print(f"[Webhook2] Received event: {event.get('type')}")
            event_type = event.get('type')
            
            # 自動偵測人工回覆事件
            # LINE 的人工回覆會透過 postback 或特殊事件傳送
            # 這裡檢查是否有特殊標記
            if event_type == 'message':
                message = event.get('message', {})
                # 檢查是否是人工回覆（通常會有特殊的 source 或 metadata）
                source = event.get('source', {})
                user_id = source.get('userId')
                
                # 如果訊息來自官方帳號（人工回覆），設定冷卻期
                # 注意：LINE 的人工回覆可能需要特殊的識別方式
                # 這裡假設人工回覆會有特殊的訊息前綴或標記
                text = message.get('text', '')
                
                # 檢查是否是人工回覆（以 # 開頭）
                if text.startswith('#'):
                    if user_id:
                        set_human_reply_cooldown(user_id)
                        print(f"[Webhook2] Auto-detected manual reply from user {user_id}")
    except Exception as e:
        print(f"[Webhook2] Debug error: {e}")
    
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
        # 在冷卻期內不回覆
        return
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
