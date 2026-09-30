import datetime
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.settings import Settings, get_settings
from app.intent.models import ExtractedField, IntentSource, StructuredSearchIntent
from app.utils.clock import TimeProvider, get_clock

logger = logging.getLogger("qdrant_edge.intent.parser")

# Category aliases mapped directly to dataset categories
CATEGORY_MAPPINGS: Dict[str, str] = {
    "movies": "movies",
    "movie": "movies",
    "film": "movies",
    "films": "movies",
    "cinema": "movies",
    "cinemas": "movies",
    "screening": "movies",
    "screenings": "movies",
    "concert": "concerts",
    "concerts": "concerts",
    "live music": "concerts",
    "gig": "concerts",
    "gigs": "concerts",
    "music": "concerts",
    "orchestra": "concerts",
    "symphony": "concerts",
    "band": "concerts",
    "comedy": "comedy",
    "standup": "comedy",
    "stand-up": "comedy",
    "improv": "comedy",
    "comic": "comedy",
    "theatre": "theatre",
    "theater": "theatre",
    "play": "theatre",
    "plays": "theatre",
    "drama": "theatre",
    "musical": "theatre",
    "musicals": "theatre",
    "stage": "theatre",
    "sports": "sports",
    "sport": "sports",
    "match": "sports",
    "game": "sports",
    "tournament": "sports",
    "festival": "festivals",
    "festivals": "festivals",
    "fest": "festivals",
    "fests": "festivals",
    "workshop": "workshops",
    "workshops": "workshops",
    "masterclass": "workshops",
    "class": "workshops",
    "classes": "workshops",
    "lessons": "workshops",
    "lesson": "workshops",
    "exhibition": "exhibitions",
    "exhibitions": "exhibitions",
    "gallery": "exhibitions",
    "museum": "exhibitions",
    "museums": "exhibitions",
    "exhibit": "exhibitions",
    "exhibits": "exhibitions",
    "activity": "activities",
    "activities": "activities",
    "tour": "activities",
    "tours": "activities",
    "adventure": "activities",
    "adventures": "activities",
}

# Known supported languages in dataset
SUPPORTED_LANGUAGES = {
    "english": "English",
    "japanese": "Japanese",
    "spanish": "Spanish",
    "french": "French",
    "korean": "Korean",
    "hindi": "Hindi",
    "tamil": "Tamil",
    "telugu": "Telugu",
}

# Known movie formats
SUPPORTED_FORMATS = {
    "imax": "IMAX",
    "3d": "3D",
    "2d": "2D",
    "4dx": "4DX",
    "70mm": "70mm",
    "35mm": "35mm",
}

# Known neighborhoods represented in dataset
KNOWN_NEIGHBORHOODS = [
    # Indian Metro Neighborhoods
    "Bandra", "Juhu", "Colaba", "Khar", "Fort", "Dadar", "Andheri", "Worli", "Marine Drive", "Byculla", "Powai",
    "Connaught Place", "Hauz Khas", "Mandi House", "Chandni Chowk", "Vasant Kunj", "Saket", "Lodhi", "Janpath", "Mehrauli",
    "Koramangala", "Indiranagar", "Whitefield", "JP Nagar", "Malleshwaram", "MG Road", "Cubbon Park", "Jayanagar",
    "Koregaon Park", "Kothrud", "Deccan", "Shivajinagar", "Camp", "Viman Nagar", "Baner", "Aundh",
    # Legacy / baseline neighborhoods
    "Castro", "Mission", "SOMA", "Chinatown", "North Beach", "Marina",
    "Haight-Ashbury", "Haight", "Presidio", "Richmond", "Sunset", "Embarcadero",
    "Dogpatch", "Civic Center", "Downtown", "Pacific Heights", "Fisherman's Wharf",
]

