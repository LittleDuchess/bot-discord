import os
import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN introuvable. Ajoute-le dans Render > Environment Variables.")

TZ = ZoneInfo("Europe/Paris")
DATA_FILE = "bot_data.json"

# Structure:
# {
#   "guilds": {
#     "<guild_id>": {
#       "welcome_channel_id": <int|None>,
#       "required_role_id": <int|None>,       # rôle "La dream team ✨"
#       "staff_log_channel_id": <int|None>,   # optionnel
#       "birthday_channel_id": <int|None>,    # salon anniversaires
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
        "welcome_channel_id": None,
        "required_role_id": None,
        "staff_log_channel_id": None,
        "birthday_channel_id": None,
        "birthdays": {}
    })
    return data["guilds"][gid]

# ============================================================
# HELPERS
# ============================================================

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
    dt = datetime.strptime(s.title(), "%d-%b")
    return dt.strftime("%d/%m")

# ============================================================
# BOT INIT
# ============================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # pour !check

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
# 1) RÈGLEMENT -> BOUTON -> DONNE LE RÔLE
# ============================================================

class RulesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Valider le règlement",
        style=discord.ButtonStyle.success,
        custom_id="rules:validate"
    )
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message("Utilise ça dans un serveur.", ephemeral=True)

        cfg = gcfg(interaction.guild.id)
        role_id = cfg.get("required_role_id")

        if not role_id:
            return await interaction.response.send_message(
                "⚠️ Le rôle n’est pas configuré.\nAdmin : `/rules set_role @La dream team ✨`",
                ephemeral=True
            )

        role = interaction.guild.get_role(int(role_id))
        if not role:
            return await interaction.response.send_message(
                "⚠️ Le rôle configuré n’existe plus. Admin : `/rules set_role ...`",
                ephemeral=True
            )

        # ✅ Toujours récupérer un Member à jour (cache = pas fiable)
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.NotFound:
            return await interaction.response.send_message("Erreur: membre introuvable.", ephemeral=True)

        if role in member.roles:
            return await interaction.response.send_message(
                "✅ Tu as déjà accès à **La dream team ✨**.",
                ephemeral=True
            )

        try:
            await member.add_roles(role, reason="Validation du règlement")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Je ne peux pas attribuer le rôle.\n"
                "👉 Vérifie : le bot a **Gérer les rôles** et que son rôle est **au-dessus** de `La dream team ✨`.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "✅ Bienvenue dans **La dream team ✨** !\nTu as maintenant accès au serveur 💙",
            ephemeral=True
        )

        staff_log_id = cfg.get("staff_log_channel_id")
        if staff_log_id:
            ch = interaction.guild.get_channel(int(staff_log_id))
            if ch:
                await ch.send(f"✅ **Règlement validé** : {member.mention} (`{member.id}`)")

rules_group = app_commands.Group(name="rules", description="Règlement / validation")

@rules_group.command(name="set_role", description="(Admin) Définit le rôle donné après validation")
@app_commands.checks.has_permissions(administrator=True)
async def rules_set_role(interaction: discord.Interaction, role: discord.Role):
    cfg = gcfg(interaction.guild.id)
    cfg["required_role_id"] = role.id
    save_data(data)
    await interaction.response.send_message(f"✅ Rôle de validation défini : {role.mention}", ephemeral=True)

