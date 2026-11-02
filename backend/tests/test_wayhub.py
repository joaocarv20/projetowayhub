"""Testes das regras de negócio e do fluxo completo. Uso (na pasta backend): python -m unittest discover tests"""
import io
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rules  # noqa: E402
from app import create_app  # noqa: E402
from seed import make_cnpj  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_phone_case_is_at_most_70_cents(self):
        self.assertLessEqual(rules.calculate_fee_cents(15, 8, 2, 0.05), 70)

    def test_fee_uses_cubic_weight_when_larger(self):
        light_big = rules.calculate_fee_cents(60, 40, 40, 1)   # cubado ≈ 28,8 kg
        heavy_small = rules.calculate_fee_cents(20, 20, 20, 1)
        self.assertGreater(light_big, heavy_small)

    def test_min_trip_fee(self):
        with self.assertRaises(rules.RuleError):
            rules.validate_min_trip_fee([70, 200, 229])
        self.assertEqual(rules.validate_min_trip_fee([300, 200]), 500)

    def test_lead_time_40_minutes(self):
        now = rules.utcnow()
        with self.assertRaises(rules.RuleError):
            rules.validate_lead_time(now + timedelta(minutes=39), now)
        rules.validate_lead_time(now + timedelta(minutes=40), now)

    def test_eta(self):
        self.assertTrue(40 <= rules.estimate_travel_minutes("Anápolis", "Goiânia") <= 90)
        self.assertIsNone(rules.estimate_travel_minutes("Cidade X", "Goiânia"))


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app = create_app({"DATABASE": f"{self.tmp.name}/t.db", "STORAGE_DIR": f"{self.tmp.name}/st", "TESTING": True})
        self.c = app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def make_hub(self, n, city):
        r = self.c.post("/api/auth/register/hub", json={
            "name": f"Hub {n}", "cnpj": make_cnpj(n), "email": f"h{n}@t.com", "password": "123456", "phone": "62999",
            "cep": "75000000", "street": "Rua A", "neighborhood": "Centro", "city": city, "state": "GO"})
        self.assertEqual(r.status_code, 201, r.json)
        token = r.json["token"]
        return token, self.c.get("/api/me", headers=self.auth(token)).json["hub"]["id"]

    def test_full_handshake_flow(self):
        origin_tok, _ = self.make_hub(1, "Anápolis")
        dest_tok, dest_id = self.make_hub(2, "Goiânia")
        pickup = rules.to_iso(rules.utcnow() + timedelta(hours=2))

        ids = []
        for dims in [(15, 8, 2, 0.05), (40, 30, 25, 4.0)]:
            r = self.c.post("/api/hub/orders", headers=self.auth(origin_tok), json={
                "height_cm": dims[0], "width_cm": dims[1], "length_cm": dims[2], "weight_kg": dims[3],
                "dest_hub_id": dest_id, "pickup_at": pickup})
            self.assertEqual(r.status_code, 201, r.json)
            ids.append(r.json["id"])

        r = self.c.post("/api/auth/register/driver", json={
            "email": "m@t.com", "password": "123456", "first_name": "Ana", "last_name": "Silva",
            "phone": "62988", "origin_city": "Anápolis", "home_address": "Rua B"})
        drv = self.auth(r.json["token"])

        # Sem documentos não pode reservar
        self.assertEqual(self.c.post("/api/driver/trips", headers=drv, json={"order_ids": ids}).status_code, 422)

        # Veículo de terceiro exige documento do proprietário
        png = b"\x89PNG\r\n\x1a\nfake"
        form = {"plate": "ABC1D23", "model": "Gol", "color": "Prata", "year": "2018", "cargo_type": "porta_malas_medio",
                "owned_by_third_party": "1", "cnh": (io.BytesIO(png), "cnh.png", "image/png"),
                "crlv": (io.BytesIO(png), "crlv.png", "image/png")}
        r = self.c.post("/api/driver/onboarding", headers=drv, data=form, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 422)
        self.assertIn("proprietário", r.json["error"])
        form.update(cnh=(io.BytesIO(png), "cnh.png", "image/png"), crlv=(io.BytesIO(png), "crlv.png", "image/png"),
                    owner_id=(io.BytesIO(png), "rg.png", "image/png"))
        r = self.c.post("/api/driver/onboarding", headers=drv, data=form, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.json)

        # URL assinada funciona; adulterada não
        docs = self.c.get("/api/driver/documents", headers=drv).json
        r = self.c.get(docs[0]["url"])
        self.assertEqual(r.status_code, 200)
        r.close()
        self.assertEqual(self.c.get(docs[0]["url"] + "x").status_code, 403)

        found = self.c.get("/api/driver/orders/search?origin=anapolis&destination=GOIANIA", headers=drv).json
        self.assertEqual(len(found), 2)

        # Só a capinha (< R$ 5,00) é bloqueada pela taxa mínima
        r = self.c.post("/api/driver/trips", headers=drv, json={"order_ids": [ids[0]]})
        self.assertEqual(r.status_code, 422)
        r = self.c.post("/api/driver/trips", headers=drv, json={"order_ids": ids})
        self.assertEqual(r.status_code, 201, r.json)
        code1 = r.json["pickup_code"]

        trip = self.c.get("/api/driver/trips", headers=drv).json[0]
        self.assertIsNone(trip["delivery_code"])
        mon = self.c.get("/api/hub/monitoring", headers=self.auth(origin_tok)).json
        self.assertEqual({m["status_label"] for m in mon}, {"Solicitado"})

        # Código 1 no destino não vale; na origem libera
        self.assertEqual(self.c.post("/api/hub/validate-code", headers=self.auth(dest_tok), json={"code": code1}).status_code, 422)
        r = self.c.post("/api/hub/validate-code", headers=self.auth(origin_tok), json={"code": code1})
        self.assertEqual(r.json["action"], "pickup")

        code2 = self.c.get("/api/driver/trips", headers=drv).json[0]["delivery_code"]
        self.assertIsNotNone(code2)
        r = self.c.post("/api/hub/validate-code", headers=self.auth(dest_tok), json={"code": code2})
        self.assertEqual(r.json["action"], "delivery")

        mon = self.c.get("/api/hub/monitoring", headers=self.auth(dest_tok)).json
        self.assertTrue(all(m["status_label"] == "Encerrado" and m["paid_at"] for m in mon))
        self.assertEqual(self.c.get("/api/driver/trips", headers=drv).json[0]["status"], "closed")

    def test_order_requires_lead_time(self):
        tok, _ = self.make_hub(3, "Anápolis")
        _, dest = self.make_hub(4, "Goiânia")
        r = self.c.post("/api/hub/orders", headers=self.auth(tok), json={
            "height_cm": 10, "width_cm": 10, "length_cm": 10, "weight_kg": 1, "dest_hub_id": dest,
            "pickup_at": rules.to_iso(rules.utcnow() + timedelta(minutes=20))})
        self.assertEqual(r.status_code, 422)

    def test_invalid_token_rejected(self):
        self.assertEqual(self.c.get("/api/me", headers=self.auth("a.b.c")).status_code, 401)


