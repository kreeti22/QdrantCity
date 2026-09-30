import datetime
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.edge.repository import ExperienceRepository
from app.memory.models import (
    BookmarkItem,
    InteractionEvent,
    InteractionType,
    PersonalizationMetadata,
    UserPreferenceProfile,
)
from app.memory.repository import MemoryRepository
from app.models.experience import ExperienceSearchResult

logger = logging.getLogger("qdrant_edge.memory.service")

# Weight hierarchy: Bookmark > View > Search
WEIGHT_BOOKMARK = 5.0
WEIGHT_VIEW = 2.0
WEIGHT_SEARCH = 1.0

# Modest boost coefficient: 20% max adjustment
DEFAULT_MAX_BOOST = 0.20


class UserMemoryService:
    """Manages user interactions, bookmarks, deterministic preference learning, and personalized re-ranking."""

    def __init__(self, memory_repo: MemoryRepository, experience_repo: Optional[ExperienceRepository] = None):
        self.repo = memory_repo
        self.exp_repo = experience_repo

    def set_experience_repository(self, experience_repo: ExperienceRepository) -> None:
        self.exp_repo = experience_repo

    # 1. Bookmarks API
    def add_bookmark(
        self,
        user_id: str,
        experience_id: Any,
        category: Optional[str] = None,
        title: Optional[str] = None,
        price: Optional[float] = None,
    ) -> bool:
        """Saves experience and records bookmark interaction."""
        if self.exp_repo and (not title or not category or price is None):
            try:
                exp = self.exp_repo.get_by_id(int(experience_id))
                if exp:
                    title = title or exp.title
                    category = category or exp.category
                    price = price if price is not None else exp.price
            except Exception:
                pass

        inserted = self.repo.add_bookmark(
            user_id=user_id,
            experience_id=experience_id,
            title=title,
            category=category,
            price=price,
        )
        if inserted:
            meta = {}
            if category:
                meta["category"] = category
            if title:
                meta["title"] = title
            if price is not None:
                meta["price"] = price
            if self.exp_repo:
                try:
                    exp = self.exp_repo.get_by_id(int(experience_id))
                    if exp and exp.subcategories:
                        meta["subcategories"] = exp.subcategories
                except Exception:
                    pass
            self.repo.record_interaction(
                user_id=user_id,
                event_type=InteractionType.BOOKMARK.value,
                experience_id=experience_id,
                metadata=meta,
            )
        return inserted

    def remove_bookmark(self, user_id: str, experience_id: Any) -> bool:
        """Removes bookmark and records unbookmark interaction."""
        removed = self.repo.remove_bookmark(user_id, experience_id)
        if removed:
            self.repo.record_interaction(
                user_id=user_id,
                event_type=InteractionType.UNBOOKMARK.value,
                experience_id=experience_id,
            )
        return removed

    def is_bookmarked(self, user_id: str, experience_id: Any) -> bool:
        """Checks if experience is saved."""
        return self.repo.is_bookmarked(user_id, experience_id)

    def get_bookmarks(self, user_id: str) -> List[Any]:
        """Returns list of bookmarked experience IDs."""
        return self.repo.get_bookmarks(user_id)

    def list_bookmarks(self, user_id: str) -> List[BookmarkItem]:
        """Lists bookmarks with available metadata."""
        detailed = self.repo.get_bookmarks_detailed(user_id)
        results: List[BookmarkItem] = []
        for b in detailed:
            exp = None
            if self.exp_repo:
                try:
                    exp = self.exp_repo.get_by_id(int(b["experience_id"]))
                except Exception:
                    pass
            title = (exp.title if exp else None) or b.get("title") or f"Experience {b['experience_id']}"
            category = (exp.category if exp else None) or b.get("category")
            price = (exp.price if exp else None) or b.get("price")
            results.append(
                BookmarkItem(
                    user_id=user_id,
                    experience_id=b["experience_id"],
                    title=title,
                    category=category,
                    price=price,
                    created_at=b.get("created_at") or "",
                )
            )
        return results

    def get_bookmarked_experiences(self, user_id: str) -> List[ExperienceSearchResult]:
        """Retrieves full ExperienceSearchResult items for all bookmarked experiences."""
        ids = self.repo.get_bookmarks(user_id)
        results: List[ExperienceSearchResult] = []
        if not self.exp_repo:
            return results

        for exp_id in ids:
            try:
                exp = self.exp_repo.get_by_id(int(exp_id))
                if exp:
                    results.append(exp)
            except Exception:
                pass
        return results

    # 2. Interaction Recording
    def record_search(self, user_id: str, query: str) -> None:
        """Logs search query interaction."""
        if query and query.strip():
            self.repo.record_interaction(
                user_id=user_id,
                event_type=InteractionType.SEARCH.value,
                query=query.strip(),
            )

    def record_view(self, user_id: str, experience_id: Any) -> None:
        """Logs experience card view/open interaction."""
        self.repo.record_interaction(
            user_id=user_id,
            event_type=InteractionType.VIEW.value,
            experience_id=experience_id,
        )

    def record_interaction(
        self,
        user_id: str,
        interaction_type: Any,
        experience_id: Optional[Any] = None,
        query: Optional[str] = None,
        category: Optional[str] = None,
        price: Optional[float] = None,
        is_indoor: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InteractionEvent:
        """Records an interaction with optional contextual metadata."""
        meta = dict(metadata or {})
        if category:
            meta["category"] = category
        if price is not None:
            meta["price"] = price
        if is_indoor is not None:
            meta["is_indoor"] = is_indoor

        e_val = interaction_type.value if hasattr(interaction_type, "value") else str(interaction_type)
        return self.repo.record_interaction(
            user_id=user_id,
            event_type=e_val,
            experience_id=experience_id,
            query=query,
            metadata=meta,
        )

    # 3. Deterministic Preference Learning
    def get_user_preferences(self, user_id: str) -> UserPreferenceProfile:
        """Computes and updates user preference profile deterministically from bookmarks and interaction history."""
        uid = user_id.strip() if user_id else "local-default"
        bookmarks = self.repo.get_bookmarks(uid)
        interactions = self.repo.get_recent_interactions(uid, limit=100)

        cat_scores: Dict[str, float] = {}
        subcat_scores: Dict[str, float] = {}
        prices: List[float] = []
        indoor_votes: List[bool] = []
        languages: Dict[str, float] = {}

        # Cache experience lookups
        exp_cache: Dict[str, Optional[ExperienceSearchResult]] = {}

        def get_exp(e_id: Any) -> Optional[ExperienceSearchResult]:
            if not self.exp_repo or e_id is None:
                return None
            key = str(e_id)
            if key not in exp_cache:
                try:
                    exp_cache[key] = self.exp_repo.get_by_id(int(key))
                except Exception:
                    exp_cache[key] = None
            return exp_cache[key]

        # 1. Process bookmarks (highest weight = 5.0)
        for exp_id in bookmarks:
            exp = get_exp(exp_id)
            if exp:
                cat = exp.category.lower().strip() if exp.category else ""
                if cat:
                    cat_scores[cat] = cat_scores.get(cat, 0.0) + WEIGHT_BOOKMARK
                for sub in exp.subcategories or []:
                    s = sub.lower().strip()
                    if s:
                        subcat_scores[s] = subcat_scores.get(s, 0.0) + (WEIGHT_BOOKMARK * 0.5)
                if exp.price is not None:
                    prices.append(float(exp.price))
                if exp.is_indoor is not None:
                    indoor_votes.append(bool(exp.is_indoor))
                if exp.language:
                    lang = exp.language.strip()
                    languages[lang] = languages.get(lang, 0.0) + WEIGHT_BOOKMARK

        # 2. Process interactions
        for event in interactions:
            weight = WEIGHT_VIEW if event.event_type == InteractionType.VIEW.value else (
                WEIGHT_SEARCH if event.event_type == InteractionType.SEARCH.value else (
                    WEIGHT_BOOKMARK if event.event_type == InteractionType.BOOKMARK.value else 0.0
                )
            )
            if weight == 0.0:
                continue

            exp = get_exp(event.experience_id) if event.experience_id is not None else None
            meta = event.metadata or {}

            # Category resolution
            cat = None
            if exp and exp.category:
                cat = exp.category.lower().strip()
            elif "category" in meta and meta["category"]:
                cat = str(meta["category"]).lower().strip()

            if cat:
                cat_scores[cat] = cat_scores.get(cat, 0.0) + weight

            # Subcategories
            if exp and exp.subcategories:
                for sub in exp.subcategories:
                    s = sub.lower().strip()
                    if s:
                        subcat_scores[s] = subcat_scores.get(s, 0.0) + (weight * 0.5)

            # Price
            if exp and exp.price is not None:
                prices.append(float(exp.price))
            elif "price" in meta and meta["price"] is not None:
                try:
                    prices.append(float(meta["price"]))
                except (ValueError, TypeError):
                    pass

            # Indoor
            if exp and exp.is_indoor is not None:
                indoor_votes.append(bool(exp.is_indoor))
            elif "is_indoor" in meta and meta["is_indoor"] is not None:
                indoor_votes.append(bool(meta["is_indoor"]))

            # Search query keyword inference
            if event.event_type == InteractionType.SEARCH.value and event.query:
                q_lower = event.query.lower()
                for c in ("comedy", "movies", "concerts", "theatre", "sports", "festivals", "workshops", "exhibitions", "activities"):
                    if c in q_lower and (not cat or c != cat):
                        cat_scores[c] = cat_scores.get(c, 0.0) + WEIGHT_SEARCH

        # Normalize category scores summing to 1.0 (or 1.0 if single)
        tot_cat = sum(cat_scores.values())
        if tot_cat > 0:
            norm_cats = {k: round(v / tot_cat, 3) for k, v in cat_scores.items()}
        else:
            norm_cats = {}

        tot_sub = sum(subcat_scores.values())
        if tot_sub > 0:
            norm_subcats = {k: round(v / tot_sub, 3) for k, v in subcat_scores.items()}
        else:
            norm_subcats = {}

        # Compute price stats
        p_min = round(min(prices), 2) if prices else None
        p_max = round(max(prices), 2) if prices else None
        p_avg = round(sum(prices) / len(prices), 2) if prices else None

        # Compute indoor preference
        pref_indoor: Optional[bool] = None
        if indoor_votes:
            ratio = sum(1 for v in indoor_votes if v) / len(indoor_votes)
            if ratio >= 0.65:
                pref_indoor = True
            elif ratio <= 0.35:
                pref_indoor = False

        profile = UserPreferenceProfile(
            user_id=uid,
            preferred_categories=norm_cats,
            category_affinities=norm_cats,
            preferred_subcategories=norm_subcats,
            preferred_price_min=p_min,
            preferred_price_max=p_max,
            preferred_price_avg=p_avg,
            preferred_indoor=pref_indoor,
            preferred_languages=languages,
            total_interactions=len(interactions),
            total_bookmarks=len(bookmarks),
            saved_experience_count=len(bookmarks),
            updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        self.repo.save_profile(profile)
        return profile

    # 4. Modest Personalization Re-ranking
    def personalize_results(
        self,
        user_id: Optional[str],
        results: List[ExperienceSearchResult],
        boost_weight: float = DEFAULT_MAX_BOOST,
    ) -> Tuple[List[ExperienceSearchResult], PersonalizationMetadata]:
        """Applies a modest personalization ranking adjustment after RRF fusion."""
        uid = user_id.strip() if user_id else "local-default"
        if not results:
            return results, PersonalizationMetadata(enabled=True, applied=False, user_id=uid)

        profile = self.get_user_preferences(uid)

        # If user has no interaction history, return results untouched
        if not profile.preferred_categories and not profile.preferred_subcategories and profile.preferred_price_avg is None:
            return results, PersonalizationMetadata(
                enabled=True,
                applied=False,
                signals_used=[],
                user_id=uid,
            )

        signals_used: Set[str] = set()
        boosted_items: List[Tuple[float, ExperienceSearchResult]] = []
        any_adjusted = False

        for exp in results:
            original_score = exp.score if exp.score is not None else 0.0
            affinity_score = 0.0

            # 1. Category affinity signal (up to 0.25)
            if exp.category:
                cat_norm = exp.category.lower().strip()
                cat_weight = profile.preferred_categories.get(cat_norm, 0.0)
                if cat_weight > 0:
                    affinity_score += 0.25 * cat_weight
                    signals_used.add("category")

            # 2. Subcategory affinity signal (up to 0.75)
            if exp.subcategories and profile.preferred_subcategories:
                sub_match_sum = 0.0
                for s in exp.subcategories:
                    s_norm = s.lower().strip()
                    val = profile.preferred_subcategories.get(s_norm, 0.0)
                    if val > 0:
                        sub_match_sum += val
                if sub_match_sum > 0:
                    affinity_score += 0.75 * min(1.0, sub_match_sum * 1.5)
                    signals_used.add("subcategories")

            # 3. Price compatibility signal (up to 0.25)
            if exp.price is not None and profile.preferred_price_avg is not None:
                p = float(exp.price)
                if profile.preferred_price_max is not None and p <= profile.preferred_price_max:
                    affinity_score += 0.25
                    signals_used.add("price")
                elif p <= profile.preferred_price_avg * 1.2:
                    affinity_score += 0.15
                    signals_used.add("price")

            # 4. Modest score calculation: S_final = S_rrf * (1.0 + alpha * affinity)
            if affinity_score > 0:
                effective_weight = max(boost_weight, 0.50) if "subcategories" in signals_used else boost_weight
                boost = 1.0 + (effective_weight * min(affinity_score, 1.0))
                new_score = round(original_score * boost, 6)
                any_adjusted = True
            else:
                new_score = original_score

            # Create updated card with new score
            updated_exp = exp.model_copy(update={"score": new_score})
            boosted_items.append((new_score, updated_exp))

        # Re-sort candidates by new boosted score descending
        boosted_items.sort(key=lambda x: x[0], reverse=True)

        final_results: List[ExperienceSearchResult] = []
        for rank_idx, (_, item) in enumerate(boosted_items, start=1):
            final_results.append(item.model_copy(update={"rank": rank_idx}))

        return final_results, PersonalizationMetadata(
            enabled=True,
            applied=any_adjusted,
            signals_used=sorted(list(signals_used)),
            user_id=uid,
        )

    def reset_memory(self, user_id: str) -> None:
        """Clears all local memory, bookmarks, and preferences for a user."""
        self.repo.reset_user_memory(user_id)
