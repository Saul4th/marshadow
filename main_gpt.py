'''

v0.52 - Added the modify team option - OK

v0.53 - Loading Pokemon Data from Gsheets -OK

v0.54 - Improve logging
'''

import discord
from discord import app_commands
from discord.ext import commands
import pandas as pd
import taken  # Custom module for storing the bot token
import difflib  # For finding similar Pokémon names
from PIL import Image
import requests
from io import BytesIO
import asyncio  # For the timer functionality
import logging
'''v0.46'''
from discord.ui import Button, View
'''v0.49'''
from discord.app_commands import CheckFailure
'''v0.50'''
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from google.auth.exceptions import TransportError
from google.api_core.exceptions import DeadlineExceeded
'''v0.53'''
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
'''v0.54'''
from logging.handlers import RotatingFileHandler

print("Current Working Directory:", os.getcwd())


# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Define the log format
    handlers=[
        RotatingFileHandler("draft_bot.log", maxBytes=5 * 1024 * 1024, backupCount=3),  # Log to a file (5 MB per file, keep 3 backups)
        logging.StreamHandler()  # Log to the console
    ]
)

# Create a logger instance
logger = logging.getLogger(__name__)

# Initialize the bot with slash command support
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Enable server members intent
bot = commands.Bot(command_prefix="!", intents=intents)

'''v0.50'''
#Function to Authenticate with Google Sheets
def authenticate_google_sheets():
 
    try:
        # Define the scope
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # Load credentials from the JSON file
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
        # Authorize the client
        client = gspread.authorize(creds)
        logger.info("Successfully authenticated with Google Sheets.")
        return client
    except FileNotFoundError:
        logger.error("Credentials file (credentials.json) not found.")
        raise
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Sheets: {e}")
        raise

# Function to create a 6x2 grid collage with the user's avatar in position (1,1)
def create_sprite_collage(pokemon_names, pokemon_data, avatar_url):
    images = []
    
    # Download the user's avatar (handle cases where avatar_url is None)
    if avatar_url:
        response = requests.get(avatar_url)
        if response.status_code == 200:
            avatar_img = Image.open(BytesIO(response.content))
            avatar_img = avatar_img.resize((96, 96))  # Resize avatar to match sprite size
            images.append(avatar_img)  # Add avatar as the first image
    else:
        # Use a default image if no avatar is available
        default_avatar = Image.new("RGBA", (96, 96), (255, 255, 255, 0))  # Transparent image
        images.append(default_avatar)
    
    # Download Pokémon sprites
    for pokemon_name in pokemon_names:
        pokemon_id = pokemon_data[pokemon_name]["id"]
        sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_id}.png"
        response = requests.get(sprite_url)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            images.append(img)
    
    # Create a blank canvas for the collage (6 columns x 2 rows)
    sprite_width = 96  # Width of each sprite
    sprite_height = 96  # Height of each sprite
    collage_width = sprite_width * 6
    collage_height = sprite_height * 2
    collage = Image.new("RGBA", (collage_width, collage_height))
    
    # Paste images into the grid
    for i, img in enumerate(images):
        if i >= 12:  # Limit to 12 images (6x2 grid)
            break
        x = (i % 6) * sprite_width
        y = (i // 6) * sprite_height
        collage.paste(img, (x, y))
    
    # Save the collage to a file
    collage.save("collage.png")
    return "collage.png"

# Function to Load Pokémon data from Google Sheets
def load_pokemon_data_from_google_sheets():
    """
    Load Pokémon data from a Google Sheet named "Pokemon Data" in a specific folder.
    """
    pokemon_data = {}
    try:
        # Authenticate with Google Sheets
        client = authenticate_google_sheets()
        
        # Define the folder ID and sheet name
        folder_id = "13B6DevETQRkLON7yuonkpAHiar0NwwyU"  # Replace with your folder ID
        sheet_name = "Pokemon Data"  # Replace with your sheet name
        
        # Authenticate with Google Drive
        creds = Credentials.from_service_account_file("credentials.json", scopes=["https://www.googleapis.com/auth/drive"])
        drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        
        # List files in the folder
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
        response = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = response.get("files", [])
        
        # Find the sheet by name
        sheet_id = None
        for file in files:
            if file["name"] == sheet_name:
                sheet_id = file["id"]
                break
        
        if not sheet_id:
            raise Exception(f"Could not find Google Sheet with name '{sheet_name}' in folder '{folder_id}'.")
        
        # Open the Google Sheet by ID
        spreadsheet = client.open_by_key(sheet_id)
        
        # Access the first (and only) worksheet
        worksheet = spreadsheet.sheet1  # First sheet in the spreadsheet
        
        # Get all records from the worksheet
        records = worksheet.get_all_records()
        
        # Convert records to a pandas DataFrame for easier processing
        df = pd.DataFrame(records)
        
        # Normalize column names to lowercase
        df.columns = df.columns.str.lower()
        
        # Exclude specific tiers ("B" and "-")
        df = df[~df["tier"].isin(["B", "-"])]
        
        # Ensure "points" column is numeric, replacing non-numeric or missing values with 20
        df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(20).astype(int)
        
        # Process each row
        for _, row in df.iterrows():
            pokemon_data[row["name"].lower()] = {
                "id": int(row["id"]),  # PokeAPI ID for sprites
                "dex_number": int(row["dex_number"]),  # Pokédex number for Species Clause
                "tier": row.get("tier", "Unknown"),
                "points": row["points"],  # Points is now guaranteed to be an integer
            }
        
        logger.info("Successfully loaded Pokémon data from Google Sheets.")
    except Exception as e:
        logger.error(f"Error loading Pokémon data from Google Sheets: {e}")
        raise
    return pokemon_data

# Load Pokémon data from Google Sheets
try:
    pokemon_data = load_pokemon_data_from_google_sheets()
    if not pokemon_data:
        logger.error("Failed to load Pokémon data. Exiting.")
        exit(1)
except Exception as e:
    logger.error(f"Failed to load Pokémon data: {e}")
    exit(1)

pokemon_names = list(pokemon_data.keys())

# Set the maximum number of timer extensions allowed per participant
extensions_limit = 3  # You can adjust this value

#Function to Update Google Sheets
def update_google_sheet(is_intentional_clear=False):
    try:
        # Authenticate with Google Sheets
        client = authenticate_google_sheets()
        
        # Authenticate with Google Drive
        creds = Credentials.from_service_account_file("credentials.json", scopes=["https://www.googleapis.com/auth/drive"])
        drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        
        # Define the folder ID and sheet name
        folder_id = "13B6DevETQRkLON7yuonkpAHiar0NwwyU"  # Replace with your folder ID
        sheet_name = "Draft Sheet"  # Replace with your sheet name
        
        # List files in the folder
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
        response = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = response.get("files", [])
        
        # Find the sheet by name
        sheet_id = None
        for file in files:
            if file["name"] == sheet_name:
                sheet_id = file["id"]
                break
        
        if not sheet_id:
            raise Exception(f"Could not find Google Sheet with name '{sheet_name}' in folder '{folder_id}'.")
        
        # Open the Google Sheet by ID
        spreadsheet = client.open_by_key(sheet_id)
        
        # Clear the Pokémon picks sheet
        pokemon_sheet = spreadsheet.sheet1  # First sheet (Pokémon picks)
        pokemon_sheet.clear()
        logger.info("Cleared Pokémon picks sheet.")
        
        # Add headers for the Pokémon picks sheet
        pokemon_sheet.append_row(["Coach", "Pokémon", "Points"])
        logger.info("Added headers to Pokémon picks sheet.")
        
        # Check if draft state is valid
        if draft_state.get("teams"):
            for coach, team in draft_state["teams"].items():
                for pokemon in team["pokemon"]:
                    pokemon_points = pokemon_data[pokemon]["points"]
                    pokemon_sheet.append_row([coach.display_name, pokemon, pokemon_points])
            logger.info("Updated Pokémon picks sheet with draft data.")
        elif not is_intentional_clear:
            # Only log a warning if the draft state is empty unintentionally
            logger.warning("Draft state is empty. Skipping Pokémon picks update.")
        
        # Clear the draft state sheet
        draft_state_sheet = spreadsheet.worksheet("Draft State")  # Second sheet (Draft State)
        draft_state_sheet.clear()
        logger.info("Cleared Draft State sheet.")
        
        # Add headers for the draft state sheet
        draft_state_sheet.append_row(["Participants", "Current Pick", "Remaining Pokémon", "Skipped Turns", "Extensions", "Auto Extensions"])
        logger.info("Added headers to Draft State sheet.")
        
        # Add draft state data (if available)
        if draft_state.get("participants"):
            participants = ", ".join([p.display_name for p in draft_state["participants"]])
            current_pick = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])].display_name
            remaining_pokemon = len(draft_state["available_pokemon"])
            skipped_turns = ", ".join([f"{p.display_name}: {t}" for p, t in draft_state["skipped_turns"].items()])
            extensions = ", ".join([f"{p.display_name}: {e}" for p, e in draft_state["extensions"].items()])
            auto_extensions = ", ".join([f"{p.display_name}: {a}" for p, a in draft_state["auto_extensions"].items()])
            
            draft_state_sheet.append_row([participants, current_pick, remaining_pokemon, skipped_turns, extensions, auto_extensions])
            logger.info("Updated Draft State sheet with draft data.")
        elif not is_intentional_clear:
            # Only log a warning if the draft state is empty unintentionally
            logger.warning("Draft state is empty. Skipping Draft State update.")
    
    except Exception as e:
        logger.error(f"Error updating Google Sheet: {e}")
        raise

