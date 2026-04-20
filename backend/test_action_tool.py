from app.database import AsyncSessionLocal
from app.models.tool import Tool
from app.core.security import decrypt_value
from sqlalchemy import select
import subprocess
import json
import time

async def test_action_tool():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tool).where(Tool.source == 'maton'))
        tools = result.scalars().all()
        if not tools:
            print('No Maton tools')
            return
        t = tools[0]
        config = dict(t.config)
        raw_key = config.get('api_token', '')
        decrypted = decrypt_value(raw_key)
        app = config.get('app', 'google-sheet')

    cmd = ['npx.cmd', '-y', '@maton/mcp', app, '--agent', f'--api-key={decrypted}']

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        shell=False,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    # Initialize and call create_spreadsheet directly (skip handshake)
    time.sleep(2)

    # Call create_spreadsheet directly
    create_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "google-sheet_create_spreadsheet",
            "arguments": {
                "title": "Test Spreadsheet from OCIN",
                "sheets": [{
                    "title": "Sheet 1",
                    "rows": [
                        {"cells": [
                            {"user_entered_value": "A1"},
                            {"user_entered_value": "B1"}
                        ]
                    }]
                }]
            }
        }
    })

    print(f'Calling google-sheet_create_spreadsheet...')

    out, err = proc.communicate(create_req + '\n', timeout=15)

    print('=== STDOUT (first 500 chars) ===')
    print(out[:500])
    print('=== STDERR ===')
    print(err)
    print(f'=== RETURN CODE: {proc.returncode} ===')

if __name__ == '__main__':
    import asyncio
    asyncio.run(test_action_tool())
