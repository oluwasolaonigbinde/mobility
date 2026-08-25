"""Migration 0047: source-link authority is append-only and downgrade-safe."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_LINK_REVISION = "0046_retargeting_sources"


def test_link_empty_roundtrip_append_only_and_populated_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_verify() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                ids = (
                    (
                        await connection.execute(
                            text(
                                "WITH u AS (INSERT INTO users "
                                "(email,password_hash,full_name,role,status) VALUES "
                                "('link-migration@example.com','hash','Link Migration',"
                                "'advertiser','active') RETURNING id), "
                                "o AS (INSERT INTO advertiser_organizations "
                                "(name,currency,status) VALUES "
                                "('Link Migration Org','NGN','active') RETURNING id), "
                                "c AS (INSERT INTO campaigns "
                            "(organization_id,created_by_user_id,name,status,"
                            "currency,metadata) "
                                "SELECT o.id,u.id,'Link Campaign','draft','NGN','{}'::jsonb "
                                "FROM o,u RETURNING id,organization_id,created_by_user_id), "
                                "z AS (INSERT INTO campaign_zones "
                                "(campaign_id,created_by_user_id,name,zone_type,geom,metadata) "
                                "SELECT c.id,c.created_by_user_id,'Target','target',"
                                "ST_Multi(ST_GeomFromText("
                                "'POLYGON((3 6,3.1 6,3.1 6.1,3 6.1,3 6))',4326)),"
                                "'{}'::jsonb FROM c RETURNING id,campaign_id), "
                                "s AS (INSERT INTO retargeting_sources "
                                "(organization_id,source_type,snapshot,snapshot_sha256,expires_at) "
                                "SELECT o.id,'manual-insight','{}'::jsonb,repeat('a',64),"
                                "now()+interval '30 days' FROM o RETURNING id,organization_id) "
                            "SELECT u.id AS user_id,o.id AS organization_id,"
                            "c.id AS campaign_id,"
                                "z.id AS zone_id,s.id AS source_id FROM u,o,c,z,s"
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                link_id = await connection.scalar(
                    text(
                        "INSERT INTO retargeting_source_links "
                        "(organization_id,source_id,campaign_id,zone_id,start_at,end_at,"
                        "source_fingerprint,campaign_fingerprint,zone_fingerprint,snapshot,"
                        "snapshot_sha256) VALUES (:organization_id,:source_id,:campaign_id,"
                        ":zone_id,now(),now()+interval '1 day',repeat('b',64),repeat('c',64),"
                        "repeat('d',64),'{}'::jsonb,repeat('e',64)) RETURNING id"
                    ),
                    ids,
                )
                await connection.execute(
                    text(
                        "INSERT INTO retargeting_source_link_events "
                        "(link_id,sequence_number,event_type,snapshot,snapshot_sha256) "
                        "VALUES (:link_id,1,'created','{}'::jsonb,repeat('e',64))"
                    ),
                    {"link_id": link_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO retargeting_source_link_idempotency "
                        "(actor_user_id,operation,idempotency_key,request_fingerprint,link_id) "
                        "VALUES (:user_id,'create','migration-link',repeat('f',64),:link_id)"
                    ),
                    {"user_id": ids["user_id"], "link_id": link_id},
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text("DELETE FROM retargeting_source_link_events WHERE link_id=:link_id"),
                        {"link_id": link_id},
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_LINK_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_LINK_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_verify())
        with pytest.raises(RuntimeError, match="Refusing to drop populated"):
            downgrade_to(migration_url, PRE_LINK_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
