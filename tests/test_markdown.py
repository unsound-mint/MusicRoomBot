from unittest import TestCase

from app.bot.markdown import escape_markdown, markdown_display


class MarkdownTests(TestCase):
    def test_escape_markdown_escapes_legacy_entity_delimiters(self) -> None:
        self.assertEqual(
            escape_markdown(r"@user_name *bold* `code` [label] \slash"),
            r"@user\_name \*bold\* \`code\` \[label] \\slash",
        )

    def test_markdown_display_uses_fallback_for_blank_values(self) -> None:
        self.assertEqual(markdown_display(""), "-")
        self.assertEqual(markdown_display(None, fallback="(missing)"), "(missing)")
