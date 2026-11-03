"""
Backfill-Skript für Lücken: holt Nachrichten, Voice-Sessions (aus Carl-bots
#voice) und Beitritte/Austritte (aus #join-leave) für einen bestimmten
Zeitraum nach, z. B. wenn bot.py wegen eines Netzausfalls nicht lief.

Anders als die vollen Backfill-Skripte liest es nur das Zeitfenster und
fasst bereits live erfasste Daten nicht an:
- bot.py speichert bei Nachrichten die Empfangszeit, die API liefert die
  Erstellzeit -> Nachrichten werden nur im Fenster eingetragen, das live
  nichts enthält (deshalb --to knapp vor den ersten Live-Daten wählen)
- Voice-Sessions, die sich mit einer vorhandenen Session desselben Users
  überschneiden, werden übersprungen

Vorher bot.py stoppen (ein Prozess pro Token).

Nutzung (Zeiten in UTC):
  python backfill_gap.py --from 2026-10-09T18:23:42 --to 2026-10-27T13:18:40 --dry-run
  python backfill_gap.py --from 2026-10-09T18:23:42 --to 2026-10-27T13:18:40
"""

import argparse
import collections
import datetime
import os
import sqlite3

import discord
from dotenv import load_dotenv

from backfill_voice import DESC_RE, MAX_SESSION_SECONDS

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "activity.db")
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")
VOICE_CHANNEL_ID = os.environ.get("DISCORD_VOICE_LOG_CHANNEL_ID", "889201063410941962")
JOIN_CHANNEL_ID = os.environ.get("DISCORD_JOIN_LEAVE_CHANNEL_ID", "889200831436570738")

parser = argparse.ArgumentParser()
parser.add_argument("--from", dest="start", required=True, type=datetime.datetime.fromisoformat)
parser.add_argument("--to", dest="end", required=True, type=datetime.datetime.fromisoformat)
parser.add_argument("--dry-run", action="store_true", help="nur zählen, nichts speichern")
args = parser.parse_args()
UTC = datetime.timezone.utc
START, END = args.start.replace(tzinfo=UTC), args.end.replace(tzinfo=UTC)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
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


def naive(dt):
    return dt.replace(tzinfo=None)


async def collect_messages(guild):
    channels = list(guild.text_channels) + list(guild.threads)
    for tc in guild.text_channels:
        try:
            async for thread in tc.archived_threads(limit=None):
                if thread.archive_timestamp and thread.archive_timestamp >= START:
                    channels.append(thread)
        except (discord.Forbidden, discord.HTTPException):
            pass
    rows = []
    for ch in channels:
        try:
            async for m in ch.history(limit=None, after=START, before=END, oldest_first=True):
                if m.author.bot:
                    continue
                rows.append((str(m.author.id), str(m.author), str(ch.id), getattr(ch, "name", "unknown"),
                             len(m.content), naive(m.created_at).isoformat()))
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"  ⚠ #{getattr(ch, 'name', ch.id)} übersprungen: {e}")
    return rows


async def collect_voice():
    channel = client.get_channel(int(VOICE_CHANNEL_ID))
    open_sessions, sessions = {}, []
    # einen Tag Vorlauf, damit Sessions erfasst werden, die kurz vor dem Fenster begannen
    async for m in channel.history(limit=None, after=START - datetime.timedelta(days=1),
                                   before=END + datetime.timedelta(days=1), oldest_first=True):
        if not m.embeds:
            continue
        e = m.embeds[0]
        if e.title not in ("Member joined voice channel", "Member left voice channel"):
            continue
        if not e.footer or not e.footer.text or not e.footer.text.startswith("ID: "):
            continue
        user_id = e.footer.text.replace("ID: ", "").strip()
        if await is_bot_account(user_id):
            continue
        username = e.author.name if e.author else "Unbekannt"
        channel_name = "unknown"
        if e.description:
            dm = DESC_RE.match(e.description)
            if dm:
                username, channel_name = dm.group(1), dm.group(2)
        ts = naive(m.created_at)
        if e.title == "Member joined voice channel":
            open_sessions[user_id] = (username, channel_name, ts)
        elif user_id in open_sessions:
            name, ch, joined = open_sessions.pop(user_id)
            dur = int((ts - joined).total_seconds())
            if naive(START) <= joined < naive(END) and 0 < dur <= MAX_SESSION_SECONDS:
                sessions.append((user_id, name, "", ch, joined.isoformat(), ts.isoformat(), dur))
    return sessions


