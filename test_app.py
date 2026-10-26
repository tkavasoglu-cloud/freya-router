"""send_to_n8n: N8N_WEBHOOK_SECRET doluysa X-Freya-Secret basligi gider, bossa hic baslik gitmez.
Calistir: python -m unittest test_app.py
"""

import importlib
import os
import unittest
from unittest import mock


def yukle(sir):
    with mock.patch.dict(os.environ, {"N8N_WEBHOOK_SECRET": sir}):
        import app
        return importlib.reload(app)


class SendToN8n(unittest.TestCase):
    def gonder(self, sir):
        app = yukle(sir)
        with mock.patch.object(app.requests, "post") as post:
            post.return_value.json.return_value = {"reply": "ok"}
            self.assertEqual(app.send_to_n8n("905000000000", "Ad", "merhaba", "whatsapp"), {"reply": "ok"})
            return post.call_args.kwargs

    def test_sir_doluysa_baslik_gider(self):
        self.assertEqual(self.gonder("gizli-deger")["headers"], {"X-Freya-Secret": "gizli-deger"})

    def test_sir_bossa_baslik_yok(self):
        self.assertIsNone(self.gonder("")["headers"])

    def test_govde_degismez(self):
        self.assertEqual(self.gonder("x")["json"], {"from": "whatsapp:905000000000", "name": "Ad", "message": "merhaba", "media_url": None})


class InstagramCevap(unittest.TestCase):
    def calistir(self, n8n_cevabi):
        app = yukle("")
        with mock.patch.object(app, "send_to_n8n", return_value=n8n_cevabi), mock.patch.object(app.requests, "post") as post, self.assertLogs(app.logger, "INFO") as kayit:
            app.send_instagram_reply_async("1234567890", "Ayse Yilmaz", "merhaba")
        return post, "\n".join(kayit.output)

    def test_bilerek_sessiz_gonderilmez_hata_yok(self):
        post, kayit = self.calistir({"reply": None, "ignored": True})
        post.assert_not_called()
        self.assertIn("sessiz", kayit)
        self.assertNotIn("error:", kayit.lower())

    def test_beklenmeyen_bos_cevap_hata_olarak_kaydedilir(self):
        post, kayit = self.calistir({"reply": None})
        post.assert_not_called()
        self.assertIn("bos cevap", kayit)
        self.assertNotIn("NoneType", kayit)

    def test_normal_cevap_manychat_ile_gider(self):
        post, _ = self.calistir({"reply": "Merhaba"})
        self.assertEqual(post.call_args.kwargs["json"]["data"]["content"]["messages"][0]["text"], "Merhaba")


class ManychatGunlugu(unittest.TestCase):
    def test_musteri_verisi_gunluge_yazilmaz(self):
        app = yukle("")
        with mock.patch.object(app.threading, "Thread"), self.assertLogs(app.logger, "INFO") as kayit:
            r = app.app.test_client().post("/manychat/instagram", json={"id": "1234567890", "name": "Ayse Yilmaz", "profile_pic": "https://x/p.jpg", "last_input_text": "gizli mesaj"})
        self.assertEqual(r.status_code, 200)
        metin = "\n".join(kayit.output)
        for sir in ("1234567890", "Ayse Yilmaz", "https://x/p.jpg", "gizli mesaj"):
            self.assertNotIn(sir, metin)


