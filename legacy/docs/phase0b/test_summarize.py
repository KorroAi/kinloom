import tempfile
import unittest
from pathlib import Path

from summarize import summarize

HEADER = "date,handle,channel,engine,genre,team_size,pain_unprompted,hours_on_npc_ai,tools_or_assets_bought,would_pay_signal,quote,notes\n"


def write(rows: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
    f.write(HEADER + rows)
    f.close()
    return Path(f.name)


class SummarizeTests(unittest.TestCase):
    def test_empty_file_reports_zero(self):
        out = summarize(write(""))
        self.assertIn("Interviews: 0", out)
        self.assertIn("pain_unprompted = yes AND strong pay signal: 0", out)

    def test_counts_pain_and_strong_signals(self):
        out = summarize(write(
            "2026-10-01,a,reddit,Unity,rpg,1,yes,40,Behavior Designer,offered_to_test,,\n"
            "2026-10-02,b,discord,Unity,sim,2,yes,10,,asked_for_demo,,\n"
            "2026-10-03,c,forum,Godot,fps,1,no,0,Behavior Designer;Emerald AI,none,,\n"
        ))
        self.assertIn("Interviews: 3", out)
        self.assertIn("pain_unprompted = yes: 2", out)
        self.assertIn("pain_unprompted = yes AND strong pay signal: 1", out)
        self.assertIn("Behavior Designer (2)", out)

    def test_missing_signal_is_counted_and_reported(self):
        out = summarize(write("2026-10-01,a,reddit,Unity,rpg,1,no,5,,,,\n"))
        self.assertIn("(empty)=1", out)
        self.assertIn("line 2: would_pay_signal", out)

    def test_invalid_values_are_reported_with_line_numbers(self):
        out = summarize(write("2026-10-01,a,reddit,Unity,rpg,1,maybe,5,,would_buy,,\n"))
        self.assertIn("line 2: pain_unprompted", out)
        self.assertIn("line 2: would_pay_signal", out)


if __name__ == "__main__":
    unittest.main()
