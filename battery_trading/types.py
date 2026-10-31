"""Small shared types used across the package.

Kept in its own module so that ``battery``, ``strategy`` and ``simulator`` can all import
``Direction`` without creating circular imports between them.
"""
from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    """The action the battery (or a single market commitment) takes in a settlement period.

    Subclassing ``str`` makes the value serialise naturally (e.g. ``"charge"``) when written
    to CSV or compared against plain strings in reports and tests.
    """

    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"