# Known venues represented in dataset
KNOWN_VENUES = [
    # Indian Cultural Venues & Landmarks
    "Prithvi Theatre", "NCPA Mumbai", "National Centre for the Performing Arts", "Habitat Comedy Club",
    "Shri Ram Centre", "Kamani Auditorium", "National Museum", "National Gallery of Modern Art", "NGMA",
    "Ranga Shankara", "Bangalore International Centre", "Chowdiah Memorial Hall", "Museum of Art & Photography", "MAP",
    "Bal Gandharva Ranga Mandir", "Raja Dinkar Kelkar Museum", "Shaniwar Wada", "High Spirits",
    "Wankhede Stadium", "Feroz Shah Kotla", "Kanteerava Stadium", "Chhatrapati Shivaji Maharaj Vastu Sangrahalaya", "CSMVS",
    # Legacy / baseline venues
    "Alamo Drafthouse Cinema", "Alamo Drafthouse", "The Roxie Cinema", "The Roxie",
    "Castro Theatre Pavilion", "Castro Theatre", "Balboa Theatre", "Vogue Theater",
    "OmniSphere IMAX Dome", "OmniSphere IMAX", "The Warfield", "Bimbo's 365 Club",
    "SFJAZZ Center", "SFJAZZ", "Great American Music Hall", "The Independent",
]

WEEKDAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