@unittest.skipUnless((Path(__file__).resolve().parents[2] / "ml" / "models" / "transit_model.joblib").exists(),
                     "modelo não treinado (rode ml/train.py)")
class PredictTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = create_app({"DATABASE": f"{self.tmp.name}/t.db", "TESTING": True}).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def predict(self, dest_cep, **kw):
        data = {"origin_cep": "01310-100", "dest_cep": dest_cep, "weight_kg": 1, "height_cm": 20, "width_cm": 20,
                "length_cm": 20, "posted_at": "2026-10-29T12:00:00Z", **kw}
        return self.c.post("/api/predict/transit", json=data)

    def test_far_destination_takes_longer(self):
        near = self.predict("04001-000").json   # São Paulo → São Paulo
        far = self.predict("69005-000").json    # São Paulo → Manaus
        self.assertEqual((near["origin"]["state"], far["destination"]["state"]), ("SP", "AM"))
        self.assertLess(near["expected_days"], far["expected_days"])
        self.assertGreaterEqual(far["safe_days"], far["expected_days"])

    def test_invalid_input(self):
        self.assertEqual(self.predict("123").status_code, 422)
        self.assertEqual(self.predict("69005-000", weight_kg=0).status_code, 422)


if __name__ == "__main__":
    unittest.main()
