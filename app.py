"""
Freya Yachting — Flask Router
WhatsApp (Twilio) + Instagram DM (Meta) → n8n AI Webhook

Railway'e deploy et, environment variables'ları ayarla.
"""

import os
import json
import hmac
import hashlib
import logging
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import requests

# ============================================================
# AYARLAR — Railway Environment Variables olarak tanımla
# ============================================================
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "https://SENIN-N8N.app.n8n.cloud/webhook/whatsapp-ai")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_VERIFY_TOKEN = os.environ.get("IG_VERIFY_TOKEN", "FREYA_VERIFY_2024")
IG_APP_SECRET = os.environ.get("IG_APP_SECRET", "")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "+905XXXXXXXXX")
PORT = int(os.environ.get("PORT", 5000))

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================
def send_to_n8n(from_id, name, message, channel, media_url=None):
    """Mesajı n8n webhook'una gönder ve AI yanıtını al."""
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json={
                "from": f"{channel}:{from_id}",
                "name": name,
                "message": message,
                "media_url": media_url
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("n8n webhook timeout")
        return {"reply": "Şu anda yoğunluk yaşıyoruz, lütfen biraz sonra tekrar yazın. ⛵"}
    except Exception as e:
        logger.error(f"n8n webhook error: {e}")
        return {"reply": "Bir sorun oluştu, lütfen tekrar deneyin veya bizi arayın. 📞"}


def send_ig_reply(recipient_id, text):
    """Instagram DM üzerinden yanıt gönder."""
    try:
        # Uzun mesajları böl (IG limiti 1000 karakter)
        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        for chunk in chunks:
            resp = requests.post(
                "https://graph.facebook.com/v21.0/me/messages",
                params={"access_token": IG_ACCESS_TOKEN},
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": chunk}
                },
                timeout=30
            )
            if resp.status_code != 200:
                logger.error(f"IG send error: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"IG reply error: {e}")


def verify_ig_signature(payload, signature):
    """Meta webhook imza doğrulaması (güvenlik)."""
    if not IG_APP_SECRET or not signature:
        return True  # Secret yoksa doğrulamayı atla
    expected = hmac.new(
        IG_APP_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ============================================================
# HEALTH CHECK
# ============================================================
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Freya Yachting Router",
        "channels": ["whatsapp", "instagram"]
    })


# ============================================================
# WHATSAPP — Twilio Webhook
# ============================================================
@app.route("/whatsapp/incoming", methods=["POST"])
def whatsapp_incoming():
    """Twilio'dan gelen WhatsApp mesajlarını işle."""
    try:
        from_number = request.form.get("From", "")          # whatsapp:+905...
        body = request.form.get("Body", "")
        profile_name = request.form.get("ProfileName", "")
        media_url = request.form.get("MediaUrl0")
        num_media = int(request.form.get("NumMedia", 0))

        # Boş mesaj kontrolü
        if not body and num_media == 0:
            resp = MessagingResponse()
            return str(resp)

        # Medya varsa ama metin yoksa
        if not body and num_media > 0:
            body = "[Görsel/Dosya gönderildi]"

        # Numara temizle
        clean_number = from_number.replace("whatsapp:", "").replace("+", "")

        logger.info(f"WhatsApp mesaj: {clean_number} - {body[:50]}...")

        # n8n'e gönder
        ai_result = send_to_n8n(
            from_id=clean_number,
            name=profile_name or "WhatsApp Kullanıcı",
            message=body,
            channel="whatsapp",
            media_url=media_url
        )

        # Twilio yanıtı oluştur
        resp = MessagingResponse()
        msg = resp.message(ai_result.get("reply", ""))

        # AI medya öneriyorsa
        media = ai_result.get("media")
        if media:
            msg.media(media)

        return str(resp)

    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        resp = MessagingResponse()
        resp.message("Bir sorun oluştu, lütfen tekrar deneyin. ⛵")
        return str(resp)


# ============================================================
# INSTAGRAM — Meta Webhook (GET: doğrulama, POST: mesajlar)
# ============================================================
@app.route("/instagram/webhook", methods=["GET"])
def ig_verify():
    """Meta webhook doğrulaması."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == IG_VERIFY_TOKEN:
        logger.info("Instagram webhook doğrulandı")
        return challenge, 200

    logger.warning(f"Instagram doğrulama başarısız: mode={mode}, token={token}")
    return "Forbidden", 403


@app.route("/instagram/webhook", methods=["POST"])
def ig_incoming():
    """Meta'dan gelen Instagram DM mesajlarını işle."""
    try:
        # İmza doğrulama (opsiyonel ama önerilir)
        signature = request.headers.get("X-Hub-Signature-256", "")
        if IG_APP_SECRET and not verify_ig_signature(request.data, signature):
            logger.warning("Instagram imza doğrulama başarısız")
            return "Unauthorized", 401

        data = request.json

        # Mesajları işle
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id", "")

                # Mesaj var mı kontrol et
                message = messaging.get("message", {})
                if not message:
                    continue

                # Echo kontrolü (kendi gönderdiğimiz mesajları atla)
                if message.get("is_echo"):
                    continue

                text = message.get("text", "")

                # Görsel/sticker geldiyse
                attachments = message.get("attachments", [])
                if not text and attachments:
                    text = "[Görsel/Medya gönderildi]"

                if not text:
                    continue

                logger.info(f"Instagram DM: {sender_id} - {text[:50]}...")

                # n8n'e gönder (AYNI FORMAT)
                ai_result = send_to_n8n(
                    from_id=sender_id,
                    name=sender_id,
                    message=text,
                    channel="instagram",
                    media_url=None
                )

                # Instagram DM yanıtı gönder
                reply_text = ai_result.get("reply", "")
                if reply_text:
                    send_ig_reply(sender_id, reply_text)

        return "OK", 200

    except Exception as e:
        logger.error(f"Instagram error: {e}")
        return "OK", 200  # Meta'ya her zaman 200 dön, yoksa webhook'u devre dışı bırakır


# ============================================================
# ÇALIŞTIR
# ============================================================
if __name__ == "__main__":
    logger.info(f"Freya Router başlatılıyor - Port: {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
