import os
import secrets
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Body, Header, HTTPException
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

@asynccontextmanager
async def lifespan(app: FastAPI):
    '''Выполняется при запуске: создаем пул подключений'''
    app.state.pool = await asyncpg.create_pool(DATABASE_URL)

    async with app.state.pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pastes(
                id varchar(8) PRIMARY KEY,
                s3_key varchar(255),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

    yield

    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

MAX_PASTE_SIZE_BYTES = 10 * 1024 * 1024


app.post("/pastes")
async def create_paste(
            text: str = Body(..., media_type="text/plain"), 
            content_length: int = Header(0, alias="Content-Length")
        ):
    # Быстрая проверка по заголовку
    if content_length > MAX_PASTE_SIZE_BYTES:
         raise HTTPException(status_code=413, detail="Превышен лимит в 10 Мб")
    
    # # Точная проверка реального размера текста (на случай, если заголовок подделан)
    text_bytes = text.encode('utf-8')
    if len(text_bytes) > MAX_PASTE_SIZE_BYTES:
         raise HTTPException(status_code=413, detail="Превышен лимит в 10 Мб")

    paste_id = secrets.token_urlsafe(6)
    s3_key = f"pastes/{paste_id}.txt"

    try:
        # Загружаем текст в Amazon S3
        pass 
        # Сохраняем метаданные в PostgreSQL
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ошибка сохранения текста")

    return {
        "id": paste_id,
        "url": f"https://yourdomain.com/{paste_id}"
    }
