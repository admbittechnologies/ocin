import sys
sys.path.insert(0, '/app')
import asyncio
import requests

BASE = "http://localhost:8000/api/v1"

# Login
r = requests.post(f"{BASE}/auth/login", json={"email": "user@test.com", "password": "test123456"})
data = r.json()
token = data.get("access_token")
print(f"LOGIN: {r.status_code} token={'ok' if token else 'FAILED'}")
if not token:
    print(data)
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}

# Get first agent
r = requests.get(f"{BASE}/agents", headers=headers)
agents = r.json()
agent_id = agents[0]["id"] if agents else None
print(f"AGENT: {agent_id}")

# Get first thread
r = requests.get(f"{BASE}/chat/threads", headers=headers)
threads = r.json()
thread_id = threads[0]["id"] if threads else None
print(f"THREAD: {thread_id}")

# Send message
payload = {
    "agent_id": agent_id,
    "message": "Create a Google Sheet called OCIN_Demo with 5 rows of sample data using Maton"
}
if thread_id:
    payload["thread_id"] = thread_id

r = requests.post(f"{BASE}/chat/send", json=payload, headers=headers)
result = r.json()
run_id = result.get("run_id") or result.get("id")
print(f"RUN_ID: {run_id}")
print(f"SEND: {r.status_code}")

# Wait for completion
import time
print("Waiting 90 seconds for run to complete...")
time.sleep(90)

# Get run details
if run_id:
    r = requests.get(f"{BASE}/runs/{run_id}", headers=headers)
    run = r.json()
    print(f"STATUS: {run.get('status')}")
    print(f"OUTPUT: {run.get('output', '')[:500]}")
    print(f"ERROR: {run.get('error')}")
