import json
import os
from datetime import datetime
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import discord
from datetime import datetime, UTC, timezone

@dataclass
class DraftState:
    participants: list
    order: list
    current_pick: int
    teams: dict
    available_pokemon: list
    skipped_turns: dict
    extensions: dict
    is_paused: bool
    auto_extensions: dict
    remaining_times: dict
    draft_phase: str
    timestamp: str

class StateManager:
    def __init__(self, save_directory: str = "draft_states", max_saves: int = 10):
        self.save_directory = save_directory
        self.max_saves = max_saves  # Maximum number of save files to keep
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)
        self.logger = logging.getLogger(__name__)

    def _serialize_member(self, member: discord.Member) -> Dict[str, Any]:
        """Serialize Discord Member object to dictionary"""
        return {
            'id': member.id,
            'name': member.name,
            'discriminator': member.discriminator,
            'display_name': member.display_name
        }

    def _deserialize_member(self, data: Dict[str, Any], guild: discord.Guild) -> Optional[discord.Member]:
        """Deserialize dictionary back to Discord Member object"""
        try:
            if not guild:
                self.logger.error("Guild is None when attempting to deserialize member")
                return None
            
            member_id = int(data.get('id')) if isinstance(data, dict) else int(data)
            member = guild.get_member(member_id)
            
            if member is None:
                self.logger.error(f"Could not find member with ID {member_id} in guild {guild.name}")
                return None
                
            return member
        except Exception as e:
            self.logger.error(f"Error deserializing member: {e}")
            return None

    def save_state(self, draft_state: dict, remaining_times: dict, 
                filename: Optional[str] = None) -> str:
        """Save the current draft state to a file"""
        try:
            self.logger.info(f"Attempting to save state with remaining_times: {remaining_times}")
            # Create a serializable version of the state
            serializable_state = {
                'draft_channel_id': draft_state.get('draft_channel_id'),
                'participants': [self._serialize_member(m) for m in draft_state['participants']],
                'order': [self._serialize_member(m) for m in draft_state['order']],
                'current_pick': draft_state['current_pick'],
                'teams': {
                    str(member.id): data 
                    for member, data in draft_state['teams'].items()
                },
                'available_pokemon': draft_state['available_pokemon'],
                'skipped_turns': {
                    str(member.id): count 
                    for member, count in draft_state['skipped_turns'].items()
                },
                'extensions': {
                    str(member.id): count 
                    for member, count in draft_state['extensions'].items()
                },
                'is_paused': draft_state['is_paused'],
                'auto_extensions': {
                    str(member.id): count 
                    for member, count in draft_state['auto_extensions'].items()
                },
                'remaining_times': {
                    str(member.id): time 
                    for member, time in remaining_times.items()
                },
                'draft_phase': draft_state['draft_phase'],  # Add this line
                'timestamp': datetime.now().isoformat()
            }

            # Generate filename if not provided
            if filename is None:
                filename = f"draft_state_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

            # Check if we need to clean up old save files
            self._manage_save_limit()

            filepath = os.path.join(self.save_directory, filename)
            
            with open(filepath, 'w') as f:
                json.dump(serializable_state, f, indent=2)
            
            self.logger.info(f"Draft state saved to {filepath}")
            return filename

        except Exception as e:
            self.logger.error(f"Error saving draft state: {e}")
            raise
    
    def _manage_save_limit(self):
        """Ensure we don't exceed max_saves limit by removing oldest save files"""
        try:
            # Get list of all save files with their timestamps
            save_files = []
            for filename in os.listdir(self.save_directory):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.save_directory, filename)
                    mod_time = os.path.getmtime(filepath)
                    save_files.append((filename, mod_time, filepath))
            
            # If we're under the limit, do nothing
            if len(save_files) < self.max_saves:
                return
                
            # Sort files by modification time (oldest first)
            save_files.sort(key=lambda x: x[1])
            
            # Delete oldest files to get back to the limit
            files_to_delete = len(save_files) - self.max_saves + 1  # +1 for the new file we're about to create
            for i in range(files_to_delete):
                if i < len(save_files):
                    oldest_file = save_files[i][2]  # Full path to the file
                    os.remove(oldest_file)
                    self.logger.info(f"Deleted oldest save file: {save_files[i][0]} to maintain {self.max_saves} save limit")
        
        except Exception as e:
            self.logger.error(f"Error managing save file limits: {e}")
            # Don't raise the exception - just log it and continue
            # This way, saving will still work even if cleanup fails

    def load_state(self, filename: str, guild: discord.Guild) -> tuple[dict, dict]:
        """Load a draft state from a file"""
        try:
            if not guild:
                raise ValueError("Guild object is None")
                
            filepath = os.path.join(self.save_directory, filename)
            
            with open(filepath, 'r') as f:
                saved_state = json.load(f)

            # Helper function to safely deserialize members
            def safe_deserialize(member_data):
                member = self._deserialize_member(member_data, guild)
                if member is None:
                    self.logger.warning(f"Could not deserialize member: {member_data}")
                return member

            # Reconstruct the draft state with proper objects
            draft_state = {
                'participants': [
                    m for m in (safe_deserialize(m) for m in saved_state['participants']) if m is not None
                ],
                'order': [
                    m for m in (safe_deserialize(m) for m in saved_state['order']) if m is not None
                ],
                'current_pick': saved_state['current_pick'],
                'teams': {
                    member: data 
                    for member_id, data in saved_state['teams'].items()
                    if (member := safe_deserialize({'id': int(member_id)})) is not None
                },
                'available_pokemon': saved_state['available_pokemon'],
                'skipped_turns': {
                    member: count 
                    for member_id, count in saved_state['skipped_turns'].items()
                    if (member := safe_deserialize({'id': int(member_id)})) is not None
                },
                'extensions': {
                    member: count 
                    for member_id, count in saved_state['extensions'].items()
                    if (member := safe_deserialize({'id': int(member_id)})) is not None
                },
                'is_paused': saved_state['is_paused'],
                'auto_extensions': {
                    member: count 
                    for member_id, count in saved_state['auto_extensions'].items()
                    if (member := safe_deserialize({'id': int(member_id)})) is not None
                },
                'draft_channel_id': saved_state.get('draft_channel_id'),
                'draft_phase': saved_state.get('draft_phase', 'setup')
            }

            remaining_times = {
                member: time 
                for member_id, time in saved_state['remaining_times'].items()
                if (member := safe_deserialize({'id': int(member_id)})) is not None
            }

            # Add these logs
            self.logger.info(f"Loaded remaining_times from file: {saved_state.get('remaining_times', {})}")
            self.logger.info(f"Deserialized remaining_times: {remaining_times}")
            self.logger.info(f"Draft state loaded from {filepath}")
            self.logger.info(f"Loaded {len(draft_state['participants'])} participants")
            return draft_state, remaining_times

        except Exception as e:
            self.logger.error(f"Error loading draft state: {e}")
            raise

    def list_saved_states(self) -> list[tuple[str, str]]:
        """List all saved draft states with their timestamps"""
        saved_states = []
        for filename in os.listdir(self.save_directory):
            if filename.endswith('.json'):
                filepath = os.path.join(self.save_directory, filename)
                try:
                    with open(filepath, 'r') as f:
                        state = json.load(f)
                        saved_states.append((filename, state['timestamp']))
                except Exception as e:
                    self.logger.error(f"Error reading state file {filename}: {e}")
        
        return sorted(saved_states, key=lambda x: x[1], reverse=True)

    def delete_state(self, filename: str) -> bool:
        """Delete a saved state file"""
        try:
            filepath = os.path.join(self.save_directory, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                self.logger.info(f"Deleted draft state file {filepath}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error deleting state file {filename}: {e}")
            return False
