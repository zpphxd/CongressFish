#!/usr/bin/env python3
"""End-to-end test of the simulation API."""

import sys
sys.path.insert(0, '/Users/zachpowers/CongressFish')

import asyncio
import json
from fastapi.testclient import TestClient
from backend.api.simulation_api import app

client = TestClient(app)

def test_simulation_flow():
    """Test full simulation flow: start → poll → get results."""

    print("1. Starting simulation...")
    response = client.post("/api/simulation/start", json={
        "query": "A bill to expand renewable energy investment and create green jobs",
        "scope": "house"
    })

    if response.status_code != 200:
        print(f"✗ Failed to start simulation: {response.status_code}")
        print(response.json())
        return False

    data = response.json()
    sim_id = data["simulation_id"]
    print(f"✓ Started simulation: {sim_id}")
    print(f"  Poll URL: {data['poll_url']}")

    # Give the background task a moment to start
    import time
    time.sleep(0.5)

    print(f"\n2. Checking status...")
    response = client.get(f"/api/simulation/{sim_id}/status")

    if response.status_code == 404:
        print(f"✗ Simulation not found in active_simulations")
        print(f"  Response: {response.json()}")
        return False

    if response.status_code != 200:
        print(f"✗ Status check failed: {response.status_code}")
        print(response.json())
        return False

    status_data = response.json()
    print(f"✓ Status check passed")
    print(f"  Status: {status_data['status']}")
    print(f"  Progress: {status_data['progress']}")

    # Poll until complete (max 30 seconds)
    print(f"\n3. Polling for completion...")
    for attempt in range(30):
        response = client.get(f"/api/simulation/{sim_id}/status")
        status_data = response.json()

        print(f"  [{attempt+1}] Status: {status_data['status']}, Progress: {status_data['progress']}%")

        if status_data['status'] == 'complete':
            print(f"✓ Simulation complete!")
            break
        elif status_data['status'] == 'error':
            print(f"✗ Simulation error: {status_data.get('error')}")
            return False

        time.sleep(1)
    else:
        print(f"✗ Simulation timed out after 30 seconds")
        return False

    print(f"\n4. Getting results...")
    response = client.get(f"/api/simulation/{sim_id}/results")

    if response.status_code != 200:
        print(f"✗ Failed to get results: {response.status_code}")
        print(response.json())
        return False

    results = response.json()
    print(f"✓ Got results")
    print(f"  Bill: {results.get('bill_title')}")
    print(f"  Final Status: {results.get('final_status')}")
    print(f"  Passed: {results.get('passed')}")
    print(f"  Vote Results: YES={results['vote_results']['yes']}, NO={results['vote_results']['no']}, ABSTAIN={results['vote_results']['abstain']}")
    print(f"  Stages: {results.get('total_stages', len(results.get('stage_results', [])))}")

    # Print stage results
    for stage in results.get('stage_results', []):
        print(f"    - {stage['stage']}: {'✓ PASSED' if stage['passed'] else '✗ FAILED'} ({stage['yes_votes']} YES, {stage['no_votes']} NO)")

    return True

if __name__ == '__main__':
    print("🚀 CongressFish E2E Test\n")
    success = test_simulation_flow()

    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed")
        sys.exit(1)
