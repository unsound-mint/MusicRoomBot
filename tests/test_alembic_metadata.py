import importlib
import pkgutil
from pathlib import Path
from unittest import TestCase

from alembic.config import Config
from alembic.script import ScriptDirectory

import app.models
from app.core.database import Base


class AlembicMetadataTests(TestCase):
    def test_alembic_revision_graph_has_single_head(self) -> None:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        script = ScriptDirectory.from_config(config)

        self.assertEqual(1, len(script.get_heads()))

    def test_model_modules_import_into_metadata(self) -> None:
        for module in pkgutil.iter_modules(app.models.__path__):
            if not module.ispkg:
                importlib.import_module(f"{app.models.__name__}.{module.name}")

        self.assertTrue(Base.metadata.tables)
        self.assertSetEqual(
            {
                "admins",
                "bookings",
                "club_leaders",
                "club_slot_cancellations",
                "clubs",
                "config",
                "equipment_request_ranges",
                "equipment_requests",
                "gift_offers",
                "swap_offers",
                "users",
                "weekly_slots",
            },
            set(Base.metadata.tables),
        )
