import httpx

client = httpx.Client()

# 1. High confidence (0.96), LOW risk -> should auto-approve
res1 = client.post("http://localhost:8002/api/patches", json={
    "entity_id": "HDFC_TOP_100",
    "attribute": "expense_ratio",
    "canonical_value": "1.20%",
    "corrected_value": "1.22%",
    "confidence": 0.96,
    "approved": False,
    "provenance": {"source": "Verified Audit"}
})
print("Patch 1 (0.96):", res1.json())

# 2. Moderate confidence (0.82), LOW risk -> should remain in review
res2 = client.post("http://localhost:8002/api/patches", json={
    "entity_id": "SBI_BLUECHIP",
    "attribute": "exit_load",
    "canonical_value": "1.00%",
    "corrected_value": "0.90%",
    "confidence": 0.82,
    "approved": False,
    "provenance": {"source": "User Feedback"}
})
print("Patch 2 (0.82):", res2.json())

# 3. High confidence (0.98), HIGH risk (>20% shift) -> should remain in review
res3 = client.post("http://localhost:8002/api/patches", json={
    "entity_id": "AXIS_GROWTH",
    "attribute": "nav",
    "canonical_value": "50.0",
    "corrected_value": "85.0",
    "confidence": 0.98,
    "approved": False,
    "provenance": {"source": "Analyst Note"}
})
print("Patch 3 (0.98 HIGH risk):", res3.json())
