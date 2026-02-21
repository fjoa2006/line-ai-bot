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

# =============================================
# 帳號 1：角落整合 官方 LINE
# =============================================
CHANNEL_SECRET_1 = os.getenv('LINE_CHANNEL_SECRET', '758691ddb63dabf3711a807297dcabd7')
CHANNEL_ACCESS_TOKEN_1 = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'XbOeNFRjnqp0jKPZuX4aMgJJGsJ9IcHAGsiT925Zq8qgb9lT6AdP0OAeAM613QejMfep/+NkW+i18G9rMof++aIE1tjG4vDKYACF/CQAYcHqmekqRKvdI6Xr2KL7ClYQ3D8YNHJRrz3v2qOp0ZC6uwdB04t89/1O/w1cDnyilFU=')
SYSTEM_PROMPT_1 = "你是一位專業的 LINE 官方帳號小幫手，請用親切、專業且簡潔的語氣回覆客戶。"

configuration_1 = Configuration(access_token=CHANNEL_ACCESS_TOKEN_1)
handler_1 = WebhookHandler(CHANNEL_SECRET_1)

# =============================================
# 帳號 2：三軍總醫院 陳宣位醫師 官方 LINE
# =============================================
CHANNEL_SECRET_2 = os.getenv('LINE_CHANNEL_SECRET_2', 'fc6b23caa737ae9b6967f892f5e2c553')
CHANNEL_ACCESS_TOKEN_2 = os.getenv('LINE_CHANNEL_ACCESS_TOKEN_2', 'mQfneQs6JkSPQ5jcGELeH0gWRKfJLiBUpTVinUwLwJB7g3teldp3J8QPFgJnt4didHsa2ryBG74THOpzvIQhVNN7I0lHoT5i9NWD5pFRyFwm9raWjcqEtbR/9XFu/TvYJyyfMDw33P0MWRrFhDpQKAdB04t89/1O/w1cDnyilFU=')
SYSTEM_PROMPT_2 = """你是三軍總醫院陳宣位醫師診所的專業醫療助理。
陳宣位醫師的主要業務是 ESG 內視鏡縫胃手術（Endoscopic Sleeve Gastroplasty），這是一種微創的減重手術，透過內視鏡縫合胃部，縮小胃容量，幫助患者達到減重效果，無需開刀且恢復快。

你的職責包括：
1. 以親切、專業且易懂的語氣回答病患關於 ESG 手術的問題，例如：手術原理、適應症、術前準備、術後照護、預期效果等。
2. 分享減重相關的健康常識，例如：飲食控制、運動建議、BMI 計算、代謝症候群等。
3. 在涉及具體診斷、用藥或個人病情判斷時，務必提醒病患：以上資訊僅供參考，實際情況請親自回診與陳醫師確認，以獲得最適合您的醫療建議。
4. 不要自行診斷疾病或開立處方，保持醫療安全的邊界。"""

configuration_2 = Configuration(access_token=CHANNEL_ACCESS_TOKEN_2)
handler_2 = WebhookHandler(CHANNEL_SECRET_2)

# =============================================
# OpenAI 客戶端
# =============================================
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)


def generate_reply(user_message, system_prompt):
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
    ai_reply = generate_reply(user_message, SYSTEM_PROMPT_1)
    send_reply(event.reply_token, ai_reply, configuration_1)


# =============================================
# Webhook 路由：帳號 2（陳宣位醫師）
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
    user_message = event.message.text
    ai_reply = generate_reply(user_message, SYSTEM_PROMPT_2)
    send_reply(event.reply_token, ai_reply, configuration_2)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