# Draft state
draft_state = {
    "participants": [],  # List of participants
    "order": [],  # Draft order
    "current_pick": 0,  # Index of the current pick
    "teams": {},  # Teams of each participant
    "available_pokemon": pokemon_names.copy(),  # Pokémon available for drafting
    "skipped_turns": {},  # Track skipped turns for each participant
    "extensions": {},  # Track the number of timer extensions for each participant by failed pick
    "is_paused": False,  # Track if the draft is paused
    "auto_extensions": {},  # Track automatic extensions per participant by unconfirmed pick
}

#Error Handler
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        # Log the unauthorized attempt
        logger.info(
            f"User {interaction.user.name} tried to use command '{interaction.command.name}' "
            f"but does not have the required role."
        )
        return
    else:
        # Log other errors
        logger.error(f"Command error: {error}")
        await interaction.response.send_message(
            "An error occurred while processing the command.",
            ephemeral=True
        )

# Check for "Draft" role
def has_draft_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        draft_staff_role = discord.utils.get(interaction.guild.roles, name="Draft")
        if not draft_staff_role:
            await interaction.response.send_message(
                "The 'Draft' role does not exist in this server.",
                ephemeral=True
            )
            return False
        if draft_staff_role not in interaction.user.roles:
            await interaction.response.send_message(
                "You do not have the 'Draft' role required to use this command.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)
# Check for "Draft Staff" role
def has_draft_staff_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        draft_staff_role = discord.utils.get(interaction.guild.roles, name="Draft Staff")
        if not draft_staff_role:
            await interaction.response.send_message(
                "The 'Draft Staff' role does not exist in this server.",
                ephemeral=True
            )
            return False
        if draft_staff_role not in interaction.user.roles:
            await interaction.response.send_message(
                "You do not have the 'Draft Staff' role required to use this command.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

# Set the guild ID for the slash commands
GUILD_ID = discord.Object(id=1326634506605691080)  # Replace with your guild ID

# Define the stall group (replace with actual Pokémon names)
stall_group = ["blissey", "toxapex", "skarmory", "chansey","clefable","clodsire","corviknight","cresselia","dondozo","garganacl","gliscor","mandibuzz","quagsire","slowking-galar"]

# Set variable for number of Pokémon per Draft
draft_size = 4
total_points = 400

# Define the number of coaches allowed in the draft
coaches_size = 4  # Default value

# Timer duration (in seconds)
TIMER_DURATION = 60  # Default timer duration (1 minute)
timer_task = None  # Global variable to store the timer task

# Dictionary to store timers for each participant
participant_timers = {}

# Global variable to track remaining time for each participant
remaining_times = {}

# Global variable to store the selected coaches
selected_coaches = []

# Function to generate autocomplete choices for coaches
async def coach_autocomplete(interaction: discord.Interaction, current: str):
    # Fetch members with the "Draft" role
    draft_role = discord.utils.get(interaction.guild.roles, name="Draft")
    if not draft_role:
        return []

    # Filter members with the "Draft" role and match the current input
    members = [member for member in interaction.guild.members if draft_role in member.roles]
    choices = [
        app_commands.Choice(name=member.display_name, value=str(member.id))
        for member in members
        if current.lower() in member.display_name.lower()
    ][:25]  # Limit to 25 choices

    return choices

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync(guild=GUILD_ID)
        logger.info(f'Synced {len(synced)} commands to guild {GUILD_ID.id}')
    except Exception as e:
        logger.info(f"Error syncing commands: {e}")
    
    # Fetch the guild and its members
    guild = bot.get_guild(GUILD_ID.id)
    if guild:
        logger.info("Members in the guild:")
        try:
            # Fetch members explicitly
            async for member in guild.fetch_members(limit=None):
                logger.info(f"Username: {member.name}, Display Name: {member.display_name}")
        except Exception as e:
            logger.info(f"Error fetching members: {e}")
    else:
        logger.info(f"Guild with ID {GUILD_ID.id} not found.")

# Function to start the draft (updated in v0.50)
async def start_draft(interaction: discord.Interaction, participants: list[discord.Member]):
    global selected_coaches

    try:

        # Reset the draft state
        draft_state["participants"] = participants
        draft_state["order"] = participants + participants[::-1]  # Snake draft order
        draft_state["current_pick"] = 0
        draft_state["teams"] = {member: {"pokemon": [], "points": total_points} for member in participants}
        draft_state["available_pokemon"] = pokemon_names.copy()
        draft_state["skipped_turns"] = {member: 0 for member in participants}

        # Clear the selected coaches list
        selected_coaches = []

        # Update the Google Sheet
        try:
            update_google_sheet()
        except Exception as e:
            logger.error(f"Error updating Google Sheet: {e}")
            await interaction.followup.send(
                "⚠️ The draft was started, but there was an error updating the Google Sheet. "
                "Please check the logs for details.",
                ephemeral=True
            )

        # Send the draft start message
        await interaction.followup.send(
            "Draft started! \n\nThe order is:\n" + "\n".join([member.mention for member in draft_state["participants"]]) + "\n in snake format"
        )

        # Notify the first participant and start the timer
        await notify_current_participant(interaction)

    except Exception as e:
        logger.error(f"Error starting draft: {e}")
        await interaction.followup.send(
            "An error occurred while starting the draft. Please try again or contact the administrator.",
            ephemeral=True
        )

#Funtion to format the timer
def format_time(seconds: int) -> str:
    """
    Format time in seconds as minutes:seconds (e.g., 90 -> "1:30").
    """
    minutes = seconds // 60
    seconds_remaining = seconds % 60
    return f"{minutes}:{seconds_remaining:02}"  # Ensures seconds are always 2 digits

#Function that starts the timer
async def start_timer(interaction: discord.Interaction, participant, adjusted_duration=None):
    global participant_timers, remaining_times

    # Calculate the adjusted timer duration based on skipped turns if not provided
    if adjusted_duration is None:
        skipped_turns = draft_state["skipped_turns"].get(participant, 0)
        if skipped_turns == 1:
            adjusted_duration = TIMER_DURATION // 2  # Half the initial time
            await interaction.followup.send(
                f"⚠️ {participant.mention}, you were skipped once. Your timer is now **{format_time(adjusted_duration)}**."
            )
        elif skipped_turns >= 2:
            adjusted_duration = TIMER_DURATION // 4  # Quarter of the initial time
            await interaction.followup.send(
                f"⚠️ {participant.mention}, you were skipped multiple times. Your timer is now **{format_time(adjusted_duration)}**."
            )
        else:
            adjusted_duration = TIMER_DURATION  # Initial time

    # Check if there's an existing remaining time and not an extension
    if participant in remaining_times and adjusted_duration is None:
        adjusted_duration = remaining_times[participant]
        logger.info(f"Resuming timer for {participant.name}: {adjusted_duration} seconds")
    else:
        logger.info(f"Starting new timer for {participant.name}: {adjusted_duration} seconds")

    remaining_time = adjusted_duration

    # Send an initial message with the timer
    timer_message = await interaction.followup.send(
        f"⏰ Time remaining for {participant.mention}: **{format_time(remaining_time)}**"
    )

    # Countdown loop
    while remaining_time > 0:
        try:
            await asyncio.sleep(1)  # Wait for 1 second
            remaining_time -= 1
            await timer_message.edit(content=f"⏰ Time remaining for {participant.mention}: **{format_time(remaining_time)}**")
        except asyncio.CancelledError:
            # Timer was canceled, store the remaining time only if it was extended
            remaining_times[participant] = remaining_time
            logger.info(f"Timer for {participant.name} was canceled. Remaining time: {remaining_time} seconds")
            return

    # Notify when the timer runs out
    await interaction.followup.send(f"⏰ Time's up for {participant.mention}! Moving to the next participant.")

    # Increment the skipped turns counter for the participant
    if participant in draft_state["skipped_turns"]:
        draft_state["skipped_turns"][participant] += 1
    else:
        draft_state["skipped_turns"][participant] = 1

    # Move to the next participant
    await next_participant(interaction)

#Function that cancels the timer
async def cancel_timer(participant):
    global participant_timers
    if participant in participant_timers:
        timer_task = participant_timers[participant]
        if not timer_task.done():
            timer_task.cancel()  # Cancel the timer task
            try:
                await timer_task  # Wait for the task to be canceled
            except asyncio.CancelledError:
                logger.info(f"Timer for {participant.name} was canceled successfully.")
        del participant_timers[participant]  # Remove the timer from the dictionary

#Function that extends the timer
async def extend_timer(interaction: discord.Interaction, participant, extend_time):
    global participant_timers, remaining_times
    
    #Extend the timer for the current participant by the specified time (in seconds).
    

    # Initialize the extension count if it doesn't exist
    if participant not in draft_state["extensions"]:
        draft_state["extensions"][participant] = 0

    # Check if the participant has reached the extension limit
    if draft_state["extensions"][participant] >= extensions_limit:
        await interaction.followup.send(
            f"⚠️ {participant.mention}, you have reached the limit of **{extensions_limit} timer extensions**. "
            "Make a valid pick to reset your extension count."
        )
        return

    # Increment the extension count
    draft_state["extensions"][participant] += 1

    # Cancel the current timer if it exists
    if participant in participant_timers:
        timer_task = participant_timers[participant]
        if not timer_task.done():
            timer_task.cancel()
            try:
                await timer_task  # Wait for the task to be canceled
            except asyncio.CancelledError:
                logger.info(f"Timer for {participant.name} was canceled successfully.")

    # Calculate the new duration by adding the extend time to the remaining time
    if participant in remaining_times:
        new_duration = remaining_times[participant] + extend_time
    else:
        new_duration = extend_time  # If no remaining time, start with just the extend time

    # Update the remaining time for the participant
    remaining_times[participant] = new_duration

    await interaction.followup.send(
        f"⏰ {participant.mention}, you were granted **{extend_time} extra seconds** to make a valid pick. "
        f"You have **{format_time(new_duration)}** remaining."
    )
    logger.info(f"{participant.name} has **{extensions_limit - draft_state['extensions'][participant]} extensions** remaining")

    # Restart the timer with the new duration
    timer_task = asyncio.create_task(start_timer(interaction, participant, new_duration))
    participant_timers[participant] = timer_task
    
#Function that notifies the current participant
async def notify_current_participant(interaction: discord.Interaction):
    global participant_timers

    # Get the current participant
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    remaining_points = draft_state["teams"][current_user]["points"]
    remaining_picks = draft_size - len(draft_state["teams"][current_user]["pokemon"])

    # Notify the current participant
    await interaction.followup.send(
        f"It's {current_user.mention}'s turn to pick!\n"
        f"You have **{remaining_points} points** and can pick **{remaining_picks} more Pokémon**."
    )

    # Start the timer for the current participant
    timer_task = asyncio.create_task(start_timer(interaction, current_user))
    participant_timers[current_user] = timer_task #Store timer task

async def next_participant(interaction: discord.Interaction):
    global draft_state, remaining_times

    # Cancel the timer for the current participant
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    await cancel_timer(current_user)

    # Reset auto-extensions counter when turn is skipped
    if current_user in draft_state["auto_extensions"]:
        logger.info(f"Resetting auto-extensions counter for {current_user.name} due to turn skip")
        draft_state["auto_extensions"][current_user] = 0

    # Clear any remaining time for the current user
    if current_user in remaining_times:
        del remaining_times[current_user]

    # Increment the current pick index
    draft_state["current_pick"] += 1

    # Get the next participant
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]

    # Check if the next participant has completed their draft
    while len(draft_state["teams"][current_user]["pokemon"]) == draft_size:
        draft_state["current_pick"] += 1  # Skip this participant
        current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]

    # Notify the next participant
    await notify_current_participant(interaction)