class LocalQueryParser:
    """Deterministic, local query parser extracting structured intent and filters offline."""

    @staticmethod
    def is_gibberish(text: str) -> bool:
        """Deterministic check for nonsensical keyboard smash / unpronounceable strings (e.g. 'dhcashivfhrgvi', 'asdfghjkl')."""
        if not text or not text.strip():
            return False
        clean = re.sub(r"[^a-zA-Z\s]", "", text).lower().strip()
        words = clean.split()
        if not words:
            return False

        vowels = set("aeiouy")
        known_safe = {
            "imax", "dj", "vr", "4dx", "70mm", "35mm", "edm", "rnb", "hiphop", "qawwali",
            "sitar", "tabla", "maratha", "prithvi", "ncpa", "pune", "delhi", "mumbai",
            "dune", "tumbbad", "sholay", "ddlj", "kamshet", "pawna", "sahyadri",
        }

        keyboard_walks = ["qwerty", "asdfgh", "zxcvbn", "dfghjk", "fghjkl", "wertyu", "ertyui", "rtyuio"]

        for w in words:
            if w in known_safe or len(w) < 4:
                continue
            # Check keyboard walk patterns
            if any(walk in w for walk in keyboard_walks):
                return True
            # Check repeated characters (e.g. 'aaaaa', 'zzzzz')
            if re.search(r"(.)\1{3,}", w):
                return True
            # Check 5+ consecutive consonants (unpronounceable in natural text)
            if re.search(r"[^aeiouy\s]{5,}", w):
                return True
            # Low vowel ratio on long words (length >= 6 with < 18% vowels)
            v_count = sum(1 for c in w if c in vowels)
            if len(w) >= 6 and (v_count == 0 or (v_count / len(w) < 0.18)):
                return True

        return False

    def __init__(self, settings: Optional[Settings] = None, clock: Optional[TimeProvider] = None):
        self.settings = settings or get_settings()
        self.clock = clock or get_clock()

    def parse(self, query: str) -> StructuredSearchIntent:
        """Parses raw user query into structured search intent without external network calls."""
        t0 = time.perf_counter()

        if not query or not query.strip():
            return StructuredSearchIntent(
                original_query=query or "",
                semantic_query="",
                is_gibberish=False,
                parse_latency_ms=0.0,
            )

        original_text = query.strip()
        tokens_to_remove: List[str] = []

        # 1. Negation handling (e.g. "not horror", "not comedy", "don't want comedy")
        excluded_cats, excluded_subcats = self._parse_negations(original_text, tokens_to_remove)

        # 2. Category extraction
        category_field = self._parse_category(original_text, tokens_to_remove)

        # 3. Price extraction
        price_min_field, price_max_field, currency = self._parse_price(original_text, tokens_to_remove)

        # 4. Date and Time extraction
        date_field, start_time_field, end_time_field, time_period_field = self._parse_datetime(
            original_text, tokens_to_remove
        )

        # 5. Location (City, Neighborhood, Venue)
        city_field, neighborhood_field, venue_field = self._parse_location(original_text, tokens_to_remove)

        # 6. Radius constraint
        radius_field, location_required = self._parse_radius(original_text, tokens_to_remove)

        # 7. Movie format extraction
        format_field = self._parse_format(original_text, tokens_to_remove)

        # 8. Language extraction
        language_field = self._parse_language(original_text, tokens_to_remove)

        # 9. Indoor / Outdoor constraint
        indoor_field = self._parse_indoor(original_text, tokens_to_remove)

        # 10. Status extraction
        status_field = self._parse_status(original_text, tokens_to_remove)

        # 11. Construct refined semantic query
        semantic_query = self._build_semantic_query(original_text, tokens_to_remove)

        latency_ms = (time.perf_counter() - t0) * 1000

        return StructuredSearchIntent(
            original_query=original_text,
            semantic_query=semantic_query,
            category=category_field,
            city=city_field,
            neighborhood=neighborhood_field,
            venue=venue_field,
            date=date_field,
            start_time=start_time_field,
            end_time=end_time_field,
            time_period=time_period_field,
            price_min=price_min_field,
            price_max=price_max_field,
            currency=currency,
            is_indoor=indoor_field,
            format=format_field,
            language=language_field,
            status=status_field,
            radius_km=radius_field,
            location_required=location_required,
            excluded_categories=excluded_cats,
            excluded_subcategories=excluded_subcats,
            is_gibberish=self.is_gibberish(original_text),
            parse_latency_ms=round(latency_ms, 3),
        )

    def _parse_negations(self, text: str, tokens_to_remove: List[str]) -> Tuple[List[str], List[str]]:
        """Extracts explicit negative constraints without destroying general text."""
        excluded_cats: List[str] = []
        excluded_subcats: List[str] = []

        # Matches: "not horror", "no comedy", "don't want plays"
        neg_patterns = [
            r"\b(?:not|no|don't want|dont want|without)\s+([a-zA-Z0-9_\-]+)\b"
        ]
        for pat in neg_patterns:
            for match in re.finditer(pat, text, re.IGNORECASE):
                neg_word = match.group(1).lower()
                full_match = match.group(0)
                if neg_word in CATEGORY_MAPPINGS:
                    cat = CATEGORY_MAPPINGS[neg_word]
                    excluded_cats.append(cat)
                    tokens_to_remove.append(full_match)
                elif neg_word in ("horror", "scary", "slasher", "thriller", "kids", "romance", "family"):
                    excluded_subcats.append(neg_word)
                    tokens_to_remove.append(full_match)

        return excluded_cats, excluded_subcats

    def _parse_category(self, text: str, tokens_to_remove: List[str]) -> Optional[ExtractedField]:
        """Recognizes primary city experience categories."""
        # Multi-word categories first
        multi_word_cats = [("live music", "concerts")]
        for phrase, cat in multi_word_cats:
            pattern = rf"\b{re.escape(phrase)}\b"
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                tokens_to_remove.append(m.group(0))
                return ExtractedField(value=cat, source=IntentSource.EXPLICIT, raw_token=m.group(0), confidence="high")

        # Single word categories
        for alias, cat in CATEGORY_MAPPINGS.items():
            if " " in alias:
                continue
            pattern = rf"\b{re.escape(alias)}\b"
            for m in re.finditer(pattern, text, re.IGNORECASE):
                # Ensure not part of negation (e.g. "not comedy")
                preceding = text[:m.start()].strip().lower()
                if any(preceding.endswith(w) for w in ("not", "no", "without", "don't want", "dont want")):
                    continue
                tokens_to_remove.append(m.group(0))
                return ExtractedField(value=cat, source=IntentSource.EXPLICIT, raw_token=m.group(0), confidence="high")

        return None

    def _parse_price(
        self, text: str, tokens_to_remove: List[str]
    ) -> Tuple[Optional[ExtractedField], Optional[ExtractedField], Optional[str]]:
        """Parses price limits, ranges, and currencies deterministically."""
        currency_detected = None
        if "₹" in text or re.search(r"\b(?:rs\.?|inr)\b", text, re.I):
            currency_detected = "INR"
        elif "$" in text or re.search(r"\b(?:usd|dollars?)\b", text, re.I):
            currency_detected = "USD"

        # 1. Free experiences
        free_match = re.search(r"\b(?:free|zero cost|no cost|free admission|free entry)\b", text, re.IGNORECASE)
        if free_match:
            tokens_to_remove.append(free_match.group(0))
            return (
                None,
                ExtractedField(value=0.0, source=IntentSource.EXPLICIT, raw_token=free_match.group(0), confidence="high"),
                currency_detected or self.settings.default_currency,
            )

        # 2. Price range: "between 500 and 1000", "500 to 1000", "₹500 - ₹1000"
        range_match = re.search(
            r"\b(?:between|from)?\s*(?:[₹$]|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:to|and|-)\s*(?:[₹$]|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\b",
            text,
            re.IGNORECASE,
        )
        if range_match:
            # Check context: avoid matching date ranges or time ranges (e.g. 5 to 7 pm)
            trailing = text[range_match.end():range_match.end()+10].lower()
            if not re.match(r"\s*(?:am|pm|km|miles|oct|nov)", trailing):
                p_min = float(range_match.group(1))
                p_max = float(range_match.group(2))
                if p_min <= p_max:
                    tokens_to_remove.append(range_match.group(0))
                    return (
                        ExtractedField(value=p_min, source=IntentSource.EXPLICIT, raw_token=range_match.group(0), confidence="high"),
                        ExtractedField(value=p_max, source=IntentSource.EXPLICIT, raw_token=range_match.group(0), confidence="high"),
                        currency_detected or self.settings.default_currency,
                    )

        # 3. Upper bound: "under ₹1000", "below 1000", "less than 1000", "up to 1500", "budget 1000"
        max_match = re.search(
            r"\b(?:under|below|less than|up to|budget|max(?:imum)?|<=?)\s*(?:[₹$]|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\b",
            text,
            re.IGNORECASE,
        )
        if max_match:
            trailing = text[max_match.end():max_match.end()+10].lower()
            if not re.match(r"\s*(?:km|kilometers|miles|pm|am)", trailing):
                val = float(max_match.group(1))
                tokens_to_remove.append(max_match.group(0))
                return (
                    None,
                    ExtractedField(value=val, source=IntentSource.EXPLICIT, raw_token=max_match.group(0), confidence="high"),
                    currency_detected or self.settings.default_currency,
                )

        # 4. Explicit currency followed by amount: "₹1000" or "$30"
        curr_match = re.search(r"(?:[₹$]|(?:rs\.?|inr)\s+)(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
        if curr_match:
            val = float(curr_match.group(1))
            tokens_to_remove.append(curr_match.group(0))
            return (
                None,
                ExtractedField(value=val, source=IntentSource.EXPLICIT, raw_token=curr_match.group(0), confidence="medium"),
                currency_detected or self.settings.default_currency,
            )

        # 5. Ambiguous price expressions: "around 1000", "something cheap", "affordable"
        # Conservative handling per Section 29: do not generate hard filter
        ambig_match = re.search(r"\b(?:around|approx(?:imately)?)\s+(?:[₹$]|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
        if ambig_match:
            return None, None, currency_detected

        return None, None, currency_detected

    def _parse_datetime(
        self, text: str, tokens_to_remove: List[str]
    ) -> Tuple[Optional[ExtractedField], Optional[ExtractedField], Optional[ExtractedField], Optional[ExtractedField]]:
        """Parses dates and times using the centralized TimeProvider."""
        now = self.clock.now()
        today = now.date()

        date_val: Optional[datetime.date] = None
        date_token: Optional[str] = None
        time_period_val: Optional[str] = None
        time_period_token: Optional[str] = None
        start_time_val: Optional[str] = None
        end_time_val: Optional[str] = None

        # 1. Named relative dates
        if re.search(r"\btonight\b", text, re.I):
            m = re.search(r"\btonight\b", text, re.I)
            date_val = today
            date_token = m.group(0)
            time_period_val = "night"
            time_period_token = m.group(0)
            tokens_to_remove.append(m.group(0))
        elif re.search(r"\btoday\b", text, re.I):
            m = re.search(r"\btoday\b", text, re.I)
            date_val = today
            date_token = m.group(0)
            tokens_to_remove.append(m.group(0))
        elif re.search(r"\btomorrow\b", text, re.I):
            m = re.search(r"\btomorrow\b", text, re.I)
            date_val = today + datetime.timedelta(days=1)
            date_token = m.group(0)
            tokens_to_remove.append(m.group(0))
        elif re.search(r"\b(?:this\s+)?weekend\b", text, re.I):
            m = re.search(r"\b(?:this\s+)?weekend\b", text, re.I)
            # Find upcoming Saturday
            days_ahead = (5 - today.weekday()) % 7
            date_val = today + datetime.timedelta(days=days_ahead)
            date_token = m.group(0)
            tokens_to_remove.append(m.group(0))

        # 2. Weekdays: "next Friday", "this Saturday", "Sunday"
        for day_name, day_idx in WEEKDAY_NAMES.items():
            pattern = rf"\b(?:(next|this)\s+)?{day_name}\b"
            m = re.search(pattern, text, re.IGNORECASE)
            if m and date_val is None:
                is_next = m.group(1) and m.group(1).lower() == "next"
                days_ahead = (day_idx - today.weekday()) % 7
                if days_ahead == 0 or is_next:
                    days_ahead += 7
                date_val = today + datetime.timedelta(days=days_ahead)
                date_token = m.group(0)
                tokens_to_remove.append(m.group(0))
                break

        # 3. Explicit ISO or month/day date: "October 15", "Oct 16"
        month_match = re.search(
            r"\b(october|oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)\s+(\d{1,2})\b",
            text,
            re.IGNORECASE,
        )
        if month_match and date_val is None:
            m_str = month_match.group(1).lower()
            day_num = int(month_match.group(2))
            month_map = {
                "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
                "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
                "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
                "august": 8, "aug": 8, "september": 9, "sep": 9,
            }
            m_num = month_map.get(m_str, 10)
            try:
                date_val = datetime.date(today.year, m_num, day_num)
                date_token = month_match.group(0)
                tokens_to_remove.append(month_match.group(0))
            except ValueError:
                pass

        # 4. Coarse time periods
        period_patterns = [
            (r"\b(?:in the\s+)?morning\b", "morning"),
            (r"\b(?:in the\s+)?afternoon\b", "afternoon"),
            (r"\b(?:in the\s+)?evening\b", "evening"),
            (r"\b(?:late\s+)?night\b", "night"),
        ]
        for pat, period_name in period_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                time_period_val = period_name
                time_period_token = m.group(0)
                tokens_to_remove.append(m.group(0))
                break

        # 5. Exact / Bound Time expressions: "after 8 pm", "before 6 pm", "at 7 pm", "around 8"
        start_time_confidence = "high"
        start_time_source = IntentSource.EXPLICIT
        end_time_confidence = "high"
        end_time_source = IntentSource.EXPLICIT

        # "around 8" or "around 8 pm" - conservative, non-exact per Section 10
        around_match = re.search(r"\baround\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
        if around_match:
            # Ambiguous; do not create false exact minute constraint
            time_period_val = time_period_val or "evening"
            time_period_token = around_match.group(0)

        after_match = re.search(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
        if after_match and not around_match:
            h = int(after_match.group(1))
            mn = int(after_match.group(2) or 0)
            mer = after_match.group(3)
            if mer:
                if mer.lower() == "pm" and h < 12:
                    h += 12
                elif mer.lower() == "am" and h == 12:
                    h = 0
            else:
                # "after 8" without am/pm is ambiguous
                start_time_confidence = "low"
                start_time_source = IntentSource.AMBIGUOUS
            start_time_val = f"{h:02d}:{mn:02d}:00"
            tokens_to_remove.append(after_match.group(0))

        before_match = re.search(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
        if before_match and not around_match:
            h = int(before_match.group(1))
            mn = int(before_match.group(2) or 0)
            mer = before_match.group(3)
            if mer:
                if mer.lower() == "pm" and h < 12:
                    h += 12
                elif mer.lower() == "am" and h == 12:
                    h = 0
            else:
                end_time_confidence = "low"
                end_time_source = IntentSource.AMBIGUOUS
            end_time_val = f"{h:02d}:{mn:02d}:00"
            tokens_to_remove.append(before_match.group(0))

        at_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
        if at_match and not start_time_val and not around_match:
            h = int(at_match.group(1))
            mn = int(at_match.group(2) or 0)
            mer = at_match.group(3)
            if mer:
                if mer.lower() == "pm" and h < 12:
                    h += 12
                elif mer.lower() == "am" and h == 12:
                    h = 0
            else:
                start_time_confidence = "low"
                start_time_source = IntentSource.AMBIGUOUS
            start_time_val = f"{h:02d}:{mn:02d}:00"
            tokens_to_remove.append(at_match.group(0))

        date_field = (
            ExtractedField(value=date_val.isoformat(), source=IntentSource.EXPLICIT, raw_token=date_token)
            if date_val
            else None
        )
        time_period_field = (
            ExtractedField(value=time_period_val, source=IntentSource.EXPLICIT, raw_token=time_period_token)
            if time_period_val
            else None
        )
        start_time_field = (
            ExtractedField(
                value=start_time_val, source=start_time_source, raw_token=start_time_val, confidence=start_time_confidence
            )
            if start_time_val
            else None
        )
        end_time_field = (
            ExtractedField(
                value=end_time_val, source=end_time_source, raw_token=end_time_val, confidence=end_time_confidence
            )
            if end_time_val
            else None
        )

        return date_field, start_time_field, end_time_field, time_period_field

    def _parse_location(
        self, text: str, tokens_to_remove: List[str]
    ) -> Tuple[Optional[ExtractedField], Optional[ExtractedField], Optional[ExtractedField]]:
        """Extracts cities, neighborhoods, and venues represented in the bounded dataset."""
        city_field = None
        neighborhood_field = None
        venue_field = None

        # 1. Cities: Indian metros & legacy
        city_patterns = [
            (r"\b(?:Mumbai|Bombay)\b", "Mumbai"),
            (r"\b(?:Delhi|New Delhi|NCR)\b", "Delhi"),
            (r"\b(?:Bengaluru|Bangalore)\b", "Bengaluru"),
            (r"\b(?:Pune|Poona)\b", "Pune"),
            (r"\b(?:San Francisco|SF)\b", "San Francisco"),
        ]
        for pat, canonical_city in city_patterns:
            city_match = re.search(pat, text, re.IGNORECASE)
            if city_match:
                city_field = ExtractedField(
                    value=canonical_city, source=IntentSource.EXPLICIT, raw_token=city_match.group(0), confidence="high"
                )
                tokens_to_remove.append(city_match.group(0))
                break

        # 2. Venues (checked before neighborhoods to avoid partial overlap)
        for v in KNOWN_VENUES:
            v_match = re.search(rf"\b{re.escape(v)}\b", text, re.IGNORECASE)
            if v_match:
                venue_field = ExtractedField(
                    value=v, source=IntentSource.EXPLICIT, raw_token=v_match.group(0), confidence="high"
                )
                tokens_to_remove.append(v_match.group(0))
                break

        # 3. Neighborhoods
        for n in KNOWN_NEIGHBORHOODS:
            n_match = re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE)
            if n_match:
                neighborhood_field = ExtractedField(
                    value=n, source=IntentSource.EXPLICIT, raw_token=n_match.group(0), confidence="high"
                )
                tokens_to_remove.append(n_match.group(0))
                break

        return city_field, neighborhood_field, venue_field

    def _parse_radius(self, text: str, tokens_to_remove: List[str]) -> Tuple[Optional[ExtractedField], bool]:
        """Parses distance radius expressions, explicitly signaling if user location is required."""
        radius_match = re.search(
            r"\b(?:within|under|in|less than)?\s*(\d+(?:\.\d+)?)\s*(?:km|kilometers|kms|miles|mi)\b",
            text,
            re.IGNORECASE,
        )
        if radius_match:
            val = float(radius_match.group(1))
            tokens_to_remove.append(radius_match.group(0))
            # In Phase 1D, since no device location provider exists, we require location
            return (
                ExtractedField(value=val, source=IntentSource.EXPLICIT, raw_token=radius_match.group(0), confidence="high"),
                True,
            )

        near_me_match = re.search(r"\b(?:near me|nearby|close by)\b", text, re.IGNORECASE)
        if near_me_match:
            tokens_to_remove.append(near_me_match.group(0))
            return (
                ExtractedField(value=5.0, source=IntentSource.INFERRED, raw_token=near_me_match.group(0), confidence="medium"),
                True,
            )

        return None, False

    def _parse_format(self, text: str, tokens_to_remove: List[str]) -> Optional[ExtractedField]:
        """Extracts movie/presentation formats (e.g. IMAX, 3D, 70mm)."""
        for raw, canonical in SUPPORTED_FORMATS.items():
            fmt_match = re.search(rf"\b{re.escape(raw)}\b", text, re.IGNORECASE)
            if fmt_match:
                # Do NOT remove IMAX from tokens if user also wants it as semantic keyword,
                # but track it as an explicit extracted filter!
                return ExtractedField(
                    value=canonical, source=IntentSource.EXPLICIT, raw_token=fmt_match.group(0), confidence="high"
                )
        return None

    def _parse_language(self, text: str, tokens_to_remove: List[str]) -> Optional[ExtractedField]:
        """Extracts spoken/subtitled languages supported in dataset."""
        for raw, canonical in SUPPORTED_LANGUAGES.items():
            lang_match = re.search(rf"\b{re.escape(raw)}\b", text, re.IGNORECASE)
            if lang_match:
                tokens_to_remove.append(lang_match.group(0))
                return ExtractedField(
                    value=canonical, source=IntentSource.EXPLICIT, raw_token=lang_match.group(0), confidence="high"
                )
        return None

    def _parse_indoor(self, text: str, tokens_to_remove: List[str]) -> Optional[ExtractedField]:
        """Extracts indoor or outdoor preference."""
        in_match = re.search(r"\b(?:indoors?|inside)\b", text, re.IGNORECASE)
        if in_match:
            tokens_to_remove.append(in_match.group(0))
            return ExtractedField(value=True, source=IntentSource.EXPLICIT, raw_token=in_match.group(0), confidence="high")

        out_match = re.search(r"\b(?:outdoors?|outside|open-?air)\b", text, re.IGNORECASE)
        if out_match:
            tokens_to_remove.append(out_match.group(0))
            return ExtractedField(value=False, source=IntentSource.EXPLICIT, raw_token=out_match.group(0), confidence="high")

        return None

    def _parse_status(self, text: str, tokens_to_remove: List[str]) -> Optional[ExtractedField]:
        """Extracts explicit event status constraint."""
        for st in ("available", "upcoming", "sold out", "cancelled"):
            st_match = re.search(rf"\b{re.escape(st)}\b", text, re.IGNORECASE)
            if st_match:
                tokens_to_remove.append(st_match.group(0))
                return ExtractedField(value=st, source=IntentSource.EXPLICIT, raw_token=st_match.group(0), confidence="high")
        return None

    def _build_semantic_query(self, original_text: str, tokens_to_remove: List[str]) -> str:
        """Constructs a refined semantic query while preserving descriptive intent."""
        result = original_text
        for token in sorted(tokens_to_remove, key=len, reverse=True):
            # Replace token with single space
            pattern = re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
            result = pattern.sub(" ", result)

        # Remove filler/operator words: "find me a", "show me", "looking for"
        fillers = [
            r"\bfind\s+(?:me\s+)?(?:a\s+|an\s+|some\s+)?",
            r"\bshow\s+(?:me\s+)?(?:a\s+|an\s+|some\s+)?",
            r"\blooking\s+for\s+(?:a\s+|an\s+|some\s+)?",
            r"\bi\s+want\s+(?:a\s+|an\s+|some\s+)?",
        ]
        for f_pat in fillers:
            result = re.sub(f_pat, " ", result, flags=re.IGNORECASE)

        # Clean up whitespace and punctuation
        result = re.sub(r"[^\w\s\-]", " ", result)
        result = re.sub(r"\s+", " ", result).strip()

        # If result is empty or too short, fall back to original query
        if not result or len(result) < 3:
            return original_text

        return result


_global_parser: Optional[LocalQueryParser] = None


def get_query_parser() -> LocalQueryParser:
    """Singleton accessor for local query parser."""
    global _global_parser
    if _global_parser is None:
        _global_parser = LocalQueryParser()
    return _global_parser
