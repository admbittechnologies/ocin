import asyncio
import sys
sys.path.insert(0, '/app')

async def get_key():
    from app.database import async_session_maker
    from app.models.tool import Tool
    from app.core.security import decrypt_value
    from sqlalchemy import select

    async with async_session_maker() as db:
        result = await db.execute(select(Tool).where(Tool.source == 'maton'))
        tools = result.scalars().all()
        for t in tools:
            raw = t.config.get('api_key') or t.config.get('api_token', '')
            try:
                key = decrypt_value(raw)
                print('MATON_KEY=' + key)
                print('APP=' + t.config.get('app'))
            except Exception as e:
                print('ERROR: ' + str(e))

    asyncio.run(get_key())
