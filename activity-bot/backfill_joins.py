"""
Backfill-Skript: rekonstruiert historische Beitrittsdaten aus dem
Carl-bot Join/Leave-Log-Channel (#join-leave) und speichert sie in
activity.db (Tabelle "members"), damit auch länger zurückliegende oder
mittlerweile wieder verlassene Mitglieder in der Rangliste ein korrektes
Beitrittsdatum haben.

Carl-bot postet dort pro Beitritt ein Embed:
  title:       "Member joined"
  footer.text: "ID: {user_id}"
  author.name: Username zum Zeitpunkt des Beitritts

Events werden chronologisch (älteste zuerst) verarbeitet, sodass am Ende
- für aktuelle Mitglieder derselbe (letzte) Beitrittszeitpunkt steht, den
  auch bot.py per Discord-API live ermitteln würde
- für mittlerweile ausgetretene Mitglieder trotzdem ein Beitrittsdatum
  erhalten bleibt

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
    print(f"Eingeloggt als {client.user}. Starte Join-Backfill...\n")

    channel = client.get_channel(int(CHANNEL_ID))
    if channel is None:
        print(f"Channel {CHANNEL_ID} nicht gefunden (falscher Server / keine Berechtigung?).")
        await client.close()
        return

    imported = 0
    skipped_bots = 0
    seen = 0

    async for message in channel.history(limit=None, oldest_first=True):
        if not message.embeds:
            continue
        embed = message.embeds[0]
        if embed.title != "Member joined":
            continue
        if not embed.footer or not embed.footer.text or not embed.footer.text.startswith("ID: "):
            continue
        seen += 1
        user_id = embed.footer.text.replace("ID: ", "").strip()

        if await is_bot_account(user_id):
            skipped_bots += 1
            continue

        username = embed.author.name if embed.author else "Unbekannt"
        joined_at = message.created_at.replace(tzinfo=None).isoformat()
        upsert_join(user_id, username, joined_at)
        imported += 1

    print(f"\nFertig. {seen} Beitritts-Events gelesen, {imported} in {DB_PATH} gespeichert, "
          f"{skipped_bots} Bot-Events übersprungen.")
    await client.close()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Bitte DISCORD_BOT_TOKEN setzen (Umgebungsvariable oder .env-Datei)."
        )
    client.run(TOKEN)