#Function to Check Stall Group Limits
def has_reached_stall_limit(user):
    """
    Check if the user already has 2 Pokémon from the stall group in their team.
    """
    stall_count = sum(1 for pokemon in draft_state["teams"][user]["pokemon"] if pokemon in stall_group)
    return stall_count >= 2

'''V0.47'''
#slash command to set the number of coaches
@bot.tree.command(name="numberofcoaches", description="Change the number of coaches allowed in the draft", guild=GUILD_ID)
@app_commands.describe(new_size="The new number of coaches allowed in the draft (minimum 2)")
@has_draft_staff_role()
async def number_of_coaches_command(interaction: discord.Interaction, new_size: int):
    global coaches_size
    
    # Defer the response immediately to prevent timeout
    await interaction.response.defer(ephemeral=True)

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /numberofcoaches with new_size: {new_size}."
    )

    # Send initial status message and store the message for updates
    status_message = await interaction.followup.send(
        "⏳ Updating the number of coaches...\n□ Validating request\n□ Rebuilding commands\n□ Syncing with Discord",
        ephemeral=True,
        wait=True  # Wait for the message to be sent and get its reference
    )

    # Check if a draft is in progress or paused
    if draft_state["participants"] or draft_state["is_paused"]:
        await status_message.edit(content="❌ Cannot change the number of coaches while a draft is in progress or paused.")
        return

    # Validate the new size (minimum 2)
    if new_size < 2:
        await status_message.edit(content="❌ The number of coaches must be at least **2**.")
        return

    try:
        # Update the coaches_size variable
        old_size = coaches_size
        coaches_size = new_size

        # Update status - Step 1 complete
        await status_message.edit(content=(
            "✓ Validating request... complete\n"
            "⏳ Rebuilding commands...\n"
            "□ Syncing with Discord"
        ))

        # Remove the existing set_coaches command
        try:
            bot.tree.remove_command("set_coaches", guild=GUILD_ID)
        except Exception:
            pass  # Command might not exist yet

        # Create and add the new set_coaches command
        def create_dynamic_set_coaches():
            # Create the parameters dictionary for app_commands.describe
            params_dict = {
                f"coach{i+1}": f"Coach #{i+1}" for i in range(coaches_size)
            }
            
            # Create the function parameters as a string
            func_params = ", ".join([
                "interaction: discord.Interaction",
                *[f"coach{i+1}: str = None" for i in range(coaches_size)]
            ])
            
            # Create the coach parameters list for the command code
            coach_params_list = [f"coach{i+1}" for i in range(coaches_size)]
            coach_params_str = ", ".join(coach_params_list)
            
            # Create the command function code
            command_code = f"""
@has_draft_staff_role()
async def set_coaches_command({func_params}):
    global selected_coaches
    # Add defer at the start
    await interaction.response.defer(ephemeral=True)

    # Check if a draft is already in progress
    if draft_state["participants"]:
        await interaction.followup.send("A draft is already in progress. You cannot change coaches now.", ephemeral=True)
        return

    # Validate that all selected members have the "Draft" role
    draft_role = discord.utils.get(interaction.guild.roles, name="Draft")
    if not draft_role:
        await interaction.followup.send("The 'Draft' role does not exist in this server.", ephemeral=True)
        return

    # Resolve members from their IDs or names
    coaches = []
    seen_coaches = set()
    coach_params = [{coach_params_str}]
    
    for i, coach_id in enumerate(coach_params, 1):
        if not coach_id:
            await interaction.followup.send(f"Coach #{{i}} is required.", ephemeral=True)
            return

        try:
            member = interaction.guild.get_member(int(coach_id))
        except ValueError:
            member = None
            
        if not member:
            await interaction.followup.send(f"Could not find member for Coach #{{i}}", ephemeral=True)
            return
            
        if draft_role not in member.roles:
            await interaction.followup.send(
                f"{{member.display_name}} does not have the 'Draft' role and cannot be a coach.",
                ephemeral=True
            )
            return

        # Check if this coach has already been selected
        if member.id in seen_coaches:
            await interaction.followup.send(
                f"❌ Error: {{member.display_name}} has been selected multiple times. Each coach can only be selected once.",
                ephemeral=True
            )
            return
            
        seen_coaches.add(member.id)
        coaches.append(member)

    # Validate the number of coaches
    if len(coaches) != coaches_size:
        await interaction.followup.send(
            f"You must provide exactly {coaches_size} coaches.", 
            ephemeral=True
        )
        return

    # Store the selected coaches
    selected_coaches = coaches
    await interaction.followup.send(
        f"Coaches set successfully: {{', '.join([c.mention for c in selected_coaches])}}"
    )
"""
    
            # Create the function namespace
            namespace = {}
            exec(command_code, globals(), namespace)
            dynamic_command = namespace['set_coaches_command']
            
            # Create the command
            command = bot.tree.command(
                name="set_coaches",
                description=f"Set the {coaches_size} coaches for the draft",
                guild=GUILD_ID
            )(dynamic_command)
            
            # Add the descriptions
            command = app_commands.describe(**params_dict)(command)
            
            # Add autocomplete for all coach arguments
            for i in range(coaches_size):
                command.autocomplete(f"coach{i+1}")(coach_autocomplete)
            
            return command

        # Create and add the new command
        new_command = create_dynamic_set_coaches()

        # Update status - Step 2 complete
        await status_message.edit(content=(
            "✓ Validating request... complete\n"
            "✓ Rebuilding commands... complete\n"
            "⏳ Syncing with Discord..."
        ))
        
        # Sync the commands
        await bot.tree.sync(guild=GUILD_ID)

        # Final success message
        await status_message.edit(content=(
            "✅ Command update complete!\n\n"
            f"**Number of coaches updated:**\n"
            f"• Previous: {old_size}\n"
            f"• Current: {coaches_size}\n\n"
            f"The `/set_coaches` command has been updated to accept **{coaches_size}** coaches."
        ))

    except Exception as e:
        logger.error(f"Error updating commands: {e}")
        await status_message.edit(content=(
            "❌ An error occurred while updating the commands:\n"
            f"```\n{str(e)}\n```\n"
            "Please try again or contact the bot administrator."
        ))

