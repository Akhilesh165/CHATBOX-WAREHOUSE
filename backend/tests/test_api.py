from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_endpoints():
    # Test both /health and /api/health
    for path in ["/health", "/api/health"]:
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "Warehouse" in data["app"]
        assert "database" in data

def test_schema_endpoint():
    response = client.get("/api/schema")
    assert response.status_code == 200
    data = response.json()
    assert "dbo.ZWMS_INVENTORY" in data["tables"]
    assert "dbo.ZWMS_BIN_MASTER" in data["tables"]
    assert "dbo.ZWMS_MATERIAL_MASTER" in data["tables"]
    assert "dbo.vw_WMS_InventoryEnriched" in data["tables"]

def test_feedback_endpoint():
    payload = {
        "conversation_id": "test-session-123",
        "rating": "up",
        "comment": "Accurate response and fast!",
        "sql": "SELECT TOP 5 Material FROM dbo.ZWMS_INVENTORY"
    }
    response = client.post("/api/feedback", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "recorded"

def test_chat_utilization_and_occupancy_query():
    questions = [
        "What is the overall warehouse bin utilization percentage right now, based on total occupied volume versus total bin capacity?",
        "What is our current warehouse space utilization rate across all bins?",
        "How much total bin volume is currently occupied compared to total available capacity",
        "Give me the real-time overall bin fill percentage for the facility",
        "How full is the warehouse right now in terms of bin space?"
    ]
    for q in questions:
        response = client.post("/api/chat", json={"message": q})
        assert response.status_code == 200
        data = response.json()
        assert "77.45%" in data["answer"] or "Volume Utilization" in data["answer"]
        assert len(data["data"]) > 0
        assert "VolumeUtilizationPct" in data["data"][0]
        assert "BinOccupancyPct" in data["data"][0]


def test_chat_empty_bins_query():
    payload = {
        "message": "Show me empty bins available for immediate put-away"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) > 0
    assert "BinLocation" in data["data"][0]

def test_chat_consolidation_query():
    payload = {
        "message": "Which materials are stored across multiple bins and can be consolidated?"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) > 0
    assert "ActiveBinCount" in data["data"][0]

def test_chat_difference_query():
    payload = {
        "message": "Find materials with highest quantity difference between ZWMS and ZWS"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) > 0
    assert "QuantityDifference" in data["data"][0]

