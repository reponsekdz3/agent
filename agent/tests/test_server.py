import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nova_apex.server.app import app

def test_api():
    client = TestClient(app)

    # 1. Test status
    res = client.get("/api/status")
    assert res.status_code == 200
    print("✓ GET /api/status passed:", res.json())

    # 2. Test telemetry
    res = client.get("/api/telemetry")
    assert res.status_code == 200
    print("✓ GET /api/telemetry passed:", res.json()["os"])

    # 3. Test vault
    res = client.get("/api/vault")
    assert res.status_code == 200
    print("✓ GET /api/vault passed: found", len(res.json()["created_accounts"]), "saved accounts")

    # 4. Test UI index serving
    res = client.get("/")
    assert res.status_code == 200
    assert "NOVA-APEX" in res.text
    print("✓ GET / (Mission Control UI) served successfully!")

    print("\n🎉 Mission Control API and Web Interface verified 100%!")

if __name__ == "__main__":
    test_api()
