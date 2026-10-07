"""
Freya Yachting — Flask Router
WhatsApp (Twilio) + Instagram DM (ManyChat) → n8n AI Webhook
Async Instagram: Returns immediately to ManyChat, sends reply via ManyChat API
"""

import os
import json
import logging
import threading
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import requests

N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "https://freyayachting.app.n8n.cloud/webhook/whatsapp-ai")
MANYCHAT_API_KEY = os.environ.get("MANYCHAT_API_KEY", "")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "+908508402465")
PORT = int(os.environ.get("PORT", 5000))
# Twilio REST ile WhatsApp cevabi (API Key). Uc degisken de doluysa kullanilir, yoksa TwiML ile cevap verilir.
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_API_KEY_SID = os.environ.get("TWILIO_API_KEY_SID", "")
TWILIO_API_KEY_SECRET = os.environ.get("TWILIO_API_KEY_SECRET", "")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_to_n8n(from_id, name, message, channel, media_url=None):
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json={
                "from": f"{channel}:{from_id}",
                "name": name,
                "message": message,
                "media_url": media_url
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("n8n webhook timeout")
        return {"reply": "Su anda yogunluk yasiyoruz, lutfen biraz sonra tekrar yazin."}
    except Exception as e:
        logger.error(f"n8n webhook error: {e}")
        return {"reply": "Bir sorun olustu, lutfen tekrar deneyin veya bizi arayin."}


def send_instagram_reply_async(subscriber_id, name, message):
    """Background thread: n8n'den cevap al, ManyChat API ile gonder"""
    try:
        ai_result = send_to_n8n(
            from_id=subscriber_id,
            name=name,
            message=message,
            channel="instagram"
        )

        logger.info(f"n8n response for Instagram: {json.dumps(ai_result, ensure_ascii=False)[:500]}")

        reply_text = ai_result.get("reply", "Bir sorun olustu, lutfen tekrar deneyin.")

        if len(reply_text) > 1000:
            reply_text = reply_text[:997] + "..."

        logger.info(f"Sending Instagram reply via ManyChat API ({len(reply_text)} chars)")

        # ManyChat API ile mesaj gonder
        manychat_response = requests.post(
            "https://api.manychat.com/fb/sending/sendContent",
            headers={
                "Authorization": f"Bearer {MANYCHAT_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "subscriber_id": int(subscriber_id),
                "data": {
                    "version": "v2",
                    "content": {
                        "type": "instagram",
                        "messages": [
                            {
                                "type": "text",
                                "text": reply_text
                            }
                        ]
                    }
                }
            },
            timeout=30
        )

        logger.info(f"ManyChat API response: {manychat_response.status_code} - {manychat_response.text[:200]}")

    except Exception as e:
        logger.error(f"Instagram async reply error: {e}")


def mask_number(number):
    digits = "".join(c for c in str(number) if c.isdigit())
    return "***" + digits[-4:] if digits else "***"


def twilio_rest_ready():
    return bool(TWILIO_ACCOUNT_SID and TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET)


def send_whatsapp_reply_async(customer, business, clean_number, name, body, media_url):
    """Background thread: n8n'den cevap al, Twilio REST API ile gonder (Twilio webhook'u 15 sn'de vazgecer)"""
    who = mask_number(customer)
    try:
        ai_result = send_to_n8n(
            from_id=clean_number,
            name=name,
            message=body,
            channel="whatsapp",
            media_url=media_url
        )

        reply = ai_result.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            logger.error(f"WhatsApp: n8n bos cevap dondu, mesaj gonderilmedi ({who})")
            return

        params = {"from_": business, "to": customer, "body": reply}
        media = ai_result.get("media")
        if media:
            params["media_url"] = [media]

        Client(TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWILIO_ACCOUNT_SID).messages.create(**params)
        logger.info(f"WhatsApp cevap gonderildi ({who})")

    except Exception as e:
        logger.error(f"WhatsApp cevap gonderilemedi ({who}): {type(e).__name__} kod={getattr(e, 'code', '-')} http={getattr(e, 'status', '-')}")


@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Freya Yachting Router",
        "channels": ["whatsapp", "instagram"]
    })


@app.route("/whatsapp/incoming", methods=["POST"])
def whatsapp_incoming():
    try:
        from_number = request.form.get("From", "")
        body = request.form.get("Body", "")
        profile_name = request.form.get("ProfileName", "")
        media_url = request.form.get("MediaUrl0")
        num_media = int(request.form.get("NumMedia", 0))

        if not body and num_media == 0:
            resp = MessagingResponse()
            return str(resp)

        if not body and num_media > 0:
            body = "[Gorsel/Dosya gonderildi]"

        clean_number = from_number.replace("whatsapp:", "").replace("+", "")
        logger.info(f"WhatsApp mesaj: {clean_number} - {body[:50]}...")

        to_number = request.form.get("To", "")
        if twilio_rest_ready() and to_number:
            # Twilio'ya hemen bos TwiML don, cevabi arka planda REST ile gonder
            threading.Thread(
                target=send_whatsapp_reply_async,
                args=(from_number, to_number, clean_number, profile_name or "WhatsApp Kullanici", body, media_url)
            ).start()
            return str(MessagingResponse())

        ai_result = send_to_n8n(
            from_id=clean_number,
            name=profile_name or "WhatsApp Kullanici",
            message=body,
            channel="whatsapp",
            media_url=media_url
        )

        logger.info(f"n8n response for WhatsApp: {json.dumps(ai_result, ensure_ascii=False)[:200]}")

        resp = MessagingResponse()
        msg = resp.message(ai_result.get("reply", ""))
        media = ai_result.get("media")
        if media:
            msg.media(media)
        return str(resp)

    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        resp = MessagingResponse()
        resp.message("Bir sorun olustu, lutfen tekrar deneyin.")
        return str(resp)


@app.route("/manychat/instagram", methods=["POST"])
def manychat_incoming():
    try:
        data = request.json
        logger.info(f"ManyChat data: {json.dumps(data, ensure_ascii=False)[:500]}")

        subscriber_id = ""
        name = "Instagram Kullanici"
        message = ""

        if "id" in data:
            subscriber_id = str(data["id"])
        elif "subscriber_id" in data:
            subscriber_id = str(data["subscriber_id"])
        elif "user_id" in data:
            subscriber_id = str(data["user_id"])

        if "name" in data:
            name = data["name"]
        elif "first_name" in data:
            first = data.get("first_name", "")
            last = data.get("last_name", "")
            name = f"{first} {last}".strip() or "Instagram Kullanici"
        elif "full_name" in data:
            name = data["full_name"]

        if "message" in data:
            message = data["message"]
        elif "last_input_text" in data:
            message = data["last_input_text"]
        elif "text" in data:
            message = data["text"]

        if not message:
            return jsonify({"status": "no_message"}), 200

        logger.info(f"Instagram DM: {subscriber_id} ({name}) - {message[:50]}...")

        # Background thread'de n8n'e gonder ve ManyChat API ile yanit gonder
        thread = threading.Thread(
            target=send_instagram_reply_async,
            args=(subscriber_id, name, message)
        )
        thread.start()

        # ManyChat'e hemen bos response don (timeout olmaz)
        return jsonify({"status": "processing"}), 200

    except Exception as e:
        logger.error(f"ManyChat error: {e}")
        return jsonify({"status": "error"}), 200


if __name__ == "__main__":
    logger.info(f"Freya Router baslatiliyor - Port: {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
