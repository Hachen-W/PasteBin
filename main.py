import secrets
from fastapi import FastAPI, HTTPException, Header, Body


app = FastAPI()

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
