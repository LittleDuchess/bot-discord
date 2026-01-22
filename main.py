import os
import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN manquant (Render > Environment Variables)")

TZ = ZoneInfo("Europe/Paris")
DATA_FILE = "server_data.json"

# -------------------- Stockage --------------------
# Structure:
# {
#   "guilds": {
#     "<guild_id>": {
#       "welcome_channel_name": "ladreamteam✨",
#       "birthday_channel_id": 123,
#       "staff_log_channel_id": 456,
#       "spam_channel_id": 789,
#       "required_role_id": 999,
#       "birthdays": { "<user_id>": "DD/MM" }
#     }
#   }
# }

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"guilds": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

def gcfg(guild_id: int):
    gid = str(guild_id)
    data["guilds"].setdefault(gid, {
        "welcome_channel_name": "ladreamteam✨",
        "birthday_channel_id": None,       # salon privé anniversaires
        "staff_log_channel_id": None,      # salon staff notif-bot
        "spam_channel_id": None,           # salon #☁️spambot
        "required_role_id": None,          # rôle requis: La dream team ✨
        "birthdays": {}                    # { user_id: "DD/MM" }
    })
    return data["guilds"][gid]

# -------------------- Parsing anniversaire --------------------
def parse_birthday(s: str) -> str:
    """
    Accepte:
      - 25-Oct
      - 25/10
      - 25-10
      - 25.10
    Stocke en "DD/MM"
    """
    s = s.strip()

    # formats numériques
    for sep in ["/", "-", "."]:
        if sep in s:
            parts = s.split(sep)
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                d = int(parts[0]); m = int(parts[1])
                if 1 <= d <= 31 and 1 <= m <= 12:
                    return f"{d:02d}/{m:02d}"

    # format 25-Oct
    try:
        dt = datetime.strptime(s.title(), "%d-%b")  # Oct, Nov, etc.
        return dt.strftime("%d/%m")
    except ValueError:
        raise ValueError("Format invalide")

def has_required_role(member: discord.Member, required_role_id: int | None) -> bool:
    if not required_role_id:
        return True
    return any(r.id == int(required_role_id) for r in member.roles)

# -------------------- Bot --------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # nécessaire pour !check + anti-spam bot messages
bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
# 1) Bienvenue + !check (comme ton bot)
# ============================================================

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    cfg = gcfg(guild.id)

    members = [m for m in guild.members if not m.bot]
    sorted_members = sorted(members, key=lambda m: m.joined_at or discord.utils.utcnow())
    member_number = next((i + 1 for i, m in enumerate(sorted_members) if m.id == member.id), None)

    welcome_message = (
        f"Hello ! {member.mention}\n"
        "Bienvenue dans la Dream Team ! ✨\n"
        f"Tu es le membre numéro **{member_number}** de notre team. 🙀"
    )

    channel = discord.utils.get(guild.text_channels, name=cfg.get("welcome_channel_name") or "ladreamteam✨")
    if channel:
        await channel.send(welcome_message)
    else:
        try:
            await member.send(welcome_message)
        except discord.Forbidden:
            pass

@bot.command()
async def check(ctx):
    guild = ctx.guild
    member = ctx.author

    members = [m for m in guild.members if not m.bot]
    sorted_members = sorted(members, key=lambda m: m.joined_at or discord.utils.utcnow())
    member_number = next((i + 1 for i, m in enumerate(sorted_members) if m.id == member.id), None)

    await ctx.send(f"Tu es le membre numéro **{member_number}** de la Dream Team ! ✨")

# ============================================================
# 2) Slash commands anniversaires (Carl/Birthday-bot style)
# ============================================================

birthday_group = app_commands.Group(name="birthday", description="Gestion des anniversaires")

@birthday_group.command(name="set", description="Enregistre ton anniversaire (ex: 25-Oct ou 25/10)")
@app_commands.describe(date="Ex: 25-Oct ou 25/10")
async def birthday_set(interaction: discord.Interaction, date: str):
    if not interaction.guild:
        return await interaction.response.send_message("Utilise ça dans un serveur.", ephemeral=True)

    cfg = gcfg(interaction.guild.id)
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return await interaction.response.send_message("Erreur: membre introuvable.", ephemeral=True)

    # 🔒 rôle requis
    if not has_required_role(member, cfg.get("required_role_id")):
        return await interaction.response.send_message(
            "🔒 Tu dois valider le règlement (rôle **La dream team ✨**) pour enregistrer ton anniversaire.",
            ephemeral=True
        )

    # parse date
    try:
        ddmm = parse_birthday(date)
    except ValueError:
        return await interaction.response.send_message(
            "❌ Format invalide. Exemples: `25-Oct` ou `25/10`",
            ephemeral=True
        )

    cfg["birthdays"][str(interaction.user.id)] = ddmm
    save_data(data)

    # ✅ réponse cachée utilisateur
    await interaction.response.send_message(
        "✅ Ton anniversaire est bien enregistré 🎂\n"
        "Hâte d’être à ce jour si spécial ✨",
        ephemeral=True
    )

    # 🔔 log staff (sans afficher la date)
    staff_log_id = cfg.get("staff_log_channel_id")
    if staff_log_id:
        ch = interaction.guild.get_channel(int(staff_log_id))
        if ch:
            await ch.send(f"🔔 **Anniversaire enregistré** : {interaction.user.mention} (`{interaction.user.id}`)")

