import sys
sys.path.insert(0, 'backend')
import asyncio
from app.database import fetch, fetchrow

async def check():
    r = await fetchrow("SELECT count(*) FROM chunks WHERE document_id = '46e83c6b-b945-449c-82e7-5ce1fa89098f'")
    print('Chunks for 46e83c6b:', r['count'])
    doc = await fetchrow("SELECT id, original_filename, ingestion_status, ingestion_error, total_pages, created_at, updated_at FROM documents WHERE id = '46e83c6b-b945-449c-82e7-5ce1fa89098f'")
    print('Doc 46e83c6b:', dict(doc))

asyncio.run(check())
