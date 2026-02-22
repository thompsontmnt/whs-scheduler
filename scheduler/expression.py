"""Build PowerSchool Expression strings from day/mod meeting data."""

from collections import defaultdict

_DAY_CODE = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}


def _collapse_numbers(values: list[int]) -> str:
    """Collapse sorted ints into range syntax: [1,2,4] -> '1-2,4'."""
    if not values:
        return ""
    parts: list[str] = []
    start = values[0]
    prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        parts.append(f"{start}-{prev}" if start != prev else str(start))
        start = value
        prev = value
    parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(parts)


def _collapse_days(days: list[int]) -> str:
    """Collapse sorted day numbers to PowerSchool day letters/ranges."""
    mapped = [_DAY_CODE[d] for d in days if d in _DAY_CODE]
    if not mapped:
        return ""
    # convert contiguous based on numeric day, then map to letters
    parts: list[str] = []
    start = days[0]
    prev = days[0]
    for value in days[1:]:
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

    tokens: list[str] = []
    for day_tuple in sorted(mods_by_dayset, key=lambda d: (len(d), d)):
        mods = sorted(mods_by_dayset[day_tuple])
        mod_label = _collapse_numbers(mods)
        day_label = _collapse_days(list(day_tuple))
        if mod_label and day_label:
            tokens.append(f"{mod_label}({day_label})")

    return " ".join(tokens)

