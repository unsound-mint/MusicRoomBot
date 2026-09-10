from pathlib import Path
from unittest import TestCase


class TransactionConventionTests(TestCase):
    def test_handlers_do_not_perform_direct_database_writes(self) -> None:
        handler_root = Path(__file__).resolve().parents[1] / "app" / "bot" / "handlers"
        forbidden = (
            "db.commit(",
            "db.rollback(",
            "db.flush(",
            "db.add(",
            "db.delete(",
            "session.commit(",
            "session.rollback(",
            "session.flush(",
            "session.add(",
            "session.delete(",
        )
        violations: list[str] = []

        for path in sorted(handler_root.glob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if any(pattern in stripped for pattern in forbidden):
                    violations.append(f"{path.relative_to(handler_root.parents[2])}:{lineno}: {stripped}")

        self.assertEqual(violations, [])