# Slash command to start the draft (specific to the guild)
@bot.tree.command(name="start_draft", description="Start the Pokémon draft", guild=GUILD_ID)
async def start_draft_command(interaction: discord.Interaction):
    global selected_coaches

    # Defer the response immediately to prevent interaction timeout
    await interaction.response.defer()

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /start_draft."
    )

    # Check if coaches have been set
    if not selected_coaches:
        await interaction.followup.send("No coaches have been set. Use `/set_coaches` first.", ephemeral=True)
        return

    # Check if a draft is already in progress
    if draft_state["participants"]:
        await interaction.followup.send("A draft is already in progress. Please wait until the current draft finishes before starting a new one.")
        return

    try:
        # Start the draft with the selected coaches
        await start_draft(interaction, selected_coaches)
    except Exception as e:
        logger.error(f"Error starting draft: {e}")
        await interaction.followup.send(
            "An error occurred while starting the draft. Please try again or contact the administrator.",
            ephemeral=True
        )

'''v0.48'''
#Slash command to stop the draft
@bot.tree.command(
    name="stop_draft", 
    description="Emergency stop: Completely stops and resets the draft", 
    guild=GUILD_ID
)
@has_draft_staff_role()
async def stop_draft_command(interaction: discord.Interaction):
    # Defer the response to prevent timeout
    await interaction.response.defer(ephemeral=True)
    
    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /stop_draft."
    )

    # Send warning message with confirmation buttons
    view = ConfirmationView(timeout=60)  # Using our improved ConfirmationView
    
    # Send the warning message with the buttons
    await interaction.followup.send(
        "⚠️ **WARNING: Emergency Draft Stop**\n\n"
        "This will:\n"
        "• Immediately stop the current draft\n"
        "• Reset all draft data\n"
        "• Clear all selections and progress\n"
        "• Cannot be undone\n\n"
        "Are you sure you want to stop and reset the draft?",
        view=view,
        ephemeral=True
    )

    # Wait for confirmation
    await view.wait()

    if view.value:  # Confirmed
        try:
            # Cancel all active timers first
            global participant_timers, remaining_times
            for participant, timer in participant_timers.copy().items():
                try:
                    await cancel_timer(participant)
                    logger.info(f"Cancelled timer for {participant.name}")
                except Exception as e:
                    logger.error(f"Error cancelling timer for {participant.name}: {e}")
            
            # Clear timer-related dictionaries
            participant_timers.clear()
            remaining_times.clear()

            # Reset all global variables
            global draft_state, selected_coaches
            draft_state = {
                "participants": [],
                "order": [],
                "current_pick": 0,
                "teams": {},
                "available_pokemon": pokemon_names.copy(),
                "skipped_turns": {},
                "extensions": {},
                "is_paused": False,
                "auto_extensions": {}
            }
            selected_coaches = []
            
            # Update Google Sheets (with error handling)
            try:
                update_google_sheet(is_intentional_clear=True)
            except Exception as e:
                    logger.error(f"Error updating Google Sheet: {e}")
                    await interaction.followup.send(
                        "⚠️ The draft was stopped, but there was an error updating the Google Sheet. "
                        "Please check the logs for details.",
                        ephemeral=True
                    )

            # Send success message
            await interaction.followup.send(
                "✅ Draft has been completely stopped and reset.\n\n"
                "• All timers have been cancelled\n"
                "• All draft data has been cleared\n"
                "• The bot is ready for a new draft", 
                ephemeral=True
            )
                
            # Optional: Send a message to the channel that the draft was stopped
            try:
                channel = interaction.channel
                await channel.send(
                    "🚨 **DRAFT STOPPED**\n"
                    f"• Draft forcefully stopped by {interaction.user.mention}\n"
                    "• All timers cancelled\n"
                    "• All draft data has been reset"
                )
            except Exception as e:
                logger.error(f"Failed to send channel notification: {e}")
                    
        except Exception as e:
            logger.error(f"Error in stop_draft confirmation: {e}")
            await interaction.followup.send(
                "❌ An error occurred while stopping the draft. Please try again or contact the administrator.",
                ephemeral=True
            )
    else:  # Cancelled or timed out
        await interaction.followup.send(
            "✅ Stop draft cancelled. The draft will continue normally.",
            ephemeral=True
        )

'''Empieza V0.44'''

'''HELPER FUNCTIONS'''
## Split Validations into Helper Functions##
async def validate_draft_state(interaction: discord.Interaction, user) -> bool:
    """Check if draft exists and user can pick"""
    # Check if a draft exists and user can pick
    if not draft_state["participants"]:
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return False
        
    if draft_state["is_paused"]:
        await interaction.response.send_message("The draft is currently paused. You cannot pick a Pokémon until it is resumed.", ephemeral=True)
        return False

    if user not in draft_state["participants"]:
        await interaction.response.send_message("You are not part of the draft.", ephemeral=True)
        return False
    return True

