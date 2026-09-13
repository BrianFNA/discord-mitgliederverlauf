"""
Dumpt die komplette Nachrichten-Historie EINES Channels (z. B. #voice)
roh in eine Textdatei - Text-Content UND Embed-Inhalte, damit wir sehen,
in welchem Format Carl-bot die Voice-Logs tatsächlich postet.

Nutzt denselben Bot-Token wie bot.py / backfill_messages.py.
Der Bot muss im Zielserver sein und den Channel sehen können
(View Channel + Read Message History).

Nutzung:
  1. Erst ohne CHANNEL_ID starten -> listet alle Text-Channels mit ID auf
  2. Channel-ID des Voice-Log-Channels als DISCORD_CHANNEL_ID setzen
     (Umgebungsvariable) oder unten eintragen
  3. Nochmal starten -> schreibt voicelog_raw_dump.txt
"""

import os
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "HIER_DEIN_BOT_TOKEN_EINTRAGEN")
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")  # z.B. "123456789012345678"
OUT_PATH = os.path.join(os.path.dirname(__file__), "voicelog_raw_dump.txt")
MAX_MESSAGES = 300  # für den ersten Test bewusst klein halten

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Eingeloggt als {client.user}\n")

    if not CHANNEL_ID:
        print("Keine CHANNEL_ID gesetzt. Verfügbare Text-Channels:\n")
        for guild in client.guilds:
            print(f"=== {guild.name} ===")
            for ch in guild.text_channels:
                print(f"  #{ch.name}  ->  ID: {ch.id}")
        print("\nSetze DISCORD_CHANNEL_ID auf die passende ID und starte erneut.")
        await client.close()
        return

    channel = client.get_channel(int(CHANNEL_ID))
    if channel is None:
        print(f"Channel mit ID {CHANNEL_ID} nicht gefunden (falscher Server / keine Berechtigung?).")
        await client.close()
        return

    print(f"Lese die letzten {MAX_MESSAGES} Nachrichten aus #{channel.name} ...")
    lines = []
    count = 0
    async for message in channel.history(limit=MAX_MESSAGES, oldest_first=False):
        lines.append(f"--- Message {message.id} | {message.created_at.isoformat()} | Autor: {message.author} ---")
        lines.append(f"content: {message.content!r}")
        if message.embeds:
            for i, emb in enumerate(message.embeds):
                lines.append(f"  embed[{i}].title:       {emb.title!r}")
                lines.append(f"  embed[{i}].description: {emb.description!r}")
                lines.append(f"  embed[{i}].author.name: {emb.author.name if emb.author else None!r}")
                lines.append(f"  embed[{i}].footer.text: {emb.footer.text if emb.footer else None!r}")
                for f in emb.fields:
                    lines.append(f"  embed[{i}].field: {f.name!r} -> {f.value!r}")
        lines.append("")
        count += 1

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Fertig. {count} Nachrichten roh gespeichert in {OUT_PATH}")
    await client.close()


if __name__ == "__main__":
    if TOKEN == "HIER_DEIN_BOT_TOKEN_EINTRAGEN":
        raise SystemExit(
            "Bitte zuerst den Bot-Token eintragen (Zeile TOKEN = ...) "
            "oder als Umgebungsvariable DISCORD_BOT_TOKEN setzen."
        )
    client.run(TOKEN)
