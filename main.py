import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# Charger le token depuis le fichier .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    print("❌ Erreur : le token n'a pas été trouvé dans le fichier .env !")
    exit()

# Intents nécessaires
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Création du bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Événement : quand un nouveau membre rejoint
@bot.event
async def on_member_join(member):
    guild = member.guild

    # Obtenir la liste des membres humains triés par date d'arrivée
    members = [m for m in guild.members if not m.bot]
    sorted_members = sorted(members, key=lambda m: m.joined_at)

    # Trouver la position du nouveau membre
    member_number = next((i + 1 for i, m in enumerate(sorted_members) if m.id == member.id), None)

    # Message de bienvenue
    welcome_message = (
        f"Hello ! {member.mention}\n"
        "Bienvenue dans la Dream Team ! ✨\n"
        f"Tu es le membre numéro **{member_number}** de notre team. 🙀"
    )

    # Chercher le salon #ladreamteam✨
    channel = discord.utils.get(guild.text_channels, name="ladreamteam✨")

    if channel:
        await channel.send(welcome_message)
    else:
        await member.send(welcome_message)

# Commande !check
@bot.command()
async def check(ctx):
    guild = ctx.guild
    member = ctx.author

    members = [m for m in guild.members if not m.bot]
    sorted_members = sorted(members, key=lambda m: m.joined_at)
    member_number = next((i + 1 for i, m in enumerate(sorted_members) if m.id == member.id), None)

    await ctx.send(f"Tu es le membre numéro **{member_number}** de la Dream Team ! ✨")

# Lancement du bot
print("✅ Le bot est en train de démarrer...")
bot.run(TOKEN)
