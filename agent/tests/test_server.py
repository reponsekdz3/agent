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

    # 5. Test Workspace Tree
    res = client.get("/api/manage/workspace/tree")
    assert res.status_code == 200
    print("✓ GET /api/manage/workspace/tree passed: found", len(res.json()["items"]), "items")

    # 6. Test OS Windows
    res = client.get("/api/manage/windows")
    assert res.status_code == 200
    print("✓ GET /api/manage/windows passed: found", len(res.json()["windows"]), "windows")

    # 7. Test Processes
    res = client.get("/api/manage/processes")
    assert res.status_code == 200
    print("✓ GET /api/manage/processes passed: found", len(res.json()["processes"]), "processes")

    # 8. Test Mobile Info & OTP
    res = client.get("/api/manage/mobile/info")
    assert res.status_code == 200
    print("✓ GET /api/manage/mobile/info passed: connected =", res.json()["connected"])

    res = client.get("/api/manage/mobile/otp")
    assert res.status_code == 200
    print("✓ GET /api/manage/mobile/otp passed")

    # 9. Test Vault Credential CRUD
    res = client.post("/api/manage/vault/credential", json={
        "service": "test_service.org",
        "username": "test_admin",
        "secret": "super_secret_key_123"
    })
    assert res.status_code == 200
    assert res.json()["success"] is True
    print("✓ POST /api/manage/vault/credential passed")

    res = client.delete("/api/manage/vault/credential?service=test_service.org&username=test_admin")
    assert res.status_code == 200
    assert res.json()["success"] is True
    print("✓ DELETE /api/manage/vault/credential passed")

    print("\n🎉 Mission Control API & Omni Management Hub verified 100%!")

if __name__ == "__main__":
    test_api()
