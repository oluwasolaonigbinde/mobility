import asyncio

from sqlalchemy import func, select
from test_fraud_assessments import build_graph, create_flag

from app.models.notification import Notification
from app.models.trip_analytics import FraudFlag
from app.services.notifications import create_fraud_hold_raised_notice


def test_notice_dedupe_is_stable_and_payload_is_bounded(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, "notice-dedupe")
    flag = create_flag(db_sessionmaker, graph)

    async def run() -> tuple[Notification, int]:
        async with db_sessionmaker() as session:
            attached = await session.get(FraudFlag, flag.id)
            first = await create_fraud_hold_raised_notice(session, attached)
            second = await create_fraud_hold_raised_notice(session, attached)
            await session.commit()
            count = int(await session.scalar(select(func.count()).select_from(Notification)) or 0)
            assert first.id == second.id
            return first, count

    notice, count = asyncio.run(run())
    assert count == 1
    assert notice.payload == {
        "fraud_flag_id": str(flag.id),
        "trip_session_id": str(graph.trip.id),
    }