async def validate_turn(interaction: discord.Interaction, user) -> bool:
    """Check if it's user's turn and they can still pick"""
    # Check if it's user's turn
    current_pick_index = draft_state["current_pick"] % len(draft_state["order"])
    if draft_state["order"][current_pick_index] != user:
        await interaction.response.send_message("It's not your turn to pick.", ephemeral=True)
        return False

    # Check if user's draft is full
    if len(draft_state["teams"][user]["pokemon"]) >= draft_size:
        await interaction.response.send_message(f"Your team already has {draft_size} Pokémon. You can't pick more!", ephemeral=True)
        return False
    return True

##Create a Points Calculator Helper
def calculate_minimum_points(available_pokemon: list, remaining_picks: int) -> int:
    """Calculate minimum points needed for remaining picks"""
    min_points_required = 0
    available_sorted = sorted(available_pokemon, key=lambda x: pokemon_data[x]["points"])
    for i in range(remaining_picks):
        if i < len(available_sorted):
            min_points_required += pokemon_data[available_sorted[i]]["points"]
        else:
            # If there aren't enough Pokémon left, assume the next tier (e.g., 40 points)
            min_points_required += 40  # Adjust this value based on your tier system
    return min_points_required

##Separate Embed Creation
def create_pick_announcement_embed(user: discord.Member, pokemon_name: str, pokemon_info: dict) -> discord.Embed:
    """Create and return embed for pick announcement"""
    # Create and send embed
    embed = discord.Embed(
        title=f"¡{pokemon_name.capitalize()} YO TE ELIJO!",
        description=f"{user.mention} ha elegido a {pokemon_name.capitalize()}\n\n**Tier:** {pokemon_info['tier']}",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_info['id']}.png")
    return embed

#Helper Function to display final teams (updated in v0.50)
async def show_final_teams(interaction: discord.Interaction):
    """Display the final teams for all participants"""
    await interaction.followup.send("All participants have completed their picks! Now here are the draft of each team:")

    # Show final teams
    for member, team in draft_state["teams"].items():
        # Get the user's avatar URL
        avatar_url = str(member.avatar.url)  # Get the URL of the user's avatar
        
        # Create a sprite collage with the user's avatar
        collage_path = create_sprite_collage(team["pokemon"], pokemon_data, avatar_url)
        
        file = discord.File(collage_path, filename="collage.png")
        embed = discord.Embed(title=f"{member.display_name}'s Team", color=discord.Color.blue())
        embed.set_image(url="attachment://collage.png")
        
        # Send the embed with the file
        await interaction.followup.send(file=file, embed=embed)
   
    # Update the Google Sheet with final results
    update_google_sheet()

'''Empieza V0.45'''
#Pokemon name validation - This function handles name checking and suggestions:
async def validate_pokemon_name(interaction: discord.Interaction, pokemon_name: str, user) -> tuple[bool, dict]:
    """Validate pokemon name and return (is_valid, pokemon_info)"""
    pokemon_name = pokemon_name.lower()
    
    if pokemon_name not in draft_state["available_pokemon"]:
        similar_names = difflib.get_close_matches(pokemon_name, draft_state["available_pokemon"], n=5, cutoff=0.6)
        message = (
            f"Invalid Pokémon name. Did you mean one of these?\n" +
            "\n".join(similar_names) if similar_names else "Sorry, no similar names found."
        )
        await interaction.response.send_message(message, ephemeral=True)
        await extend_timer(interaction, user, 60)
        return False, None
    
    return True, pokemon_data[pokemon_name]

#Rules Validation - Combines stall group and species clause checks:
async def validate_pokemon_rules(interaction: discord.Interaction, pokemon_name: str, pokemon_info: dict, user) -> bool:
    """Validate stall group and species clause rules"""
    # Check stall group limit
    if pokemon_name in stall_group and has_reached_stall_limit(user):
        await interaction.response.send_message(
            f"You already have 2 Pokémon from the stall group in your team. "
            f"You cannot pick another Pokémon from this group.",
            ephemeral=True
        )
        await extend_timer(interaction, user, 60)
        return False

    # Check Species Clause
    if any(pokemon_data[p]["dex_number"] == pokemon_info["dex_number"] for p in draft_state["teams"][user]["pokemon"]):
        await interaction.response.send_message(
            f"You already have a Pokémon with the same Pokédex number in your team. "
            f"You cannot pick {pokemon_name.capitalize()} due to the Species Clause.",
            ephemeral=True
        )
        await extend_timer(interaction, user, 60)
        return False
    
    return True

#Points Validation - For checking if the pick is valid points-wise:
async def validate_points(interaction: discord.Interaction, pokemon_name: str, pokemon_info: dict, user) -> bool:
    """Validate if user has enough points for the pick"""
    remaining_picks = draft_size - len(draft_state["teams"][user]["pokemon"]) - 1
    min_points_required = calculate_minimum_points(draft_state["available_pokemon"], remaining_picks)
    current_points = draft_state["teams"][user]["points"]

    if pokemon_info["points"] > (current_points - min_points_required):
        valid_points = sorted(set(
            pokemon_data[name]["points"] 
            for name in draft_state["available_pokemon"]
            if pokemon_data[name]["points"] <= current_points - min_points_required
        ))
        
        message = (
            f"You cannot pick {pokemon_name.capitalize()} because it would leave you with insufficient points "
            f"to complete your team. You can pick a Pokémon with a maximum of **{valid_points[-1]}** points."
            "\n\nAvailable Tiers from which you can pick:\n"
            + "\n".join([f"• {point} points" for point in valid_points])
        )
        await interaction.response.send_message(message, ephemeral=True)
        await extend_timer(interaction, user, 60)
        return False
    
    return True

#Process Pick - Handles updating the draft state after a valid pick: (updated in v0.50)
def process_pick(user: discord.Member, pokemon_name: str, pokemon_info: dict) -> int:
    draft_state["teams"][user]["pokemon"].append(pokemon_name)
    draft_state["teams"][user]["points"] -= pokemon_info["points"]
    draft_state["available_pokemon"].remove(pokemon_name)
    
    if user in draft_state["extensions"]:
        draft_state["extensions"][user] = 0
        logger.info(f"Reset extension count for {user.name}.")

    if user in remaining_times:
        logger.info(f"Clearing remaining time for {user.name}. Previous remaining time: {remaining_times[user]} seconds.")
        del remaining_times[user]
    else:
        logger.info(f"No remaining time to clear for {user.name}.")
    
    # Update the Google Sheet
    update_google_sheet()
    
    return draft_state["teams"][user]["points"]
 
'''v0.46'''
##Confirmation View Class
class PickConfirmationView(discord.ui.View):
    def __init__(self, remaining_time: int, timeout=30):
        super().__init__(timeout=timeout)
        self.value = None
        self.remaining_time = remaining_time  # Store the remaining time when view is created
        self.clicked = False  # Track if a button has been clicked

    async def disable_all_buttons(self, interaction: discord.Interaction):
        """Disable all buttons and update the message"""
        for item in self.children:
            item.disabled = True
        # Update message with disabled buttons immediately
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:  # Prevent multiple clicks
            return
        self.clicked = True
        
        # Disable buttons immediately
        await self.disable_all_buttons(interaction)
        
        # Then process the confirmation
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:  # Prevent multiple clicks
            return
        self.clicked = True
        
        # Disable buttons immediately
        await self.disable_all_buttons(interaction)
        
        # Then process the cancellation
        self.value = False
        self.stop()

    async def on_timeout(self):
        self.value = None
        # Disable all buttons
        for item in self.children:
            item.disabled = True

