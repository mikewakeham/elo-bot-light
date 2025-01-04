import gspread
from gspread.exceptions import GSpreadException
import requests
import re
import json
import aiohttp

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

def load_players_data(JSON_file):
    try:
        with open(JSON_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}