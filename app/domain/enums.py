from __future__ import annotations

import enum


class TripType(str, enum.Enum):
    ONE_WAY = "one_way"
    ROUND_TRIP = "round_trip"


class DateMode(str, enum.Enum):
    FIXED = "fixed"
    RANGE = "range"
    DURATION = "duration"


class BaggagePolicy(str, enum.Enum):
    IGNORE = "ignore"
    OPTIONAL = "optional"
    REQUIRED = "required"


class CheckTrigger(str, enum.Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    API = "api"


class CheckStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    NO_RESULTS = "no_results"


class NotificationReason(str, enum.Enum):
    PRICE_BELOW_THRESHOLD = "price_below_threshold"
    PRICE_DROP = "price_drop"
    NEW_VARIANT = "new_variant"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