'''v0.51'''
#Class for skip confirmation
class SkipConfirmationView(discord.ui.View):
    def __init__(self, timeout=30):
        super().__init__(timeout=timeout)
        self.value = None
        self.clicked = False  # Track if a button has been clicked

    async def disable_all_buttons(self, interaction: discord.Interaction):
        """Disable all buttons and update the message"""
        for item in self.children:
            item.disabled = True
        # Update message with disabled buttons immediately
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Confirm Skip", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:  # Prevent multiple clicks
            return
        self.clicked = True
        
        # Disable buttons immediately
        await self.disable_all_buttons(interaction)
        
        # Then process the confirmation
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:  # Prevent multiple clicks
            return
        self.clicked = True
        
        # Disable buttons immediately
        await self.disable_all_buttons(interaction)
        
        # Then process the cancellation
        self.value = False
        self.stop()

    async def on_timeout(self):
        self.value = None
        # Disable all buttons
        for item in self.children:
            item.disabled = True

#Slash command to skip coach turnn
@bot.tree.command(name="skip", description="Skip the current player's turn (Draft Staff only)", guild=GUILD_ID)
@has_draft_staff_role()
async def skip_command(interaction: discord.Interaction):
    # Defer immediately since we'll do multiple operations
    await interaction.response.defer()

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /skip."
    )
    # Get the current participant that will be skipped
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]

    # Validate draft state first
    if not draft_state["participants"]:
        await interaction.followup.send("No draft is currently in progress.", ephemeral=True)
        return

    if draft_state["is_paused"]:
        await interaction.followup.send("The draft is currently paused. Cannot skip turns while paused.", ephemeral=True)
        return

    # Create confirmation embed
    confirmation_embed = discord.Embed(
        title="⚠️ Confirm Skip",
        description=f"Are you sure you want to skip {current_user.mention}'s turn?",
        color=discord.Color.red()
    )
    confirmation_embed.add_field(
        name="Current Status",
        value=(
            f"• Player: {current_user.display_name}\n"
            f"• Previous Skips: {draft_state['skipped_turns'].get(current_user, 0)}\n"
            f"• Remaining Time: {format_time(remaining_times.get(current_user, TIMER_DURATION))}"
        )
    )
    confirmation_embed.set_footer(text="You have 30 seconds to confirm")

    # Create and send the view with confirmation buttons
    view = SkipConfirmationView()
    await interaction.followup.send(embed=confirmation_embed, view=view, ephemeral=True)

    # Wait for the user's response
    await view.wait()

    if view.value is None:
        await interaction.followup.send("Skip confirmation timed out.", ephemeral=True)
        return
    
    if not view.value:
        await interaction.followup.send("Skip cancelled.", ephemeral=True)
        return

    # Proceed with the skip
    # Cancel the current timer
    await cancel_timer(current_user)

    # Clear any remaining time for the user
    if current_user in remaining_times:
        del remaining_times[current_user]

    # Increment skip counter
    if current_user not in draft_state["skipped_turns"]:
        draft_state["skipped_turns"][current_user] = 0
    draft_state["skipped_turns"][current_user] += 1

    # Reset auto-extensions counter when turn is skipped
    if current_user in draft_state["auto_extensions"]:
        logger.info(f"Resetting auto-extensions counter for {current_user.name} due to turn skip")
        draft_state["auto_extensions"][current_user] = 0

    # Log the skip
    logger.info(f"Draft Staff {interaction.user.name} skipped {current_user.name}'s turn. Total skips: {draft_state['skipped_turns'][current_user]}")

    # Announce the skip
    await interaction.followup.send(
        f"⏭️ {interaction.user.mention} has skipped {current_user.mention}'s turn.\n"
        f"This is skip #{draft_state['skipped_turns'][current_user]} for {current_user.display_name}."
    )

    # Update Google Sheet to reflect the skip
    try:
        update_google_sheet()
    except Exception as e:
        logger.error(f"Error updating Google Sheet after skip: {e}")
        await interaction.followup.send(
            "⚠️ The skip was processed, but there was an error updating the Google Sheet.",
            ephemeral=True
        )

    # Move to next participant
    await next_participant(interaction)

# Slash command to make a pick (specific to the guild)
@bot.tree.command(name="pick", description="Pick a Pokémon", guild=GUILD_ID)
@app_commands.describe(pokemon_name="Name of the Pokémon to pick")
@has_draft_role()
async def pick_pokemon(interaction: discord.Interaction, pokemon_name: str):
    global participant_timers, remaining_times
    user = interaction.user
    
    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /pick with Pokémon: {pokemon_name}."
    )

    # --- 1. Initial validations ---
    if not await validate_draft_state(interaction, user):
        return
    if not await validate_turn(interaction, user):
        return

    # --- 2. Pokemon validation ---
    is_valid, pokemon_info = await validate_pokemon_name(interaction, pokemon_name, user)
    if not is_valid:
        return

    # --- 3. Rules validation ---
    if not await validate_pokemon_rules(interaction, pokemon_name, pokemon_info, user):
        return

    # --- 4. Points validation ---
    if not await validate_points(interaction, pokemon_name, pokemon_info, user):
        return

        # Get current timer before canceling it
    current_timer = participant_timers.get(user)
    
    # Get the CURRENT remaining time before canceling the timer
    current_remaining_time = remaining_times.get(user)
    
    # Cancel current timer - this will update remaining_times with the latest value
    if current_timer:
        await cancel_timer(user)
        current_remaining_time = remaining_times.get(user)
        logger.info(f"Captured remaining time for {user.name}: {current_remaining_time} seconds")

    # Send public message if remaining time is less than a minute
    if current_remaining_time and current_remaining_time < 60:
        await interaction.channel.send(f" {user.display_name} is confirming their Pokémon pick, timer will resume in 30 seconds")

    # --- 5. Create confirmation message ---
    confirmation_embed = discord.Embed(
        title="Confirm Your Pick",
        description=f"Are you sure you want to pick **{pokemon_name.capitalize()}**?",
        color=discord.Color.blue()
    )
    confirmation_embed.add_field(
        name="Details",
        value=f"• Points: {pokemon_info['points']}\n"
              f"• Remaining Points After Pick: {draft_state['teams'][user]['points'] - pokemon_info['points']}\n"
              f"• Timer will resume with: **{format_time(current_remaining_time)}**"
    )
    confirmation_embed.set_thumbnail(
        url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_info['id']}.png"
    )
    confirmation_embed.set_footer(
        text="You have 30 seconds to confirm your pick"
    )

      # Create and send the view with the confirmation buttons
    view = PickConfirmationView(current_remaining_time)
    await interaction.response.send_message(embed=confirmation_embed, view=view, ephemeral=True)

    # Wait for the user's response
    await view.wait()

    # Initialize auto-extensions counter if not exists
    if user not in draft_state["auto_extensions"]:
        draft_state["auto_extensions"][user] = 0

    if view.value is None or not view.value:
        # For both timeout and cancellation
        resume_time = current_remaining_time
        
        # Check if automatic extension should be applied
        if current_remaining_time < 60 and draft_state["auto_extensions"][user] < 3:
            resume_time = current_remaining_time + 60
            draft_state["auto_extensions"][user] += 1
            logger.info(f"{user.name} received automatic extension #{draft_state['auto_extensions'][user]}")
            
            # Prepare extension message
            extensions_left = 3 - draft_state["auto_extensions"][user]
            extension_msg = (
                f"Your remaining time was less than 1 minute. "
                f"You've been granted a 60-second extension. "
                f"You have {extensions_left} automatic extension{'s' if extensions_left != 1 else ''} remaining this turn."
            )
        else:
            extension_msg = (
                "No automatic extension granted. " +
                ("You've used all 3 automatic extensions this turn." if draft_state["auto_extensions"][user] >= 3 else "")
            )

        # Resume timer with appropriate time
        timer_task = asyncio.create_task(start_timer(interaction, user, resume_time))
        participant_timers[user] = timer_task
        
        await interaction.followup.send(
            "Pick confirmation timed out. Please try again.\n" + extension_msg if view.value is None 
            else "Pick cancelled. You can try picking another Pokémon.\n" + extension_msg, 
            ephemeral=True
        )
        return

    # --- 6. Process confirmed pick ---
    points_left = process_pick(user, pokemon_name, pokemon_info)
    
    # Reset auto-extensions counter after successful pick
    if user in draft_state["auto_extensions"]:
        logger.info(f"Resetting auto-extensions counter for {user.name}")
        draft_state["auto_extensions"][user] = 0
    
    # --- 7. Send announcement ---
    embed = create_pick_announcement_embed(user, pokemon_name, pokemon_info)
    await interaction.followup.send(embed=embed)

    # --- 8. Handle draft progression ---
    if len(draft_state["teams"][user]["pokemon"]) < draft_size:
        await interaction.followup.send(f"{user.mention}, you now have **{points_left} points** remaining.", ephemeral=True)
    else:
        await cancel_timer(user)
        draft_state["order"] = [p for p in draft_state["order"] if p != user]
        await interaction.followup.send(f"{user.mention}, your draft is complete! You will no longer be part of the rotation.")

    if all(len(team["pokemon"]) == draft_size for team in draft_state["teams"].values()):
        await show_final_teams(interaction)
        draft_state["participants"] = []
        draft_state["order"] = []
        draft_state["current_pick"] = 0
        draft_state["teams"] = {}
        draft_state["available_pokemon"] = pokemon_names.copy()
        await interaction.followup.send("The draft has finished! The draft state has been reset.")
        return

    await next_participant(interaction)

