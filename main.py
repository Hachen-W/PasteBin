import os
import secrets
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Body, Header, HTTPException
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
STORAGE_DIR = Path("pasted_texts")

@asynccontextmanager
async def lifespan(app: FastAPI):
    '''Выполняется при запуске: создаем пул подключений'''
    STORAGE_DIR.mkdir(exist_ok=True)
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


@app.post("/pastes")
async def create_paste(
    request: Request, 
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
    file_path = STORAGE_DIR / f"{paste_id}.txt"

    # Сохраняем файл локально
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Записываем в базу путь к файлу
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pastes (id, s3_key) VALUES ($1, $2)",
            paste_id, str(file_path)
        )

    return {"id": paste_id, "url": f"http://localhost:8000/pastes/{paste_id}"}


@app.get("/pastes/{paste_id}")
async def get_paste(request: Request, paste_id: str):
    pool = request.app.state.pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT s3_key FROM pastes WHERE id = $1", paste_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Текст не найден")

    file_path = row['s3_key']

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"id": paste_id, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл был удален с сервера")
