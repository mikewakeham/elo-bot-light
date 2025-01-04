import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from discord import app_commands
from gspread.exceptions import GSpreadException
import re
import asyncio
from util import *

DC_VERIFIED_ROLE_ID = 1323577921981648906
VERIFIED_ROLE_ID = 1323577899894181888
PRIVILEGED_ROLE_ID = 1323578013887238194
ROBLOX_GROUP_ID = 35383229
JSON_FILE = "players.json"
LOGS_CHANNEL_ID = 1324866568609595413

def authenticate_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Insert relative path to .json file for google api credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name("GOOGLE API CREDENTIALS JSON FILE HERE", scope)

    client = gspread.authorize(creds)
    return client.open("elo database").sheet1 
    
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync() 
    print(f'Logged in as {bot.user}')

@bot.tree.command(name="verify", description="Verify a player by checking their roles and group membership.")
async def verify(interaction: discord.Interaction):
    member = interaction.user
    sheet = authenticate_google_sheets()

    has_dc_verified = any(role.id == DC_VERIFIED_ROLE_ID for role in member.roles)
    has_verified = any(role.id == VERIFIED_ROLE_ID for role in member.roles)

    nickname = member.nick
    roblox_name = nickname_to_roblox(nickname)
    if not roblox_name:
        await interaction.response.send_message(f"There is no username surrounded by parenthesis")
        return

    roblox_id = get_roblox_user_id(roblox_name)
    if roblox_id is None:
        await interaction.response.send_message(f"Cant find roblox ID for username {roblox_name}")
        return
    elif roblox_id == 429:
        await interaction.response.send_message(f"Currently on cooldown")
        return
    
    in_roblox_group = await is_in_roblox_group(roblox_id, ROBLOX_GROUP_ID)


    if has_dc_verified and has_verified and in_roblox_group:
        if get_player_data(sheet, roblox_id) is not None:
            await interaction.response.send_message(f"You are already verified in the database")
        elif get_player_data(sheet, interaction.user.id) is not None:
            await interaction.response.send_message(f"Discord account is already registered in database, update username")
        else:
            add_player(sheet, roblox_id, roblox_name, interaction.user.id)
            await interaction.response.send_message(f"You have been verified and added to the database")
    else:
        missing = []
        if not has_dc_verified:
            missing.append("DC Verified role")
        if not has_verified:
            missing.append("Verified role")
        if not in_roblox_group:
            missing.append("Roblox group member")

        await interaction.response.send_message(f"You are missing the following requirements: {', '.join(missing)}")

@bot.tree.command(name="add", description="Add Elo points to a player.")
@app_commands.describe(member="The member to add points to", points="The number of Elo points to add")
async def add(interaction: discord.Interaction, member: discord.Member, points: int):
    if PRIVILEGED_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission to use this command.")
        return

    if points <= 0:
        await interaction.response.send_message("Points must be a positive integer.")
        return

    sheet = authenticate_google_sheets()
    player_data = get_player_data(sheet, member.id)
    
    if player_data:
        current_elo = int(player_data[2]) 
        new_elo = current_elo + points
        update_player_elo(sheet, member.id, new_elo, True)
        await interaction.response.send_message(f"Added {points} points to {member.mention}. New ELO: {new_elo}")
    else:
        await interaction.response.send_message(f"{member.mention} is not in the database. Verify them first.")

@bot.tree.command(name="subtract", description="Subtract Elo points from a player.")
@app_commands.describe(member="The member to subtract points from", points="The number of Elo points to subtract")
async def subtract(interaction: discord.Interaction, member: discord.Member, points: int):
    if PRIVILEGED_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission to use this command.")
        return

    if points <= 0:
        await interaction.response.send_message("Points must be a positive integer.")
        return

    sheet = authenticate_google_sheets()
    player_data = get_player_data(sheet, member.id)
    
    if player_data:
        current_elo = int(player_data[2]) 
        new_elo = max(0, current_elo - points) 

        update_player_elo(sheet, member.id, new_elo, False)
        await interaction.response.send_message(f"Subtracted {points} points from {member.mention}. New ELO: {new_elo}")
    else:
        await interaction.response.send_message(f"{member.mention} is not in the database. Verify them first.")

@bot.tree.command(name="leaderboard", description="View the top players on the leaderboard.")
@app_commands.describe(top_n="The number of top players to display")
async def leaderboard(interaction: discord.Interaction, top_n: int = 10):
    if top_n < 1 or top_n > 50:
        await interaction.response.send_message('top_n must be between 1 and 50')
        return

    sheet = authenticate_google_sheets()
    all_data = sheet.get_all_records()[0:]
    filtered_data = [row for row in all_data if str(row.get('Elo')).isdigit()]
    print(filtered_data)
    sorted_data = sorted(filtered_data, key=lambda x: x['Elo'], reverse=True)[:top_n]
    if sorted_data:
        leaderboard_message = "**Leaderboard:**\n"
        for rank, player in enumerate(sorted_data, start=1):
            name = player.get('Roblox Name')
            elo = player.get('Elo')
            leaderboard_message += f"{rank}. {name} - ELO: {elo}\n"
        await interaction.response.send_message(leaderboard_message)
    else:
        await interaction.response.send_message("The leaderboard is empty.")