# Function to autocomplete for Pokémon names (specific to the guild)
@pick_pokemon.autocomplete('pokemon_name')
async def pokemon_name_autocomplete(interaction: discord.Interaction, current: str):
    # Get a list of Pokémon names and their points
    suggestions = [
        (name, pokemon_data[name]["points"])
        for name in draft_state["available_pokemon"]
    ]
    
    # Filter suggestions based on the user's input
    filtered_suggestions = [
        (name, points)
        for name, points in suggestions
        if current.lower() in name.lower() or current == str(points)
    ]
    
    # Sort suggestions by name (optional)
    filtered_suggestions.sort(key=lambda x: x[0])
    
    # Format the suggestions as "Pokémon Name (Points)"
    choices = [
        app_commands.Choice(name=f"{name.capitalize()} ({points} points)", value=name)
        for name, points in filtered_suggestions[:25]  # Limit to first 25 matches
    ]
    
    await interaction.response.autocomplete(choices)


# Slash command to clear all messages in the current channel
@bot.tree.command(name="clear", description="Clear all messages in the current channel", guild=GUILD_ID)
@has_draft_staff_role()
async def clear_messages_command(interaction: discord.Interaction):

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /clear."
    )

    if draft_state["is_paused"]:
        await interaction.response.send_message("The draft is currently paused. Messages can't be deleted at this moment.", ephemeral=True)
        return

    # Check if the bot has the required permissions
    if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
        await interaction.response.send_message("I don't have permission to manage messages in this channel.", ephemeral=True)
        return

    await interaction.response.send_message("Clearing all messages...", ephemeral=True)

    try:
        # Use the purge method to bulk delete messages
        deleted = await interaction.channel.purge(limit=None)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to clear messages: {e}")
        await interaction.followup.send(f"An error occurred while clearing messages: {e}", ephemeral=True)

#Slash Command to pause the draft
@bot.tree.command(name="pause_draft", description="Pause the current draft", guild=GUILD_ID)
@has_draft_staff_role()
async def pause_draft_command(interaction: discord.Interaction):
    global draft_state

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /pause_draft."
    )

    # Check if a draft is in progress
    if not draft_state["participants"]:
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return

    # Check if the draft is already paused
    if draft_state["is_paused"]:
        await interaction.response.send_message("The draft is already paused.", ephemeral=True)
        return

    # Cancel the current timer and store the remaining time
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    await cancel_timer(current_user)

    # Set the draft to paused state
    draft_state["is_paused"] = True

    await interaction.response.send_message(f"The draft has been paused. {current_user.mention} was in turn.")

#Slash Command to resume the draft
@bot.tree.command(name="resume_draft", description="Resume the paused draft", guild=GUILD_ID)
@has_draft_staff_role()
async def resume_draft_command(interaction: discord.Interaction):
    global draft_state

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /resume_draft."
    )

    # Check if a draft is in progress
    if not draft_state["participants"]:
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return

    # Check if the draft is not paused
    if not draft_state["is_paused"]:
        await interaction.response.send_message("The draft is not paused.", ephemeral=True)
        return

    # Set the draft to active state
    draft_state["is_paused"] = False

    # Resume the timer for the current participant
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    remaining_time = remaining_times.get(current_user, TIMER_DURATION)
    timer_task = asyncio.create_task(start_timer(interaction, current_user, remaining_time))
    participant_timers[current_user] = timer_task

    await interaction.response.send_message(f"The draft has been resumed. {current_user.mention}, you have {format_time(remaining_time)} remaining.")

