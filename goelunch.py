import re
import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Dict

from maubot import Plugin, MessageEvent
from maubot.handlers import command

from typing import Type
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper

URL_TMPL = (
    "https://www.studierendenwerk-goettingen.de/fileadmin/templates/php/"
    "mensaspeiseplan/cached/{lang}/{date}/alle.html"
)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_date(token: Optional[str]) -> dt.date:
    if not token or token.lower() == "today":
        return dt.date.today()
    if token.lower() == "tomorrow":
        return dt.date.today() + dt.timedelta(days=1)
    return dt.date.fromisoformat(token)


@dataclass
class MenuItem:
    typ: str
    title: str
    details: Optional[str]


# --- Parser for alle.html structure (tables with sp_tab) ---

TABLE_RE = re.compile(r'<table class="sp_tab".*?>.*?</table>', re.I | re.S)
CANTEEN_RE = re.compile(
    r"<th[^>]*>.*?<strong>(.*?)</strong>.*?(?:<div class=\"sp_date\">(.*?)</div>)?.*?</th>",
    re.I | re.S,
)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
TYP_RE = re.compile(r'<td class="sp_typ">(.*?)</td>', re.I | re.S)
BEZ_RE = re.compile(r'<td class="sp_bez">(.*?)</td>', re.I | re.S)
STRONG_RE = re.compile(r"<strong>(.*?)</strong>", re.I | re.S)
TAG_STRIP_RE = re.compile(r"<[^>]+>")


def html_to_text(fragment: str) -> str:
    frag = re.sub(r"<br\s*/?>", "\n", fragment or "", flags=re.I)
    frag = TAG_STRIP_RE.sub("", frag)
    return norm(frag.replace("\xa0", " "))


def parse_alle_html(html: str) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for table_html in TABLE_RE.findall(html or ""):
        m = CANTEEN_RE.search(table_html)
        if not m:
            continue
        canteen = html_to_text(m.group(1))
        date_str = html_to_text(m.group(2)) if m.group(2) else None

        items: List[MenuItem] = []
        for row in ROW_RE.findall(table_html):
            if "<th" in row.lower():
                continue
            mt = TYP_RE.search(row)
            mb = BEZ_RE.search(row)
            if not mt or not mb:
                continue

            typ = html_to_text(mt.group(1))
            bez_html = mb.group(1)

            ms = STRONG_RE.search(bez_html)
            title = html_to_text(ms.group(1)) if ms else html_to_text(bez_html)

            full = html_to_text(bez_html)
            details = norm(full[len(title) :]) if full.startswith(title) else full
            details = details if details and details != title else None

            items.append(MenuItem(typ=typ, title=title, details=details))

        out[canteen] = {"date": date_str, "items": items}
    return out


def best_canteen_match(query: str, available: List[str]) -> Optional[str]:
    q = query.strip().lower()
    if not q:
        return None
    for name in available:
        if name.lower() == q:
            return name
    hits = [name for name in available if q in name.lower()]
    return hits[0] if len(hits) == 1 else None


def format_menu(
    canteen: str,
    iso_date: str,
    parsed_date: Optional[str],
    items: List[MenuItem],
    max_items: int,
) -> str:
    header_date = parsed_date or iso_date
    lines = [f"**{canteen}** — {header_date}"]
    if not items:
        lines.append("_No items found._")
        return "\n".join(lines)

    for it in items[:max_items]:
        detail_txt = f" — {it.details}" if it.details else ""
        lines.append(f"- **{it.typ}**: {it.title}{detail_txt}")

    if len(items) > max_items:
        lines.append(f"_…and {len(items) - max_items} more._")
    return "\n".join(lines)


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("lang")
        helper.copy("default_canteen")
        helper.copy("max_items")
        helper.copy("request_timeout")


class GoeLunchBot(Plugin):
    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    async def _fetch(self, url: str, timeout: int = 30) -> str:
        async with self.http.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
            return await resp.text()

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    @command.new(name="lunch", help="Usage: !lunch [date] [canteen...]")
    @command.argument("args", pass_raw=True, required=False)
    async def lunch(self, evt: MessageEvent, args: str) -> None:
        cfg = self.config or {}
        lang = cfg.get("lang", "en")
        timeout = int(cfg.get("request_timeout", 30))
        default_canteen = cfg.get("default_canteen", "")
        max_items = int(cfg.get("max_items", 30))

        tokens = [t for t in (args or "").strip().split() if t]
        date_token = None
        canteen_query = None

        if not tokens:
            # !lunch  -> today + default canteen
            date_token = "today"
            canteen_query = default_canteen or None
        else:
            first = tokens[0].lower()

            # If first token is a date keyword or ISO date, treat it as date
            if first in {"today", "tomorrow"} or re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", tokens[0]
            ):
                date_token = tokens[0]
                rest = " ".join(tokens[1:]).strip()
                # If user only wrote "!lunch tomorrow", use default canteen
                canteen_query = rest or (default_canteen or None)
            else:
                # Otherwise treat the whole input as canteen query, date defaults to today
                date_token = "today"
                canteen_query = " ".join(tokens).strip() or (default_canteen or None)

        if not canteen_query:
            await evt.reply(
                "No default canteen configured. Please set `default_canteen` in the instance config."
            )
            return

        try:
            date = parse_date(date_token)
        except Exception:
            await evt.reply(
                "Could not parse date. Use `today`, `tomorrow`, or `YYYY-MM-DD`."
            )
            return

        url = URL_TMPL.format(lang=lang, date=date.isoformat())
        try:
            html = await self._fetch(url, timeout=timeout)
        except Exception as e:
            await evt.reply(f"Menu fetch failed: {type(e).__name__}: {e}")
            return

        parsed = parse_alle_html(html)
        if not parsed:
            await evt.reply(
                "No menus found in the fetched document (structure changed?)."
            )
            return

        available = sorted(parsed.keys())
        match = best_canteen_match(canteen_query, available)
        if not match:
            q = canteen_query.lower()
            candidates = [c for c in available if q in c.lower()]
            if candidates:
                await evt.reply(
                    "Canteen name is ambiguous. Matches:\n"
                    + "\n".join(f"- {c}" for c in candidates)
                )
            else:
                await evt.reply(
                    "Canteen not found. Available:\n"
                    + "\n".join(f"- {c}" for c in available)
                )
            return

        info = parsed[match]
        await evt.respond(
            format_menu(
                match,
                date.isoformat(),
                info.get("date"),
                info.get("items", []),
                max_items,
            )
        )