@bot.tree.command(name="view", description="View a player's information.")
@app_commands.describe(member="The player to view")
async def view(interaction: discord.Interaction, member: discord.Member):
    sheet = authenticate_google_sheets()
    player_data = get_player_data(sheet, member.id)
    
    if player_data:
        elo = player_data[2]
        await interaction.response.send_message(f"{member.mention} ELO: {elo} Latest change: {player_data[3]}")
    else:
        await interaction.response.send_message(f"{member.mention} is not in the database. Verify them first.")

@bot.tree.command(name="update_discord", description="Update Discord ID based on Roblox name.")
@app_commands.describe(roblox_name="Roblox name", member="The player's new Discord")
async def update_discord(interaction: discord.Interaction, roblox_name: str, member: discord.Member):
    if PRIVILEGED_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission to use this command.")
        return
    
    sheet = authenticate_google_sheets()
    
    try:
        player_data = sheet.findall(roblox_name)
        
        if player_data:
            for cell in player_data:
                row = sheet.row_values(cell.row)
                row[4] = str(member.id)

                sheet.update(f'A{cell.row}:E{cell.row}', [row])
            await interaction.response.send_message(f"Discord ID for {roblox_name} has been updated to {member.mention}.")
        else:
            await interaction.response.send_message(f"{roblox_name} not found in the database.")
    except gspread.exceptions.GSpreadException as e:
        await interaction.response.send_message(f"Error occurred while updating Discord ID: {str(e)}")

@bot.tree.command(name="update_roblox", description="Update Roblox ID and Name based on new Discord nickname.")
@app_commands.describe(member="The player's Discord with updated nickname")
async def update_roblox(interaction: discord.Interaction, member: discord.Member):
    if PRIVILEGED_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission to use this command.")
        return
    
    sheet = authenticate_google_sheets()

    try:
        player_data = sheet.findall(str(member.id))
        
        if player_data:
            for cell in player_data:
                nickname = member.nick
                roblox_name = nickname_to_roblox(nickname)
                row = sheet.row_values(cell.row)
                roblox_id = get_roblox_user_id(roblox_name)  
                if roblox_id == 429:
                    await interaction.response.send_message(f"Roblox API is on cooldown")
                    return
                row[0] = roblox_id
                row[1] = roblox_name

                sheet.update(f'A{cell.row}:E{cell.row}', [row])
            await interaction.response.send_message(f"Roblox name is now {roblox_name} and Roblox ID is now {roblox_id} for {member.mention}.")
        else:
            await interaction.response.send_message(f"Player with Discord ID {member.id} not found in the database.")
    except gspread.exceptions.GSpreadException as e:
        await interaction.response.send_message(f"Error occurred while updating Discord ID: {str(e)}")

@bot.tree.context_menu(name="match elo update")
async def update_match_elo(interaction: discord.Interaction, message: discord.Message):
    if PRIVILEGED_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission to use this command")
        return
    
    if not message.content:
        await interaction.response.send_message("This message does not contain match elo")
        return

    await interaction.response.defer(ephemeral=True)

    try:
        await asyncio.wait_for(process_match_elo_update(interaction, message), timeout=10.0)
    except asyncio.TimeoutError:
        await interaction.followup.send("The operation is taking too long, please try again later.")
        return

async def process_match_elo_update(interaction, message):
    message_lines = message.content.split("\n")
    updates = []

    first_line = message.content.split("\n")[0]
    match_num = re.search(r"(\d+)", first_line)
    print(match_num, first_line)

    if match_num:
        match_num = match_num.group(1)
    else:
        await interaction.followup.send("Could not find the game number in the message")
        return
    
    for line in message_lines:
        match = re.match(r"<@(\d+)>.*?([+-]\s*\d+)", line.strip())
        if match:
            user_id = match.group(1)
            elo_change = match.group(2).replace(" ", "")
            try:
                elo_change = int(elo_change)
            except ValueError:
                await interaction.followup.send(f"Invalid Elo change value for <@{user_id}>")
                return
            
            if elo_change == 0:
                continue

            updates.append((user_id, elo_change))
        else:
            continue
    
    if len(updates) != 12:
        await interaction.followup.send(f"Invalid number of mentions with elo change, there should be 12")
        return
    
    sheet = authenticate_google_sheets()
    response_message = f"Match {match_num} elo update: [message]({message.jump_url})" + "\n\n"

    for id, elo in updates:
        player_data = get_player_data(sheet, id)

        if player_data:
            current_elo = int(player_data[2]) 
            new_elo = current_elo + elo

            if new_elo < 0:
                new_elo = 0

            if elo > 0:
                update_player_elo(sheet, id, new_elo, True)
                response_message += f"<@{id}>: +{elo} elo. New ELO: {new_elo}" + "\n"
            else:
                update_player_elo(sheet, id, new_elo, False)
                response_message += f"<@{id}>: {elo} elo. New ELO: {new_elo}" + "\n"
        else:
            response_message += f"<@{id}> is not in the databaset" + "\n"

    log_channel = bot.get_channel(LOGS_CHANNEL_ID)

    if log_channel:
        await log_channel.send(response_message)
    else:
        await interaction.followup.send("The log channel could not be found")

    await interaction.followup.send("Success")

# discord API token
bot.run("DISCORD API TOKEN HERE")
