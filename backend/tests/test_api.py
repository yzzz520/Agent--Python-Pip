"""API contract tests. They run against the real artifacts in the repository."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_healthz_after_seed(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["cases"] >= 40
    assert body["reports"] >= 60


def test_list_cases_is_paginated(client: TestClient) -> None:
    response = client.get("/api/cases", params={"limit": 5, "offset": 0})
    assert response.status_code == 200

    page = response.json()
    assert len(page) == 5
    assert page[0]["id"] == "000"


def test_filter_by_failure_type(client: TestClient) -> None:
    response = client.get("/api/cases", params={"failure_type": "no_failure", "limit": 100})
    assert response.status_code == 200

    cases = response.json()
    assert cases
    assert all("no_failure" in case["failure_types"].values() for case in cases)


def test_case_detail_exposes_three_approaches(client: TestClient) -> None:
    response = client.get("/api/cases/8")  # normalized to 008
    assert response.status_code == 200

    body = response.json()
    assert body["id"] == "008"
    assert {report["approach"] for report in body["reports"]} == {"rule", "llm", "agent"}
    assert body["label"]["failure_type"] == "python_version_mismatch"
    assert body["latest_run"]["returncode"] == 1
    assert "sphinx" in body["requirements_text"]


def test_missing_case_is_404(client: TestClient) -> None:
    assert client.get("/api/cases/999").status_code == 404
    assert client.get("/api/cases/not-a-number").status_code == 404


def test_raw_log_and_patch_endpoints(client: TestClient) -> None:
    log = client.get("/api/cases/000/log", params={"max_chars": 500})
    assert log.status_code == 200
    assert log.headers["content-type"].startswith("text/plain")
    assert "PIP RUN METADATA" in log.text or "pip" in log.text.lower()

    patch = client.get("/api/cases/000/patch")
    assert patch.status_code == 200
    assert "numpy==1.26.4" in patch.text


def test_stats_compares_three_approaches(client: TestClient) -> None:
    body = client.get("/api/stats").json()

    assert body["case_count"] >= 40
    assert body["labeled_count"] >= 10
    assert [item["approach"] for item in body["by_approach"]] == ["rule", "llm", "agent"]
    assert all(item["evaluated"] >= 10 for item in body["by_approach"])


def test_label_upsert_roundtrip(client: TestClient) -> None:
    payload = {
        "failure_type": "no_failure",
        "root_cause_hint": "created by the API test",
        "reviewed": True,
        "reviewed_by": "pytest",
    }
    created = client.put("/api/labels/001", json=payload)
    assert created.status_code == 200
    assert created.json()["reviewed_by"] == "pytest"

    fetched = client.get("/api/labels/001")
    assert fetched.status_code == 200
    assert fetched.json()["failure_type"] == "no_failure"


def test_rule_job_runs_and_persists(client: TestClient) -> None:
    created = client.post("/api/cases/008/jobs", json={"kind": "rule"})
    assert created.status_code == 202

    job_id = created.json()["id"]
    status = "queued"
    for _ in range(50):
        body = client.get(f"/api/jobs/{job_id}").json()
        status = body["status"]
        if status in {"succeeded", "failed"}:
            break
        time.sleep(0.1)

    assert status == "succeeded", body
    assert body["result"]["failure_type"] == "python_version_mismatch"
