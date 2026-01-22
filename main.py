import os
import json
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN manquant (Render > Environment Variables)")

DATA_FILE = "config.json"

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
        "welcome_channel_id": None,  # <-- on met l'ID, pas le nom
        "required_role_id": None,    # "La dream team ✨"
        "staff_log_channel_id": None # optionnel
    })
    return data["guilds"][gid]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- VIEW BOUTON RÈGLEMENT --------------------
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
                "⚠️ Rôle non configuré. Admin: `/rules set_role @La dream team ✨`",
                ephemeral=True
            )

        role = interaction.guild.get_role(int(role_id))
        if not role:
            return await interaction.response.send_message(
                "⚠️ Le rôle configuré n’existe plus.",
                ephemeral=True
            )

        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return await interaction.response.send_message("Erreur: membre introuvable.", ephemeral=True)

        if role in member.roles:
            return await interaction.response.send_message(
                "✅ Tu as déjà le rôle **La dream team ✨**.",
                ephemeral=True
            )

        # Tentative d’ajout de rôle
        try:
            await member.add_roles(role, reason="Validation du règlement")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Je ne peux pas donner le rôle.\n"
                "👉 Vérifie : le bot a **Gérer les rôles** et que son rôle est AU-DESSUS de `La dream team ✨`.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "✅ Bienvenue dans **La dream team ✨** !",
            ephemeral=True
        )

        # log staff optionnel
        staff_log_id = cfg.get("staff_log_channel_id")
        if staff_log_id:
            ch = interaction.guild.get_channel(int(staff_log_id))
            if ch:
                await ch.send(f"✅ Règlement validé : {member.mention} (`{member.id}`)")

# -------------------- COMMANDES SLASH SETUP --------------------
rules = app_commands.Group(name="rules", description="Règlement / validation")

@rules.command(name="set_role", description="(Admin) Définit le rôle donné quand on valide le règlement")
@app_commands.checks.has_permissions(administrator=True)
async def set_role(interaction: discord.Interaction, role: discord.Role):
    cfg = gcfg(interaction.guild.id)
    cfg["required_role_id"] = role.id
    save_data(data)
    await interaction.response.send_message(f"✅ Rôle défini : {role.mention}", ephemeral=True)

@rules.command(name="set_welcome", description="(Admin) Définit le salon de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["welcome_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon de bienvenue : {channel.mention}", ephemeral=True)

@rules.command(name="set_stafflog", description="(Admin) Définit le salon de logs staff (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def set_stafflog(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["staff_log_channel_id"] = channel.id
    save_data(data)
    await interaction.response.send_message(f"✅ Salon logs staff : {channel.mention}", ephemeral=True)

@rules.command(name="post", description="(Admin) Poste le message du règlement + bouton dans ce salon")
@app_commands.checks.has_permissions(administrator=True)
async def post(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Règlement",
        description="Lis le règlement puis clique sur **Valider le règlement** pour accéder au serveur."
    )
    await interaction.channel.send(embed=embed, view=RulesView())
    await interaction.response.send_message("✅ Règlement posté.", ephemeral=True)

bot.tree.add_command(rules)

# -------------------- BIENVENUE (SALON ID) --------------------
@bot.event
async def on_member_join(member: discord.Member):
    cfg = gcfg(member.guild.id)

    # calc numéro de membre (humains)
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
        except discord.Forbidden:
            # si le bot ne peut pas écrire -> DM fallback
            try:
                await member.send(welcome_message)
            except discord.Forbidden:
                pass
    else:
        # si salon pas configuré -> DM fallback
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

@bot.event
async def on_ready():
    print(f"🤖 Connecté en tant que {bot.user}")
    bot.add_view(RulesView())  # rend le bouton persistant après redémarrage
    await bot.tree.sync()
    print("✅ Slash commands synchronisées.")

print("✅ Le bot est en train de démarrer...")
bot.run(TOKEN)
