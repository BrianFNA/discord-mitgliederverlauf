"""
Backfill-Skript: rekonstruiert historische Voice-Sessions aus dem
Carl-bot Voice-Log-Channel (#voice) und speichert sie in activity.db,
genau wie bot.py es für neue Sessions tut.

Carl-bot postet dort pro Event ein Embed:
  title:       "Member joined voice channel" / "Member left voice channel"
  description: "**{username}** joined/left #{channel_name}"
  footer.text: "ID: {user_id}"

Join/Leave-Paare pro User werden chronologisch (älteste zuerst) zu
Sitzungen mit Dauer verrechnet. Bot-Accounts (z.B. Musik-Bots) werden
übersprungen, analog zu bot.py.

Läuft einmalig durch und beendet sich danach selbst.
Setup: wie bot.py (gleicher Token/​.env)
Nutzung: python backfill_voice.py
"""

import os
import re
import sqlite3
import datetime

import discord
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "activity.db")
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("DISCORD_VOICE_LOG_CHANNEL_ID", "889201063410941962")

DESC_RE = re.compile(r"^\*\*(.+?)\*\* (?:joined|left) #(.+)$")


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            left_at TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            UNIQUE(user_id, channel_name, joined_at)
        )
    """)
    con.commit()
    con.close()


def log_voice_session(user_id, username, channel_name, joined_at, left_at):
    duration = int((left_at - joined_at).total_seconds())
    if duration <= 0:
        return
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT OR IGNORE INTO voice_sessions (user_id, username, channel_id, channel_name, joined_at, left_at, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(user_id), username, "", channel_name,
         joined_at.isoformat(), left_at.isoformat(), duration)
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


def parse_event(embed):
    if embed.title not in ("Member joined voice channel", "Member left voice channel"):
        return None
    if not embed.footer or not embed.footer.text or not embed.footer.text.startswith("ID: "):
        return None
    user_id = embed.footer.text.replace("ID: ", "").strip()

    channel_name = "unknown"
    username = embed.author.name if embed.author else "Unbekannt"
    if embed.description:
        m = DESC_RE.match(embed.description)
        if m:
            username = m.group(1)
            channel_name = m.group(2)

    is_join = embed.title == "Member joined voice channel"
    return user_id, username, channel_name, is_join


@client.event
async def on_ready():
    init_db()
    print(f"Eingeloggt als {client.user}. Starte Voice-Backfill...\n")

    channel = client.get_channel(int(CHANNEL_ID))
    if channel is None:
        print(f"Channel {CHANNEL_ID} nicht gefunden (falscher Server / keine Berechtigung?).")
        await client.close()
        return

    open_sessions = {}  # user_id -> (username, channel_name, joined_at)
    imported = 0
    skipped_bots = 0
    seen = 0

    async for message in channel.history(limit=None, oldest_first=True):
        if not message.embeds:
            continue
        event = parse_event(message.embeds[0])
        if event is None:
            continue
        seen += 1
        user_id, username, channel_name, is_join = event

        if await is_bot_account(user_id):
            skipped_bots += 1
            continue

        ts = message.created_at.replace(tzinfo=None)

        if is_join:
            open_sessions[user_id] = (username, channel_name, ts)
        else:
            session = open_sessions.pop(user_id, None)
            if session:
                sess_username, sess_channel, joined_at = session
                log_voice_session(user_id, sess_username, sess_channel, joined_at, ts)
                imported += 1

    print(f"\nFertig. {seen} Events gelesen, {imported} Voice-Sessions importiert, "
          f"{skipped_bots} Bot-Events übersprungen, {len(open_sessions)} offene Sessions ohne "
          f"passendes 'left'-Event ignoriert (z. B. noch aktiv).")
    await client.close()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Bitte DISCORD_BOT_TOKEN setzen (Umgebungsvariable oder .env-Datei)."
        )
    client.run(TOKEN)
