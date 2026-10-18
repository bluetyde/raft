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


class Boundaries(unittest.TestCase):
    """The limits found by the whole-repo review: who may connect and what one request may cost."""

    def test_the_origin_check(self):
        for ok in (None, "http://localhost:5187", "http://127.0.0.1:5188", "https://localhost", "http://[::1]:5187"):
            self.assertTrue(server.origin_allowed(ok), ok)
        for bad in ("https://evil.example", "http://localhost.evil.example", "http://127.0.0.1.evil.example:5187", "http://192.168.1.5:5187", "null", "file://"):
            self.assertFalse(server.origin_allowed(bad), bad)
        import os
        os.environ["JEV_ALLOWED_ORIGINS"] = "https://class.example, http://10.0.0.7:5187"
        try:
            self.assertTrue(server.origin_allowed("https://class.example"))
            self.assertTrue(server.origin_allowed("http://10.0.0.7:5187"))
            self.assertFalse(server.origin_allowed("https://other.example"))
        finally:
            del os.environ["JEV_ALLOWED_ORIGINS"]

    def test_a_page_from_another_origin_is_refused_before_it_is_accepted(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with client().websocket_connect("/jev", headers={"origin": "https://evil.example"}) as ws:
                ws.send_json(REQ)
                ws.receive_json()
        with client().websocket_connect("/jev", headers={"origin": "http://localhost:5187"}) as ws:     # a local page is served
            ws.send_json(REQ)
            self.assertEqual(ws.receive_json()["status"], "ok")

    def test_a_request_outside_the_bounds_is_an_error_not_an_inference(self):
        calls = []
        c = client()
        inner = server.evaluate_hypotheses
        server.evaluate_hypotheses = lambda p, cands: calls.append(1) or inner(p, cands)
        bad = [
            {**REQ, "premise": "x" * (server.MAX_PREMISE_CHARS + 1)},
            {**REQ, "premise": ""},
            {**REQ, "premise": 5},
            {**REQ, "candidates": [{"id": str(i), "text": "t"} for i in range(server.MAX_CANDIDATES + 1)]},
            {**REQ, "candidates": []},
            {**REQ, "candidates": "hold"},
            {**REQ, "candidates": [{"id": "a", "text": "x" * (server.MAX_CANDIDATE_CHARS + 1)}]},
            {**REQ, "candidates": [{"id": 1, "text": "t"}]},
            {**REQ, "candidates": [{"id": "a"}]},
            {**REQ, "candidates": ["hold"]},
        ]
        with c.websocket_connect("/jev") as ws:
            for msg in bad:
                ws.send_json(msg)
                r = ws.receive_json()
                self.assertEqual((r["status"], r["errorCode"]), ("error", "INVALID_PAYLOAD"), str(msg)[:80])
            ws.send_text("[1, 2]")                                                # valid JSON that is not an object
            self.assertEqual(ws.receive_json()["errorCode"], "INVALID_PAYLOAD")
            ws.send_text("x" * (server.MAX_MESSAGE_CHARS + 1))                    # over the size limit
            self.assertEqual(ws.receive_json()["errorCode"], "INVALID_PAYLOAD")
            ws.send_json({**REQ, "candidates": [{"id": str(i), "text": "t"} for i in range(server.MAX_CANDIDATES)]})     # at the limit: served
            self.assertEqual(ws.receive_json()["status"], "ok")
        self.assertEqual(len(calls), 1)

    def test_the_server_listens_on_this_machine_by_default(self):
        import inspect
        src = inspect.getsource(server)
        self.assertNotIn('host="0.0.0.0"', src)
        self.assertIn('os.environ.get("JEV_HOST", "127.0.0.1")', src)


if __name__ == "__main__":
    unittest.main()
