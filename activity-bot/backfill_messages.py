"""
Backfill-Skript: lädt die KOMPLETTE bisherige Nachrichten-Historie
aller Text-Channels (inkl. Threads) eines Servers und speichert die
Metadaten (User, Channel, Zeitstempel, Länge — kein Nachrichtentext)
in dieselbe activity.db wie bot.py.

Läuft einmalig durch und beendet sich danach selbst. Je nach
Servergröße kann das je nach Nachrichtenmenge einige Minuten bis
Stunden dauern (Discord-Rate-Limits werden von discord.py automatisch
eingehalten).

Setup: wie bot.py (gleicher Token, gleiche Intents nötig)
Nutzung: python backfill_messages.py
"""

import os
import sqlite3
import datetime

import discord

DB_PATH = os.path.join(os.path.dirname(__file__), "activity.db")
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "HIER_DEIN_BOT_TOKEN_EINTRAGEN")
# Optional: nur einen bestimmten Server verarbeiten (Server-ID als String).
# Leer lassen, um alle Server zu verarbeiten, in denen der Bot Mitglied ist.
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
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
    con.commit()
    con.close()


def log_messages_bulk(rows):
    """rows: Liste von Tupeln (user_id, username, channel_id, channel_name, char_length, timestamp)"""
    if not rows:
        return
    con = sqlite3.connect(DB_PATH)
    con.executemany(
        "INSERT OR IGNORE INTO messages "
        "(user_id, username, channel_id, channel_name, char_length, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    con.commit()
    con.close()


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)


async def backfill_channel(channel):
    rows = []
    count = 0
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            if message.author.bot:
                continue
            rows.append((
                str(message.author.id),
                str(message.author),
                str(channel.id),
                getattr(channel, "name", "unknown"),
                len(message.content),
                message.created_at.replace(tzinfo=None).isoformat(),
            ))
            count += 1
            # alle 500 Nachrichten zwischenspeichern, um RAM zu sparen
            if len(rows) >= 500:
                log_messages_bulk(rows)
                rows = []
    except discord.Forbidden:
        print(f"  ⚠ Kein Zugriff auf #{getattr(channel, 'name', channel.id)} — übersprungen")
        return 0
    except discord.HTTPException as e:
        print(f"  ⚠ Fehler bei #{getattr(channel, 'name', channel.id)}: {e}")

    log_messages_bulk(rows)
    return count


@client.event
async def on_ready():
    init_db()
    print(f"Eingeloggt als {client.user}. Starte Backfill...\n")

    guilds = client.guilds
    if GUILD_ID:
        guilds = [g for g in guilds if str(g.id) == GUILD_ID]

    total = 0
    for guild in guilds:
        print(f"=== Server: {guild.name} ===")

        channels = list(guild.text_channels)
        # aktive Threads
        channels += list(guild.threads)
        # archivierte Threads pro Textchannel dazuholen
        for tc in guild.text_channels:
            try:
                async for thread in tc.archived_threads(limit=None):
                    channels.append(thread)
            except (discord.Forbidden, discord.HTTPException):
                pass

        for ch in channels:
            n = await backfill_channel(ch)
            total += n
            print(f"  #{getattr(ch, 'name', ch.id)}: {n} Nachrichten")

    print(f"\nFertig. Insgesamt {total} Nachrichten in {DB_PATH} gespeichert.")
    await client.close()


if __name__ == "__main__":
    if TOKEN == "HIER_DEIN_BOT_TOKEN_EINTRAGEN":
        raise SystemExit(
            "Bitte zuerst den Bot-Token eintragen (Zeile TOKEN = ...) "
            "oder als Umgebungsvariable DISCORD_BOT_TOKEN setzen."
        )
    client.run(TOKEN)
