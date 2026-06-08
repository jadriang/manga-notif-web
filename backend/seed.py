"""Seed script — imports manga + state from the original manga-notif project."""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend to path
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from app.database import async_session, engine
from app.models.tables import Base, ChapterState, Manga


# Data from original config.py
MANGA_LIST = [
    {"title": "Nano Machine", "asura": "nano-machine-75e30c62", "demonic": "Nano-Machine"},
    {"title": "The Regressed Mercenary's Machinations", "asura": "the-regressed-mercenarys-machinations-75e30c62", "demonic": "The-Regressed-Mercenary%2527s-Machinations"},
    {"title": "Return of the Mount Hua Sect", "asura": "return-of-the-mount-hua-sect-75e30c62", "demonic": "Return-of-the-Mount-Hua-Sect"},
    {"title": "Chronicles of the Lazy Sovereign", "asura": "chronicles-of-the-lazy-sovereign-75e30c62", "demonic": "Chronicles-of-the-Lazy-Sovereign"},
    {"title": "I Am the Fated Villain", "asura": "i-am-the-fated-villain-75e30c62", "demonic": "I-Am-the-Fated-Villain"},
    {"title": "Raising Villains the Right Way", "asura": "raising-villains-the-right-way-75e30c62", "demonic": "Raising-Villains-the-Right-Way"},
    {"title": "Absolute Sword Sense", "asura": "absolute-sword-sense-75e30c62", "demonic": "Absolute-Sword-Sense"},
    {"title": "Murim Psychopath", "asura": "murim-psychopath-75e30c62", "demonic": "Murim-Psychopath"},
    {"title": "Star-Embracing Swordmaster", "asura": "star-embracing-swordmaster-75e30c62", "demonic": "Star%25252DEmbracing-Swordmaster"},
    {"title": "Return of the Apocalypse-Class Death Knight", "asura": "return-of-the-apocalypse-class-death-knight-75e30c62", "demonic": "Return-of-the-Apocalypse%25252DClass-Death-Knight"},
    {"title": "Eternally Regressing Knight", "asura": "eternally-regressing-knight-75e30c62", "demonic": "Eternally-Regressing-Knight"},
    {"title": "Reborn Rich", "demonic": "Reborn-Rich"},
    {"title": "Real Man", "demonic": "Real-Man"},
    {"title": "Overgeared", "asura": "overgeared-5abb513e", "demonic": "Overgeared"},
    {"title": "The Great Mage Returns After 4000 Years", "demonic": "The-Steel-Emperor"},
]

# State from original state.json
STATE = {
    "Nano Machine|asura": "307",
    "Nano Machine|demonic": "308",
    "The Regressed Mercenary's Machinations|asura": "84",
    "The Regressed Mercenary's Machinations|demonic": "85",
    "Return of the Mount Hua Sect|asura": "152.6",
    "Return of the Mount Hua Sect|demonic": "158",
    "Chronicles of the Lazy Sovereign|asura": "42",
    "Chronicles of the Lazy Sovereign|demonic": "43",
    "I Am the Fated Villain|asura": "323",
    "I Am the Fated Villain|demonic": "324",
    "Raising Villains the Right Way|asura": "30",
    "Raising Villains the Right Way|demonic": "31",
    "Absolute Sword Sense|asura": "177",
    "Absolute Sword Sense|demonic": "178",
    "Murim Psychopath|asura": "21",
    "Murim Psychopath|demonic": "22",
    "Star-Embracing Swordmaster|asura": "117",
    "Star-Embracing Swordmaster|demonic": "118",
    "Return of the Apocalypse-Class Death Knight|asura": "65",
    "Return of the Apocalypse-Class Death Knight|demonic": "66",
    "Eternally Regressing Knight|asura": "104",
    "Eternally Regressing Knight|demonic": "105",
    "Reborn Rich|demonic": "195",
    "Real Man|demonic": "247",
}


async def seed():
    async with async_session() as db:
        for entry in MANGA_LIST:
            title = entry["title"]

            # Check if already exists
            result = await db.execute(select(Manga).where(Manga.title == title))
            if result.scalar_one_or_none():
                print(f"  Skipping {title} (already exists)")
                continue

            manga = Manga(
                title=title,
                asura_slug=entry.get("asura"),
                demonic_slug=entry.get("demonic"),
            )
            db.add(manga)
            await db.flush()

            # Add chapter states from the old state.json
            for site in ("asura", "demonic"):
                key = f"{title}|{site}"
                chapter = STATE.get(key)
                if chapter:
                    db.add(ChapterState(
                        manga_id=manga.id,
                        site=site,
                        latest_chapter=chapter,
                    ))

            print(f"  ✓ {title}")

        await db.commit()
        print("\nSeed complete!")


async def seed_invite_code(code: str, max_uses: int, description: str = "") -> None:
    """Insert (or skip if exists) a single invite code."""
    from app.models.tables import InviteCode

    async with async_session() as db:
        result = await db.execute(select(InviteCode).where(InviteCode.code == code))
        if result.scalar_one_or_none():
            print(f"  Skipping invite code {code} (already exists)")
            return
        db.add(InviteCode(code=code, max_uses=max_uses, description=description))
        await db.commit()
        print(f"  ✓ invite code {code} (max_uses={max_uses})")


async def main():
    import secrets
    await seed()
    initial_code = secrets.token_urlsafe(12)
    await seed_invite_code(initial_code, max_uses=10, description="initial migration")
    print(f"\nIMPORTANT: save this invite code -> {initial_code}")


if __name__ == "__main__":
    asyncio.run(main())
