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


if __name__ == "__main__":
    unittest.main()