def yukle_ortam(**ortam):
    temel = {"N8N_WEBHOOK_SECRET": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_WEBHOOK_URL": "", "MANYCHAT_WEBHOOK_SECRET": "", "GIRIS_DOGRULAMA": "kayit", "TWILIO_ACCOUNT_SID": ""}
    with mock.patch.dict(os.environ, {**temel, **ortam}):
        import app
        return importlib.reload(app)


URL = "https://router.example.com/whatsapp/incoming"
FORM = {"From": "whatsapp:+905000000000", "To": "whatsapp:+908500000000", "Body": "merhaba", "NumMedia": "0"}
JETON = "twilio-auth-jeton-deneme"


def imza(form=FORM, jeton=JETON, url=URL):
    from twilio.request_validator import RequestValidator
    return RequestValidator(jeton).compute_signature(url, form)


class TwilioImzasi(unittest.TestCase):
    def gonder(self, ortam, basliklar):
        app = yukle_ortam(**ortam)
        with mock.patch.object(app, "send_to_n8n", return_value={"reply": "ok"}) as n8n, self.assertLogs(app.logger, "INFO") as kayit:
            r = app.app.test_client().post("/whatsapp/incoming", data=FORM, headers=basliklar)
        return r, n8n, "\n".join(kayit.output)

    def test_gecerli_imza_islenir(self):
        r, n8n, kayit = self.gonder({"TWILIO_AUTH_TOKEN": JETON, "TWILIO_WEBHOOK_URL": URL}, {"X-Twilio-Signature": imza()})
        self.assertEqual(r.status_code, 200); n8n.assert_called_once(); self.assertIn("dogrulama: gecerli", kayit)

    def test_url_basliklardan_kurulur(self):
        h = {"X-Twilio-Signature": imza(), "X-Forwarded-Proto": "https", "X-Forwarded-Host": "router.example.com"}
        r, n8n, kayit = self.gonder({"TWILIO_AUTH_TOKEN": JETON}, h)
        self.assertIn("dogrulama: gecerli", kayit); n8n.assert_called_once()

    def test_kayit_modunda_gecersiz_imza_yine_islenir(self):
        r, n8n, kayit = self.gonder({"TWILIO_AUTH_TOKEN": JETON, "TWILIO_WEBHOOK_URL": URL}, {"X-Twilio-Signature": "sahte"})
        self.assertEqual(r.status_code, 200); n8n.assert_called_once(); self.assertIn("gecersiz", kayit); self.assertIn("KAYIT MODU", kayit)

    def test_zorunlu_modda_gecersiz_ve_eksik_imza_reddedilir(self):
        for h in ({"X-Twilio-Signature": "sahte"}, {}):
            r, n8n, kayit = self.gonder({"TWILIO_AUTH_TOKEN": JETON, "TWILIO_WEBHOOK_URL": URL, "GIRIS_DOGRULAMA": "zorunlu"}, h)
            self.assertEqual(r.status_code, 403); n8n.assert_not_called(); self.assertIn("REDDEDILDI", kayit)

    def test_jeton_yoksa_denetim_kapali_davranis_eski(self):
        r, n8n, kayit = self.gonder({"GIRIS_DOGRULAMA": "zorunlu"}, {})
        self.assertEqual(r.status_code, 200); n8n.assert_called_once(); self.assertIn("dogrulama: kapali", kayit)

    def test_imza_ve_jeton_gunluge_yazilmaz(self):
        s = imza()
        _, _, kayit = self.gonder({"TWILIO_AUTH_TOKEN": JETON, "TWILIO_WEBHOOK_URL": URL}, {"X-Twilio-Signature": s})
        self.assertNotIn(s, kayit); self.assertNotIn(JETON, kayit)


class ManychatSirri(unittest.TestCase):
    SIR = "manychat-sir-deneme"
    VERI = {"id": "1234567890", "name": "Ad", "last_input_text": "merhaba"}

    def gonder(self, ortam, basliklar):
        app = yukle_ortam(**ortam)
        with mock.patch.object(app.threading, "Thread") as is_parcacigi, self.assertLogs(app.logger, "INFO") as kayit:
            r = app.app.test_client().post("/manychat/instagram", json=self.VERI, headers=basliklar)
        return r, is_parcacigi, "\n".join(kayit.output)

    def test_dogru_sir_islenir(self):
        r, t, kayit = self.gonder({"MANYCHAT_WEBHOOK_SECRET": self.SIR, "GIRIS_DOGRULAMA": "zorunlu"}, {"X-Freya-Secret": self.SIR})
        self.assertEqual(r.status_code, 200); t.assert_called_once(); self.assertIn("dogrulama: gecerli", kayit)

    def test_kayit_modunda_yanlis_sir_yine_islenir(self):
        r, t, kayit = self.gonder({"MANYCHAT_WEBHOOK_SECRET": self.SIR}, {"X-Freya-Secret": "yanlis"})
        self.assertEqual(r.status_code, 200); t.assert_called_once(); self.assertIn("KAYIT MODU", kayit)

    def test_zorunlu_modda_yanlis_ve_eksik_sir_reddedilir(self):
        for h in ({"X-Freya-Secret": "yanlis"}, {}):
            r, t, kayit = self.gonder({"MANYCHAT_WEBHOOK_SECRET": self.SIR, "GIRIS_DOGRULAMA": "zorunlu"}, h)
            self.assertEqual(r.status_code, 403); t.assert_not_called()

    def test_sir_degeri_gunluge_yazilmaz(self):
        _, _, kayit = self.gonder({"MANYCHAT_WEBHOOK_SECRET": self.SIR}, {"X-Freya-Secret": "yanlis-deger-123"})
        self.assertNotIn(self.SIR, kayit); self.assertNotIn("yanlis-deger-123", kayit)


if __name__ == "__main__":
    unittest.main()