@rules_group.command(name="set_welcome", description="(Admin) Définit le salon de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def rules_set_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["welcome_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon de bienvenue défini : {channel.mention}", ephemeral=True)

@rules_group.command(name="set_stafflog", description="(Admin) Définit le salon logs staff (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def rules_set_stafflog(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["staff_log_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salonôle logs staff défini : {channel.mention}", ephemeral=True)

@rules_group.command(name="post", description="(Admin) Poste le règlement + bouton dans ce salon")
@app_commands.checks.has_permissions(administrator=True)
async def rules_post(interaction: discord.Interaction):
    if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("Utilise ça dans un salon texte.", ephemeral=True)

    rules_text = (
        ":sparkles: **Règlement du serveur discord**\n"
        "Le non-respect des règles peuvent entrainer un bannissement partiel ou définitif.\n\n"
        ":one: **Âge minimum**\n"
        "Ce serveur est réservé aux personnes âgées de 13 ans ou plus, conformément aux règles de Discord.\n"
        "Si vous avez moins de 13 ans, merci de quitter le serveur immédiatement.\n\n"
        ":two: **Respect & Comportement**\n"
        "Soyez respectueux, poli(e)s et bienveillant(e)s envers tous les membres.\n"
        "Pas d’insultes, moqueries, discriminations, harcèlement ou comportements toxiques.\n"
        "Pas d’usurpation d’identité (membre, modérateur, bot, etc.).\n\n"
        ":three: **Contenu & Partages**\n"
        "Contenu NSFW interdit : pas de contenu adulte, choquant ou gore.\n"
        "Pas de propos haineux ou discriminatoires (sexisme, racisme, homophobie, etc.).\n"
        "Pas de partage d’informations personnelles (les vôtres ou celles des autres).\n"
        "Les spoilers doivent être cachés avec la balise spoiler.\n\n"
        ":four: **Publicité & Spam**\n"
        "Publicité interdite sans l’accord du staff (serveurs, liens commerciaux, autopromo).\n"
        "Pas de spam : pas de messages répétés, d’abus d’emojis ou de mentions.\n\n"
        ":five: **Sujets sensibles**\n"
        "Les discussions sur la religion, politique, sexualité ou autres sujets polémiques sont interdites pour préserver une bonne ambiance.\n\n"
        ":six: **Utilisation des salons**\n"
        "Respectez les thèmes des salons : postez dans les bons channels.\n"
        "Ne pas déranger les vocaux avec des bruits gênants, cris ou musiques sans l’accord des participants.\n\n"
        ":seven: **Pseudo & Avatar**\n"
        "Choisissez un pseudo et un avatar corrects et lisibles.\n"
        "Pas de pseudos ou images choquantes, sexuelles, provocantes ou discriminatoires.\n\n"
        ":eight: **Comportement en vocal**\n"
        "Soyez respectueux aussi bien à l’oral qu’à l’écrit.\n"
        "Pas d’abus de bruit, d’interruptions ou de comportement gênant.\n\n"
        ":nine: **Modération & Sanctions**\n"
        "Les décisions du staff doivent être respectées.\n"
        "En cas de problème, contactez un modérateur en MP.\n\n"
        ":warning: **Pensez à cliquer sur le bouton ✅ pour voir le serveur entier.**"
    )

    embed = discord.Embed(title="📜 Règlement", description=rules_text)
    await interaction.channel.send(embed=embed, view=RulesView())
    await interaction.response.send_message("✅ Règlement posté avec le bouton.", ephemeral=True)

bot.tree.add_command(rules_group)

# ============================================================
# 2) BIENVENUE + !check
# ============================================================

@bot.event
async def on_member_join(member: discord.Member):
    cfg = gcfg(member.guild.id)

    members = [m for m in member.guild.members if not m.bot]
    sorted_members = sorted(members, key=lambda m: m.joined_at or discord.utils.utcnow())
    member_number = next((i + 1 for i, m in enumerate(sorted_members) if m.id == member.id), None)

    welcome_message = (
        f"Hello ! {member.mention}\n"
        "Bienvenue dans la Dream Team ! ✨\n"
        f"Tu es le membre numéro **{member_number}** de notre team. 🙀"
    )

    channel_id = cfg.get("welcome_channel_id")
    channel = member.guild.get_channel(int(channel_id)) if channel_id else None

    if channel:
        try:
            await channel.send(welcome_message)
            return
        except discord.Forbidden:
            pass

    try:
        await member.send(welcome_message)
    except discord.Forbidden:
        pass

@bot.command()
async def check(ctx):
    members = [m for m in ctx.guild.members if not m.bot]
    sorted_members = sorted(members, key=lambda m: m.joined_at or discord.utils.utcnow())
    member_number = next((i + 1 for i, m in enumerate(sorted_members) if m.id == ctx.author.id), None)
    await ctx.send(f"Tu es le membre numéro **{member_number}** de la Dream Team ! ✨")

# ============================================================
# 3) ANNIVERSAIRES (/birthday) - FIXED member fetch
# ============================================================

birthday_group = app_commands.Group(name="birthday", description="Anniversaires")

@birthday_group.command(name="set", description="Enregistre ton anniversaire (ex: 25-Oct ou 25/10)")
@app_commands.describe(date="Ex: 25-Oct ou 25/10")
async def birthday_set(interaction: discord.Interaction, date: str):
    if not interaction.guild:
        return await interaction.response.send_message("Utilise ça dans un serveur.", ephemeral=True)

    cfg = gcfg(interaction.guild.id)

    # ✅ Toujours récupérer un Member à jour (cache = pas fiable)
    try:
        member = await interaction.guild.fetch_member(interaction.user.id)
    except discord.NotFound:
        return await interaction.response.send_message("Erreur: membre introuvable.", ephemeral=True)

    # réservé aux validés (si rôle configuré)
    role_id = cfg.get("required_role_id")
    if role_id:
        required_role = interaction.guild.get_role(int(role_id))
        if required_role and required_role not in member.roles:
            return await interaction.response.send_message(
                "🔒 Tu dois valider le règlement (rôle **La dream team ✨**) pour enregistrer ton anniversaire.",
                ephemeral=True
            )

    try:
        ddmm = parse_birthday(date)
    except Exception:
        return await interaction.response.send_message(
            "❌ Format invalide. Exemples: `25-Oct` ou `25/10`",
            ephemeral=True
        )

    cfg["birthdays"][str(interaction.user.id)] = ddmm
    save_data(data)

    await interaction.response.send_message(
        "✅ Ton anniversaire est bien enregistré 🎂\nHâte d’être à ce jour si spécial ✨",
        ephemeral=True
    )

@birthday_group.command(name="me", description="Affiche ton anniversaire enregistré (réponse cachée)")
async def birthday_me(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Utilise ça dans un serveur.", ephemeral=True)

    cfg = gcfg(interaction.guild.id)
    ddmm = cfg["birthdays"].get(str(interaction.user.id))
    if not ddmm:
        return await interaction.response.send_message(
            "ℹ️ Tu n’as pas encore enregistré ton anniversaire.\nFais `/birthday set date:25-Oct`",
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

    await interaction.response.send_message(
        "🗑️ Anniversaire supprimé." if existed else "ℹ️ Aucun anniversaire enregistré.",
        ephemeral=True
    )

@birthday_group.command(name="set_channel", description="(Admin) Définit le salon où le bot annonce les anniversaires")
@app_commands.checks.has_permissions(administrator=True)
async def birthday_set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["birthday_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon anniversaires défini : {channel.mention}", ephemeral=True)

bot.tree.add_command(birthday_group)

@tasks.loop(minutes=1)
async def birthday_daily_loop():
    # envoie à 09:00 (Paris) le jour J
    now = datetime.now(TZ)
    if not (now.hour == 9 and now.minute == 0):
        return

    today = now.strftime("%d/%m")

    for guild in bot.guilds:
        cfg = gcfg(guild.id)
        ch_id = cfg.get("birthday_channel_id")
        if not ch_id:
            continue

        channel = guild.get_channel(int(ch_id))
        if not channel:
            continue

        todays_users = [uid for uid, ddmm in cfg["birthdays"].items() if ddmm == today]
        if not todays_users:
            continue

        mentions = " ".join(f"<@{uid}>" for uid in todays_users)
        await channel.send(f"🥳🎂 **Joyeux anniversaire** {mentions} !! 🎉✨")

# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():
    print(f"🤖 Connecté en tant que {bot.user}")
    bot.add_view(RulesView())  # bouton persistant après redémarrage
    await bot.tree.sync()
    print("✅ Slash commands synchronisées.")

    if not birthday_daily_loop.is_running():
        birthday_daily_loop.start()

print("✅ Le bot est en train de démarrer...")
bot.run(TOKEN)
