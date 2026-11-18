import unittest
from practice import Endpoint, Session, cited_lines, evidence


class PracticeTests(unittest.TestCase):
    def test_pause_follows_sustained_speech(self):
        detector = Endpoint(0.7)
        for level in [0] * 20 + [.03, 0, .03, .03, .03] + [0] * 6:
            self.assertFalse(detector.update(level))
        self.assertTrue(detector.update(0))

    def test_context_limit_and_reset(self):
        session = Session()
        for i in range(6):
            session.remember(str(i), "reply")
        self.assertEqual(session.messages()[0]["content"], "2")
        self.assertEqual(len(session.messages()), 8)
        session.turns.clear()
        self.assertEqual(session.messages(), [])

    def test_cv_evidence_across_full_document(self):
        match = "বাংলা ভাষা মূল্যায়ন"
        lines = evidence("older line\n" * 900 + match, "বাংলা", "", "")
        self.assertEqual(lines[0], match)
        self.assertEqual(cited_lines("Example [CV1] [CV99]", lines), ["[CV1] " + match])


if __name__ == "__main__":
    unittest.main()
