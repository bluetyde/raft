"""Handshake tests for the /jev route. No model is loaded: evaluate_hypotheses is stubbed."""
import sys
from types import SimpleNamespace

import unittest
from fastapi.testclient import TestClient

sys.argv = ["server.py"]
import server  # noqa: E402

REQ = {
    "protocolVersion": 1, "sessionId": "s", "temporalEpoch": 3, "connectionId": "c",
    "requestId": "r1", "observationStep": 7, "role": "operator",
    "premise": "p", "candidates": [{"id": "hold", "text": "a"}, {"id": "scram", "text": "b"}],
}



def client(shadow=False, fail=False):
    server.args = SimpleNamespace(model_backend="mica", shadow=shadow)
    def fake(premise, candidates):
        if fail:
            raise RuntimeError("no model")
        return "hold"
    server.evaluate_hypotheses = fake
    # no `with`: the lifespan (model loading) does not run
    return TestClient(server.app)


class JevRoute(unittest.TestCase):
    def test_ok_reply_echoes_identity(self):
        for path in ("/jev", "/ws/operator"):
            with self.subTest(path=path), client().websocket_connect(path) as ws:
                ws.send_json(REQ)
                r = ws.receive_json()
                self.assertEqual((r["status"], r["candidateId"]), ("ok", "hold"))
                for k in ("sessionId", "temporalEpoch", "connectionId", "requestId", "observationStep"):
                    self.assertEqual(r[k], REQ[k])

    def test_shadow_reply_is_marked_shadow(self):
        with client(shadow=True).websocket_connect("/jev") as ws:
            ws.send_json(REQ)
            self.assertEqual(ws.receive_json()["status"], "shadow")

    def test_model_failure_is_an_error_envelope(self):
        with client(fail=True).websocket_connect("/jev") as ws:
            ws.send_json(REQ)
            r = ws.receive_json()
        self.assertEqual((r["status"], r["requestId"]), ("error", "r1"))
        self.assertNotIn("candidateId", r)


if __name__ == "__main__":
    unittest.main()
