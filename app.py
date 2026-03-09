"""
Freya Yachting — Flask Router
WhatsApp (Twilio) + Instagram DM (ManyChat) → n8n AI Webhook
"""

import os
import json
import logging
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import requests

N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "https://freyayachting.app.n8n.cloud/webhook/whatsapp-ai")
MANYCHAT_API_KEY = os.environ.get("MANYCHAT_API_KEY", "")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "+908508402465")
PORT = int(os.environ.get("PORT", 5000))

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

        ai_result = send_to_n8n(
            from_id=clean_number,
            name=profile_name or "WhatsApp Kullanici",
            message=body,
            channel="whatsapp",
            media_url=media_url
        )

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
            return jsonify({
                "version": "v2",
                "content": {
                    "type": "instagram",
                    "messages": [{"type": "text", "text": "Merhaba! Size nasil yardimci olabilirim?"}]
                }
            })

        logger.info(f"Instagram DM: {subscriber_id} ({name}) - {message[:50]}...")

        ai_result = send_to_n8n(
            from_id=subscriber_id,
            name=name,
            message=message,
            channel="instagram"
        )

        reply_text = ai_result.get("reply", "Bir sorun olustu, lutfen tekrar deneyin.")

        return jsonify({
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
        })

    except Exception as e:
        logger.error(f"ManyChat error: {e}")
        return jsonify({
            "version": "v2",
            "content": {
                "type": "instagram",
                "messages": [{"type": "text", "text": "Bir sorun olustu, lutfen tekrar deneyin."}]
            }
        }), 200


if __name__ == "__main__":
    logger.info(f"Freya Router baslatiliyor - Port: {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
