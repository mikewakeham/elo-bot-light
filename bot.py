import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from discord import app_commands
from gspread.exceptions import GSpreadException
import requests
import re
import aiohttp

def authenticate_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Insert relative path to .json file for google api credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name("GOOGLE API CREDENTIALS JSON FILE HERE", scope)


    client = gspread.authorize(creds)
    return client.open("elo database").sheet1 

def get_roblox_user_id(username):
    url = f"https://users.roblox.com/v1/users/search?keyword={username}"
    print(username)
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        if data.get('data'):
            user_id = data['data'][0]['id']
            return user_id
        else:
            print("User not found.")
            return None
    elif response.status_code == 429:
        return 429
    else:
        print(f"Error: {response.status_code}")
        return None


def get_player_data(sheet, discord_id):
    discord_id = str(discord_id)
    try:
        cell = sheet.find(str(discord_id)) 
        if cell:
            return sheet.row_values(cell.row)
        else:
            print(f"Player ID {discord_id} not found.")
            return None
    except GSpreadException as e:
        print(f"Error occurred: {e}")
        return None

def add_player(sheet, roblox_id, roblox_name, discord_id):
    sheet.append_row([str(roblox_id), roblox_name, 0, 'None', str(discord_id)]) 

def update_player_elo(sheet, discord_id, new_elo, positive):
    discord_id = str(discord_id)
    try:
        cell = sheet.find(str(discord_id))
        row = sheet.row_values(cell.row)
        if positive:
            row[3] = '+' + str(new_elo - int(row[2]))
        else:
            row[3] = '-' + str(int(row[2]) - new_elo)
        row[2] = new_elo 
        sheet.update(f'A{cell.row}:E{cell.row}', [row]) 
    except gspread.exceptions.CellNotFound:
        return None
    
async def is_in_roblox_group(roblox_id, group_id):
    url = f"https://groups.roblox.com/v2/users/{roblox_id}/groups/roles"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for group in data.get("data", []):
                        if group["group"]["id"] == group_id:
                            return True
                    
                    return False
                else:
                    print(f"Failed to fetch group data: {response.status}")
                    return False
        except Exception as e:
            print(f"An error occurred: {e}")
            return False

def nickname_to_roblox(nickname):
    match = re.search(r'\((.*?)\)', nickname)
    if match:
        return match.group(1)
    else:
        return None
    
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync() 

DC_VERIFIED_ROLE_ID = 1323577921981648906
VERIFIED_ROLE_ID = 1323577899894181888
PRIVILEGED_ROLE_ID = 1323578013887238194

ROBLOX_GROUP_ID = 35383229
TOP_N = 10 


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
async def leaderboard(interaction: discord.Interaction, top_n: int = TOP_N):
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
        await interaction.response.send_message(f"{member.mention} ELO: {elo}")
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

# discord API token
bot.run('DISCORD API TOKEN HERE')
