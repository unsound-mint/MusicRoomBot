"""move attendance state to bookings

Revision ID: 7b2d9a4c1e0f
Revises: 6f8e3c2d1a90
Create Date: 2026-05-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b2d9a4c1e0f"
down_revision: str | Sequence[str] | None = "6f8e3c2d1a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_has_column("bookings", "attendance_verified"):
        op.add_column(
            "bookings",
            sa.Column(
                "attendance_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if not _table_has_column("bookings", "attendance_lat"):
        op.add_column(
            "bookings",
            sa.Column("attendance_lat", sa.Float(), nullable=True),
        )
    if not _table_has_column("bookings", "attendance_lon"):
        op.add_column(
            "bookings",
            sa.Column("attendance_lon", sa.Float(), nullable=True),
        )
    if not _table_has_column("bookings", "attendance_recorded_at"):
        op.add_column(
            "bookings",
            sa.Column("attendance_recorded_at", sa.DateTime(timezone=True), nullable=True),
        )

    if _table_exists("attendance_log"):
        op.execute(
            """
            WITH latest_attendance AS (
                SELECT DISTINCT ON (booking_id)
                    booking_id,
                    lat,
                    lon,
                    verified,
                    timestamp
                FROM attendance_log
                ORDER BY booking_id, verified DESC, timestamp DESC NULLS LAST, id DESC
            )
            UPDATE bookings
            SET
                attendance_verified = latest_attendance.verified,
                attendance_lat = latest_attendance.lat,
                attendance_lon = latest_attendance.lon,
                attendance_recorded_at = latest_attendance.timestamp,
                absence_reported = true,
                location_prompted = true
            FROM latest_attendance
            WHERE bookings.id = latest_attendance.booking_id
            """
        )
        op.drop_table("attendance_log")


def downgrade() -> None:
    op.create_table(
        "attendance_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attendance_log_booking_id",
        "attendance_log",
        ["booking_id"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_log_user_id",
        "attendance_log",
        ["user_id"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO attendance_log (booking_id, user_id, lat, lon, verified, timestamp)
        SELECT
            id,
            user_id,
            COALESCE(attendance_lat, 0.0),
            COALESCE(attendance_lon, 0.0),
            attendance_verified,
            COALESCE(attendance_recorded_at, now())
        FROM bookings
        WHERE absence_reported = true
        """
    )

    if _table_has_column("bookings", "attendance_recorded_at"):
        op.drop_column("bookings", "attendance_recorded_at")
    if _table_has_column("bookings", "attendance_lon"):
        op.drop_column("bookings", "attendance_lon")
    if _table_has_column("bookings", "attendance_lat"):
        op.drop_column("bookings", "attendance_lat")
    if _table_has_column("bookings", "attendance_verified"):
        op.drop_column("bookings", "attendance_verified")
