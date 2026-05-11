import os
import secrets
import asyncpg
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Body, Header, HTTPException
from cryptography.fernet import Fernet


# 1. Настройки и конфигурация
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
STORAGE_DIR = Path("pasted_texts")
MAX_PASTE_SIZE_BYTES = 10 * 1024 * 1024  # Лимит 10 Мб


# 2. Жизненный цикл приложения (Lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise ValueError("ENCRYPTION_KEY не найден в .env!")
    
    app.state.fernet = Fernet(key)

    # Действия при запуске: создаем папку и подключаемся к БД
    STORAGE_DIR.mkdir(exist_ok=True)
    app.state.pool = await asyncpg.create_pool(DATABASE_URL)
    
    async with app.state.pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pastes(
                id varchar(12) PRIMARY KEY,
                s3_key varchar(255),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                delete_at TIMESTAMPTZ
            );
        """)
    yield
    # Действия при остановке: закрываем пул соединений
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)


# 3. Эндпоинт для создания записи (POST)
@app.post("/pastes")
async def create_paste(
    request: Request, 
    text: str = Body(..., media_type="text/plain"),
    content_length: int = Header(0, alias="Content-Length"),
    ttl_mins: int = 60  # Срок жизни по умолчанию — 1 час
):
    # Проверка размера контента
    if content_length > MAX_PASTE_SIZE_BYTES or len(text.encode()) > MAX_PASTE_SIZE_BYTES:
         raise HTTPException(status_code=413, detail="Текст слишком большой")

    # Генерация ID и сохранение файла локально
    paste_id = secrets.token_urlsafe(8)
    file_path = STORAGE_DIR / f"{paste_id}.txt"

    encrypted_content = request.app.state.fernet.encrypt(text.encode())
    with open(file_path, "wb") as f:
        f.write(encrypted_content)

    # Сохранение метаданных в БД с расчетом TTL
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pastes (id, s3_key, delete_at) 
            VALUES ($1, $2, NOW() + $3 * INTERVAL '1 minute')
            """,
            paste_id, str(file_path), ttl_mins
        )

    return {
        "id": paste_id, 
        "url": f"http://localhost:8000/pastes/{paste_id}",
        "expires_in_mins": ttl_mins
    }


# 4. Эндпоинт для получения записи (GET)
@app.get("/pastes/{paste_id}")
async def get_paste(request: Request, paste_id: str):
    async with request.app.state.pool.acquire() as conn:
        # Ищем запись, которая еще не просрочена
        row = await conn.fetchrow(
            "SELECT s3_key FROM pastes WHERE id = $1 AND delete_at > NOW()", 
            paste_id
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="Текст не найден или срок его жизни истек")

    try:
        with open(row['s3_key'], "rb") as f:
            decrypted_content = request.app.state.fernet.decrypt(f.read()).decode('utf-8')
            return {"id": paste_id, "content": decrypted_content}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл физически удален с сервера")
