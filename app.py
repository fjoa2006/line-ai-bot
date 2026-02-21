import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from openai import OpenAI

app = Flask(__name__)

# 從環境變數讀取金鑰 (更安全)
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', '758691ddb63dabf3711a807297dcabd7')
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'XbOeNFRjnqp0jKPZuX4aMgJJGsJ9IcHAGsiT925Zq8qgb9lT6AdP0OAeAM613QejMfep/+NkW+i18G9rMof++aIE1tjG4vDKYACF/CQAYcHqmekqRKvdI6Xr2KL7ClYQ3D8YNHJRrz3v2qOp0ZC6uwdB04t89/1O/w1cDnyilFU=')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

@app.route("/line/webhook", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位專業的 LINE 官方帳號小幫手，請用親切、專業且簡潔的語氣回覆客戶。"},
                {"role": "user", "content": user_message}
            ]
        )
        ai_reply = response.choices[0].message.content
    except Exception:
        ai_reply = "收到您的訊息！我們將盡快由專人為您服務。"

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=ai_reply)]
            )
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
