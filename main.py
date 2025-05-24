import os
import discord
from discord.ext import commands, tasks
import asyncpg
from discord import app_commands

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

RANKS = {
    "Iron": "Iron",
    "Bronze": "Bronze",
    "Silver": "Silver",
    "Gold": "Gold",
    "Platinum": "Platinum",
    "Diamond": "Diamond",
    "Immortal": "Immortal",
    "Radiant": "Radiant"
}

db_pool = None

async def create_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

@bot.event
async def on_ready():
    global db_pool
    print(f"Connecté en tant que {bot.user}")
    try:
        db_pool = await create_db_pool()

        async with db_pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS roles_valorant (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                tag TEXT NOT NULL,
                rank TEXT NOT NULL
            )
            """)

        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
        print("Commandes synchronisées")

        update_roles.start()

    except Exception as e:
        print(f"Erreur dans on_ready : {e}")

@bot.tree.command(name="link", description="Lie ton compte Valorant (pseudo#tag)")
@app_commands.describe(tag="Ton tag Valorant (ex: pseudo#1234)")
async def link(interaction: discord.Interaction, tag: str):
    await interaction.response.defer(ephemeral=True)
    if "#" not in tag:
        await interaction.followup.send(embed=discord.Embed(
            title="Erreur",
            description="Format invalide. Exemple : pseudo#1234",
            color=discord.Color.red()
        ), ephemeral=True)
        return

    username, usertag = tag.split("#", 1)
    user_id = str(interaction.user.id)
    rank = "Silver"  # Placeholder

    async with db_pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO roles_valorant(user_id, username, tag, rank)
        VALUES($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, tag = EXCLUDED.tag, rank = EXCLUDED.rank
        """, user_id, username, usertag, rank)

    await interaction.followup.send(embed=discord.Embed(
        title="Compte lié",
        description=f"Le compte `{tag}` a été lié avec le rang `{rank}`.",
        color=discord.Color.green()
    ), ephemeral=True)

@bot.tree.command(name="unlink", description="Délie ton compte Valorant")
async def unlink(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM roles_valorant WHERE user_id=$1", user_id)
    await interaction.response.send_message(embed=discord.Embed(
        title="Compte délié",
        description="Ton compte Valorant a bien été délié.",
        color=discord.Color.orange()
    ), ephemeral=True)

async def fetch_rank_from_api(username, tag):
    # À remplacer par un vrai appel API plus tard
    return "Silver"

@tasks.loop(hours=24)
async def update_roles():
    print("Mise à jour des rôles Valorant...")
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Serveur non trouvé.")
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, tag, rank FROM roles_valorant")

    for row in rows:
        user_id = int(row['user_id'])
        username = row['username']
        tag = row['tag']
        old_rank = row['rank']

        member = guild.get_member(user_id)
        if not member:
            continue

        new_rank = await fetch_rank_from_api(username, tag)

        if new_rank != old_rank:
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE roles_valorant SET rank=$1 WHERE user_id=$2", new_rank, str(user_id))

            roles_to_remove = [discord.utils.get(guild.roles, name=r) for r in RANKS.values()]
            for r in roles_to_remove:
                if r and r in member.roles:
                    await member.remove_roles(r, reason="Mise à jour rang Valorant")

            role = discord.utils.get(guild.roles, name=new_rank)
            if role is None:
                role = await guild.create_role(name=new_rank, reason="Rôle Valorant créé automatiquement")

            await member.add_roles(role, reason="Mise à jour rang Valorant")

    print("Mise à jour terminée.")

bot.run(TOKEN)
