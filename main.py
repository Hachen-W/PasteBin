import os
import secrets
import asyncpg
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Body, Header, HTTPException

# Загружаем настройки
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
STORAGE_DIR = Path("pasted_texts")
MAX_PASTE_SIZE_BYTES = 10 * 1024 * 1024 


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте: создаем папку и пул БД
    STORAGE_DIR.mkdir(exist_ok=True)
    app.state.pool = await asyncpg.create_pool(DATABASE_URL)
    async with app.state.pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pastes(
                id varchar(12) PRIMARY KEY,
                s3_key varchar(255),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    yield
    # При выключении: закрываем БД
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)


@app.post("/pastes")
async def create_paste(
    request: Request, 
    text: str = Body(..., media_type="text/plain"),
    content_length: int = Header(0, alias="Content-Length")
):
    # Проверка лимитов
    if content_length > MAX_PASTE_SIZE_BYTES or len(text.encode()) > MAX_PASTE_SIZE_BYTES:
         raise HTTPException(status_code=413, detail="Текст слишком большой (макс 10 Мб)")

    # Генерация ID и сохранение файла
    paste_id = secrets.token_urlsafe(8)
    file_path = STORAGE_DIR / f"{paste_id}.txt"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Запись в БД
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pastes (id, s3_key) VALUES ($1, $2)",
            paste_id, str(file_path)
        )

    return {"id": paste_id, "url": f"http://localhost:8000/pastes/{paste_id}"}


@app.get("/pastes/{paste_id}")
async def get_paste(request: Request, paste_id: str):
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT s3_key FROM pastes WHERE id = $1", paste_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    try:
        with open(row['s3_key'], "r", encoding="utf-8") as f:
            return {"id": paste_id, "content": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл на диске не найден")
