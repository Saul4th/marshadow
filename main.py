'''

    0.62 work on improving the /my_draft embed format -OK
    0.63 figure out how to include the team logo in the final collage -OK
    0.63.1 Added new slash command to set logos and fixed minor bugs found in the final grid and other functions -OK
    0.64 Traducir a español
    0.65 Documentar requerimientos

    Después de eso, versión pre-alpha (base antes de incluir tera caps) debería estar lista 
'''
'''LIBRARIES'''
import discord                          #Core Discord.py functionality 
from discord import app_commands        #Used throughout for bot commands and interactions
from discord.ext import commands        #Used throughout for bot commands and interactions
import pandas as pd                     #For pandas usage in load_pokemon_data_from_google_sheets() ONLY
import taken                            #Custom module for storing the bot token
import difflib                          #Used for Pokémon name suggestions in validate_pokemon_name() and swap_pokemon_command()
from PIL import Image                   #Used for creating team collages in create_sprite_collage()
import requests                         #Used for fetching Pokémon sprites and avatars
from io import BytesIO                  #Used with PIL for image processing
import asyncio                          #Used for timer functionality throughout the draft
import logging                          #Used throughout for debug and error logging
import gspread                                                     #Used for Google Sheets integration
from oauth2client.service_account import ServiceAccountCredentials #Used for Google Sheets integration
import os                                                          #Used for working directory and file paths
from google.oauth2.service_account import Credentials              #Used for Google Drive API authentication and access
from googleapiclient.discovery import build                        #Used for Google Drive API authentication and access
from datetime import datetime, UTC, timezone                       #For handling timezone-aware timestamps in token refresh and security validation
from dataclasses import dataclass       # For creating the SecurityMetadata class with clean attribute definitions
import secrets                          # For generating cryptographically strong random keys for instance tracking
from typing import Optional             # For type hinting functions that might return None (like get_sheets_client)
from state_manager import StateManager
import signal
import sys
import time
import random
import json
from pathlib import Path  # Add this at the top with your other imports

print("Current Working Directory:", os.getcwd())   #Can be removed as needed

'''GLOBAL VARIABLES'''
# Modify the constant to use Path
TEAM_LOGOS_DIR = Path("assets/team_logos")
TEAM_LOGOS_DIR.mkdir(parents=True, exist_ok=True)  # Create directory if it doesn't exist

# Set the maximum number of timer extensions allowed per participant
extensions_limit = 3  # You can adjust this value

# Set the guild ID for the slash commands
GUILD_ID = discord.Object(id=1326634506605691080)  # Replace with your guild ID

#Set the guild ID for bot.event
GUILD_ID_RAW = 1326634506605691080

# Define the stall group (replace with actual Pokémon names)
stall_group = ["blissey", "toxapex", "skarmory", "chansey","clefable","clodsire","corviknight","cresselia","dondozo","garganacl","gliscor","mandibuzz","quagsire","slowking-galar"]

# Set variable for number of Pokémon per Draft
draft_size = 4
total_points = 1200

# Define the number of coaches allowed in the draft
coaches_size = 2 # Default value

# Timer duration (in seconds)
TIMER_DURATION = 720 # Default timer duration (1 minute)
timer_task = None  # Global variable to store the timer task

# Dictionary to store timers for each participant
participant_timers = {}

# Global variable to track remaining time for each participant
remaining_times = {}

# Store your Discord ID in a constant at the top of the file for easy reference
PRIORITY_STAFF_ID = 361021962585112576  # Your Discord ID

# In the global scope, add a variable to track which staff members have been contacted
staff_notification_attempts = {}

# Global variable to track pending draft state
pending_draft_state = None

'''INITIALIZE'''
# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Define the log format
    handlers=[
        logging.FileHandler("draft_bot.log"),  # Log to a file
        logging.StreamHandler()  # Log to the console
    ]
)

# Create a logger instance
logger = logging.getLogger(__name__)

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Enable server members intent
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

#SecureGoogleServicesManager [v0.56] - block to Authenticate Google Sheets
@dataclass
class SecurityMetadata:
    """Tracks security-related metadata for credentials"""
    last_refresh: datetime
    instance_id: str
    initialization_time: datetime

