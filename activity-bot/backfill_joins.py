"""
Backfill-Skript: rekonstruiert historische Beitritte UND Austritte aus dem
Carl-bot Join/Leave-Log-Channel (#join-leave) und speichert sie in
activity.db:
  - Tabelle "members": Username/Avatar/aktuellstes Beitrittsdatum pro
    User (für die Ranglisten)
  - Tabelle "member_events": komplette Beitritts-/Austritts-Historie
    (für den Mitgliederverlauf-Chart im "Beigetreten"-Tab, der daraus
    die tatsächliche Mitgliederzahl über Zeit berechnet)

Carl-bot postet dort pro Event ein Embed:
  title:       "Member joined" / "Member left"
  footer.text: "ID: {user_id}"
  author.name: Username zum Zeitpunkt des Events

Events werden chronologisch (älteste zuerst) verarbeitet, sodass am Ende
für aktuelle Mitglieder derselbe (letzte) Beitrittszeitpunkt in "members"
steht, den auch bot.py per Discord-API live ermitteln würde.

Bot-Accounts werden übersprungen, analog zu bot.py.

Läuft einmalig durch und beendet sich danach selbst.
Setup: wie bot.py (gleicher Token/​.env)
Nutzung: python backfill_joins.py
"""

import os
import sqlite3

import discord
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "activity.db")
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("DISCORD_JOIN_LEAVE_CHANNEL_ID", "889200831436570738")


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            avatar_url TEXT,
            joined_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS member_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(user_id, event_type, timestamp)
        )
    """)
    con.commit()
    con.close()


def upsert_join(user_id, username, joined_at_iso):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO members (user_id, username, avatar_url, joined_at)
        VALUES (?, ?, NULL, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            joined_at=excluded.joined_at
    """, (str(user_id), username, joined_at_iso))
    con.commit()
    con.close()


def log_event(user_id, username, event_type, timestamp_iso):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT OR IGNORE INTO member_events (user_id, username, event_type, timestamp) "
        "VALUES (?, ?, ?, ?)",
        (str(user_id), username, event_type, timestamp_iso)
    )
    con.commit()
    con.close()


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

bot_account_cache = {}


async def is_bot_account(user_id):
    if user_id in bot_account_cache:
        return bot_account_cache[user_id]
    try:
        user = await client.fetch_user(int(user_id))
        bot_account_cache[user_id] = user.bot
    except (discord.NotFound, discord.HTTPException, ValueError):
        bot_account_cache[user_id] = False
    return bot_account_cache[user_id]


@client.event
async def on_ready():
    init_db()
    print(f"Eingeloggt als {client.user}. Starte Join/Leave-Backfill...\n")

    channel = client.get_channel(int(CHANNEL_ID))
    if channel is None:
        print(f"Channel {CHANNEL_ID} nicht gefunden (falscher Server / keine Berechtigung?).")
        await client.close()
        return

    imported_joins = 0
    imported_leaves = 0
    skipped_bots = 0
    seen = 0

    async for message in channel.history(limit=None, oldest_first=True):
        if not message.embeds:
            continue
        embed = message.embeds[0]
        if embed.title not in ("Member joined", "Member left"):
            continue
        if not embed.footer or not embed.footer.text or not embed.footer.text.startswith("ID: "):
            continue
        seen += 1
        user_id = embed.footer.text.replace("ID: ", "").strip()

        if await is_bot_account(user_id):
            skipped_bots += 1
            continue

        username = embed.author.name if embed.author else "Unbekannt"
        timestamp = message.created_at.replace(tzinfo=None).isoformat()

        if embed.title == "Member joined":
            upsert_join(user_id, username, timestamp)
            log_event(user_id, username, "join", timestamp)
            imported_joins += 1
        else:
            log_event(user_id, username, "leave", timestamp)
            imported_leaves += 1

    print(f"\nFertig. {seen} Events gelesen, {imported_joins} Beitritte + {imported_leaves} Austritte "
          f"in {DB_PATH} gespeichert, {skipped_bots} Bot-Events übersprungen.")
    await client.close()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Bitte DISCORD_BOT_TOKEN setzen (Umgebungsvariable oder .env-Datei)."
        )
    client.run(TOKEN)
