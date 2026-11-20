"""Testes do servidor web (nao batem na Binance: so rotas locais)."""
import json
import threading
import unittest
import urllib.error
import urllib.request

from finagent.webapp import make_server


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = make_server("127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_health(self):
        code, body = self.get("/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_index_serve_dashboard(self):
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("finagent", body.lower())
        self.assertIn("/api/analyze", body)

    def test_tf_invalido(self):
        code, body = self.get("/api/analyze?symbol=BTCUSDT&tf=7h")
        self.assertEqual(code, 400)
        self.assertIn("tf invalido", json.loads(body)["error"])

    def test_symbol_invalido(self):
        code, body = self.get("/api/analyze?symbol=BT-CUSDT")
        self.assertEqual(code, 400)
        self.assertIn("symbol invalido", json.loads(body)["error"])

    def test_rota_desconhecida(self):
        code, body = self.get("/nada")
        self.assertEqual(code, 404)
        self.assertIn("rota nao encontrada", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
