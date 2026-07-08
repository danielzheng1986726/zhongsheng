import os
import unittest

os.environ.setdefault("SECONDME_CLIENT_ID", "test-client")
os.environ.setdefault("SECONDME_CLIENT_SECRET", "test-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("ZHIHU_ACCESS_KEY", "test-zhihu-key")
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["AI_BUILDER_TOKEN"] = ""

from fastapi.testclient import TestClient

from app import app


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_mcp_tools_list(self):
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], 1)
        tools = body["result"]["tools"]
        self.assertTrue(any(tool["name"] == "zhongsheng_search" for tool in tools))

    def test_me_endpoint_without_cookie(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"logged_in": False})


if __name__ == "__main__":
    unittest.main()
