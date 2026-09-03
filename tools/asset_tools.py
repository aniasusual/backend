import os
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


# Offline / fallback curated catalog of verified high-res Unsplash photos
# Used when no API keys are present or when working offline.
FALLBACK_CURATED_ASSETS: Dict[str, List[Dict[str, Any]]] = {
    "avatar": [
        {
            "id": "avatar-1",
            "url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=256&q=80",
            "alt": "Portrait of smiling woman in casual attire",
            "category": "avatar",
            "tags": ["user", "profile", "woman", "person", "team", "customer"],
        },
        {
            "id": "avatar-2",
            "url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&q=80",
            "alt": "Portrait of smiling young man in blue shirt",
            "category": "avatar",
            "tags": ["user", "profile", "man", "person", "developer", "founder"],
        },
        {
            "id": "avatar-3",
            "url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&q=80",
            "alt": "Modern portrait of woman with creative background",
            "category": "avatar",
            "tags": ["user", "profile", "woman", "designer", "creator"],
        },
        {
            "id": "avatar-4",
            "url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&q=80",
            "alt": "Portrait of confident man outdoors",
            "category": "avatar",
            "tags": ["user", "profile", "man", "executive", "member"],
        },
        {
            "id": "avatar-5",
            "url": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=256&q=80",
            "alt": "Professional businesswoman in modern office",
            "category": "avatar",
            "tags": ["user", "profile", "woman", "business", "leader", "manager"],
        },
    ],
    "hero": [
        {
            "id": "hero-tech-1",
            "url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
            "alt": "Futuristic electronic circuit board and technology lights",
            "category": "hero",
            "tags": ["tech", "ai", "hardware", "futuristic", "dark", "saas", "landing"],
        },
        {
            "id": "hero-workspace-1",
            "url": "https://images.unsplash.com/photo-1497215728101-856f4ea42174?auto=format&fit=crop&w=1200&q=80",
            "alt": "Modern bright open-concept office workspace",
            "category": "hero",
            "tags": ["office", "workspace", "business", "startup", "collaboration", "saas"],
        },
        {
            "id": "hero-dashboard-1",
            "url": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
            "alt": "Data analytics charts and graphs on digital screens",
            "category": "hero",
            "tags": ["analytics", "charts", "data", "finance", "dashboard", "metrics"],
        },
        {
            "id": "hero-creative-1",
            "url": "https://images.unsplash.com/photo-1558655146-d09347e92766?auto=format&fit=crop&w=1200&q=80",
            "alt": "Abstract gradient modern design shapes",
            "category": "hero",
            "tags": ["abstract", "gradient", "creative", "design", "banner", "art"],
        },
    ],
    "product": [
        {
            "id": "product-headphones",
            "url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80",
            "alt": "Premium wireless headphones on yellow background",
            "category": "product",
            "tags": ["audio", "ecommerce", "headphones", "gadget", "music", "shop"],
        },
        {
            "id": "product-sneakers",
            "url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80",
            "alt": "Red sports running shoes sneakers",
            "category": "product",
            "tags": ["shoes", "sneakers", "fashion", "sports", "ecommerce", "shop"],
        },
        {
            "id": "product-watch",
            "url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=800&q=80",
            "alt": "Minimalist white smart watch on clean surface",
            "category": "product",
            "tags": ["watch", "smartwatch", "accessory", "tech", "ecommerce", "luxury"],
        },
        {
            "id": "product-camera",
            "url": "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=800&q=80",
            "alt": "Vintage instant camera minimalist product shot",
            "category": "product",
            "tags": ["camera", "photography", "gadget", "ecommerce", "retro"],
        },
    ],
    "finance": [
        {
            "id": "finance-growth",
            "url": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=800&q=80",
            "alt": "Stock market trading candlestick chart on monitor",
            "category": "finance",
            "tags": ["crypto", "stocks", "trading", "investment", "money", "growth"],
        },
        {
            "id": "finance-card",
            "url": "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=800&q=80",
            "alt": "Modern payment card and digital banking",
            "category": "finance",
            "tags": ["banking", "payment", "credit", "fintech", "wallet"],
        },
    ],
    "food": [
        {
            "id": "food-pizza",
            "url": "https://images.unsplash.com/photo-1513104890138-7c749659a591?auto=format&fit=crop&w=800&q=80",
            "alt": "Freshly baked artisan pizza with basil and cheese",
            "category": "food",
            "tags": ["pizza", "restaurant", "italian", "dinner", "delivery", "food"],
        },
        {
            "id": "food-burger",
            "url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=800&q=80",
            "alt": "Gourmet beef burger with melted cheese and fries",
            "category": "food",
            "tags": ["burger", "fastfood", "restaurant", "lunch", "meal"],
        },
        {
            "id": "food-coffee",
            "url": "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=800&q=80",
            "alt": "Hot latte with latte art in ceramic cup",
            "category": "food",
            "tags": ["coffee", "cafe", "latte", "breakfast", "drink"],
        },
    ],
    "nature": [
        {
            "id": "nature-mountains",
            "url": "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=800&q=80",
            "alt": "Scenic view of mountain peaks during golden hour sunrise",
            "category": "nature",
            "tags": ["mountain", "landscape", "travel", "hiking", "adventure"],
        },
        {
            "id": "nature-ocean",
            "url": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",
            "alt": "Tropical turquoise ocean beach and white sand",
            "category": "nature",
            "tags": ["beach", "ocean", "sea", "vacation", "tropical", "travel"],
        },
    ],
}

