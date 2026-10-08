"""Deploy afya schema to local Postgres. Run: uv run python examples/deploy_schema.py [dsn]
Default DSN: postgresql://localhost/afya (local Postgres.app; database 'afya' must exist).
"""
import asyncio
import sys

from afya.persistence.postgres_store import PostgresStore


async def main() -> None:
	dsn = sys.argv[1] if len(sys.argv) > 1 else 'postgresql://localhost/afya'
	store = PostgresStore(dsn)
	n = await store.deploy()
	stats = await store.stats()
	await store.close()
	print(f'deployed {n} statements to {dsn.split("@")[-1]}: {stats.model_dump(mode="json")}')


if __name__ == '__main__':
	asyncio.run(main())
