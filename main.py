import os
import discord
from discord.ext import commands

# Récupération du token depuis Render (Environment Variables)
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN introuvable (Render > Environment Variables)")

# Intents nécessaires
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Création du bot
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Bot connecté en tant que {bot.user}")

# Événement : quand un nouveau membre rejoint
@bot.event
async def on_member_join(member):
    guild = member.guild

    # Membres humains uniquement
    members = [m for m in guild.members if not m.bot]

    # Sécurisation de joined_at (peut être None)
    sorted_members = sorted(
        members,
        key=lambda m: m.joined_at or discord.utils.utcnow()
    )

    # Position du membre
    member_number = next(
        (i + 1 for i, m in enumerate(sorted_members) if m.id == member.id),
        None
    )

    welcome_message = (
        f"Hello ! {member.mention}\n"
        "Bienvenue dans la Dream Team ! ✨\n"
        f"Tu es le membre numéro **{member_number}** de notre team. 🙀"
    )

    # Salon de bienvenue
    channel = discord.utils.get(guild.text_channels, name="ladreamteam✨")

    if channel:
        await channel.send(welcome_message)
    else:
        try:
            await member.send(welcome_message)
        except discord.Forbidden:
            print("⚠️ Impossible d'envoyer le message de bienvenue en DM")

# Commande !check
@bot.command()
async def check(ctx):
    guild = ctx.guild
    member = ctx.author

    members = [m for m in guild.members if not m.bot]
    sorted_members = sorted(
        members,
        key=lambda m: m.joined_at or discord.utils.utcnow()
    )

    member_number = next(
        (i + 1 for i, m in enumerate(sorted_members) if m.id == member.id),
        None
    )

    await ctx.send(
        f"Tu es le membre numéro **{member_number}** de la Dream Team ! ✨"
    )

# Lancement du bot
print("✅ Le bot est en train de démarrer...")
bot.run(TOKEN)
