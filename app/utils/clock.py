import datetime
import logging
from typing import Dict, Optional, Tuple, Union

from app.config.settings import Settings, get_settings

logger = logging.getLogger("qdrant_edge.clock")

# Common timezone offset mappings
NAMED_TIMEZONE_OFFSETS: Dict[str, datetime.timezone] = {
    "UTC": datetime.timezone.utc,
    "GMT": datetime.timezone.utc,
    "Z": datetime.timezone.utc,
    "PDT": datetime.timezone(datetime.timedelta(hours=-7)),
    "PST": datetime.timezone(datetime.timedelta(hours=-8)),
    "EDT": datetime.timezone(datetime.timedelta(hours=-4)),
    "EST": datetime.timezone(datetime.timedelta(hours=-5)),
    "IST": datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
}


def resolve_timezone(tz_name: str) -> datetime.timezone:
    """Safely resolves timezone without requiring external tzdata packages on Windows."""
    tz_upper = tz_name.strip().upper()
    if tz_upper in NAMED_TIMEZONE_OFFSETS:
        return NAMED_TIMEZONE_OFFSETS[tz_upper]

    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        logger.debug(f"Could not load zoneinfo for '{tz_name}', falling back to UTC.")
        return datetime.timezone.utc


class TimeProvider:
    """Centralized, deterministic clock for the platform.
    
    Eliminates scattered datetime.now() calls and guarantees reproducible date/time interpretation.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        tz_name: Optional[str] = None,
        reference_datetime: Optional[str] = None,
    ):
        self.settings = settings or get_settings()
        timezone_str = tz_name or self.settings.timezone
        self.tz = resolve_timezone(timezone_str)
        self._reference_time: Optional[datetime.datetime] = None

        ref = reference_datetime if reference_datetime is not None else self.settings.reference_datetime
        if ref:
            try:
                # Parse ISO format reference string
                ref_str = ref.replace("Z", "+00:00")
                parsed = datetime.datetime.fromisoformat(ref_str)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=self.tz)
                else:
                    parsed = parsed.astimezone(self.tz)
                self._reference_time = parsed
            except Exception as e:
                logger.warning(f"Could not parse reference_datetime '{ref}': {e}")

    def now(self) -> datetime.datetime:
        """Returns the current timezone-aware datetime or configured reference time."""
        if self._reference_time is not None:
            return self._reference_time
        return datetime.datetime.now(self.tz)

    def today(self) -> datetime.date:
        """Returns the current date in the configured timezone."""
        return self.now().date()

    def set_reference_time(self, dt: Union[datetime.datetime, str, None]) -> None:
        """Dynamically overrides the reference time (useful for unit tests and benchmarks)."""
        if dt is None:
            self._reference_time = None
        elif isinstance(dt, str):
            ref_str = dt.replace("Z", "+00:00")
            parsed = datetime.datetime.fromisoformat(ref_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self.tz)
            else:
                parsed = parsed.astimezone(self.tz)
            self._reference_time = parsed
        else:
            if dt.tzinfo is None:
                self._reference_time = dt.replace(tzinfo=self.tz)
            else:
                self._reference_time = dt.astimezone(self.tz)

    def reset_reference_time(self) -> None:
        """Restores reference time to settings default."""
        if self.settings.reference_datetime:
            self.set_reference_time(self.settings.reference_datetime)
        else:
            self._reference_time = None

    @staticmethod
    def get_time_period(dt: datetime.datetime) -> str:
        """Maps an hour to a coarse time period."""
        hour = dt.hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def time_period_bounds(self, target_date: datetime.date, period: str) -> Tuple[datetime.datetime, datetime.datetime]:
        """Returns the start and end datetimes for a given day and named time period."""
        p_lower = period.strip().lower()
        if p_lower == "morning":
            start = datetime.datetime.combine(target_date, datetime.time(6, 0, 0), tzinfo=self.tz)
            end = datetime.datetime.combine(target_date, datetime.time(11, 59, 59), tzinfo=self.tz)
        elif p_lower == "afternoon":
            start = datetime.datetime.combine(target_date, datetime.time(12, 0, 0), tzinfo=self.tz)
            end = datetime.datetime.combine(target_date, datetime.time(16, 59, 59), tzinfo=self.tz)
        elif p_lower == "evening":
            start = datetime.datetime.combine(target_date, datetime.time(17, 0, 0), tzinfo=self.tz)
            end = datetime.datetime.combine(target_date, datetime.time(20, 59, 59), tzinfo=self.tz)
        elif p_lower in ("night", "tonight"):
            start = datetime.datetime.combine(target_date, datetime.time(21, 0, 0), tzinfo=self.tz)
            # Extends to 4:00 AM next day
            next_day = target_date + datetime.timedelta(days=1)
            end = datetime.datetime.combine(next_day, datetime.time(4, 0, 0), tzinfo=self.tz)
        else:
            # Full day
            start = datetime.datetime.combine(target_date, datetime.time(0, 0, 0), tzinfo=self.tz)
            end = datetime.datetime.combine(target_date, datetime.time(23, 59, 59), tzinfo=self.tz)

        return start, end


_global_clock: Optional[TimeProvider] = None


def get_clock() -> TimeProvider:
    """Singleton accessor for central TimeProvider."""
    global _global_clock
    if _global_clock is None:
        _global_clock = TimeProvider()
    return _global_clock
