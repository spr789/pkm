import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine(
        'postgresql+asyncpg://postgres:123@localhost:5432/postgres', 
        isolation_level='AUTOCOMMIT'
    )
    async with engine.connect() as conn:
        try:
            await conn.execute(text('CREATE DATABASE pkm;'))
            print("Database 'pkm' created successfully.")
        except Exception as e:
            if "already exists" in str(e):
                print("Database 'pkm' already exists.")
            else:
                raise e
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