# Slash command to check current draft
@bot.tree.command(name="my_draft", description="View your current draft", guild=GUILD_ID)
@has_draft_role()
async def my_draft_command(interaction: discord.Interaction):
    user = interaction.user

    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /my_draft."
    )

    # Check if a draft is in progress
    if not draft_state["participants"]:
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return

    if user not in draft_state["participants"]:
        await interaction.response.send_message("You are not part of the draft.", ephemeral=True)
        return

    team = draft_state["teams"][user]
    pokemon_list = ", ".join(team["pokemon"]) if team["pokemon"] else "None"
    points_left = team["points"]

    embed = discord.Embed(
        title=f"{user.display_name}'s Draft",
        description=f"**Pokémon:** {pokemon_list}\n**Points Left:** {points_left}",
        color=discord.Color.blue()
    )

    try:
        await user.send(embed=embed)
        await interaction.response.send_message("Check your DMs for your draft details!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(embed=embed, ephemeral=True)

'''v0.52'''
#Class for ConfirmationView
class ConfirmationView(discord.ui.View):
    """
    A generic confirmation view with Yes/No buttons.
    Buttons are disabled immediately upon clicking.
    """
    def __init__(self, timeout=30):
        super().__init__(timeout=timeout)
        self.value = None
        self.clicked = False  # Track if a button has been clicked

    async def disable_all_buttons(self, interaction: discord.Interaction):
        """Disable all buttons and update the message"""
        for item in self.children:
            item.disabled = True
        # Update message with disabled buttons immediately
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:  # Prevent multiple clicks
            return
        self.clicked = True
        
        # Disable buttons immediately
        await self.disable_all_buttons(interaction)
        
        # Then process the confirmation
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:  # Prevent multiple clicks
            return
        self.clicked = True
        
        # Disable buttons immediately
        await self.disable_all_buttons(interaction)
        
        # Then process the cancellation
        self.value = False
        self.stop()

    async def on_timeout(self):
        self.value = None
        # Disable all buttons
        for item in self.children:
            item.disabled = True

#Slash Command to swap pokémon
@bot.tree.command(
    name="swap_pokemon",
    description="Swap a Pokémon in a coach's team with another available Pokémon ",
    guild=GUILD_ID
)
@app_commands.describe(
    coach="The coach whose team you want to modify",
    current_pokemon="The Pokémon to remove from the team",
    new_pokemon="The Pokémon to add to the team"
)
@has_draft_staff_role()
async def swap_pokemon_command(
    interaction: discord.Interaction,
    coach: str,
    current_pokemon: str,
    new_pokemon: str
):
    # Defer response due to potentially longer processing time
    await interaction.response.defer(ephemeral=True)
    
    logger.info(
        f"User {interaction.user.name} (ID: {interaction.user.id}) used /swap_pokemon with coach: {coach}, current_pokemon: {current_pokemon}, new_pokemon: {new_pokemon}."
    )
    try:
        # Validate draft state and pause status
        if not draft_state["participants"]:
            await interaction.followup.send(
                "❌ No draft is currently in progress.",
                ephemeral=True
            )
            return

        # Check if draft is paused
        if not draft_state["is_paused"]:
            await interaction.followup.send(
                "❌ The draft must be paused before making team modifications.\n"
                "Please use `/pause_draft` first.",
                ephemeral=True
            )
            return

        # Convert coach ID to member object
        coach_id = int(coach)
        coach_member = interaction.guild.get_member(coach_id)
        
        if not coach_member:
            await interaction.followup.send(
                "❌ Could not find the specified coach.",
                ephemeral=True
            )
            return

        if coach_member not in draft_state["teams"]:
            await interaction.followup.send(
                f"❌ {coach_member.display_name} is not part of the current draft.",
                ephemeral=True
            )
            return

        # Normalize pokemon names
        current_pokemon = current_pokemon.lower()
        new_pokemon = new_pokemon.lower()

        # Validate current_pokemon is in coach's team
        if current_pokemon not in draft_state["teams"][coach_member]["pokemon"]:
            await interaction.followup.send(
                f"❌ {current_pokemon.capitalize()} is not in {coach_member.display_name}'s team.",
                ephemeral=True
            )
            return

        # Validate new_pokemon exists in pokemon_data
        if new_pokemon not in pokemon_data:
            similar_names = difflib.get_close_matches(new_pokemon, pokemon_names, n=5, cutoff=0.6)
            message = (
                f"❌ Invalid Pokémon name: {new_pokemon}. Did you mean one of these?\n" +
                "\n".join(similar_names) if similar_names else "No similar names found."
            )
            await interaction.followup.send(message, ephemeral=True)
            return

        # Calculate points difference
        current_points = pokemon_data[current_pokemon]["points"]
        new_points = pokemon_data[new_pokemon]["points"]
        points_difference = new_points - current_points
        new_total_points = draft_state["teams"][coach_member]["points"] - points_difference

        # Validate new_pokemon is available (not in any team)
        for team_member, team_data in draft_state["teams"].items():
            if new_pokemon in team_data["pokemon"]:
                await interaction.followup.send(
                    f"❌ {new_pokemon.capitalize()} is already in {team_member.display_name}'s team.\n"
                    "You can only swap with Pokémon that haven't been picked yet.",
                    ephemeral=True
                )
                return

        # Check if the swap would exceed points limit
        if new_total_points < 0:
            await interaction.followup.send(
                f"❌ This swap would exceed the points limit for {coach_member.display_name}'s team.\n"
                f"Current points: {draft_state['teams'][coach_member]['points']}\n"
                f"Points difference: {points_difference}\n"
                f"Resulting points: {new_total_points}",
                ephemeral=True
            )
            return

        # Validate Species Clause
        new_pokemon_dex = pokemon_data[new_pokemon]["dex_number"]
        team_without_current = [p for p in draft_state["teams"][coach_member]["pokemon"] if p != current_pokemon]
        if any(pokemon_data[p]["dex_number"] == new_pokemon_dex for p in team_without_current):
            await interaction.followup.send(
                f"❌ Cannot add {new_pokemon.capitalize()} due to Species Clause violation.",
                ephemeral=True
            )
            return

        # Validate Stall Group
        if new_pokemon in stall_group:
            current_stall_count = sum(1 for p in team_without_current if p in stall_group)
            if current_stall_count >= 2:
                await interaction.followup.send(
                    f"❌ Cannot add {new_pokemon.capitalize()} as it would exceed the stall group limit.",
                    ephemeral=True
                )
                return

        # Create confirmation embed with pause reminder
        embed = discord.Embed(
            title="⚠️ Confirm Pokémon Swap",
            description=(
                f"Are you sure you want to swap Pokémon in {coach_member.display_name}'s team?\n\n"
                "**Note:** Remember to use `/resume_draft` after making all necessary changes."
            ),
            color=discord.Color.yellow()
        )
        embed.add_field(
            name="Swap Details",
            value=(
                f"**Remove:** {current_pokemon.capitalize()} ({current_points} points)\n"
                f"**Add:** {new_pokemon.capitalize()} ({new_points} points)\n"
                f"**Points Change:** {points_difference:+d}\n"
                f"**New Total Points:** {new_total_points}"
            )
        )

        # Create confirmation view
        view = ConfirmationView(timeout=30)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        # Wait for confirmation
        await view.wait()

        if not view.value:
            await interaction.followup.send(
                "❌ Swap cancelled or timed out.",
                ephemeral=True
            )
            return

        # Perform the swap
        team = draft_state["teams"][coach_member]["pokemon"]
        team[team.index(current_pokemon)] = new_pokemon
        draft_state["teams"][coach_member]["points"] = new_total_points

        # If new_pokemon was in available_pokemon, remove it
        if new_pokemon in draft_state["available_pokemon"]:
            draft_state["available_pokemon"].remove(new_pokemon)
        # Add current_pokemon back to available_pokemon if it's not already there
        if current_pokemon not in draft_state["available_pokemon"]:
            draft_state["available_pokemon"].append(current_pokemon)

        # Update Google Sheet
        try:
            update_google_sheet()
        except Exception as e:
            logger.error(f"Error updating Google Sheet after swap: {e}")
            await interaction.followup.send(
                "⚠️ Swap completed but there was an error updating the Google Sheet.",
                ephemeral=True
            )

        # Send success message with embed and resume reminder
        success_embed = discord.Embed(
            title="✅ Pokémon Swap Successful",
            description=(
                f"Modified {coach_member.display_name}'s team:\n\n"
                "**Don't forget!** Use `/resume_draft` when you're done making changes."
            ),
            color=discord.Color.green()
        )
        success_embed.add_field(
            name="Swap Details",
            value=(
                f"**Removed:** {current_pokemon.capitalize()}\n"
                f"**Added:** {new_pokemon.capitalize()}\n"
                f"**New Points Total:** {new_total_points}"
            )
        )
        await interaction.followup.send(embed=success_embed)

        # Log the swap
        logger.info(
            f"Draft Staff {interaction.user.name} swapped {current_pokemon} for {new_pokemon} "
            f"in {coach_member.display_name}'s team while draft was paused"
        )

    except Exception as e:
        logger.error(f"Error in swap_pokemon_command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while processing the swap. Please try again or contact the administrator.",
            ephemeral=True
        )

# Autocomplete functions remain the same as in the previous version
@swap_pokemon_command.autocomplete('coach')
async def swap_coach_autocomplete(interaction: discord.Interaction, current: str):
    """
    Autocomplete for coach selection in swap_pokemon command.
    Only shows coaches that are part of the current draft.
    """
    if not draft_state["participants"]:
        return []
    
    coaches = [
        app_commands.Choice(name=member.display_name, value=str(member.id))
        for member in draft_state["participants"]
        if current.lower() in member.display_name.lower()
    ]
    return coaches[:25]

@swap_pokemon_command.autocomplete('current_pokemon')
async def swap_current_pokemon_autocomplete(interaction: discord.Interaction, current: str):
    """
    Autocomplete for current_pokemon selection in swap_pokemon command.
    Shows only Pokémon in the selected coach's team.
    """
    try:
        # Get the coach ID from the interaction
        coach_id = int(interaction.namespace.coach)
        coach_member = interaction.guild.get_member(coach_id)
        
        if not coach_member or coach_member not in draft_state["teams"]:
            return []

        # Get the coach's current team
        team = draft_state["teams"][coach_member]["pokemon"]
        
        # Filter and format suggestions
        suggestions = [
            app_commands.Choice(
                name=f"{name.capitalize()} ({pokemon_data[name]['points']} points)",
                value=name
            )
            for name in team
            if current.lower() in name.lower()
        ]
        return suggestions[:25]
    except (ValueError, AttributeError):
        return []

@swap_pokemon_command.autocomplete('new_pokemon')
async def swap_new_pokemon_autocomplete(interaction: discord.Interaction, current: str):
    """
    Autocomplete for new_pokemon selection in swap_pokemon command.
    Shows only Pokémon that are still available (not picked by any coach).
    """
    try:
        # Get only the available Pokémon (not in any team)
        available_pokemon = set(draft_state["available_pokemon"])
        
        # Filter and format suggestions
        suggestions = [
            app_commands.Choice(
                name=f"{name.capitalize()} ({pokemon_data[name]['points']} points)",
                value=name
            )
            for name in available_pokemon
            if current.lower() in name.lower()
        ]
        return sorted(suggestions, key=lambda x: x.name)[:25]
    except Exception as e:
        logger.error(f"Error in swap_new_pokemon_autocomplete: {e}")
        return []

# Run the bot with your token
bot.run(taken.TOKEN)