async def collect_member_events():
    channel = client.get_channel(int(JOIN_CHANNEL_ID))
    events = []
    async for m in channel.history(limit=None, after=START, before=END, oldest_first=True):
        if not m.embeds:
            continue
        e = m.embeds[0]
        if e.title not in ("Member joined", "Member left"):
            continue
        if not e.footer or not e.footer.text or not e.footer.text.startswith("ID: "):
            continue
        user_id = e.footer.text.replace("ID: ", "").strip()
        if await is_bot_account(user_id):
            continue
        events.append((user_id, e.author.name if e.author else "Unbekannt",
                       "join" if e.title == "Member joined" else "leave", naive(m.created_at).isoformat()))
    return events


def save(messages, sessions, events):
    con = sqlite3.connect(DB_PATH)
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO messages (user_id, username, channel_id, channel_name, char_length, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)", messages)
    n_msg = con.total_changes - before

    n_voice = 0
    for s in sessions:
        overlap = con.execute(
            "SELECT 1 FROM voice_sessions WHERE user_id = ? AND joined_at < ? AND left_at > ? LIMIT 1",
            (s[0], s[5], s[4])).fetchone()
        if not overlap:
            n_voice += con.execute(
                "INSERT OR IGNORE INTO voice_sessions (user_id, username, channel_id, channel_name, "
                "joined_at, left_at, duration_seconds) VALUES (?, ?, ?, ?, ?, ?, ?)", s).rowcount

    before = con.total_changes
    con.executemany("INSERT OR IGNORE INTO member_events (user_id, username, event_type, timestamp) "
                    "VALUES (?, ?, ?, ?)", events)
    n_ev = con.total_changes - before
    # neue Mitglieder anlegen, damit sie in den Ranglisten auftauchen (bestehende nicht überschreiben)
    for user_id, username, kind, ts in events:
        if kind == "join":
            con.execute("INSERT OR IGNORE INTO members (user_id, username, avatar_url, joined_at) "
                        "VALUES (?, ?, NULL, ?)", (user_id, username, ts))
    con.commit()
    con.close()
    return n_msg, n_voice, n_ev


def per_day(rows, idx):
    c = collections.Counter(r[idx][:10] for r in rows)
    return ", ".join(f"{d[5:]}: {n}" for d, n in sorted(c.items())) or "-"


@client.event
async def on_ready():
    print(f"Eingeloggt als {client.user}. Lücke {START:%Y-%m-%d %H:%M} bis {END:%Y-%m-%d %H:%M} UTC\n")
    guilds = [g for g in client.guilds if not GUILD_ID or str(g.id) == GUILD_ID]
    messages = []
    for g in guilds:
        messages += await collect_messages(g)
    sessions = await collect_voice()
    events = await collect_member_events()

    print(f"Nachrichten:   {len(messages)}  ({per_day(messages, 5)})")
    print(f"Voice:         {len(sessions)}  ({per_day(sessions, 4)})")
    print(f"Beitritte/Aus: {len(events)}  ({per_day(events, 3)})")
    if args.dry_run:
        print("\n--dry-run: nichts gespeichert.")
    else:
        n_msg, n_voice, n_ev = save(messages, sessions, events)
        print(f"\nGespeichert: {n_msg} Nachrichten, {n_voice} Voice-Sessions, {n_ev} Mitglieder-Events.")
    await client.close()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN fehlt in .env")
    client.run(TOKEN, log_handler=None)
