import asyncio
from datetime import datetime
from importlib import util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.equipment_request import EquipmentRequest
from app.models.equipment_request_range import EquipmentRequestRange
from app.services.equipment_request_service import (
    approve_equipment_request,
    check_equipment_ranges_overlap,
    create_equipment_request,
    decline_equipment_request,
    record_equipment_request_dm_result,
    record_equipment_request_review_message,
    record_equipment_request_topic_post_result,
    render_equipment_request_review,
    render_equipment_request_status,
    render_equipment_topic_post,
    update_equipment_request_field,
)

UTC = ZoneInfo("UTC")


def aware_datetime(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


class EquipmentRequestPersistenceTests(TestCase):
    def test_default_submitted_status(self) -> None:
        status_column = EquipmentRequest.__table__.c.status

        self.assertIsNotNone(status_column.default)
        self.assertEqual(status_column.default.arg, "submitted")
        self.assertIsNotNone(status_column.server_default)
        self.assertEqual(status_column.server_default.arg.text.strip("'"), "submitted")

    def test_persists_default_and_nullable_fields_at_database_boundary(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username=None,
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments=None,
                    review_chat_id=-1001234567890,
                    review_message_id=42,
                    equipment_post_chat_id=-1001234567891,
                    equipment_post_message_id=43,
                    requester_dm_error=None,
                    equipment_post_error="topic not found",
                )
                session.add(request)
                session.flush()
                session.refresh(request)

                self.assertIsNotNone(request.id)
                self.assertEqual(request.status, "submitted")
                self.assertIsNotNone(request.submitted_at)
                self.assertIsNone(request.requester_username)
                self.assertIsNone(request.comments)
                self.assertIsNone(request.decided_at)
                self.assertEqual(request.review_chat_id, -1001234567890)
                self.assertEqual(request.review_message_id, 42)
                self.assertEqual(request.equipment_post_chat_id, -1001234567891)
                self.assertEqual(request.equipment_post_message_id, 43)
                self.assertFalse(request.requester_dm_sent)
                self.assertFalse(request.equipment_post_sent)
                self.assertIsNone(request.requester_dm_error)
                self.assertEqual(request.equipment_post_error, "topic not found")
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()


class EquipmentRequestMigrationRoundTripTests(TestCase):
    class _OperationsSpy:
        def __init__(self, ops: Operations) -> None:
            self._ops = ops
            self.create_table_calls = []
            self.create_index_calls = []
            self.drop_index_calls = []
            self.drop_table_calls = []

        def create_table(self, *args, **kwargs):
            self.create_table_calls.append((args, kwargs))
            return self._ops.create_table(*args, **kwargs)

        def create_index(self, *args, **kwargs):
            self.create_index_calls.append((args, kwargs))
            return self._ops.create_index(*args, **kwargs)

        def drop_index(self, *args, **kwargs):
            self.drop_index_calls.append((args, kwargs))
            return self._ops.drop_index(*args, **kwargs)

        def drop_table(self, *args, **kwargs):
            self.drop_table_calls.append((args, kwargs))
            return self._ops.drop_table(*args, **kwargs)

    def _load_migration_module(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "8f2d1a7c9b4e_add_equipment_requests.py"
        )
        spec = util.spec_from_file_location("equipment_request_migration", migration_path)
        assert spec is not None and spec.loader is not None
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_upgrade_then_downgrade_round_trip(self) -> None:
        module = self._load_migration_module()
        engine = create_engine("sqlite://")

        try:
            with engine.begin() as conn:
                context = MigrationContext.configure(conn)
                op_spy = self._OperationsSpy(Operations(context))
                module.op = op_spy

                module.upgrade()

                create_table_args, _ = op_spy.create_table_calls[0]
                self.assertEqual(create_table_args[0], "equipment_requests")
                create_table_columns = list(create_table_args[1:])
                create_table_map = {column.name: column for column in create_table_columns}
                self.assertTrue(create_table_map["submitted_at"].type.timezone)
                self.assertFalse(create_table_map["status"].nullable)
                self.assertEqual(create_table_map["status"].server_default.arg.text.strip("'"), "submitted")
                self.assertFalse(create_table_map["requester_dm_sent"].nullable)
                self.assertEqual(create_table_map["requester_dm_sent"].server_default.arg.text, "FALSE")
                self.assertFalse(create_table_map["equipment_post_sent"].nullable)
                self.assertEqual(create_table_map["equipment_post_sent"].server_default.arg.text, "FALSE")

                inspector = inspect(conn)
                self.assertIn("equipment_requests", inspector.get_table_names())

                columns = {
                    column["name"]: column
                    for column in inspector.get_columns("equipment_requests")
                }
                self.assertEqual(
                    set(columns),
                    {
                        "id",
                        "requester_tg_user_id",
                        "requester_username",
                        "full_name",
                        "club_name",
                        "event_name",
                        "venue",
                        "equipment_text",
                        "needed_at_text",
                        "reason_text",
                        "comments",
                        "status",
                        "admin_tg_user_id",
                        "submitted_at",
                        "decided_at",
                        "review_chat_id",
                        "review_message_id",
                        "requester_dm_sent",
                        "equipment_post_sent",
                        "requester_dm_error",
                        "equipment_post_error",
                    },
                )

                self.assertIsInstance(columns["status"]["type"], sa.String)
                self.assertEqual(columns["status"]["type"].length, 32)
                self.assertFalse(columns["status"]["nullable"])
                self.assertEqual(columns["status"]["default"].strip("'"), "submitted")

                self.assertIsInstance(columns["submitted_at"]["type"], sa.DateTime)
                self.assertFalse(columns["submitted_at"]["nullable"])
                self.assertEqual(columns["submitted_at"]["default"], "CURRENT_TIMESTAMP")

                self.assertIsInstance(columns["requester_dm_sent"]["type"], sa.Boolean)
                self.assertFalse(columns["requester_dm_sent"]["nullable"])
                self.assertEqual(columns["requester_dm_sent"]["default"], "FALSE")

                self.assertIsInstance(columns["equipment_post_sent"]["type"], sa.Boolean)
                self.assertFalse(columns["equipment_post_sent"]["nullable"])
                self.assertEqual(columns["equipment_post_sent"]["default"], "FALSE")

                self.assertEqual(
                    {index["name"] for index in inspector.get_indexes("equipment_requests")},
                    {
                        "ix_equipment_requests_requester_tg_user_id",
                        "ix_equipment_requests_review_chat_message",
                        "ix_equipment_requests_status",
                    },
                )

                module.downgrade()

                self.assertEqual(
                    [call[0][0] for call in op_spy.drop_index_calls],
                    [
                        "ix_equipment_requests_review_chat_message",
                        "ix_equipment_requests_requester_tg_user_id",
                        "ix_equipment_requests_status",
                    ],
                )
                self.assertEqual(op_spy.drop_table_calls[0][0][0], "equipment_requests")
                self.assertNotIn("equipment_requests", inspect(conn).get_table_names())
        finally:
            engine.dispose()


class EquipmentRequestServiceTests(TestCase):
    def _make_request(
        self,
        *,
        requester_username: str | None = "john",
        status: str = "submitted",
        requester_dm_sent: bool = False,
        requester_dm_error: str | None = None,
        equipment_post_sent: bool = False,
        equipment_post_error: str | None = None,
        ranges: list | None = None,
    ) -> EquipmentRequest:
        if ranges is None:
            ranges = [
                EquipmentRequestRange(
                    start_at=aware_datetime(2026, 3, 30, 18, 0),
                    end_at=aware_datetime(2026, 3, 30, 22, 0),
                )
            ]
        req = EquipmentRequest(
            requester_tg_user_id=123456789,
            requester_username=requester_username,
            full_name="John Smith",
            club_name="Jazz Club",
            event_name="Spring Jam",
            venue="Main Hall",
            equipment_text="- 2 microphones\n- drum kit",
            needed_at_text="March 30, 18:00-22:00",
            reason_text="rehearsal before performance",
            comments="need setup by 17:30",
            status=status,
            requester_dm_sent=requester_dm_sent,
            requester_dm_error=requester_dm_error,
            equipment_post_sent=equipment_post_sent,
            equipment_post_error=equipment_post_error,
            equipment_post_chat_id=-1001234567890 if status == "approved" else None,
            equipment_post_message_id=123 if status == "approved" else None,
        )
        req.ranges = ranges
        return req

    def test_format_review_message_with_username(self) -> None:
        request = self._make_request()

        self.assertEqual(
            render_equipment_request_review(request),
            (
                "New equipment request\n\n"
                "From: @john\n"
                "Full name: John Smith\n"
                "Club: Jazz Club\n"
                "Event: Spring Jam\n"
                "Venue: Main Hall\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit\n"
                "Reason: rehearsal before performance\n"
                "Comments: need setup by 17:30"
            ),
        )

    def test_format_review_message_with_no_username_fallback_preserves_requester_tg_user_id(
        self,
    ) -> None:
        request = self._make_request(requester_username=None)

        self.assertEqual(request.requester_tg_user_id, 123456789)
        self.assertEqual(
            render_equipment_request_review(request),
            (
                "New equipment request\n\n"
                "From: (no username)\n"
                "Full name: John Smith\n"
                "Club: Jazz Club\n"
                "Event: Spring Jam\n"
                "Venue: Main Hall\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit\n"
                "Reason: rehearsal before performance\n"
                "Comments: need setup by 17:30"
            ),
        )

    def test_format_approved_read_only_status_view(self) -> None:
        request = self._make_request(
            status="approved",
            requester_dm_sent=True,
            equipment_post_sent=True,
        )

        self.assertEqual(
            render_equipment_request_status(request),
            (
                "Equipment request approved\n\n"
                "From: @john\n"
                "Club: Jazz Club\n"
                "Event: Spring Jam\n"
                "Venue: Main Hall\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit\n"
                "Reason: rehearsal before performance\n"
                "Comments: need setup by 17:30\n\n"
                "DM sent: yes\n"
                "Equipment topic post sent: yes"
            ),
        )

    def test_format_declined_read_only_status_view(self) -> None:
        request = self._make_request(
            status="declined",
            requester_dm_sent=True,
        )

        self.assertEqual(
            render_equipment_request_status(request),
            (
                "Equipment request declined\n\n"
                "From: @john\n"
                "Club: Jazz Club\n"
                "Event: Spring Jam\n"
                "Venue: Main Hall\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit\n"
                "Reason: rehearsal before performance\n"
                "Comments: need setup by 17:30\n\n"
                "DM sent: yes"
            ),
        )

    def test_format_approved_read_only_status_view_with_no_username_fallback_preserves_requester_tg_user_id(
        self,
    ) -> None:
        request = self._make_request(
            requester_username=None,
            status="approved",
            requester_dm_sent=False,
            requester_dm_error="bot blocked",
            equipment_post_sent=False,
            equipment_post_error="topic not found",
        )

        self.assertEqual(request.requester_tg_user_id, 123456789)
        self.assertEqual(
            render_equipment_request_status(request),
            (
                "Equipment request approved\n\n"
                "From: (no username)\n"
                "Club: Jazz Club\n"
                "Event: Spring Jam\n"
                "Venue: Main Hall\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit\n"
                "Reason: rehearsal before performance\n"
                "Comments: need setup by 17:30\n\n"
                "DM sent: no\n"
                "DM error: bot blocked\n"
                "Equipment topic post sent: no\n"
                "Equipment post error: topic not found"
            ),
        )

    def test_format_declined_read_only_status_view_with_no_username_fallback_preserves_requester_tg_user_id(
        self,
    ) -> None:
        request = self._make_request(
            requester_username=None,
            status="declined",
            requester_dm_sent=False,
            requester_dm_error="bot blocked",
        )

        self.assertEqual(request.requester_tg_user_id, 123456789)
        self.assertEqual(
            render_equipment_request_status(request),
            (
                "Equipment request declined\n\n"
                "From: (no username)\n"
                "Club: Jazz Club\n"
                "Event: Spring Jam\n"
                "Venue: Main Hall\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit\n"
                "Reason: rehearsal before performance\n"
                "Comments: need setup by 17:30\n\n"
                "DM sent: no\n"
                "DM error: bot blocked"
            ),
        )

    def test_format_approved_members_topic_post(self) -> None:
        request = self._make_request(status="approved")

        self.assertEqual(
            render_equipment_topic_post(request),
            (
                "🎤 Approved equipment request\n\n"
                "Requested time ranges:\n"
                "- 2026-03-30 18:00 -> 2026-03-30 22:00\n"
                "Equipment:\n"
                "- 2 microphones\n"
                "- drum kit"
            ),
        )

    def test_check_equipment_ranges_overlap(self) -> None:
        # No overlap
        check_equipment_ranges_overlap(
            [
                {
                    "start_at": aware_datetime(2026, 3, 30, 10, 0),
                    "end_at": aware_datetime(2026, 3, 30, 12, 0),
                },
                {
                    "start_at": aware_datetime(2026, 3, 30, 12, 0),
                    "end_at": aware_datetime(2026, 3, 30, 14, 0),
                },
            ]
        )

        # Overlap
        with self.assertRaises(ValueError) as cm:
            check_equipment_ranges_overlap(
                [
                    {
                        "start_at": aware_datetime(2026, 3, 30, 10, 0),
                        "end_at": aware_datetime(2026, 3, 30, 12, 0),
                    },
                    {
                        "start_at": aware_datetime(2026, 3, 30, 11, 0),
                        "end_at": aware_datetime(2026, 3, 30, 13, 0),
                    },
                ]
            )
        self.assertIn("Time ranges overlap", str(cm.exception))

    def test_request_submission_helper(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = asyncio.run(
                    create_equipment_request(
                        session,
                        requester_tg_user_id=123456789,
                        requester_username="john",
                        full_name="John Smith",
                        club_name="Jazz Club",
                        event_name="Spring Jam",
                        venue="Main Hall",
                        equipment_text="- 2 microphones\n- drum kit",
                        reason_text="rehearsal before performance",
                        comments="need setup by 17:30",
                        ranges=[
                            {
                                "start_at": aware_datetime(2026, 3, 30, 18, 0),
                                "end_at": aware_datetime(2026, 3, 30, 22, 0),
                            }
                        ],
                    )
                )

                self.assertIsNotNone(request.id)
                self.assertEqual(request.status, "submitted")
                self.assertEqual(request.requester_tg_user_id, 123456789)
                self.assertEqual(request.requester_username, "john")
                self.assertEqual(request.full_name, "John Smith")
                self.assertIsNotNone(request.submitted_at)
                self.assertIsNone(request.decided_at)
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_update_equipment_request_field_persists_successfully(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                updated = asyncio.run(
                    update_equipment_request_field(
                        session,
                        request,
                        "venue",
                        "Black Box Theatre",
                    )
                )

                self.assertEqual(updated.venue, "Black Box Theatre")
                self.assertEqual(request.venue, "Black Box Theatre")

                reloaded = session.get(EquipmentRequest, request.id)
                self.assertIsNotNone(reloaded)
                self.assertEqual(reloaded.venue, "Black Box Theatre")
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_update_equipment_request_field_rejects_unknown_field_name(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with self.assertRaises(AttributeError):
                    asyncio.run(
                        update_equipment_request_field(
                            session,
                            request,
                            "not_a_real_field",
                            "value",
                        )
                    )
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_update_equipment_request_field_rejects_sqlalchemy_instance_attribute(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with self.assertRaises(AttributeError):
                    asyncio.run(
                        update_equipment_request_field(
                            session,
                            request,
                            "metadata",
                            "value",
                        )
                    )
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_records_review_dm_and_topic_post_results(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                asyncio.run(
                    record_equipment_request_review_message(
                        session,
                        request,
                        chat_id=-1001234567890,
                        message_id=42,
                    )
                )
                asyncio.run(
                    record_equipment_request_dm_result(
                        session,
                        request,
                        ok=False,
                        error="bot blocked",
                    )
                )
                asyncio.run(
                    record_equipment_request_topic_post_result(
                        session,
                        request,
                        ok=True,
                        error=None,
                        chat_id=-1001234567891,
                        message_id=43,
                    )
                )

                reloaded = session.get(EquipmentRequest, request.id)
                self.assertIsNotNone(reloaded)
                assert reloaded is not None
                self.assertEqual(reloaded.review_chat_id, -1001234567890)
                self.assertEqual(reloaded.review_message_id, 42)
                self.assertFalse(reloaded.requester_dm_sent)
                self.assertEqual(reloaded.requester_dm_error, "bot blocked")
                self.assertTrue(reloaded.equipment_post_sent)
                self.assertIsNone(reloaded.equipment_post_error)
                self.assertEqual(reloaded.equipment_post_chat_id, -1001234567891)
                self.assertEqual(reloaded.equipment_post_message_id, 43)
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_approve_rejects_already_approved_request(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        decided_at = datetime(2026, 3, 25, 12, 34, 56, tzinfo=ZoneInfo("UTC"))

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with patch(
                    "app.services.equipment_request_service.now_tz",
                    return_value=decided_at,
                ):
                    approved = asyncio.run(
                        approve_equipment_request(session, request, admin_tg_user_id=999)
                    )

                with self.assertRaises(ValueError):
                    asyncio.run(
                        approve_equipment_request(session, approved, admin_tg_user_id=555)
                    )

                self.assertEqual(approved.status, "approved")
                self.assertEqual(approved.admin_tg_user_id, 999)
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_decline_rejects_already_declined_request(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        decided_at = datetime(2026, 3, 25, 12, 34, 56, tzinfo=ZoneInfo("UTC"))

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with patch(
                    "app.services.equipment_request_service.now_tz",
                    return_value=decided_at,
                ):
                    declined = asyncio.run(
                        decline_equipment_request(session, request, admin_tg_user_id=555)
                    )

                with self.assertRaises(ValueError):
                    asyncio.run(
                        decline_equipment_request(session, declined, admin_tg_user_id=999)
                    )

                self.assertEqual(declined.status, "declined")
                self.assertEqual(declined.admin_tg_user_id, 555)
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_approve_rejects_already_declined_request(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        decided_at = datetime(2026, 3, 25, 12, 34, 56, tzinfo=ZoneInfo("UTC"))

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with patch(
                    "app.services.equipment_request_service.now_tz",
                    return_value=decided_at,
                ):
                    declined = asyncio.run(
                        decline_equipment_request(session, request, admin_tg_user_id=555)
                    )

                with self.assertRaises(ValueError):
                    asyncio.run(
                        approve_equipment_request(session, declined, admin_tg_user_id=999)
                    )

                self.assertEqual(declined.status, "declined")
                self.assertEqual(declined.admin_tg_user_id, 555)
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_decline_rejects_already_approved_request(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        decided_at = datetime(2026, 3, 25, 12, 34, 56, tzinfo=ZoneInfo("UTC"))

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with patch(
                    "app.services.equipment_request_service.now_tz",
                    return_value=decided_at,
                ):
                    approved = asyncio.run(
                        approve_equipment_request(session, request, admin_tg_user_id=999)
                    )

                with self.assertRaises(ValueError):
                    asyncio.run(
                        decline_equipment_request(session, approved, admin_tg_user_id=555)
                    )

                self.assertEqual(approved.status, "approved")
                self.assertEqual(approved.admin_tg_user_id, 999)
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()

    def test_accept_decline_transition_helper_updates_timestamps_and_decision_admin(
        self,
    ) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        decided_at = datetime(2026, 3, 25, 12, 34, 56, tzinfo=ZoneInfo("UTC"))

        try:
            EquipmentRequest.metadata.create_all(engine)

            with Session(engine) as session:
                request = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request)
                session.commit()
                session.refresh(request)

                with patch(
                    "app.services.equipment_request_service.now_tz",
                    return_value=decided_at,
                ):
                    approved = asyncio.run(
                        approve_equipment_request(session, request, admin_tg_user_id=999)
                    )

                self.assertEqual(approved.status, "approved")
                self.assertEqual(approved.admin_tg_user_id, 999)
                self.assertEqual(
                    approved.decided_at.replace(tzinfo=ZoneInfo("UTC")),
                    decided_at,
                )

                request_for_decline = EquipmentRequest(
                    requester_tg_user_id=123456789,
                    requester_username="john",
                    full_name="John Smith",
                    club_name="Jazz Club",
                    event_name="Spring Jam",
                    venue="Main Hall",
                    equipment_text="- 2 microphones\n- drum kit",
                    needed_at_text="March 30, 18:00-22:00",
                    reason_text="rehearsal before performance",
                    comments="need setup by 17:30",
                )
                session.add(request_for_decline)
                session.commit()
                session.refresh(request_for_decline)

                with patch(
                    "app.services.equipment_request_service.now_tz",
                    return_value=decided_at,
                ):
                    declined = asyncio.run(
                        decline_equipment_request(
                            session,
                            request_for_decline,
                            admin_tg_user_id=555,
                        )
                    )

                self.assertEqual(declined.status, "declined")
                self.assertEqual(declined.admin_tg_user_id, 555)
                self.assertEqual(
                    declined.decided_at.replace(tzinfo=ZoneInfo("UTC")),
                    decided_at,
                )
        finally:
            EquipmentRequest.metadata.drop_all(engine)
            engine.dispose()
