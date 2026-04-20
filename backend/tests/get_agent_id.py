#!/usr/bin/env python3
"""Get agent ID for testing."""
import httpx

# Login
response = httpx.post('http://localhost:8000/api/v1/auth/login',
                     json={'email': 'alvaroantonblanco@gmail.com', 'password': 'temporal'})
response.raise_for_status()
auth_data = response.json()
token = auth_data['access_token']
print(f'Got token: {token[:50]}...')

# Get agents (no trailing slash to avoid redirect)
agents_response = httpx.get('http://localhost:8000/api/v1/agents',
                            headers={'Authorization': f'Bearer {token}'})
agents_response.raise_for_status()
agents = agents_response.json()

print(f'Found {len(agents)} agents:')
for agent in agents:
    print(f"  ID: {agent['id']}, Name: {agent['name']}, Model: {agent['model_provider']}:{agent['model_id']}")
    print(f"  OCIN_AGENT_ID={agent['id']}")
