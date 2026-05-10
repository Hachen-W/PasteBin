import os
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def cleanup():
    print("--- Запуск очистки просроченных паст ---")

    conn = await asyncpg.connect(DATABASE_URL)

    expired_pastes = await conn.fetch(
        "SELECT id, s3_key FROM pastes WHERE delete_at < NOW()"
    )
    
    if not expired_pastes:
        print("Просроченных записей не найдено. Отдыхаем.")
        await conn.close()
        return

    print(f"Найдено просроченных записей: {len(expired_pastes)}")

    for record in expired_pastes:
        paste_id = record['id']
        file_path = record['s3_key']

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[{paste_id}] Файл удален: {file_path}")
            else:
                print(f"[{paste_id}] Файл уже отсутствует на диске.")
        except Exception as e:
            print(f"[{paste_id}] Ошибка при удалении файла: {e}")

        await conn.execute("DELETE FROM pastes WHERE id = $1", paste_id)
        print(f"[{paste_id}] Запись удалена из БД.")

    await conn.close()
    print("--- Очистка завершена успешно ---")


if __name__ == "__main__":
    asyncio.run(cleanup())