DEFAULT_ICON_SUGGESTIONS: Dict[str, List[str]] = {
    "general": ["Search", "Bell", "Settings", "Menu", "X", "Check", "Plus", "Trash2", "Edit", "Share2"],
    "navigation": ["Home", "Compass", "MapPin", "ArrowRight", "ChevronDown", "ChevronRight", "ExternalLink"],
    "ecommerce": ["ShoppingCart", "CreditCard", "Package", "Tag", "Star", "Heart", "ShoppingBag", "Truck"],
    "dashboard": ["LayoutDashboard", "BarChart3", "TrendingUp", "TrendingDown", "PieChart", "Activity", "Users", "DollarSign"],
    "finance": ["DollarSign", "CreditCard", "TrendingUp", "Wallet", "ShieldCheck", "Percent", "ArrowUpRight"],
    "communication": ["Mail", "MessageSquare", "Send", "Phone", "Inbox", "ThumbsUp", "MessageCircle", "User"],
    "media": ["Image", "Camera", "Play", "Pause", "Volume2", "Video", "Mic", "Music"],
    "security": ["Shield", "ShieldCheck", "Lock", "Unlock", "Key", "AlertTriangle", "AlertCircle"],
}


class AssetTools:
    """
    Multi-tier asset resolution engine for web application development.
    - Tier 1: Live Unsplash / Pexels search when API keys or network are available.
    - Tier 2: Dynamic project inspection (scans /public, /src/assets, and detects installed packages like lucide-react).
    - Tier 3: Curated CDN catalog safety net (ensures zero 404s/placeholders when offline or without keys).
    """

    def __init__(self, sandbox_path: Path):
        self.sandbox_path = sandbox_path
        self._load_api_keys()

    def _load_api_keys(self):
        """Loads API keys from environment."""
        raw_unsplash = os.environ.get("UNSPLASH_ACCESS_KEYS", "") or os.environ.get("UNSPLASH_ACCESS_KEY", "")
        self.unsplash_keys = [k.strip() for k in raw_unsplash.split(",") if k.strip()]

        raw_pexels = os.environ.get("PEXELS_ACCESS_KEYS", "") or os.environ.get("PEXELS_ACCESS_KEY", "")
        self.pexels_keys = [k.strip() for k in raw_pexels.split(",") if k.strip()]

    def get_assets(self, query: str = "", category: str = "", count: int = 5) -> str:
        """Fetch verified CDN images, local project media, and icon recommendations.

        Args:
            query: Keyword to search for (e.g. 'avatar', 'tech hero', 'burger', 'analytics', 'ecommerce sneaker').
            category: Optional category filter ('avatar', 'hero', 'product', 'finance', 'food', 'nature').
            count: Number of results to return (default: 5).

        Returns:
            A formatted markdown block with working image URLs, alt descriptions, and icon recommendations.
        """
        clean_query = query.strip() if query else ""
        clean_cat = category.lower().strip() if category else ""
        limit = max(1, min(int(count) if count else 5, 10))

        images: List[Dict[str, Any]] = []
        data_source = "curated_catalog"

        # Tier 1: Attempt Live Unsplash / Pexels Search if keys configured
        if self.unsplash_keys and clean_query:
            live_images = self._search_unsplash_live(clean_query, limit, clean_cat)
            if live_images:
                images = live_images
                data_source = "live_unsplash_api"

        elif self.pexels_keys and clean_query and not images:
            live_images = self._search_pexels_live(clean_query, limit)
            if live_images:
                images = live_images
                data_source = "live_pexels_api"

        # Tier 3: Curated Fallback Search (if no live API results)
        if not images:
            images = self._search_curated_catalog(clean_query, clean_cat, limit)
            data_source = "verified_cdn_catalog"

        # Tier 2: Dynamic Project & Package Inspection
        local_assets = self._scan_local_assets()
        installed_icon_pkg, recommended_icons = self._inspect_installed_icon_packages(clean_query, clean_cat)

        # Format markdown response
        output_blocks = []
        source_label = "Live Unsplash API" if data_source == "live_unsplash_api" else "Verified High-Resolution CDN"
        output_blocks.append(f"### 🖼️ Curated Asset Results (Query: '{query}', Category: '{category or 'all'}', Source: {source_label})\n")

        if images:
            output_blocks.append("**Verified High-Resolution Images:**")
            for idx, img in enumerate(images, 1):
                output_blocks.append(
                    f"{idx}. **{img['alt']}** (`{img.get('category', 'photo')}`)\n"
                    f"   - **URL:** `{img['url']}`\n"
                    f"   - **JSX Example:** `<img src=\"{img['url']}\" alt=\"{img['alt']}\" className=\"rounded-xl object-cover w-full h-48\" />`"
                )
        else:
            default_hero = FALLBACK_CURATED_ASSETS["hero"][0]["url"]
            output_blocks.append(
                f"No exact matches found. Recommended default CDN URL:\n"
                f"- **Default Hero Image:** `{default_hero}`"
            )

        if local_assets:
            output_blocks.append("\n**Local Project Assets (`/public` or `/src/assets`):**")
            for la in local_assets:
                output_blocks.append(f"- `{la['path']}` ({la['size']})")

        if recommended_icons:
            pkg_name = installed_icon_pkg or "lucide-react"
            icon_names_str = ", ".join(recommended_icons[:6])
            output_blocks.append(
                f"\n**Recommended Icons (`import {{ {icon_names_str} }} from '{pkg_name}'`):**\n"
                f"- {', '.join(f'`<{icon} className=\"w-5 h-5\" />`' for icon in recommended_icons[:6])}"
            )

        return "\n".join(output_blocks)

    def _search_unsplash_live(self, query: str, limit: int, category: str = "") -> List[Dict[str, str]]:
        """Live search Unsplash API with key rotation."""
        search_term = f"{category} {query}".strip() if category else query
        for key in self.unsplash_keys:
            try:
                params = urllib.parse.urlencode({"query": search_term, "per_page": limit, "page": 1})
                url = f"https://api.unsplash.com/search/photos?{params}"
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1", "User-Agent": "Lowkey/1.0"},
                )
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        results = data.get("results", [])
                        photos = []
                        for r in results:
                            urls = r.get("urls", {})
                            img_url = urls.get("regular") or urls.get("full") or urls.get("small")
                            alt_text = r.get("alt_description") or r.get("description") or f"{query} image"
                            if img_url:
                                photos.append({
                                    "id": r.get("id", "live-photo"),
                                    "url": img_url,
                                    "alt": alt_text.capitalize(),
                                    "category": category or "photo",
                                })
                        if photos:
                            return photos
            except Exception:
                continue
        return []

    def _search_pexels_live(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Live search Pexels API with key rotation."""
        for key in self.pexels_keys:
            try:
                params = urllib.parse.urlencode({"query": query, "per_page": limit, "page": 1})
                url = f"https://api.pexels.com/v1/search?{params}"
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": key, "User-Agent": "Lowkey/1.0"},
                )
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        results = data.get("photos", [])
                        photos = []
                        for r in results:
                            src = r.get("src", {})
                            img_url = src.get("large") or src.get("original") or src.get("medium")
                            alt_text = r.get("alt") or f"{query} photo"
                            if img_url:
                                photos.append({
                                    "id": str(r.get("id", "pexels-photo")),
                                    "url": img_url,
                                    "alt": alt_text.capitalize(),
                                    "category": "photo",
                                })
                        if photos:
                            return photos
            except Exception:
                continue
        return []

    def _search_curated_catalog(self, query: str, category: str, limit: int) -> List[Dict[str, Any]]:
        """Searches curated high-resolution catalog with semantic score matching."""
        clean_query = query.lower()
        clean_cat = category.lower()

        matched: List[Dict[str, Any]] = []

        for cat_name, items in FALLBACK_CURATED_ASSETS.items():
            if clean_cat and clean_cat != cat_name:
                continue

            for item in items:
                score = 0
                if clean_cat == cat_name:
                    score += 2
                if clean_query:
                    if clean_query in item["alt"].lower():
                        score += 4
                    if clean_query in cat_name:
                        score += 3
                    if any(clean_query in tag or tag in clean_query for tag in item["tags"]):
                        score += 3
                    for token in clean_query.split():
                        if token in item["alt"].lower() or any(token in tag for tag in item["tags"]):
                            score += 1
                else:
                    score = 1

                if score > 0:
                    matched.append({**item, "_score": score})

        matched.sort(key=lambda x: x.get("_score", 0), reverse=True)
        return [{k: v for k, v in m.items() if k != "_score"} for m in matched[:limit]]

    def _scan_local_assets(self) -> List[Dict[str, str]]:
        """Dynamically scans local project directories for user-provided static assets."""
        local_assets = []
        search_dirs = [self.sandbox_path / "public", self.sandbox_path / "src" / "assets", self.sandbox_path / "assets"]

        valid_exts = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}

        for d in search_dirs:
            if d.exists() and d.is_dir():
                for f in sorted(d.glob("*")):
                    if f.is_file() and f.suffix.lower() in valid_exts:
                        try:
                            rel_path = f"/{f.name}" if d.name == "public" else f"/{f.relative_to(self.sandbox_path)}"
                            local_assets.append({
                                "name": f.name,
                                "path": rel_path,
                                "size": f"{f.stat().st_size} bytes",
                            })
                        except Exception:
                            continue
        return local_assets

    def _inspect_installed_icon_packages(self, query: str, category: str) -> Tuple[str, List[str]]:
        """Dynamically inspects project's package.json to detect icon packages and provide contextual icons."""
        pkg_json_path = self.sandbox_path / "package.json"
        installed_icon_pkg = "lucide-react"

        if pkg_json_path.exists():
            try:
                pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
                deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                if "@heroicons/react" in deps:
                    installed_icon_pkg = "@heroicons/react/24/outline"
                elif "lucide-react" in deps:
                    installed_icon_pkg = "lucide-react"
                elif "react-icons" in deps:
                    installed_icon_pkg = "react-icons"
            except Exception:
                pass

        CATEGORY_ICON_MAP = {
            "product": ["ecommerce", "general"],
            "ecommerce": ["ecommerce", "general"],
            "avatar": ["communication", "general"],
            "profile": ["communication", "general"],
            "hero": ["navigation", "dashboard"],
            "finance": ["finance", "dashboard", "ecommerce", "security"],
            "dashboard": ["dashboard", "general"],
            "food": ["ecommerce", "general"],
            "nature": ["navigation", "general"],
        }

        matching_icons = []
        target_keys = []
        clean_cat = category.lower().strip()
        clean_query = query.lower().strip()

        if clean_cat in CATEGORY_ICON_MAP:
            for k in CATEGORY_ICON_MAP[clean_cat]:
                if k not in target_keys:
                    target_keys.append(k)

        for q_token in clean_query.split():
            if q_token in CATEGORY_ICON_MAP:
                for k in CATEGORY_ICON_MAP[q_token]:
                    if k not in target_keys:
                        target_keys.append(k)
            for k in DEFAULT_ICON_SUGGESTIONS:
                if (q_token in k or k in q_token) and k not in target_keys:
                    target_keys.append(k)

        for tk in target_keys:
            if tk in DEFAULT_ICON_SUGGESTIONS:
                matching_icons.extend(DEFAULT_ICON_SUGGESTIONS[tk])

        if not matching_icons:
            matching_icons = DEFAULT_ICON_SUGGESTIONS["general"] + DEFAULT_ICON_SUGGESTIONS["dashboard"][:3]

        seen_icons = set()
        unique_icons = []
        for ic in matching_icons:
            if ic not in seen_icons:
                seen_icons.add(ic)
                unique_icons.append(ic)

        return installed_icon_pkg, unique_icons
