"""
Discord Aktivitäts-Tracking-Bot
--------------------------------
Erfasst laufend:
  - Text-Nachrichten: wer, wann, in welchem Channel, wie lang (KEIN Inhalt)
  - Voice-Zeiten: wer war wie lange in welchem Voice-Channel
  - Mitglieder: Username, Avatar, Beitrittsdatum

Speichert alles in einer lokalen SQLite-Datei (activity.db).
Veröffentlicht außerdem automatisch 4x täglich (00:00 / 06:00 / 12:00 / 18:00 UTC)
einen aktuellen JSON-Export nach ../aktivitaet/data.json und pusht ihn per Git,
damit die über GitHub Pages gehostete Website (aktivitaet/) aktuell bleibt.

Setup:
  1. pip install -r requirements.txt
  2. Bot-Application unter https://discord.com/developers/applications anlegen
  3. Im Bot-Tab aktivieren: "MESSAGE CONTENT INTENT" und "SERVER MEMBERS INTENT"
  4. Bot-Token als Umgebungsvariable DISCORD_BOT_TOKEN setzen (z.B. via .env)
  5. Bot über den OAuth2-URL-Generator einladen (Scopes: bot,
     Permissions: View Channels, Read Message History, Connect)
  6. Sicherstellen, dass `git push` in diesem Repo ohne manuelle Eingabe
     funktioniert (Credential Helper / SSH-Key ohne Passphrase-Abfrage)
  7. python bot.py
"""

import asyncio
import datetime
import os
import sqlite3

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from export_stats import build_export, push_to_github

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "activity.db")
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

PUBLISH_TIMES = [
    datetime.time(hour=0, minute=0),
    datetime.time(hour=6, minute=0),
    datetime.time(hour=12, minute=0),
    datetime.time(hour=18, minute=0),
]

# ---------- Datenbank ----------

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            avatar_url TEXT,
            joined_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            char_length INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(user_id, channel_id, timestamp, char_length)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            left_at TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()


def upsert_member(user_id, username, avatar_url, joined_at=None):
    con = sqlite3.connect(DB_PATH)
    if joined_at is not None:
        con.execute("""
            INSERT INTO members (user_id, username, avatar_url, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                avatar_url=excluded.avatar_url,
                joined_at=COALESCE(members.joined_at, excluded.joined_at)
        """, (str(user_id), username, avatar_url, joined_at))
    else:
        con.execute("""
            INSERT INTO members (user_id, username, avatar_url, joined_at)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                avatar_url=excluded.avatar_url
        """, (str(user_id), username, avatar_url))
    con.commit()
    con.close()


def log_message(user_id, username, channel_id, channel_name, char_length):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT OR IGNORE INTO messages (user_id, username, channel_id, channel_name, char_length, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(user_id), username, str(channel_id), channel_name, char_length,
         datetime.datetime.utcnow().isoformat())
    )
    con.commit()
    con.close()


def log_voice_session(user_id, username, channel_id, channel_name, joined_at, left_at):
    duration = int((left_at - joined_at).total_seconds())
    if duration <= 0:
        return
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO voice_sessions (user_id, username, channel_id, channel_name, joined_at, left_at, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(user_id), username, str(channel_id), channel_name,
         joined_at.isoformat(), left_at.isoformat(), duration)
    )
    con.commit()
    con.close()

# ---------- Bot ----------

intents = discord.Intents.default()
intents.message_content = True   # nötig, auch wenn wir den Text nicht speichern
intents.voice_states = True
intents.members = True           # privilegiert - im Dev-Portal aktivieren

client = discord.Client(intents=intents)

# hält offene Voice-Sessions im Speicher: user_id -> (channel_id, channel_name, joined_at)
active_voice_sessions = {}


async def sync_members():
    for guild in client.guilds:
        async for member in guild.fetch_members(limit=None):
            if member.bot:
                continue
            joined_at = member.joined_at.replace(tzinfo=None).isoformat() if member.joined_at else None
            upsert_member(member.id, str(member), member.display_avatar.url, joined_at)


@client.event
async def on_ready():
    init_db()
    await sync_members()
    print(f"Eingeloggt als {client.user} — Aktivitäts-Tracking läuft.")
    if not scheduled_publish.is_running():
        scheduled_publish.start()


@client.event
async def on_member_join(member):
    if member.bot:
        return
    joined_at = member.joined_at.replace(tzinfo=None).isoformat() if member.joined_at else None
    upsert_member(member.id, str(member), member.display_avatar.url, joined_at)


@client.event
async def on_message(message):
    if message.author.bot:
        return
    if message.guild is None:
        return  # keine DMs tracken
    upsert_member(message.author.id, str(message.author), message.author.display_avatar.url)
    log_message(
        user_id=message.author.id,
        username=str(message.author),
        channel_id=message.channel.id,
        channel_name=getattr(message.channel, "name", "unknown"),
        char_length=len(message.content),
    )


@client.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    now = datetime.datetime.utcnow()
    upsert_member(member.id, str(member), member.display_avatar.url)

    # User verlässt einen Voice-Channel (oder wechselt)
    if before.channel is not None:
        session = active_voice_sessions.pop(member.id, None)
        if session:
            channel_id, channel_name, joined_at = session
            log_voice_session(member.id, str(member), channel_id, channel_name, joined_at, now)

    # User betritt einen Voice-Channel (oder wechselt in einen neuen)
    if after.channel is not None:
        active_voice_sessions[member.id] = (after.channel.id, after.channel.name, now)


@tasks.loop(time=PUBLISH_TIMES)
async def scheduled_publish():
    print(f"[{datetime.datetime.utcnow().isoformat()}] Starte geplanten Export + Veröffentlichung ...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _export_and_publish)


def _export_and_publish():
    try:
        build_export()
        push_to_github()
    except Exception as e:
        print(f"Fehler beim Export/Veröffentlichen: {e}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Bitte DISCORD_BOT_TOKEN setzen (Umgebungsvariable oder .env-Datei, "
            "siehe .env.example)."
        )
    client.run(TOKEN)
