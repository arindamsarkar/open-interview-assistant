"""Local interview context and turn detection."""
import re
import unicodedata
from collections import deque


class Endpoint:
    """Detect a pause after speech using 100 ms audio frames."""
    def __init__(self, pause):
        self.required = round(float(pause) * 10)
        self.voiced = 0
        self.quiet = 0

    def update(self, rms):
        if rms >= 0.008:
            self.voiced += 1
            self.quiet = 0
        else:
            self.quiet += 1
            if self.voiced < 3:
                self.voiced = 0
        return self.voiced >= 3 and self.quiet >= self.required


def terms(text):
    normalized = "".join(c if unicodedata.category(c)[0] in "LMN" else " "
                         for c in text.casefold())
    return set(normalized.split())


def evidence(cv, question, role, job):
    lines = list(dict.fromkeys(line.strip() for line in cv.splitlines() if line.strip()))
    query, context = terms(question), terms(role + " " + job)
    ranked = sorted(lines, key=lambda line: -(3 * len(terms(line) & query)
                                              + len(terms(line) & context)))
    return [line[:500] for line in ranked[:5]]


class Session:
    def __init__(self):
        self.turns = deque(maxlen=4)

    def remember(self, question, answer):
        self.turns.append((question[:1500], answer[:1800]))

    def messages(self):
        return [dict(role=role, content=value) for pair in self.turns
                for role, value in zip(("user", "assistant"), pair)]


def cited_lines(answer, lines):
    ids = {int(n) for n in re.findall(r"\[CV(\d{1,3})\]", answer)}
    return [f"[CV{i}] {line}" for i, line in enumerate(lines, 1) if i in ids]
