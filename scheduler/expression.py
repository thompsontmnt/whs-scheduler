"""Build PowerSchool Expression strings from day/mod meeting data."""

from collections import defaultdict
import re

_DAY_CODE = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}


def _contiguous_ranges(values: list[int]) -> list[tuple[int, int]]:
    """Convert sorted ints to contiguous ranges: [1,2,4] -> [(1,2), (4,4)]."""
    if not values:
        return []
    ranges: list[tuple[int, int]] = []
    start = values[0]
    prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append((start, prev))
        start = value
        prev = value
    ranges.append((start, prev))
    return ranges


def _collapse_days(days: list[int]) -> str:
    """Collapse sorted day numbers to PowerSchool day letters/ranges."""
    valid_days = sorted({day for day in days if day in _DAY_CODE})
    if not valid_days:
        return ""
    # convert contiguous based on numeric day, then map to letters
    parts: list[str] = []
    start = valid_days[0]
    prev = valid_days[0]
    for value in valid_days[1:]:
        if value == prev + 1:
            prev = value
            continue
        parts.append(_day_range_label(start, prev))
        start = value
        prev = value
    parts.append(_day_range_label(start, prev))
    return ",".join(parts)


def _day_range_label(start: int, end: int) -> str:
    if start == end:
        return _DAY_CODE.get(start, "")
    return f"{_DAY_CODE.get(start, '')}-{_DAY_CODE.get(end, '')}"


def build_expression_from_meetings(meetings: list[tuple[int, int]]) -> str:
    """Build PowerSchool expression from (day, mod) pairs.

    Examples:
    - [(1, 1)] -> '1(A)'
    - [(1, 1), (2, 1)] -> '1(A-B)'
    - [(1, 1), (1, 2)] -> '1-2(A)'
    """
    if not meetings:
        return ""

    days_by_mod: dict[int, set[int]] = defaultdict(set)
    for day, mod in meetings:
        if day <= 0 or mod <= 0:
            continue
        days_by_mod[mod].add(day)

    if not days_by_mod:
        return ""

    mods_by_dayset: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for mod, days in days_by_mod.items():
        key = tuple(sorted(days))
        mods_by_dayset[key].append(mod)

    token_parts: list[tuple[int, str]] = []
    for day_tuple, mods in mods_by_dayset.items():
        day_label = _collapse_days(list(day_tuple))
        if not day_label:
            continue
        for start_mod, end_mod in _contiguous_ranges(sorted(mods)):
            mod_label = str(start_mod) if start_mod == end_mod else f"{start_mod}-{end_mod}"
            token_parts.append((start_mod, f"{mod_label}({day_label})"))

    tokens = [token for _, token in sorted(token_parts, key=lambda t: (t[0], t[1]))]

    return " ".join(tokens)


_DAY_REVERSE = {value: key for key, value in _DAY_CODE.items()}
_TOKEN_RE = re.compile(r"^(\d+(?:-\d+)?)\(([A-E](?:-[A-E])?(?:,[A-E](?:-[A-E])?)*)\)$")


def parse_expression_to_meetings(expression: str) -> tuple[tuple[int, int], ...]:
    """Parse PowerSchool expression text to normalized (day, mod) meetings."""
    meetings: set[tuple[int, int]] = set()
    for token in expression.strip().split():
        match = _TOKEN_RE.match(token)
        if not match:
            continue
        mod_part, day_part = match.groups()
        mod_values: list[int] = []
        if "-" in mod_part:
            start, end = mod_part.split("-", 1)
            mod_values.extend(range(int(start), int(end) + 1))
        else:
            mod_values.append(int(mod_part))

        day_values: list[int] = []
        for day_token in day_part.split(","):
            if "-" in day_token:
                start_label, end_label = day_token.split("-", 1)
                start_day = _DAY_REVERSE.get(start_label)
                end_day = _DAY_REVERSE.get(end_label)
                if start_day is None or end_day is None:
                    continue
                day_values.extend(range(start_day, end_day + 1))
            else:
                day_number = _DAY_REVERSE.get(day_token)
                if day_number is not None:
                    day_values.append(day_number)

        for mod in mod_values:
            for day in day_values:
                meetings.add((day, mod))

    return tuple(sorted(meetings))