@birthday_group.command(name="me", description="Affiche ton anniversaire enregistré (réponse cachée)")
async def birthday_me(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Utilise ça dans un serveur.", ephemeral=True)

    cfg = gcfg(interaction.guild.id)
    ddmm = cfg["birthdays"].get(str(interaction.user.id))
    if not ddmm:
        return await interaction.response.send_message(
            "ℹ️ Tu n’as pas encore enregistré ton anniversaire.\n"
            "Fais `/birthday set date:25-Oct`",
            ephemeral=True
        )
    await interaction.response.send_message(f"🎂 Ton anniversaire enregistré : **{ddmm}**", ephemeral=True)

@birthday_group.command(name="remove", description="Supprime ton anniversaire enregistré")
async def birthday_remove(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Utilise ça dans un serveur.", ephemeral=True)

    cfg = gcfg(interaction.guild.id)
    existed = cfg["birthdays"].pop(str(interaction.user.id), None)
    save_data(data)

    if existed:
        await interaction.response.send_message("🗑️ Ton anniversaire a été supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message("ℹ️ Tu n'avais pas d'anniversaire enregistré.", ephemeral=True)

    staff_log_id = cfg.get("staff_log_channel_id")
    if staff_log_id:
        ch = interaction.guild.get_channel(int(staff_log_id))
        if ch:
            await ch.send(f"🗑️ **Anniversaire supprimé** : {interaction.user.mention} (`{interaction.user.id}`)")

# -------- Setup admin (1 fois) --------
@birthday_group.command(name="set_channel", description="(Admin) Définit le salon (privé) d'anniversaires")
@app_commands.checks.has_permissions(administrator=True)
async def birthday_set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["birthday_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon anniversaires : {channel.mention}", ephemeral=True)

@birthday_group.command(name="set_stafflog", description="(Admin) Définit le salon staff 'notification bot'")
@app_commands.checks.has_permissions(administrator=True)
async def birthday_set_stafflog(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["staff_log_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon logs staff : {channel.mention}", ephemeral=True)

@birthday_group.command(name="set_spamchannel", description="(Admin) Définit le salon #☁️spambot pour logs/anti-spam")
@app_commands.checks.has_permissions(administrator=True)
async def birthday_set_spamchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["spam_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon spambot : {channel.mention}", ephemeral=True)

@birthday_group.command(name="set_required_role", description="(Admin) Définit le rôle requis (La dream team ✨)")
@app_commands.checks.has_permissions(administrator=True)
async def birthday_set_required_role(interaction: discord.Interaction, role: discord.Role):
    cfg = gcfg(interaction.guild.id)
    cfg["required_role_id"] = role.id
    save_data(data)
    await interaction.response.send_message(f"✅ Rôle requis : {role.mention}", ephemeral=True)

bot.tree.add_command(birthday_group)

# -------- Annonce jour J (09:00 Paris) --------
@tasks.loop(minutes=1)
async def birthday_daily_loop():
    now = datetime.now(TZ)
    if not (now.hour == 9 and now.minute == 0):
        return

    today = now.strftime("%d/%m")

    for guild in bot.guilds:
        cfg = gcfg(guild.id)
        bch_id = cfg.get("birthday_channel_id")
        if not bch_id:
            continue

        channel = guild.get_channel(int(bch_id))
        if not channel:
            continue

        todays_users = [uid for uid, ddmm in cfg["birthdays"].items() if ddmm == today]
        if not todays_users:
            continue

        mentions = " ".join(f"<@{uid}>" for uid in todays_users)
        await channel.send(f"🥳🎂 **Joyeux anniversaire** {mentions} !! 🎉✨")

# ============================================================
# 3) #☁️spambot : déplacer/log les messages de bots
# ============================================================
@bot.event
async def on_message(message: discord.Message):
    # Laisse fonctionner les commandes !check, etc.
    await bot.process_commands(message)

    # Ignore DMs
    if not message.guild:
        return

    # Déplacer/log les messages des AUTRES bots vers #☁️spambot
    if message.author.bot and message.author.id != bot.user.id:
        cfg = gcfg(message.guild.id)
        spam_id = cfg.get("spam_channel_id")
        if not spam_id:
            return

        spam_channel = message.guild.get_channel(int(spam_id))
        if not spam_channel:
            return

        # Ne touche pas aux messages déjà dans le salon spambot / staff / anniversaires
        protected_ids = {
            int(spam_id),
            int(cfg["staff_log_channel_id"]) if cfg.get("staff_log_channel_id") else -1,
            int(cfg["birthday_channel_id"]) if cfg.get("birthday_channel_id") else -1,
        }
        if message.channel.id in protected_ids:
            return

        # Essaie de supprimer dans le salon public
        try:
            content = message.content or ""
            attachments = [a.url for a in message.attachments]
            await message.delete()

            att_txt = ("\n📎 " + "\n📎 ".join(attachments)) if attachments else ""
            preview = content[:1500]

            await spam_channel.send(
                f"🤖 **Message bot déplacé** depuis {message.channel.mention}\n"
                f"**Bot :** {message.author} (`{message.author.id}`)\n"
                f"**Contenu :**\n{preview}{att_txt}"
            )
        except discord.Forbidden:
            # Le bot n'a pas Manage Messages ou pas accès
            pass
        except discord.HTTPException:
            pass

# -------------------- Ready --------------------
@bot.event
async def on_ready():
    print(f"🤖 Connecté en tant que {bot.user}")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands synchronisées: {len(synced)}")
    except Exception as e:
        print(f"⚠️ Sync slash commands impossible: {e}")

    if not birthday_daily_loop.is_running():
        birthday_daily_loop.start()

print("✅ Le bot est en train de démarrer...")
bot.run(TOKEN)
