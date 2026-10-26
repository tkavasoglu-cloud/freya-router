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


if __name__ == "__main__":
    unittest.main()