class SecureGoogleServicesManager:
    """Manages Google service connections with enhanced security"""
    
    def __init__(self):
        self._sheets_client = None
        self._drive_service = None
        self._credentials = None
        self._security = None
        # Generate unique instance ID for tracking
        self._instance_key = secrets.token_urlsafe(32)
        
    def initialize(self) -> bool:
        """Initialize Google services with security tracking"""
        try:
            logger.info("Initializing Google services...")
            
            # Define the scope
            scope = ["https://spreadsheets.google.com/feeds", 
                    "https://www.googleapis.com/auth/drive"]
            
            # Load credentials from the JSON file
            logger.info("Loading credentials from file...")
            self._credentials = ServiceAccountCredentials.from_json_keyfile_name(
                "credentials.json", 
                scope
            )
            
            # Initialize sheets client
            logger.info("Authorizing sheets client...")
            self._sheets_client = gspread.authorize(self._credentials)
            
            # Initialize drive service
            logger.info("Initializing drive service...")
            self._drive_service = build(
                "drive", 
                "v3",
                credentials=Credentials.from_service_account_file(
                    "credentials.json",
                    scopes=["https://www.googleapis.com/auth/drive"]
                ),
                cache_discovery=False
            )
            
            # Initialize security metadata with timezone-aware datetime
            current_time = datetime.now(UTC)
            self._security = SecurityMetadata(
                last_refresh=current_time,
                instance_id=self._instance_key,
                initialization_time=current_time
            )
            
            logger.info(
                f"Successfully initialized Google services (Instance: {self._instance_key[:8]})"
            )
            return True
            
        except FileNotFoundError:
            logger.error("Credentials file (credentials.json) not found")
            self._cleanup()
            return False
        except Exception as e:
            logger.error(
                f"Failed to initialize Google services (Instance: {self._instance_key[:8]}): {e}"
            )
            self._cleanup()
            return False
                        
    def _cleanup(self):
        """Clean up sensitive data"""
        self._sheets_client = None
        self._drive_service = None
        self._credentials = None
        import gc
        gc.collect()
            
    def force_refresh(self) -> bool:
        """Force a refresh of credentials with security checks"""
        try:
            if not self._security or self._security.instance_id != self._instance_key:
                logger.error("Security validation failed - instance mismatch")
                return False
                
            if self._credentials:
                logger.info(f"Refreshing token at {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                self._credentials.refresh()
                self._sheets_client = gspread.authorize(self._credentials)
                self._security.last_refresh = datetime.now(UTC)
                logger.info(
                    f"Token refresh successful (Instance: {self._instance_key[:8]})"
                )
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Force refresh failed: {e}")
            return False
            
    def get_sheets_client(self) -> Optional[gspread.Client]:
        """Get sheets client with security checks"""
        if not self._validate_security():
            return None
            
        try:
            # Check if token needs refresh
            if self._credentials.access_token_expired:
                if not self.force_refresh():
                    return None
                    
            # Check for token age (12 hours)
            token_age = datetime.now(UTC) - self._security.last_refresh
            if token_age.total_seconds() > 43200:  # 12 hours
                logger.warning(
                    f"Token age exceeds 12 hours (Instance: {self._instance_key[:8]}), forcing refresh"
                )
                if not self.force_refresh():
                    return None
                    
            return self._sheets_client
            
        except Exception as e:
            logger.error(
                f"Error getting sheets client (Instance: {self._instance_key[:8]}): {e}"
            )
            return None
            
    def get_drive_service(self):
        """Get drive service with security checks"""
        if not self._validate_security():
            return None
        return self._drive_service
        
    def _validate_security(self) -> bool:
        """Validate security state"""
        if not self._security:
            logger.error("Security metadata missing")
            return False
            
        if self._security.instance_id != self._instance_key:
            logger.error("Instance ID mismatch - possible security issue")
            return False
            
        # Check initialization age (24 hours)
        init_age = datetime.now(UTC) - self._security.initialization_time
        if init_age.total_seconds() > 86400:  # 24 hours
            logger.warning("Security timeout - requiring reinitialization")
            return self.initialize()
            
        return True

# Initialize Google Services Manager
google_services = SecureGoogleServicesManager()
if not google_services.initialize():
    logger.error("Failed to initialize Google Services Manager")
    exit(1)  # Exit if we can't initialize Google services

# Function to create a 6x2 grid collage with the user's avatar in position (1,1)
def create_sprite_collage(pokemon_names, pokemon_data, avatar_url, user_id):
    images = []
    
    # Try to get team logo first
    logo_path = TEAM_LOGOS_DIR / f"{user_id}.png"
    if logo_path.exists():
        try:
            logo_img = Image.open(logo_path)
            logo_img = logo_img.resize((96, 96))  # Resize logo to match sprite size
            images.append(logo_img)  # Add logo as the first image
        except Exception as e:
            logger.error(f"Failed to load team logo for user {user_id}: {e}")
            # Fallback to avatar
            if avatar_url:
                response = requests.get(avatar_url)
                if response.status_code == 200:
                    avatar_img = Image.open(BytesIO(response.content))
                    avatar_img = avatar_img.resize((96, 96))
                    images.append(avatar_img)
            else:
                default_avatar = Image.new("RGBA", (96, 96), (255, 255, 255, 0))  # Transparent image
                images.append(default_avatar)
    else:
        # No logo exists, use avatar
        if avatar_url:
            response = requests.get(avatar_url)
            if response.status_code == 200:
                avatar_img = Image.open(BytesIO(response.content))
                avatar_img = avatar_img.resize((96, 96))
                images.append(avatar_img)
        else:
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
    
   # Create a blank canvas for the collage
    sprite_width = 96  # Width of each sprite
    sprite_height = 96  # Height of each sprite
    # Calculate collage width based on whether draft_size is odd or even
    if draft_size % 2 == 0:
        collage_width = sprite_width * ((draft_size//2)+1)
    else:
        collage_width = sprite_width * (-(-draft_size//2)) 
    collage_height = sprite_height * 2
    collage = Image.new("RGBA", (collage_width, collage_height))

    # Calculate how many Pokémon per row
    first_row_pokemon = draft_size // 2  # This is the key change
    second_row_pokemon = (draft_size + 1) // 2  # For odd numbers, second row gets one more

    # Paste images into the grid
    for i, img in enumerate(images):
        if i >= draft_size + 1:  # Limit to draft_size + 1 (for logo) images
            break
            
        if i == 0:  # Logo always goes in top-left
            x = 0
            y = 0
        else:
            # For Pokémon images
            pokemon_index = i - 1  # Adjust index to account for logo
            
            if pokemon_index < first_row_pokemon:
                # First row
                x = (pokemon_index + 1) * sprite_width  # Start after logo
                y = 0
            else:
                # Second row
                second_row_index = pokemon_index - first_row_pokemon
                if draft_size % 2 == 0:  # Even number of Pokémon
                    x = (second_row_index + 1) * sprite_width  # Start indented
                else:  # Odd number of Pokémon
                    x = second_row_index * sprite_width  # Start from first column
                y = sprite_height

        collage.paste(img, (x, y))

    
    # Save the collage to a file
    collage.save("collage.png")
    return "collage.png"

# Block to Load Pokémon data from Google Sheets
def load_pokemon_data_from_google_sheets():
    """
    Load Pokémon data from a Google Sheet named "Pokemon Data" in a specific folder.
    """
    pokemon_data = {}
    try:
        # Get client from cached manager
        client = google_services.get_sheets_client()
        if not client:
            raise Exception("Failed to get Google Sheets client")
        
        # Define the folder ID and sheet name
        folder_id = "13B6DevETQRkLON7yuonkpAHiar0NwwyU"  # Replace with your folder ID
        sheet_name = "Pokemon Data"  # Replace with your sheet name
        
        # Get drive service from cached manager
        drive_service = google_services.get_drive_service()
        if not drive_service:
            raise Exception("Failed to get Google Drive service")
        
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
    # Verify Google services are initialized
    if not google_services._security:
        logger.error("Google services not properly initialized")
        exit(1)
        
    pokemon_data = load_pokemon_data_from_google_sheets()
    if not pokemon_data:
        logger.error("Failed to load Pokémon data. Exiting.")
        exit(1)
except Exception as e:
    logger.error(f"Failed to load Pokémon data: {e}")
    exit(1)

pokemon_names = list(pokemon_data.keys())

#Function to Update Google Sheets
def update_google_sheet(is_intentional_clear=False):
    max_retries = 5
    backoff_time = 1  # Start with 1 second
    for attempt in range(max_retries):
        try:
            # Get cached clients
            client = google_services.get_sheets_client()
            drive_service = google_services.get_drive_service()
            
            if not client or not drive_service:
                raise Exception("Failed to get Google services")
            
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
            
            # Clear the sheet
            pokemon_sheet = spreadsheet.sheet1
            pokemon_sheet.clear()
            logger.info("Cleared sheet.")

            # We'll use batch_update to set specific ranges
            batch_data = []

            # First row - section headers
            batch_data.append({
                'range': 'A1:E1',
                'values': [["Draft Status", "", "", "", "Skips Tracking"]]
            })

            # Second row - column headers
            batch_data.append({
                'range': 'A2:F2',
                'values': [["Coach", "Pokemon", "Points", "", "Coach", "Skips"]]
            })

            # Prepare data arrays
            picks_data = []
            if draft_state.get("teams"):
                for coach, team in draft_state["teams"].items():
                    for pokemon in team["pokemon"]:
                        picks_data.append([
                            coach.display_name,
                            pokemon,
                            pokemon_data[pokemon]["points"]
                        ])

            skips_data = []
            if draft_state.get("participants"):
                for participant in draft_state["participants"]:
                    skips_data.append([
                        participant.display_name,
                        draft_state["skipped_turns"].get(participant, 0)
                    ])

            # Combine data with specific range assignments
            max_rows = max(len(picks_data), len(skips_data))
            
            # Draft data (A3:C{max_rows+2})
            draft_values = []
            for i in range(max_rows):
                if i < len(picks_data):
                    draft_values.append(picks_data[i])
                else:
                    draft_values.append(["", "", ""])
            
            if draft_values:
                batch_data.append({
                    'range': f'A3:C{max_rows+2}',
                    'values': draft_values
                })

            # Skips data (E3:F{max_rows+2})
            skips_values = []
            for i in range(max_rows):
                if i < len(skips_data):
                    skips_values.append(skips_data[i])
                else:
                    skips_values.append(["", ""])
            
            if skips_values:
                batch_data.append({
                    'range': f'E3:F{max_rows+2}',
                    'values': skips_values
                })

            # Execute batch update
            pokemon_sheet.batch_update(batch_data)
            logger.info("Updated sheet with combined data.")
            return

        except Exception as e:
            logger.error(f"Error updating Google Sheet: {e}")
            if attempt < max_retries - 1:
                sleep_time = backoff_time + random.uniform(0, 1)  # Add jitter to prevent thundering herd
                logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                backoff_time *= 2  # Exponential backoff
            else:
                raise

# Draft state
draft_state = {
    'draft_channel_id': None,   
    'participants': [],           
    'order': [],
    'current_pick': 0,
    'teams': {},
    'available_pokemon': pokemon_names.copy(),
    'skipped_turns': {},
    'extensions': {},
    'is_paused': False,
    'auto_extensions': {},
    'draft_phase': 'setup',
    'main_message': None,
    'turn_original_durations': {},
    'notification_flags': {}  # Add this new field
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

# Create the draft_states directory if it doesn't exist
if not os.path.exists('draft_states'):
    os.makedirs('draft_states')

# Initialize state manager
state_manager = StateManager()

# Autosaver
class AutoSaver:
    def __init__(self, state_manager, save_interval=600):   #<--Interval is the duration in seconds between autosaves
        self.state_manager = state_manager
        self.save_interval = save_interval
        self.task = None
        self.last_save = None
        self.is_running = False  # New flag to track if auto-save should be running

    async def start(self):
        if not self.is_running:  # Only start if not already running
            self.is_running = True
            self.task = asyncio.create_task(self.auto_save_loop())
            logger.info("AutoSaver started")

    async def stop(self):
        if self.is_running:  # Only stop if currently running
            self.is_running = False
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
            logger.info("AutoSaver stopped")

    async def auto_save_loop(self):
        while self.is_running:  # Check running flag instead of True
            try:
                # First, check if there's an active draft
                if not draft_state.get("participants") or not draft_state.get("order"):
                    await asyncio.sleep(self.save_interval)
                    continue  # Skip this iteration and check again after interval

                # Capture current timer state before saving
                current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
                await capture_timer_state(current_user)

                # Debug logging to check state
                logger.info("Auto-save check conditions:")
                logger.info(f"Has participants: {bool(draft_state.get('participants'))}")
                logger.info(f"Has current_pick: {'current_pick' in draft_state}")
                logger.info(f"Has order: {'order' in draft_state}")

                order_length = len(draft_state.get("order", []))
                logger.info(f"Order length: {order_length}")

                if "current_pick" in draft_state:
                    if order_length > 0:
                        adjusted_pick = draft_state['current_pick'] % order_length
                    else:
                        adjusted_pick = 0
                    logger.info(f"Current pick (raw): {draft_state['current_pick']}")
                    logger.info(f"Current pick (adjusted): {adjusted_pick}")

                # Check if draft is still active
                if (draft_state.get("participants") and 
                    "current_pick" in draft_state and 
                    "order" in draft_state and 
                    order_length > 0):
                    
                    draft_state['current_pick'] = draft_state['current_pick'] % order_length
                    
                    filename = self.state_manager.save_state(
                        draft_state,
                        remaining_times
                    )
                    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    self.last_save = current_time
                    logger.info(f"Auto-saved draft state to {filename} at {current_time} UTC")
                else:
                    logger.debug("Skipping auto-save: draft complete or conditions not met")  # Changed to debug level
                    
            except Exception as e:
                logger.error(f"Failed to auto-save draft state: {e}")
                logger.error(f"Current draft state: {draft_state}")
            
            await asyncio.sleep(self.save_interval)

# Create auto-saver instance (after state_manager initialization)
auto_saver = AutoSaver(state_manager)

# Add these signal handlers
def handle_exit(signum, frame):
    logger.info("Received shutdown signal, attempting to save state...")
    
    try:
        if draft_state.get("participants"):
            # Get current participant
            current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
            
            if current_user in participant_timers:
                timer_task = participant_timers[current_user]
                if not timer_task.done():
                    # First, manually update remaining_times before cancelling
                    # This ensures we capture the time even if the CancelledError handler doesn't run
                    remaining_time = None
                    
                    # Get the task's internal state to find remaining time
                    for frame in timer_task.get_stack():
                        frame_locals = frame.f_locals
                        if 'remaining_time' in frame_locals:
                            remaining_time = frame_locals['remaining_time']
                            break
                    
                    if remaining_time is not None:
                        remaining_times[current_user] = remaining_time
                        logger.info(f"Manually stored remaining time for {current_user.name}: {remaining_time} seconds")
                    
                    # Now cancel the task
                    timer_task.cancel()
                    
                    # Small delay to allow for any cleanup
                    time.sleep(0.1)
            
            # Now save state with updated remaining_times
            filename = state_manager.save_state(
                draft_state,
                remaining_times
            )
            logger.info(f"Successfully saved draft state to {filename} during shutdown")
    except Exception as e:
        logger.error(f"Failed to save draft state during shutdown: {e}")
    
    logger.info("Shutting down bot...")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

# Modify your on_ready event
@bot.event
async def on_ready():
    global draft_state, remaining_times, participant_timers, pending_draft_state
    
    logger.info(f'Logged in as {bot.user}')
    
    # Debug: List all available guilds
    logger.info("Available guilds:")
    for guild in bot.guilds:
        logger.info(f"- {guild.name} (ID: {guild.id})")
    
    # Initialize Google services...
    if not google_services.initialize():
        logger.error("Failed to initialize Google services. Bot may not function correctly.")
        return
    
    # Wait for guild cache to be ready - use GUILD_ID_RAW here
    guild = None
    retries = 0
    max_retries = 5
    
    while not guild and retries < max_retries:
        guild = bot.get_guild(GUILD_ID_RAW)  # Use the raw ID here
        if not guild:
            logger.info(f"Waiting for guild to be available... (attempt {retries + 1}/{max_retries})")
            logger.info(f"Trying to access guild with ID: {GUILD_ID_RAW}")
            await asyncio.sleep(2)
            retries += 1
    
    if not guild:
        logger.error("Failed to get guild after maximum retries")
        return
    
    # Start auto-saver
    await auto_saver.start()
    
    # Check for save states - MODIFIED SECTION
    try:
        recovery_states = state_manager.list_saved_states()
        if recovery_states:
            latest_state = recovery_states[0][0]
            logger.info(f"Found saved draft state: {latest_state}")
            
            # First, let's load the save data to get the channel ID without actually applying the state
            try:
                with open(os.path.join(state_manager.save_directory, latest_state), 'r') as f:
                    saved_data = json.load(f)
                    
                original_channel_id = saved_data.get('draft_channel_id')
                if not original_channel_id:
                    logger.warning("No draft_channel_id found in saved state")
                    return
                
                # Fetch the original channel
                original_channel = guild.get_channel(original_channel_id)
                if not original_channel:
                    logger.error(f"Cannot find original draft channel (ID: {original_channel_id})")
                    return
                
                # Find staff members with "Draft Staff" role to notify
                staff_role = discord.utils.get(guild.roles, name="Draft Staff")
                staff_members = []
                
                if staff_role:
                    staff_members = [member for member in guild.members if staff_role in member.roles]
                    
                # Find the target staff member - prioritize you first
                target_staff = None
                
                # Look for you first by Discord ID
                for member in guild.members:
                    if member.id == PRIORITY_STAFF_ID and staff_role in member.roles:
                        target_staff = member
                        break
                
                # If you weren't found or don't have the role, fall back to other staff
                if not target_staff and staff_members:
                    # Prioritize staff members who are online
                    online_staff = [m for m in staff_members if m.status != discord.Status.offline]
                    target_staff = online_staff[0] if online_staff else staff_members[0]
                    
                # Create embed for the saved state
                saved_time = datetime.fromisoformat(recovery_states[0][1])
                formatted_time = saved_time.strftime("%Y-%m-%d %H:%M:%S")
                
                embed = discord.Embed(
                    title="🔄 Draft Save State Found",
                    description="A previous draft state was found. Would you like to restore it?",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Save Information",
                    value=f"• Filename: `{latest_state}`\n• Saved: {formatted_time}"
                )
                embed.set_footer(text="Use the buttons below to load or ignore this saved state")
                
                # Create view with load/ignore buttons
                view = SaveStatePromptView(state_manager, guild, latest_state, original_channel_id)
                
                # Initialize tracking for this file
                if latest_state not in staff_notification_attempts:
                    staff_notification_attempts[latest_state] = []
                
                if target_staff:
                    try:
                        # Send private DM with actionable buttons
                        dm_channel = await target_staff.create_dm()
                        view = SaveStatePromptView(state_manager, guild, latest_state, original_channel_id, target_staff)
                        message = await dm_channel.send(
                            f"📢 A saved draft state was found in {original_channel.mention}.\n"
                            f"Please decide whether to restore this draft state:",
                            embed=embed,
                            view=view
                        )
                        
                        # Store the message ID for future reference
                        view.message = message
                        logger.info(f"Sent save state prompt to {target_staff.name} via DM")
                        
                        # Record that this staff member was contacted
                        staff_notification_attempts[latest_state].append(target_staff.id)
                        
                        # Send notification to other staff members (without buttons)
                        for staff_member in staff_members:
                            if staff_member != target_staff:
                                try:
                                    dm_channel = await staff_member.create_dm()
                                    info_embed = discord.Embed(
                                        title="🔄 Draft Save State Found",
                                        description=f"A previous draft state was found. {target_staff.mention} has been notified to handle the restoration.",
                                        color=discord.Color.blue()
                                    )
                                    await dm_channel.send(embed=info_embed)
                                    logger.info(f"Sent notification to {staff_member.name} via DM")
                                except:
                                    logger.info(f"Could not send DM to {staff_member.name}")
                    except:
                        logger.error(f"Could not send DM to {target_staff.name}, trying another staff member")

                        # Add this staff member to the list of attempts
                        staff_notification_attempts[latest_state].append(target_staff.id)
                        
                        # Try another staff member
                        remaining_staff = [m for m in staff_members if m.id != target_staff.id]
                        if remaining_staff:
                            new_target = remaining_staff[0]
                            try:
                                dm_channel = await new_target.create_dm()
                                view = SaveStatePromptView(state_manager, guild, latest_state, original_channel_id, new_target)
                                message = await dm_channel.send(
                                    f"📢 A saved draft state was found in {original_channel.mention}.\n"
                                    f"Please decide whether to restore this draft state:",
                                    embed=embed,
                                    view=view
                                )
                                view.message = message
                                staff_notification_attempts[latest_state].append(new_target.id)
                                logger.info(f"Sent save state prompt to {new_target.name} via DM (fallback)")
                            except:
                                logger.error(f"Could not send DM to fallback staff member {new_target.name}")
                                pending_draft_state = {
                                    'filename': latest_state,
                                    'channel_id': original_channel_id,
                                    'timestamp': formatted_time
                                }
                        else:
                            logger.warning("No other staff members available to notify")
                            pending_draft_state = {
                                'filename': latest_state,
                                'channel_id': original_channel_id,
                                'timestamp': formatted_time
                            }
                else:
                    logger.warning("No Draft Staff members found to notify about saved state")
                    pending_draft_state = {
                        'filename': latest_state,
                        'channel_id': original_channel_id,
                        'timestamp': formatted_time
                    }
                
            except Exception as e:
                logger.error(f"Error reading saved state: {e}")
                
    except Exception as e:
        logger.error(f"Error checking for saved draft states: {e}")
        logger.exception("Full error details:")
    
    try:
        # Use original GUILD_ID (discord.Object) for command syncing
        synced = await bot.tree.sync(guild=GUILD_ID)
        logger.info(f'Synced {len(synced)} commands to guild {GUILD_ID.id}')
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")

# Create the button view for the save state prompt
class SaveStatePromptView(discord.ui.View):
    def __init__(self, state_manager, guild, filename, original_channel_id, staff_member=None):
        super().__init__(timeout=300)  # 5 minute timeout (300 seconds)
        self.state_manager = state_manager
        self.guild = guild
        self.filename = filename
        self.original_channel_id = original_channel_id
        self.message = None
        self.staff_member = staff_member  # Store which staff member this was sent to
        self.decision_made = False  # Add this flag
    
    @discord.ui.button(label="Load Save State", style=discord.ButtonStyle.primary, custom_id="load_state")
    async def load_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.decision_made = True  # Mark that a decision was made
        # First check if we're in a DM channel - if so, we need a different approach
        if isinstance(interaction.channel, discord.DMChannel):
            # This is a DM, so we need to get the original channel
            original_channel = self.guild.get_channel(self.original_channel_id)
            if not original_channel:
                await interaction.response.send_message(
                    "Error: Could not find the original draft channel.",
                    ephemeral=True
                )
                return
            
            await interaction.response.send_message(
                f"Loading saved draft state... I'll send you an update when it's done."
            )
        else:
            # We're in a guild channel, use ephemeral response
            await interaction.response.defer(ephemeral=True)
            
            # Verify we're in the original channel
            if interaction.channel_id != self.original_channel_id:
                await interaction.followup.send(
                    "Error: Draft can only be resumed in the original channel where it was running.",
                    ephemeral=True
                )
                return
            
            await interaction.followup.send(
                "Loading saved draft state... Please wait.",
                ephemeral=True
            )
            
            original_channel = interaction.channel
        
        try:
            # Load the state
            loaded_state, loaded_times = self.state_manager.load_state(
                self.filename,
                self.guild
            )
            
            if not loaded_state['participants']:
                if isinstance(interaction.channel, discord.DMChannel):
                    await interaction.channel.send("⚠️ Error: No participants found in loaded state")
                else:
                    await interaction.followup.send(
                        "⚠️ Error: No participants found in loaded state",
                        ephemeral=True
                    )
                return
                
            # Update global state
            draft_state.update(loaded_state)
            
            # Clear any existing timers from previous session
            participant_timers.clear()
            remaining_times.clear()
            
            # If there was an active draft with timers, restore the appropriate state
            if draft_state['is_paused']:
                logger.info("Draft was paused, restoring remaining times without starting timers")
                remaining_times.update(loaded_times)
                logger.info(f"Restored remaining times for {len(remaining_times)} participants")
                
                success_message = (
                    f"✅ Draft state loaded successfully from `{self.filename}`!\n"
                    f"• Draft is currently **paused**\n"
                    f"• {len(draft_state['participants'])} participants restored\n"
                    f"• Use `/resume_draft` to continue"
                )
                
                if isinstance(interaction.channel, discord.DMChannel):
                    await interaction.channel.send(success_message)
                else:
                    await interaction.followup.send(success_message, ephemeral=True)
                
                # No public announcement for paused state restoration as requested
            else:
                logger.info("Draft was active, restoring timers")
                current_participant = draft_state['order'][draft_state['current_pick'] % len(draft_state['order'])]
                if current_participant:
                    logger.info(f"Current participant: {current_participant.name}")
                    logger.info(f"Loaded remaining times: {loaded_times}")
                    
                    remaining_time = loaded_times.get(current_participant)
                    logger.info(f"Found remaining time for {current_participant.name}: {remaining_time}")
                    
                    if remaining_time and remaining_time > 0:
                        logger.info(f"Restarting timer for {current_participant.name} with {remaining_time} seconds remaining")
                        try:
                            # THIS IS THE ONLY PUBLIC MESSAGE - visible to everyone
                            initial_message = await original_channel.send(
                                f":arrow_forward: Draft state restored! Continuing from where we left off.\n"
                                f"It's {current_participant.mention}'s turn."
                            )
                            
                            class MinimalInteraction:
                                def __init__(self, channel, initial_message=None):
                                    self.channel = channel
                                    self.followup = self
                                    self._initial_message = initial_message
                                    
                                async def send(self, *args, **kwargs):
                                    if self._initial_message is None:
                                        self._initial_message = await self.channel.send(*args, **kwargs)
                                        return self._initial_message
                                    else:
                                        return await self._initial_message.reply(*args, **kwargs)
                            
                            mock_interaction = MinimalInteraction(original_channel, initial_message)
                            
                            # Update Google Sheet with current state
                            try:
                                update_google_sheet()
                                logger.info("Updated Draft Sheet after state restoration")
                            except Exception as e:
                                logger.error(f"Failed to update Draft Sheet after restoration: {e}")
                            
                            # Use the existing start_timer with the remaining time AND EXPLICIT REFERENCE
                            timer_task = asyncio.create_task(
                                start_timer(mock_interaction, current_participant, remaining_time, reference_message=initial_message)
                            )

                            participant_timers[current_participant] = timer_task
                            remaining_times[current_participant] = remaining_time
                            logger.info(f"Successfully restored timer for {current_participant.name}")
                            
                            success_message = (
                                f"✅ Draft state loaded successfully from `{self.filename}`!\n"
                                f"• Draft is now **active**\n"
                                f"• {len(draft_state['participants'])} participants restored\n"
                                f"• Current turn: {current_participant.mention}"
                            )
                            
                            if isinstance(interaction.channel, discord.DMChannel):
                                await interaction.channel.send(success_message)
                            else:
                                await interaction.followup.send(success_message, ephemeral=True)
                            
                        except Exception as e:
                            logger.error(f"Failed to restore timer for {current_participant.name}: {e}")
                            error_msg = f"⚠️ Draft state was loaded but there was an error restoring timers: {str(e)}"
                            
                            if isinstance(interaction.channel, discord.DMChannel):
                                await interaction.channel.send(error_msg)
                            else:
                                await interaction.followup.send(error_msg, ephemeral=True)
                    else:
                        logger.warning(f"No valid remaining time found for {current_participant.name}")
                        error_msg = f"⚠️ Draft state was loaded but no valid timer was found for {current_participant.mention}"
                        
                        if isinstance(interaction.channel, discord.DMChannel):
                            await interaction.channel.send(error_msg)
                        else:
                            await interaction.followup.send(error_msg, ephemeral=True)
            
            # Disable the buttons after load
            for child in self.children:
                child.disabled = True
                
            if self.message:
                try:
                    await self.message.edit(view=self)
                except:
                    logger.warning("Could not edit message with disabled buttons")
            
            # Clear the pending state
            pending_draft_state = None
            
        except Exception as e:
            logger.error(f"Failed to load draft state: {e}")
            error_msg = f"❌ Error loading draft state: {str(e)}"
            
            if isinstance(interaction.channel, discord.DMChannel):
                await interaction.channel.send(error_msg)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
    @discord.ui.button(label="Ignore Save", style=discord.ButtonStyle.secondary, custom_id="ignore_state")
    async def ignore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        global staff_notification_attempts, pending_draft_state
        
        # Add this flag to track that an active decision was made
        self.decision_made = True
        
        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("✅ Ignoring saved draft state. Starting fresh session.")
        else:
            await interaction.response.defer(ephemeral=True)
            # Verify we're in the original channel
            if interaction.channel_id != self.original_channel_id:
                await interaction.followup.send(
                    "Error: Draft can only be managed in the original channel where it was running.",
                    ephemeral=True
                )
                return
            
            await interaction.followup.send(
                "✅ Ignoring saved draft state. Starting fresh session.",
                ephemeral=True
            )
        
        # Disable the buttons
        for child in self.children:
            child.disabled = True
            
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                logger.warning("Could not edit message with disabled buttons")
        
        # Clear the pending state
        pending_draft_state = None
        
        # Clear staff notification tracking for this file
        if self.filename in staff_notification_attempts:
            del staff_notification_attempts[self.filename]
            logger.info(f"Cleared staff notification tracking for {self.filename} after ignore decision")

        # Notify other staff members about the decision
        if self.staff_member:
            try:
                staff_role = discord.utils.get(self.guild.roles, name="Draft Staff")
                if staff_role:
                    for member in self.guild.members:
                        if staff_role in member.roles and member != self.staff_member:
                            try:
                                dm_channel = await member.create_dm()
                                info_embed = discord.Embed(
                                    title="Draft State Update",
                                    description=f"{self.staff_member.mention} chose to ignore the saved draft state.",
                                    color=discord.Color.blue()
                                )
                                await dm_channel.send(embed=info_embed)
                                logger.info(f"Notified {member.name} about ignore decision")
                            except:
                                logger.warning(f"Could not send decision notification to {member.name}")
            except Exception as e:
                logger.error(f"Error notifying staff members about ignore decision: {e}")
        
        logger.info(f"User {interaction.user.display_name} chose to ignore saved state {self.filename}")
        
        # Stop the view
        self.stop()
    
    async def on_timeout(self):
        global staff_notification_attempts
        
        # If a decision was already made, don't proceed with timeout handling
        if self.decision_made:
            return
            
        # Disable the buttons when the view times out
        for child in self.children:
            child.disabled = True
            
        if self.message:
            try:
                await self.message.edit(
                    content=f"⏰ This prompt has timed out and is no longer active.",
                    view=self
                )
            except:
                logger.warning("Could not edit message with disabled buttons after timeout")
        
        # Try to notify another staff member if this one didn't respond
        if self.staff_member:
            # Record this timeout
            if self.filename not in staff_notification_attempts:
                staff_notification_attempts[self.filename] = []
            staff_notification_attempts[self.filename].append(self.staff_member.id)
            
            # Try to find another staff member to notify
            try:
                staff_role = discord.utils.get(self.guild.roles, name="Draft Staff")
                if staff_role:
                    # Get all staff members who haven't been contacted yet about this file
                    staff_members = [
                        member for member in self.guild.members 
                        if staff_role in member.roles and 
                        (self.filename not in staff_notification_attempts or 
                         member.id not in staff_notification_attempts[self.filename])
                    ]
                    
                    if not staff_members:
                        # No more staff members to contact - default to not loading the state
                        logger.info(f"All staff members have been contacted about {self.filename}. Defaulting to not load.")
                        
                        # Clean up our tracking for this file
                        if self.filename in staff_notification_attempts:
                            del staff_notification_attempts[self.filename]
                            
                        return
                    
                    # Find the target staff member - prioritize you first, then online staff
                    target_staff = None
                    
                    # Look for you first by Discord ID
                    for member in staff_members:
                        if member.id == PRIORITY_STAFF_ID:
                            target_staff = member
                            break
                    
                    # If you weren't found or have already been contacted, fall back to other online staff
                    if not target_staff:
                        online_staff = [m for m in staff_members if m.status != discord.Status.offline]
                        target_staff = online_staff[0] if online_staff else staff_members[0]
                    
                    # Find the original channel
                    channel = self.guild.get_channel(self.original_channel_id)
                    if not channel:
                        logger.error(f"Could not find channel with ID {self.original_channel_id}")
                        return
                        
                    # Create a new view for the new staff member
                    embed = discord.Embed(
                        title="🔄 Draft Save State Found (Previous Staff Did Not Respond)",
                        description=f"A previous draft state requires attention.",
                        color=discord.Color.gold()  # Different color to indicate it's a follow-up
                    )
                    embed.add_field(
                        name="Save Information",
                        value=f"• Filename: `{self.filename}`\n• Channel: {channel.mention}"
                    )
                    embed.add_field(
                        name="Time Remaining",
                        value="This prompt will time out in 5 minutes if no action is taken.",
                        inline=False
                    )
                    
                    new_view = SaveStatePromptView(
                        self.state_manager, 
                        self.guild, 
                        self.filename, 
                        self.original_channel_id,
                        target_staff
                    )
                    
                    try:
                        # Send DM to new staff member
                        dm_channel = await target_staff.create_dm()
                        message = await dm_channel.send(
                            f"📢 A previous staff member didn't respond to a draft state restore prompt in {channel.mention}.\n"
                            f"Could you please handle this?",
                            embed=embed,
                            view=new_view
                        )
                        new_view.message = message
                        logger.info(f"Sent save state prompt to {target_staff.name} after timeout")
                    except:
                        logger.error(f"Could not send DM to {target_staff.name} after timeout")
                        
                        # If we can't send a DM, try the next staff member on the next timeout
                        # The current target_staff will be added to the notification attempts list
                        # so they won't be selected again
            except Exception as e:
                logger.error(f"Error trying to notify another staff member after timeout: {e}")
        
        logger.info(f"Save state prompt for {self.filename} timed out")


'''HELPER FUNCTIONS'''
# Helper function to send timer notifications
# Updated send_timer_notification function to support references
async def send_timer_notification(participant, channel, message, reference_message=None):
    """
    Sends a notification to a participant about their timer.
    First attempts to send a DM, if that fails, sends a message in the channel.
    """
    try:
        # Try to send a DM first
        dm_channel = await participant.create_dm()
        await dm_channel.send(message)
        logger.info(f"Sent timer notification DM to {participant.name}")
                
    except Exception as e:
        # If DM fails, send message in the channel
        logger.warning(f"Failed to send DM to {participant.name}: {e}")
        await channel.send(
            message,
            reference=reference_message  # Add reference to create a reply
        )
        logger.info(f"Sent timer notification in channel to {participant.name}")

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
    try:
        # Mark draft as complete by clearing order
        draft_state["order"] = []
        draft_state["current_pick"] = 0
        draft_state["draft_phase"] = "setup"  # Reset phase to setup
        # Clear notification flags along with other state
        draft_state["notification_flags"] = {}

         # Stop auto-save
        await auto_saver.stop()

        await interaction.followup.send("All participants have completed their picks! Now here are the draft of each team:")

        # Show final teams
        for member, team in draft_state["teams"].items():
            # Get the user's avatar URL
            avatar_url = str(member.avatar.url) if member.avatar else None # Get the URL of the user's avatar
            
            # Create a sprite collage with team logo or fallback to avatar
            collage_path = create_sprite_collage(team["pokemon"], pokemon_data, avatar_url, member.id)
            
            file = discord.File(collage_path, filename="collage.png")
            embed = discord.Embed(title=f"{member.display_name}'s Team", color=discord.Color.blue())
            embed.set_image(url="attachment://collage.png")
            
            # Send the embed with the file
            await interaction.followup.send(file=file, embed=embed)
    
        # Update the Google Sheet with final results
        update_google_sheet()
        
    except Exception as e:
        logger.error(f"Error showing final teams: {e}")
        await interaction.followup.send(
            "There was an error displaying the final teams. Please contact an administrator.",
            ephemeral=True
        )

# Function to generate autocomplete choices for coaches
async def coach_autocomplete(interaction: discord.Interaction, current: str):
    logger.debug(f"Starting coach_autocomplete for {interaction.user.name}")
    logger.debug(f"Current input: {current}")

    # Fetch members with the "Draft" role
    draft_role = discord.utils.get(interaction.guild.roles, name="Draft")
    if not draft_role:
        logger.error("Draft role not found in guild")
        return []

    # Get values of previous selections from the command data
    used_ids = set()
    command_data = interaction.data.get('options', [])
    logger.debug(f"Command data: {command_data}")
    
    for option in command_data:
        if isinstance(option.get('value'), str):
            try:
                used_ids.add(int(option['value']))
            except (ValueError, KeyError):
                pass

    logger.debug(f"Already used coach IDs: {used_ids}")

    # Filter members with the "Draft" role, match the current input, and exclude already selected coaches
    members = [member for member in interaction.guild.members if draft_role in member.roles]
    logger.debug(f"Found {len(members)} members with Draft role")
    
    choices = [
        app_commands.Choice(name=member.display_name, value=str(member.id))
        for member in members
        if current.lower() in member.display_name.lower() and member.id not in used_ids
    ][:25]  # Limit to 25 choices

    logger.debug(f"Returning {len(choices)} choices: {[c.name for c in choices]}")
    return choices

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
        # Only extend if less than 5 minutes remaining
        if user in remaining_times and remaining_times[user] < 300:
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
        # Only extend if less than 5 minutes remaining
        if user in remaining_times and remaining_times[user] < 300:
            await extend_timer(interaction, user, 60)
        return False

    # Check Species Clause
    if any(pokemon_data[p]["dex_number"] == pokemon_info["dex_number"] for p in draft_state["teams"][user]["pokemon"]):
        await interaction.response.send_message(
            f"You already have a Pokémon with the same Pokédex number in your team. "
            f"You cannot pick {pokemon_name.capitalize()} due to the Species Clause.",
            ephemeral=True
        )
        # Only extend if less than 5 minutes remaining
        if user in remaining_times and remaining_times[user] < 300:
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
        if user in remaining_times and remaining_times[user] < 300:
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
    
    # Reset notification flags for the user
    draft_state['notification_flags'][user] = {
        'halfway_notified': False,
        'one_sixth_notified': False
    }

    return draft_state["teams"][user]["points"]
 
# Function to start the draft (updated in v0.50)
async def start_draft(interaction: discord.Interaction, participants: list[discord.Member]):

    try:

        # Reset the draft state
        draft_state["order"] = participants + participants[::-1]  # Snake draft order
        draft_state["current_pick"] = 0
        draft_state["teams"] = {member: {"pokemon": [], "points": total_points} for member in participants}
        draft_state["available_pokemon"] = pokemon_names.copy()
        draft_state["skipped_turns"] = {member: 0 for member in participants}
        draft_state["notification_flags"] = {member: {'halfway_notified': False, 'one_sixth_notified': False} for member in participants}  # Initialize for all participants
        draft_state["draft_channel_id"] = interaction.channel.id

        # Send the draft start message
        start_message = await interaction.followup.send(
            "Draft started! \n\nThe order is:\n" + "\n".join([member.mention for member in draft_state["participants"]]) + "\n in snake format"
        )

        # Store the message as the main reference point for replies
        draft_state["main_message"] = start_message
        logger.info("Set start message as main_message reference")

        # Update Google Sheet to reflect the new skip count
        try:
            update_google_sheet()
            logger.info(f"Updated Google Sheet after starting a new draft")
        except Exception as e:
            logger.error(f"Failed to update Google Sheet after starting a new draft")

        # Notify the first participant using our new reference message
        await notify_current_participant(interaction, reference_message=start_message)

    except Exception as e:
        logger.error(f"Error starting draft: {e}")
        await interaction.followup.send(
            "An error occurred while starting the draft. Please try again or contact the administrator.",
            ephemeral=True
        )
        draft_state["draft_phase"] = "setup"
    await auto_saver.start()

#Funtion to format the timer
def format_time(seconds: int) -> str:
    """
    Format time in seconds as minutes:seconds (e.g., 90 -> "1:30").
    """
    minutes = seconds // 60
    seconds_remaining = seconds % 60
    return f"{minutes}:{seconds_remaining:02}"  # Ensures seconds are always 2 digits

def create_interaction(channel, reference_message=None):
    """
    Creates a minimal interaction-like object that works with start_timer
    """
    class FollowupSender:
        def __init__(self, channel, reference_message=None):
            self.channel = channel
            self.reference_message = reference_message
            
        async def send(self, content, **kwargs):
            # If we have a reference message, use it
            if self.reference_message:
                kwargs['reference'] = self.reference_message
            return await self.channel.send(content, **kwargs)
    
    class MinimalInteraction:
        def __init__(self, channel, reference_message=None):
            self.channel = channel
            self.followup = FollowupSender(channel, reference_message)
            
        async def send(self, *args, **kwargs):
            # If we have a reference message, use it
            if reference_message:
                kwargs['reference'] = reference_message
            return await self.channel.send(*args, **kwargs)
    
    return MinimalInteraction(channel, reference_message)

#Function that starts the timer
async def start_timer(interaction, participant, adjusted_duration=None, reference_message=None):
    global participant_timers, remaining_times

    # Make sure we can access the channel
    if not hasattr(interaction, "channel") or not interaction.channel:
        logger.error(f"No channel available for timer, cannot proceed for {participant.name}")
        return
    
    channel = interaction.channel
    
    # Initialize notification flags for this participant if not exists
    if participant not in draft_state['notification_flags']:
        draft_state['notification_flags'][participant] = {
            'halfway_notified': False,
            'one_sixth_notified': False
        }

    # First, determine the original duration for this turn
    original_duration = None
    if adjusted_duration is None:
        skipped_turns = draft_state["skipped_turns"].get(participant, 0)
        if skipped_turns == 1:
            original_duration = TIMER_DURATION // 2  # Half the initial time
            await channel.send(
                f"⚠️ {participant.mention}, you were skipped once before. Your timer is now **{format_time(original_duration)}**.",
                reference=reference_message  # Add reference to create a reply
            )
        elif skipped_turns >= 2:
            original_duration = TIMER_DURATION // 4  # Quarter of the initial time
            await channel.send(
                f"⚠️ {participant.mention}, you were skipped multiple times before. Your timer is now **{format_time(original_duration)}**.",
                reference=reference_message  # Add reference to create a reply
            )
        else:
            original_duration = TIMER_DURATION

        adjusted_duration = original_duration

    # Check if there's an existing remaining time and not an extension
    if participant in remaining_times and adjusted_duration is None:
        adjusted_duration = remaining_times[participant]
        # Use the stored original duration if available
        original_duration = draft_state['turn_original_durations'].get(participant, adjusted_duration)
        logger.info(f"Resuming timer for {participant.name}: {adjusted_duration} seconds")
    else:
        # If this is a new turn or extension, store the original duration
        if original_duration is not None:
            draft_state['turn_original_durations'][participant] = original_duration
        logger.info(f"Starting new timer for {participant.name}: {adjusted_duration} seconds")

    # Calculate the end time for the timer (using absolute time)
    end_time = time.time() + adjusted_duration
    remaining_time = adjusted_duration
    remaining_times[participant] = remaining_time
    
    # Send initial timer message, as a reply if we have a reference message
    timer_message = await channel.send(
        f"⏰ Time remaining for {participant.mention}: **{format_time(remaining_time)}**",
        reference=reference_message  # Add reference to create a reply
    )
    
    # Create notification flags
    halfway_notified = False
    one_sixth_notified = False
    
    # Calculate notification thresholds based on the ORIGINAL duration for this turn
    original_duration = draft_state['turn_original_durations'].get(participant, adjusted_duration)
    should_notify = original_duration >= 600  # 15 minutes = 900 seconds
    halfway_threshold = original_duration // 2 if should_notify else 0
    one_sixth_threshold = original_duration // 6 if should_notify else 0
    
    # This will be used for message update throttling
    last_update_time = 0
    update_interval = 1  # Update the timer message every second

    # Countdown loop with absolute time tracking
    while True:
        try:
            # Calculate the current remaining time based on the end time
            now = time.time()
            remaining_time = max(0, int(end_time - now))
            remaining_times[participant] = remaining_time
            
            # Exit the loop if the timer has expired
            if remaining_time <= 0:
                break
                
            # Only update the message if enough time has passed (throttling to reduce API load)
            current_time = time.time()
            if current_time - last_update_time >= update_interval:
                try:
                    # Try to edit the existing message
                    await timer_message.edit(
                        content=f"⏰ Time remaining for {participant.mention}: **{format_time(remaining_time)}**"
                    )
                    last_update_time = current_time
                except discord.errors.HTTPException as e:
                    # If the edit fails (likely token expired after ~15 minutes)
                    logger.warning(f"Failed to edit timer message: {e}")
                    
                    # Create a new message instead, as a reply to maintain threading
                    timer_message = await channel.send(
                        f"⏰ Time remaining for {participant.mention}: **{format_time(remaining_time)}**",
                        reference=reference_message  # Keep using the same reference
                    )
                    last_update_time = current_time
            
            # Check for notification thresholds
            if should_notify:
                # Halfway notification
                if not draft_state['notification_flags'][participant]['halfway_notified'] and remaining_time < halfway_threshold:
                    draft_state['notification_flags'][participant]['halfway_notified'] = True
                    await send_timer_notification(
                        participant,
                        channel,
                        f"⏳ {participant.mention}, you have **{-(-remaining_time//60)}** minutes for your turn (half of your time).",
                        reference_message
                    )
                    
                # One-sixth notification
                if not draft_state['notification_flags'][participant]['one_sixth_notified'] and remaining_time < one_sixth_threshold:
                    draft_state['notification_flags'][participant]['one_sixth_notified'] = True
                    await send_timer_notification(
                        participant,
                        channel,
                        f"⚠️ {participant.mention}, you have only **{-(-remaining_time//60)}** minutes remaining for your turn (final reminder).",
                        reference_message
                    )
            
            # Sleep for a short time (shorter than the update interval to ensure accuracy)
            await asyncio.sleep(0.5)  # Sleep for half a second
                
        except asyncio.CancelledError:
            # Timer was canceled, store the remaining time only if it was extended
            remaining_times[participant] = remaining_time
            logger.info(f"Timer for {participant.name} was canceled. Remaining time: {remaining_time} seconds")
            return

    # Notify when the timer runs out
    timeout_message = await channel.send(
        f"⏰ Time's up for {participant.mention}! Moving to the next participant.",
        reference=reference_message  # Add reference to create a reply
    )
    # Reset notification flags for the timed out user
    draft_state['notification_flags'][participant] = {
        'halfway_notified': False,
        'one_sixth_notified': False
    }

    # Increment the skipped turns counter for the participant
    if participant in draft_state["skipped_turns"]:
        draft_state["skipped_turns"][participant] += 1
        try:
            update_google_sheet()
            logger.info(f"Updated Google Sheet after {participant.name} timed out")
        except Exception as e:
            logger.error(f"Failed to update Google Sheet after timeout: {e}")
    else:
        draft_state["skipped_turns"][participant] = 1

    # Move to the next participant using a fresh minimal interaction with the reference
    next_interaction = create_interaction(channel, timeout_message)  # Pass the timeout message
    await next_participant(next_interaction, reference_message=timeout_message)

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
        f"You have **{format_time(new_duration)}** remaining.", ephemeral=True
    )
    logger.info(f"{participant.name} has **{extensions_limit - draft_state['extensions'][participant]} extensions** remaining")

    # Restart the timer with the new duration
    timer_task = asyncio.create_task(start_timer(interaction, participant, new_duration))
    participant_timers[participant] = timer_task
    
# Modified notify_current_participant to handle message threading properly
async def notify_current_participant(interaction, reference_message=None):
    global draft_state, participant_timers

    # Get the current participant
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    remaining_points = draft_state["teams"][current_user]["points"]
    remaining_picks = draft_size - len(draft_state["teams"][current_user]["pokemon"])
    
    # Get the channel in a safe way
    channel = None
    if hasattr(interaction, "channel") and interaction.channel:
        channel = interaction.channel
    
    if not channel and draft_state.get("draft_channel_id"):
        # Fallback to getting channel from the draft_channel_id
        guild = bot.get_guild(interaction.guild_id)
        if guild:
            channel = guild.get_channel(draft_state["draft_channel_id"])
    
    if not channel:
        logger.error("Could not get channel for notification")
        return
    
    # Notification message
    notification = (
        f"It's {current_user.mention}'s turn to pick!\n"
        f"You have **{remaining_points} points** and must pick **{remaining_picks} more Pokémon**."
    )

    # Send notification as a reply if we have a reference message, otherwise as a normal message
    try:
        # First check if we're dealing with a minimal interaction with a reference
        if hasattr(interaction, 'followup') and hasattr(interaction.followup, 'reference_message') and interaction.followup.reference_message:
            # Use the reference directly from the minimal interaction
            reference_to_use = interaction.followup.reference_message
            notif_message = await channel.send(notification, reference=reference_to_use)
            logger.info("Sent notification as reply using MinimalInteraction reference")
        
        # If not, check if we have a reference passed directly
        elif reference_message:
            notif_message = await channel.send(notification, reference=reference_message)
            logger.info("Sent notification as reply using passed reference")
            
        # Otherwise try followup or regular channel send
        elif hasattr(interaction, "followup"):
            try:
                # Webhook doesn't support references, so we send a normal message
                notif_message = await interaction.followup.send(notification)
                logger.info("Sent notification using interaction.followup")
            except Exception as e:
                # If followup send fails, fall back to channel.send
                logger.warning(f"followup.send failed: {e}")
                notif_message = None
        else:
            notif_message = None
            
        # If followup failed or wasn't available, use channel send with reference
        if not notif_message:
            if reference_message:
                notif_message = await channel.send(
                    notification,
                    reference=reference_message  # Use reference to create thread
                )
                logger.info("Sent notification as reply to reference message")
            else:
                notif_message = await channel.send(notification)
                logger.info("Sent notification as new message (no reference)")
            
        # Store this as main_message if we don't have one yet
        if 'main_message' not in draft_state or draft_state['main_message'] is None:
            draft_state['main_message'] = notif_message
            logger.info("Set notification message as main_message reference")
            
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        # Last resort: try direct channel.send without reference
        try:
            notif_message = await channel.send(notification)
            logger.info("Sent notification as direct channel message after error")
        except Exception as e2:
            logger.error(f"Complete failure to send notification: {e2}")
            return

    # Create a new minimal interaction specifically for the timer
    timer_interaction = create_interaction(channel)
    
    # Start the timer for the current participant
    # Always use notif_message as reference for the timer
    timer_task = asyncio.create_task(
        start_timer(timer_interaction, current_user, reference_message=notif_message)
    )
    participant_timers[current_user] = timer_task  # Store timer task

# Updated next_participant function to maintain message threading
async def next_participant(interaction, reference_message=None):
    global draft_state, remaining_times

    # Store channel for direct use if interaction fails
    channel = interaction.channel

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

    # Pass along the reference_message to notify_current_participant
    # Always provide a reference if we have one
    await notify_current_participant(interaction, reference_message=reference_message)

#Function to Check Stall Group Limits
def has_reached_stall_limit(user):
    """
    Check if the user already has 2 Pokémon from the stall group in their team.
    """
    stall_count = sum(1 for pokemon in draft_state["teams"][user]["pokemon"] if pokemon in stall_group)
    return stall_count >= 2

#Function to capture timer state:
async def capture_timer_state(participant):
    """Captures current remaining time from an active timer"""
    if participant in participant_timers:
        timer_task = participant_timers[participant]
        if not timer_task.done():
            for frame in timer_task.get_stack():
                frame_locals = frame.f_locals
                if 'remaining_time' in frame_locals:
                    remaining_times[participant] = frame_locals['remaining_time']
                    logger.info(f"Captured current remaining time for {participant.name}: {frame_locals['remaining_time']} seconds")
                    return frame_locals['remaining_time']
    return None

'''VIEWS'''
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

# View with buttons to confirm loading latest state or choose another
class LoadStateConfirmView(discord.ui.View):
    def __init__(self, state_manager, guild, saved_states):
        super().__init__(timeout=300)  # 5 minute timeout
        self.state_manager = state_manager
        self.guild = guild
        self.saved_states = saved_states  # List of (filename, timestamp) tuples
        
    @discord.ui.button(label="Yes, Load Latest", style=discord.ButtonStyle.primary)
    async def load_latest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if not self.saved_states:
            await interaction.followup.send("❌ No saved states available.", ephemeral=True)
            return
            
        latest_state = self.saved_states[0][0]
        
        try:
            # Load the state
            loaded_state, loaded_times = self.state_manager.load_state(
                latest_state,
                self.guild
            )
            
            if not loaded_state.get('participants'):
                await interaction.followup.send(
                    "⚠️ Warning: No participants found in loaded state",
                    ephemeral=True
                )
                
            # Update global state
            draft_state.update(loaded_state)
            
            # If there was an active draft with timers, update the remaining times but keep paused
            if loaded_times:
                global remaining_times
                remaining_times.update(loaded_times)
            
            # Always set to paused state when loading
            draft_state['is_paused'] = True
            
            # Disable all buttons
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(view=self)
            
            # Send success message
            await interaction.followup.send(
                f"✅ Successfully loaded draft state from `{latest_state}`\n"
                f"• {len(draft_state.get('participants', []))} participants loaded\n"
                f"• Draft is now in paused state\n"
                f"• Use `/resume_draft` to continue",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Failed to load draft state: {e}")
            await interaction.followup.send(
                f"❌ Error loading draft state: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Choose Different State", style=discord.ButtonStyle.secondary)
    async def choose_state_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.saved_states:
            await interaction.response.send_message("❌ No saved states available.", ephemeral=True)
            return
            
        # Create view with dropdown to select state
        select_view = SelectStateView(self.state_manager, self.guild, self.saved_states)
        
        # Create embed
        embed = discord.Embed(
            title="📂 Select Draft State to Load",
            description="Choose a saved draft state from the dropdown menu:",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=select_view)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        # Update the message with disabled buttons
        await interaction.response.edit_message(view=self)
        
        # Send confirmation message
        await interaction.followup.send(
            "✅ Load state operation cancelled.",
            ephemeral=True
        )

# View with dropdown to select a specific state
class SelectStateView(discord.ui.View):
    def __init__(self, state_manager, guild, saved_states):
        super().__init__(timeout=300)  # 5 minute timeout
        self.state_manager = state_manager
        self.guild = guild
        self.saved_states = saved_states
        
        # Add the dropdown to the view
        self.add_item(StateSelectMenu(saved_states))
        self.selected_state = None
    
    @discord.ui.button(label="Load Selected State", style=discord.ButtonStyle.primary)
    async def load_selected_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_state:
            await interaction.response.send_message(
                "⚠️ Please select a state from the dropdown first.", 
                ephemeral=True
            )
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Load the selected state
            loaded_state, loaded_times = self.state_manager.load_state(
                self.selected_state,
                self.guild
            )
            
            if not loaded_state.get('participants'):
                await interaction.followup.send(
                    "⚠️ Warning: No participants found in loaded state",
                    ephemeral=True
                )
                
            # Update global state
            draft_state.update(loaded_state)
            
            # If there was an active draft with timers, update the remaining times but keep paused
            if loaded_times:
                global remaining_times
                remaining_times.update(loaded_times)
            
            # Always set to paused state when loading
            draft_state['is_paused'] = True
            
            # Disable all components
            for child in self.children:
                child.disabled = True
            
            # Update the message with disabled components
            try:
                await interaction.edit_original_response(view=self)
            except Exception as e:
                logger.error(f"Error updating message after state load: {e}")
            
            # Send success message
            await interaction.followup.send(
                f"✅ Successfully loaded draft state from `{self.selected_state}`\n"
                f"• {len(draft_state.get('participants', []))} participants loaded\n"
                f"• Draft is now in paused state\n"
                f"• Use `/resume_draft` to continue",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Failed to load selected draft state: {e}")
            await interaction.followup.send(
                f"❌ Error loading draft state: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable all components
        for child in self.children:
            child.disabled = True
        
        # Update the message with disabled components
        await interaction.response.edit_message(view=self)
        
        # Send confirmation message
        await interaction.followup.send(
            "✅ Load state operation cancelled.",
            ephemeral=True
        )

# Custom Select Menu for state selection
class StateSelectMenu(discord.ui.Select):
    def __init__(self, saved_states):
        # Create select options from saved states
        options = []
        
        # Limit to 25 options max (Discord limit)
        for i, (filename, timestamp) in enumerate(saved_states[:25]):
            # Format the timestamp for display
            dt = datetime.fromisoformat(timestamp)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M")
            
            # Try to extract additional info from the filename to make options more descriptive
            save_info = f"Save {i+1}: {formatted_time}"
            try:
                # If the save file name has a pattern like "draft_state_YYYY-MM-DD_HH-MM-SS.json"
                # Extract some meaningful information if possible
                if "_" in filename:
                    parts = filename.split("_")
                    if len(parts) >= 3:
                        # Try to add some context, like "Round X" if that info is in the filename
                        if any("round" in part.lower() for part in parts):
                            for part in parts:
                                if "round" in part.lower():
                                    save_info = f"{part}: {formatted_time}"
                                    break
            except:
                # If extraction fails, stick with the default format
                pass
                
            # Create option
            options.append(discord.SelectOption(
                label=save_info,
                description=filename[:80] if len(filename) > 80 else filename,  # Limit description length
                value=filename
            ))
        
        super().__init__(
            placeholder="Select a saved state...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Get the selected state
        selected = self.values[0]
        
        # Store in parent view
        self.view.selected_state = selected
        
        # Acknowledge the selection
        await interaction.response.send_message(
            f"Selected state: `{selected}`\nClick 'Load Selected State' to proceed.",
            ephemeral=True
        )

# First view with three options: Save and Stop, Stop Without Saving, Cancel
class StopDraftOptionsView(discord.ui.View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.value = None
        self.save_state = None
        self.clicked = False

    async def disable_all_buttons(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Save and Stop", style=discord.ButtonStyle.danger)
    async def save_and_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:
            return
        self.clicked = True
        
        await self.disable_all_buttons(interaction)
        self.value = True
        self.save_state = True
        self.stop()

    @discord.ui.button(label="Stop Without Saving", style=discord.ButtonStyle.danger)
    async def stop_without_saving(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:
            return
        self.clicked = True
        
        await self.disable_all_buttons(interaction)
        self.value = True
        self.save_state = False
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:
            return
        self.clicked = True
        
        await self.disable_all_buttons(interaction)
        self.value = False
        self.save_state = None
        self.stop()

    async def on_timeout(self):
        self.value = None
        self.save_state = None
        for item in self.children:
            item.disabled = True

# Second view with three options: Confirm, Back to Options, Cancel
class StopDraftConfirmationView(discord.ui.View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.value = None
        self.go_back = False
        self.clicked = False

    async def disable_all_buttons(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Yes, I'm Sure", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:
            return
        self.clicked = True
        
        await self.disable_all_buttons(interaction)
        self.value = True
        self.go_back = False
        self.stop()

    @discord.ui.button(label="Back to Stop Options", style=discord.ButtonStyle.primary)
    async def back_to_options(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:
            return
        self.clicked = True
        
        await self.disable_all_buttons(interaction)
        self.value = None
        self.go_back = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.clicked:
            return
        self.clicked = True
        
        await self.disable_all_buttons(interaction)
        self.value = False
        self.go_back = False
        self.stop()

    async def on_timeout(self):
        self.value = None
        self.go_back = False
        for item in self.children:
            item.disabled = True

'''SLASH COMMANDS'''
#slash command to set the number of coaches
def generate_set_coaches_command():
    logger.info(f"Generating set_coaches command for {coaches_size} coaches")
    
    # Generate the parameters for app_commands.describe
    params_dict = {f"coach{i+1}": f"Coach #{i+1}" for i in range(coaches_size)}
    
    # Create the function parameters string
    params_str = "interaction: discord.Interaction"
    params_str += "".join(f", coach{i+1}: str" for i in range(coaches_size))
    
    # Create the coach values list for the function body
    coach_values_str = ", ".join(f"coach{i+1}" for i in range(coaches_size))
    
    # Create the function body with proper escaping of format brackets
    func_body = f"""
async def set_coaches_command({params_str}):
    global draft_state
    logger.info(f"{{interaction.user.name}} attempting to set coaches")
    
    await interaction.response.defer(ephemeral=True)

    # Check if a draft is already in progress
    if draft_state['draft_phase'] != 'setup':
        logger.error(f"{{interaction.user.name}} failed to set coaches - Draft not in setup phase")
        await interaction.followup.send("Cannot set coaches now. Draft must be in setup phase.", ephemeral=True)
        return

    # Validate that all selected members have the "Draft" role
    draft_role = discord.utils.get(interaction.guild.roles, name="Draft")
    if not draft_role:
        logger.error(f"{{interaction.user.name}} failed to set coaches - Draft role not found")
        await interaction.followup.send("The 'Draft' role does not exist in this server.", ephemeral=True)
        return

    # Resolve members from their IDs or names
    coaches = []
    seen_coaches = set()
    
    coach_values = [{coach_values_str}]
    
    for i, coach_id in enumerate(coach_values, 1):
        if not coach_id:
            logger.error(f"{{interaction.user.name}} failed to set coaches - Coach #{{i}} not provided")
            await interaction.followup.send(f"Coach #{{i}} is required.", ephemeral=True)
            return

        try:
            member = interaction.guild.get_member(int(coach_id))
        except ValueError:
            member = None
            
        if not member:
            logger.error(f"{{interaction.user.name}} failed to set coaches - Coach #{{i}} not found")
            await interaction.followup.send(f"Could not find member for Coach #{{i}}", ephemeral=True)
            return
            
        if draft_role not in member.roles:
            logger.error(f"{{interaction.user.name}} failed to set coaches - {{member.display_name}} missing Draft role")
            await interaction.followup.send(
                f"{{member.display_name}} does not have the 'Draft' role and cannot be a coach.",
                ephemeral=True
            )
            return

        # Check if this coach has already been selected
        if member.id in seen_coaches:
            logger.error(f"{{interaction.user.name}} failed to set coaches - {{member.display_name}} selected multiple times")
            await interaction.followup.send(
                f"❌ Error: {{member.display_name}} has been selected multiple times. Each coach can only be selected once.",
                ephemeral=True
            )
            return
            
        seen_coaches.add(member.id)
        coaches.append(member)

    # Store the selected coaches
    draft_state['participants'] = coaches
    logger.info(f"{{interaction.user.name}} successfully set coaches: {{', '.join([c.display_name for c in draft_state['participants']])}}")
    await interaction.followup.send(
        f"Coaches set successfully: {{', '.join([c.mention for c in draft_state['participants']])}}"
    )
"""

    # Create the command function using exec
    namespace = {}
    exec(func_body, globals(), namespace)
    set_coaches_command = namespace['set_coaches_command']
    
    # Add the decorators
    set_coaches_command = bot.tree.command(
        name="set_coaches",
        description=f"Set the {coaches_size} coaches for the draft",
        guild=GUILD_ID
    )(set_coaches_command)
    set_coaches_command = has_draft_staff_role()(set_coaches_command)
    set_coaches_command = app_commands.describe(**params_dict)(set_coaches_command)

    # Apply the existing coach_autocomplete to each parameter
    for i in range(coaches_size):
        param_name = f"coach{i+1}"
        set_coaches_command.autocomplete(param_name)(coach_autocomplete)
    
    return set_coaches_command

# Generate the command at startup
set_coaches_command = generate_set_coaches_command()

# Slash command to start the draft (specific to the guild)
@bot.tree.command(name="start_draft", description="Start the Pokémon draft", guild=GUILD_ID)
async def start_draft_command(interaction: discord.Interaction):
    global draft_state
    logger.info(f"{interaction.user.name} attempting to start draft")

    # Check conditions without deferring first
    # Check if a draft is already in progress
    if draft_state["draft_phase"] != "setup":
        logger.error(f"{interaction.user.name} failed to start draft - Draft already in progress")
        await interaction.response.send_message("A draft is already in progress. Please wait until the current draft finishes before starting a new one.", ephemeral=True)
        return
    
    # Check if coaches have been set
    if not draft_state['participants']:
        logger.error(f"{interaction.user.name} failed to start draft - No coaches set")
        await interaction.response.send_message("No coaches have been set. Use `/set_coaches` first.", ephemeral=True)
        return

    # If we get here, we're good to start the draft, so NOW defer without ephemeral
    await interaction.response.defer()
    
    try:
        # Start the draft with the set coaches
        draft_state['draft_phase'] = 'active'
        await start_draft(interaction, draft_state['participants'])
        coach_names = [coach.name for coach in draft_state['participants']]
        logger.info(f"{interaction.user.name} successfully started draft with coaches: {', '.join(coach_names)}")
    except Exception as e:
        logger.error(f"{interaction.user.name} failed to start draft - Error: {str(e)}")
        # Since we've deferred without ephemeral, this error will be public,
        # but it's a rare case that happens during the start_draft process
        await interaction.followup.send(
            "An error occurred while starting the draft. Please try again or contact the administrator."
        )
#Slash command to stop the draft - NEW TO HANDLE STATE
@bot.tree.command(
    name="stop_draft", 
    description="Stop the current draft with options to save the state", 
    guild=GUILD_ID
)
@has_draft_staff_role()
async def stop_draft_command(interaction: discord.Interaction):
    global draft_state, participant_timers, remaining_times, auto_saver
    logger.info(f"{interaction.user.name} attempting emergency draft stop")
    await interaction.response.defer(ephemeral=True)
    
    if draft_state['draft_phase'] == 'inactive':
        await interaction.response.send_message(
            "No draft is currently active.", 
            ephemeral=True
        )
        return

    # Decision loop to handle the possibility of going back to the first view
    while True:
        # Send initial message with stop options
        stop_options_embed = discord.Embed(
            title="⚠️ Draft Stop Options",
            description=(
                "Please choose how you want to stop the draft:\n\n"
                "• **Save and Stop**: Save the current state before stopping\n"
                "• **Stop Without Saving**: Stop without preserving the current state\n"
                "• **Cancel**: Cancel this operation and continue the draft"
            ),
            color=discord.Color.yellow()
        )
        options_view = StopDraftOptionsView(timeout=60)
        
        await interaction.followup.send(
            embed=stop_options_embed,
            view=options_view,
            ephemeral=True
        )

        # Wait for first view decision
        await options_view.wait()
        
        # Handle timeout
        if options_view.value is None:
            logger.info(f"{interaction.user.name} let stop draft command timeout")
            await interaction.followup.send(
                "Command timed out. No action taken.",
                ephemeral=True
            )
            return
        
        # Handle cancel
        if not options_view.value:
            logger.info(f"{interaction.user.name} cancelled draft stop attempt")
            await interaction.followup.send(
                "✅ Stop draft cancelled. The draft will continue normally.",
                ephemeral=True
            )
            return
        
        # Options view returned True, meaning user selected either "Save and Stop" or "Stop Without Saving"
        should_save = options_view.save_state
        
        # Create appropriate confirmation message based on the choice
        action_text = "save the current state and then stop" if should_save else "stop WITHOUT saving"
        
        # Create the confirmation embed
        stop_confirm_embed = discord.Embed(
            title="⚠️ WARNING: Confirm Draft Stop",
            description=(
                f"Are you sure you want to {action_text} the draft?\n\n"
                "This will:\n"
                "• Immediately stop the current draft\n"
                "• Cancel all active timers\n"
                f"• {'Save the current state and then clear' if should_save else 'Clear without saving'} all draft data\n"
                "• Cannot be undone\n\n"
            ),
            color=discord.Color.red()
        )
        confirmation_view = StopDraftConfirmationView(timeout=60)
        
        await interaction.followup.send(
            embed=stop_confirm_embed,
            view=confirmation_view,
            ephemeral=True
        )

        # Wait for confirmation view
        await confirmation_view.wait()
        
        # If user clicked "Back to Stop Options", restart the loop
        if confirmation_view.go_back:
            continue
            
        # Handle confirmation timeout
        if confirmation_view.value is None:
            logger.info(f"{interaction.user.name} let stop draft confirmation timeout")
            await interaction.followup.send(
                "Command timed out. No action taken.",
                ephemeral=True
            )
            return
            
        # Handle confirmation cancel
        if not confirmation_view.value:
            logger.info(f"{interaction.user.name} cancelled draft stop in final confirmation")
            await interaction.followup.send(
                "✅ Stop draft cancelled. The draft will continue normally.",
                ephemeral=True
            )
            return
            
        # User confirmed - break out of the decision loop and proceed with stopping
        break

    # If we got here, the user confirmed the stop operation
    try:
        # First capture remaining times for any active timers
        if draft_state["order"]:
            current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
            await capture_timer_state(current_user)

        # Handle saving if requested
        save_message = ""
        if should_save:
            try:
                filename = state_manager.save_state(
                    draft_state,
                    remaining_times  
                )
                logger.info(f"{interaction.user.name} saved draft state as {filename}")
                save_message = f"\n✅ Draft state saved as `{filename}`"
            except Exception as e:
                logger.error(f"Error saving draft state: {e}")
                save_message = "\n⚠️ Failed to save draft state"
        
        # Cancel all active timers
        for participant, timer in participant_timers.copy().items():
            try:
                await cancel_timer(participant)
                logger.info(f"Cancelled timer for {participant.name}")
            except Exception as e:
                logger.error(f"Failed to cancel timer for {participant.name}: {str(e)}")

        # Stop auto-saver
        try:
            await auto_saver.stop()
            logger.info("Stopped auto-saver")
        except Exception as e:
            logger.error(f"Failed to stop auto-saver: {str(e)}")

        # Clear timer-related dictionaries
        participant_timers.clear()
        remaining_times.clear()

        # Reset all global variables
        draft_state = {
            "participants": [],
            "order": [],
            "current_pick": 0,
            "teams": {},
            "available_pokemon": pokemon_names.copy(),
            "skipped_turns": {},
            "extensions": {},
            "is_paused": False,
            "auto_extensions": {},
            "draft_phase": "setup",
            "draft_channel_id": None,
            "main_message": None,
            "turn_original_durations": {},
            "notification_flags": {}  # Add this new field
        }

        # Send success message
        success_message = (
            "✅ Draft has been completely stopped and reset.\n\n"
            "• All timers have been cancelled\n"
            "• All draft data has been cleared\n"
            "• The bot is ready for a new draft"
            f"{save_message}"
        )
        await interaction.followup.send(success_message, ephemeral=True)
        
        # Send public message
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
        logger.error(f"Error in stop_draft command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while stopping the draft. Please try again or contact the administrator.",
            ephemeral=True
        )

#Slash command to skip coach turnn
@bot.tree.command(name="skip", description="Skip the current player's turn (Draft Staff only)", guild=GUILD_ID)
@has_draft_staff_role()
async def skip_command(interaction: discord.Interaction):
    logger.info(f"User {interaction.user.name} attempting to skip turn")
    await interaction.response.defer(ephemeral=True)

    # Get the current participant that will be skipped
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]

    # Validate draft state first
    if not draft_state["participants"]:
        logger.error(f"User {interaction.user.name} failed skip - No draft in progress")
        await interaction.followup.send("No draft is currently in progress.", ephemeral=True)
        return

    if draft_state["is_paused"]:
        logger.error(f"User {interaction.user.name} failed skip - Draft is paused")
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
        logger.info(f"User {interaction.user.name} skip confirmation timed out")
        await interaction.followup.send("Skip confirmation timed out.", ephemeral=True)
        return
    
    if not view.value:
        logger.info(f"User {interaction.user.name} cancelled skip")
        await interaction.followup.send("Skip cancelled.", ephemeral=True)
        return

    # Proceed with the skip
    # Cancel the current timer
    await cancel_timer(current_user)
    logger.info(f"Timer cancelled for {current_user.name}")

    # Clear any remaining time for the user
    if current_user in remaining_times:
        del remaining_times[current_user]
        logger.info(f"Cleared remaining time for {current_user.name}")

    # Increment skip counter
    if current_user not in draft_state["skipped_turns"]:
        draft_state["skipped_turns"][current_user] = 0
    draft_state["skipped_turns"][current_user] += 1

    # Reset auto-extensions counter when turn is skipped
    if current_user in draft_state["auto_extensions"]:
        logger.info(f"Resetting auto-extensions counter for {current_user.name} due to turn skip")
        draft_state["auto_extensions"][current_user] = 0

    # Reset notification flags for the skipped user
    draft_state['notification_flags'][current_user] = {
        'halfway_notified': False,
        'one_sixth_notified': False
    }
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
        logger.info(f"Successfully updated Google Sheet after skip")
    except Exception as e:
        logger.error(f"Failed to update Google Sheet after skip: {str(e)}")
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
    logger.info(f"{user.name} attempting to pick pokemon: {pokemon_name}")
    # --- 1. Initial validations ---
    if not await validate_draft_state(interaction, user):
        logger.error(f"{user.name} failed pick - Invalid draft state")
        return

    if not await validate_turn(interaction, user):
        logger.error(f"{user.name} failed pick - Not their turn")
        return

    # --- 2. Pokemon validation ---
    is_valid, pokemon_info = await validate_pokemon_name(interaction, pokemon_name, user)
    if not is_valid:
        logger.error(f"{user.name} failed pick - Invalid Pokemon name: {pokemon_name}")
        return

    # --- 3. Rules validation ---
    if not await validate_pokemon_rules(interaction, pokemon_name, pokemon_info, user):
        logger.error(f"{user.name} failed pick - Rules violation for {pokemon_name}")
        return

    # --- 4. Points validation ---
    if not await validate_points(interaction, pokemon_name, pokemon_info, user):
        logger.error(f"{user.name} failed pick - Insufficient points for {pokemon_name}")
        return

        # Get current timer before canceling it
    current_timer = participant_timers.get(user)
    
    # Get the CURRENT remaining time before canceling the timer
    current_remaining_time = remaining_times.get(user)
    
    # Cancel current timer - this will update remaining_times with the latest value
    if current_timer:
        await cancel_timer(user)
        current_remaining_time = remaining_times.get(user)
        logger.info(f"{user.name} timer cancelled with {current_remaining_time} seconds remaining")

    # Send public message if remaining time is less than a minute
    if current_remaining_time:
        logger.info(f"{user.name} confirming pick ")
        await interaction.channel.send(f"{user.display_name} is confirming their Pokémon pick, timer will resume in 30 seconds")

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
                ("\nNo automatic extension granted. " +
                "You've used all 3 automatic extensions this turn." if draft_state["auto_extensions"][user] >= 3 else "")
            )

        action = "timed out" if view.value is None else "cancelled"
        logger.info(f"{user.name} {action} pick of {pokemon_name}")
        await interaction.followup.send(
            f"Pick confirmation {action}. Please try again.\n{extension_msg}" if view.value is None 
            else f"Pick cancelled.{extension_msg}"
        )
    
        # Resume timer with appropriate time
        timer_task = asyncio.create_task(start_timer(interaction, user, resume_time))
        participant_timers[user] = timer_task

        return
        
       

    # --- 6. Process confirmed pick ---
    points_left = process_pick(user, pokemon_name, pokemon_info)
    logger.info(f"{user.name} successfully picked {pokemon_name} - Points remaining: {points_left}")
    
    # Reset auto-extensions counter after successful pick
    if user in draft_state["auto_extensions"]:
        logger.info(f"Resetting auto-extensions counter for {user.name}")
        draft_state["auto_extensions"][user] = 0

    #Reset skipped-turns after succesful pick
    if user in draft_state["skipped_turns"]:
            logger.info(f"Resetting skipped_turns counter for {user.name}")
            draft_state["skipped_turns"][user] = 0
    
    try:
        update_google_sheet()
        logger.info(f"Updated Google Sheet after succesful pick")
    except Exception as e:
        logger.error(f"Failed to update Google Sheet after succesful pick")

    # --- 7. Send announcement ---
    embed = create_pick_announcement_embed(user, pokemon_name, pokemon_info)
    pick_message = await interaction.followup.send(embed=embed)

    # --- 8. Handle draft progression ---
    if len(draft_state["teams"][user]["pokemon"]) < draft_size:
        logger.info(f"{user.name} has {points_left} points remaining")
        await interaction.followup.send(f"{user.mention}, you now have **{points_left} points** remaining.", ephemeral=True)
    else:
        await cancel_timer(user)
        draft_state["order"] = [p for p in draft_state["order"] if p != user]
        logger.info(f"{user.name} completed their draft")
        await interaction.followup.send(f"{user.mention}'s draft is complete! {user.name} will no longer be part of the rotation.")

    if all(len(team["pokemon"]) == draft_size for team in draft_state["teams"].values()):
        logger.info("Draft completed - All teams are full")
        await show_final_teams(interaction)
        draft_state["participants"] = []
        draft_state["order"] = []
        draft_state["current_pick"] = 0
        draft_state["teams"] = {}
        draft_state["available_pokemon"] = pokemon_names.copy()
        await interaction.followup.send("The draft has finished! The draft state has been reset.", ephemeral=True)
        return

    # Update this line to pass the pick_message as reference
    await next_participant(interaction, reference_message=pick_message)

# Function to autocomplete for Pokémon names (specific to the guild) [Here because is tied to /pick_pokemon]
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
    logger.info(f"User {interaction.user.name} attempting to clear messages")

    if draft_state["is_paused"]:
        logger.error(f"User {interaction.user.name} failed clear - Draft is paused")
        await interaction.response.send_message("The draft is currently paused. Messages can't be deleted at this moment.", ephemeral=True)
        return

    # Check if the bot has the required permissions
    if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
        logger.error(f"User {interaction.user.name} failed clear - Bot lacks permissions")
        await interaction.response.send_message("I don't have permission to manage messages in this channel.", ephemeral=True)
        return

    await interaction.response.send_message("Clearing all messages...", ephemeral=True)

    try:
        # Use the purge method to bulk delete messages
        deleted = await interaction.channel.purge(limit=None)
        logger.info(f"User {interaction.user.name} successfully cleared {len(deleted)} messages")
        await interaction.followup.send(f"Successfully deleted {len(deleted)} messages.", ephemeral=True)
    except Exception as e:
        logger.error(f"User {interaction.user.name} failed to clear messages: {str(e)}")
        await interaction.followup.send(
            "An error occurred while clearing messages. Please check my permissions and try again.",
            ephemeral=True
        )

#Slash Command to pause the draft
@bot.tree.command(name="pause_draft", description="Pause the current draft", guild=GUILD_ID)
@has_draft_staff_role()
async def pause_draft_command(interaction: discord.Interaction):
    global draft_state
    logger.info(f"User {interaction.user.name} attempting to pause draft")

    # Check if a draft is in progress
    if not draft_state["participants"]:
        logger.error(f"User {interaction.user.name} failed pause - No draft in progress")
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return

    # Check if the draft is already paused
    if draft_state["is_paused"]:
        logger.error(f"User {interaction.user.name} failed pause - Draft already paused")
        await interaction.response.send_message("The draft is already paused.", ephemeral=True)
        return

    # Cancel the current timer and store the remaining time
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    await cancel_timer(current_user)

    # Set the draft to paused state
    draft_state["is_paused"] = True

    logger.info(f"User {interaction.user.name} successfully paused draft - {current_user.name} was in turn")
    await interaction.response.send_message(f"The draft has been paused. {current_user.mention} was in turn.")

    # Stop auto-saver and save state once
    await auto_saver.stop()
    try:
        filename = state_manager.save_state(draft_state, remaining_times)
        logger.info(f"Draft state saved to {filename} upon pausing")
    except Exception as e:
        logger.error(f"Failed to save draft state upon pausing: {e}")

#Slash Command to resume the draft
@bot.tree.command(name="resume_draft", description="Resume the paused draft", guild=GUILD_ID)
@has_draft_staff_role()
async def resume_draft_command(interaction: discord.Interaction):
    global draft_state
    logger.info(f"User {interaction.user.name} attempting to resume draft")

    # Check if a draft is in progress
    if not draft_state["participants"]:
        logger.error(f"User {interaction.user.name} failed resume - No draft in progress")
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return

    # Check if the draft is not paused
    if not draft_state["is_paused"]:
        logger.error(f"User {interaction.user.name} failed resume - Draft not paused")
        await interaction.response.send_message("The draft is not paused.", ephemeral=True)
        return

    # Set the draft to active state
    draft_state["is_paused"] = False

    # Get the current user
    current_user = draft_state["order"][draft_state["current_pick"] % len(draft_state["order"])]
    remaining_time = remaining_times.get(current_user, TIMER_DURATION)
    
    # Using defer() and followup.send() to get a proper message object
    await interaction.response.defer()
    
    # Webhooks don't support references, so just send a regular message
    resume_message = await interaction.followup.send(
        f"🎮 **Draft Resumed!**\n\n"
        f"Continuing from pick #{draft_state['current_pick'] + 1} with "
        f"{current_user.mention}'s turn."
    )
    
    # Store the message as our main reference
    draft_state["main_message"] = resume_message
    
    # Start the timer using the resume_message as reference
    timer_task = asyncio.create_task(
        start_timer(interaction, current_user, remaining_time, reference_message=resume_message)
    )
    participant_timers[current_user] = timer_task

    logger.info(f"User {interaction.user.name} successfully resumed draft - {current_user.name} has {remaining_time} seconds remaining")
    
    # Restart auto-saver
    await auto_saver.start()

# Slash command to check current draft
@bot.tree.command(name="my_draft", description="View your current draft", guild=GUILD_ID)
@has_draft_role()
async def my_draft_command(interaction: discord.Interaction):
    user = interaction.user
    logger.info(f"User {user.name} checking their draft status")

    # Check if a draft is in progress
    if not draft_state["participants"]:
        logger.error(f"User {user.name} failed my_draft - No draft in progress")
        await interaction.response.send_message("No draft is currently in progress. Start a draft first using `/start_draft`.", ephemeral=True)
        return

    if user not in draft_state["participants"]:
        logger.error(f"User {user.name} failed my_draft - Not in draft")
        await interaction.response.send_message("You are not part of the draft.", ephemeral=True)
        return

    team = draft_state["teams"][user]
    points_left = team["points"]
    picks_left = draft_size - len(team["pokemon"])
    skips = draft_state["skipped_turns"].get(user, 0)
    
    # Calculate points used
    points_used = total_points - points_left
    points_percentage = (points_used / total_points) * 100

    # Create the main embed
    embed = discord.Embed(
        title=f"🎮 {user.display_name}'s Draft Status",
        color=discord.Color.blue()
    )

    # Try to get team logo first, fallback to avatar
    logo_path = TEAM_LOGOS_DIR / f"{user.id}.png"
    has_logo = False
    if logo_path.exists():
        file = discord.File(str(logo_path), filename="team_logo.png")
        embed.set_thumbnail(url="attachment://team_logo.png")
        has_logo = True
    elif user.avatar:
        embed.set_thumbnail(url=user.avatar.url)

    # Add draft progress section
    embed.add_field(
        name="📊 Draft Progress",
        value=f"• Pokémon Picked: **{len(team['pokemon'])}/{draft_size}**\n"
              f"• Picks Remaining: **{picks_left}**\n"
              f"• Times Skipped: **{skips}**",
        inline=False
    )

    # Add points section
    embed.add_field(
        name="💰 Points Status",
        value=f"• Points Remaining: **{points_left}**\n"
              f"• Points Used: **{points_used}** ({points_percentage:.1f}%)\n"
              f"• Total Points: **{total_points}**",
        inline=False
    )

    # If they have Pokémon, add team section with details
    if team["pokemon"]:
        team_details = []
        for pokemon in team["pokemon"]:
            pokemon_info = pokemon_data[pokemon]
            team_details.append(
                f"• {pokemon.capitalize()} "
                f"({pokemon_info['points']} Points)"
            )
        
        embed.add_field(
            name="🎯 Your Team",
            value="\n".join(team_details),
            inline=False
        )
    else:
        embed.add_field(
            name="🎯 Your Team",
            value="No Pokémon picked yet",
            inline=False
        )

    # Add some tips based on their situation
    tips = []
    if picks_left > 0:
        if points_left < 40:  # Assuming 40 is your lowest tier
            tips.append("⚠️ Low on points! Consider picking lower-tier Pokémon.")
        elif points_left > (picks_left * 100):  # If they have lots of points left
            tips.append("💡 You have plenty of points! Consider some higher-tier picks.")
        
        # Check if they're close to stall group limit
        stall_count = sum(1 for p in team["pokemon"] if p in stall_group)
        if stall_count == 1:
            tips.append("⚠️ You have 1 stall group Pokémon. You can pick 1 more.")
        elif stall_count == 2:
            tips.append("⚠️ You've reached your stall group limit!")

    if tips:
        embed.add_field(
            name="💭 Tips",
            value="\n".join(tips),
            inline=False
        )

    # Add footer with current time
    current_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    embed.set_footer(text=f"Last Updated: {current_time}")

    try:
        if has_logo:
            await user.send(embed=embed, file=file)
        else:
            await user.send(embed=embed)
        logger.info(f"User {user.name} draft details sent via DM")
        await interaction.response.send_message("Check your DMs for your draft details!", ephemeral=True)
    except discord.Forbidden:
        logger.info(f"User {user.name} draft details sent in channel (DMs forbidden)")
        if has_logo:
            await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
    logger.info(f"User {interaction.user.name} attempting to swap {current_pokemon} with {new_pokemon} for coach {coach}")
    
    # Defer response due to potentially longer processing time
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Validate draft state and pause status
        if not draft_state["participants"]:
            logger.error(f"User {interaction.user.name} failed swap - No draft in progress")
            await interaction.followup.send(
                "❌ No draft is currently in progress.",
                ephemeral=True
            )
            return

        # Check if draft is paused
        if not draft_state["is_paused"]:
            logger.error(f"User {interaction.user.name} failed swap - Draft not paused")
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
            logger.error(f"User {interaction.user.name} failed swap - Coach not found")
            await interaction.followup.send(
                "❌ Could not find the specified coach.",
                ephemeral=True
            )
            return

        if coach_member not in draft_state["teams"]:
            logger.error(f"User {interaction.user.name} failed swap - Coach not in draft")
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
            logger.error(f"User {interaction.user.name} failed swap - Pokemon not in team")
            await interaction.followup.send(
                f"❌ {current_pokemon.capitalize()} is not in {coach_member.display_name}'s team.",
                ephemeral=True
            )
            return

        # Validate new_pokemon exists in pokemon_data
        if new_pokemon not in pokemon_data:
            logger.error(f"User {interaction.user.name} failed swap - Invalid Pokemon name: {new_pokemon}")
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
                logger.error(f"User {interaction.user.name} failed swap - Pokemon already drafted")
                await interaction.followup.send(
                    f"❌ {new_pokemon.capitalize()} is already in {team_member.display_name}'s team.\n"
                    "You can only swap with Pokémon that haven't been picked yet.",
                    ephemeral=True
                )
                return

        # Check if the swap would exceed points limit
        if new_total_points < 0:
            logger.error(f"User {interaction.user.name} failed swap - Points limit exceeded")
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
            logger.error(f"User {interaction.user.name} failed swap - Species clause violation")
            await interaction.followup.send(
                f"❌ Cannot add {new_pokemon.capitalize()} due to Species Clause violation.",
                ephemeral=True
            )
            return

        # Validate Stall Group
        if new_pokemon in stall_group:
            current_stall_count = sum(1 for p in team_without_current if p in stall_group)
            if current_stall_count >= 2:
                logger.error(f"User {interaction.user.name} failed swap - Stall group limit exceeded")
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
            logger.error(f"User {interaction.user.name} failed swap - Confirmation timed out or cancelled")
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

#Slash Command to load a saved draft state
@bot.tree.command(name="load_state", description="Load a saved draft state (Draft Staff only)", guild=GUILD_ID)
@has_draft_staff_role()
async def load_state(interaction: discord.Interaction):
    """Load a previous draft state (Draft Staff only)"""
    global draft_state
    
    # Check if draft is in setup state
    if draft_state.get('draft_phase') != "setup":
        await interaction.response.send_message(
            "❌ You can only load a previous draft state when the draft is in setup mode.",
            ephemeral=True
        )
        return
    
    # Get list of available saved states
    try:
        saved_states = state_manager.list_saved_states()
        if not saved_states:
            await interaction.response.send_message(
                "❌ No saved draft states found.",
                ephemeral=True
            )
            return
            
        # Create confirmation view for latest state
        latest_state = saved_states[0][0]
        saved_time = datetime.fromisoformat(saved_states[0][1])
        formatted_time = saved_time.strftime("%Y-%m-%d %H:%M:%S")
        
        view = LoadStateConfirmView(state_manager, interaction.guild, saved_states)
        
        # Create embed with latest state info
        embed = discord.Embed(
            title="📂 Load Draft State",
            description="Would you like to load the most recent draft state?",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Latest Save",
            value=f"• Filename: `{latest_state}`\n• Saved: {formatted_time}"
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error listing saved states: {e}")
        await interaction.response.send_message(
            f"❌ Error listing saved states: {str(e)}",
            ephemeral=True
        )

#Slash command to set the logos
@bot.tree.command(name="set_team_logo", description="Set a coach's team logo", guild=GUILD_ID)
@app_commands.describe(
    coach="The coach to set the logo for",
    logo="The team logo image (PNG format recommended)"
)
@has_draft_staff_role()
async def set_team_logo(
    interaction: discord.Interaction,
    coach: str,
    logo: discord.Attachment
):
    # Check if draft is in setup phase
    if draft_state["draft_phase"] != "setup":
        await interaction.response.send_message(
            "Team logos can only be set during draft setup.",
            ephemeral=True
        )
        return

    # Validate the attachment is an image
    if not logo.content_type.startswith('image/'):
        await interaction.response.send_message(
            "Please upload an image file.",
            ephemeral=True
        )
        return
        
    # Get the target member
    try:
        coach_id = int(coach)
        target_member = interaction.guild.get_member(coach_id)
        if not target_member:
            await interaction.response.send_message(
                "Could not find the selected coach.",
                ephemeral=True
            )
            return
            
        # Verify the member has the Draft role
        draft_role = discord.utils.get(interaction.guild.roles, name="Draft")
        if not draft_role or draft_role not in target_member.roles:
            await interaction.response.send_message(
                f"{target_member.display_name} does not have the Draft role.",
                ephemeral=True
            )
            return
            
        logo_path = TEAM_LOGOS_DIR / f"{coach_id}.png"
        
        # Check if logo already exists
        if os.path.exists(logo_path):
            # Create confirmation view
            class ConfirmReplace(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.value = None

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
                async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = True
                    self.stop()

                @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
                async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = False
                    self.stop()

            view = ConfirmReplace()
            await interaction.response.send_message(
                f"A logo already exists for {target_member.display_name}. Do you want to replace it?",
                view=view,
                ephemeral=True
            )

            # Wait for response
            await view.wait()
            if view.value is None:
                await interaction.followup.send(
                    "Response timed out. The coach is keeping their previous logo.",
                    ephemeral=True
                )
                return
            elif not view.value:
                await interaction.followup.send(
                    f"{target_member.display_name} is keeping their previous logo.",
                    ephemeral=True
                )
                return
                
            # If we get here, delete the old logo
            try:
                os.remove(logo_path)
            except Exception as e:
                logger.error(f"Error deleting old logo: {e}")
                await interaction.followup.send(
                    "Error replacing the logo. Please try again.",
                    ephemeral=True
                )
                return
        else:
            await interaction.response.defer(ephemeral=True)

        # Then in the save part:
        try:
            # Save new logo
            await logo.save(str(logo_path))  # Convert Path to string for discord.py
            
            # Verify and optimize image
            with Image.open(logo_path) as img:
                # Convert to PNG and optimize
                img = img.convert('RGBA')
                img.save(str(logo_path), 'PNG', optimize=True)
            
            success_message = f"Team logo has been {'updated' if logo_path.exists() else 'set'} for {target_member.display_name}!"
            
            # Try to delete the upload message
            try:
                if interaction.message:
                    await interaction.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete logo upload message: {e}")

            await interaction.followup.send(success_message, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error handling logo for {target_member.display_name} (ID: {coach_id}): {e}")
            # Check if the file was actually saved despite the error
            if logo_path.exists():
                await interaction.followup.send(
                    "The logo was saved successfully, but there was a minor error in the process. The logo will work correctly.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "There was an error saving the team logo.",
                    ephemeral=True
                )
            
    except Exception as e:
        logger.error(f"Error in set_team_logo: {e}")
        await interaction.followup.send(
            "An error occurred. Please try again.",
            ephemeral=True
        )

# Add autocomplete for coach selection
@set_team_logo.autocomplete('coach')
async def set_logo_coach_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for coach selection in set_team_logo command"""
    draft_role = discord.utils.get(interaction.guild.roles, name="Draft")
    if not draft_role:
        return []
        
    choices = [
        app_commands.Choice(name=member.display_name, value=str(member.id))
        for member in interaction.guild.members
        if draft_role in member.roles and current.lower() in member.display_name.lower()
    ]
    return choices[:25]  # Discord limits to 25 choices

# Autocomplete functions tied to /swap_pokemon
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
try:
    bot.run(taken.TOKEN)
except KeyboardInterrupt:
    logger.info("Received keyboard interrupt")
    handle_exit(signal.SIGINT, None)
except Exception as e:
    logger.error(f"Bot crashed with error: {e}")
    handle_exit(signal.SIGTERM, None)
finally:
    if auto_saver.task and not auto_saver.task.done():
        asyncio.run(auto_saver.stop())
