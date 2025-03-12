import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class DraftStateCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, state_manager, draft_state, GUILD_ID):
        self.bot = bot
        self.state_manager = state_manager
        self.draft_state = draft_state
        self.GUILD_ID = GUILD_ID

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

    @app_commands.command(name="save_draft", description="Save the current draft state")
    @has_draft_staff_role()
    async def save_draft(self, interaction: discord.Interaction, name: Optional[str] = None):
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not self.draft_state["participants"]:
                await interaction.followup.send("No draft is currently in progress.", ephemeral=True)
                return

            filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json" if name else None
            saved_file = self.state_manager.save_state(
                self.draft_state,
                selected_coaches,
                remaining_times,
                filename
            )

            await interaction.followup.send(
                f"✅ Draft state saved successfully as `{saved_file}`",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error saving draft state: {e}")
            await interaction.followup.send(
                "An error occurred while saving the draft state.",
                ephemeral=True
            )

    @app_commands.command(name="load_draft", description="Load a saved draft state")
    @has_draft_staff_role()
    async def load_draft(self, interaction: discord.Interaction, filename: str):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Load the state
            loaded_state, loaded_coaches, loaded_times = self.state_manager.load_state(
                filename,
                interaction.guild
            )

            # Update the global state
            self.draft_state.update(loaded_state)
            global selected_coaches, remaining_times
            selected_coaches = loaded_coaches
            remaining_times = loaded_times

            # If the draft was paused when saved, make sure it stays paused
            if self.draft_state["is_paused"]:
                await interaction.followup.send(
                    "✅ Draft state loaded successfully. The draft was paused when saved.\n"
                    "Use `/resume_draft` when ready to continue.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "✅ Draft state loaded successfully. Resuming draft...",
                    ephemeral=True
                )
                
                # Notify current participant and restart timer
                current_user = self.draft_state["order"][self.draft_state["current_pick"] % len(self.draft_state["order"])]
                remaining_time = remaining_times.get(current_user, TIMER_DURATION)
                
                await interaction.followup.send(
                    f"Draft resumed. It's {current_user.mention}'s turn!\n"
                    f"You have **{format_time(remaining_time)}** remaining."
                )
                
                timer_task = asyncio.create_task(start_timer(interaction, current_user, remaining_time))
                participant_timers[current_user] = timer_task

        except Exception as e:
            logger.error(f"Error loading draft state: {e}")
            await interaction.followup.send(
                "An error occurred while loading the draft state.",
                ephemeral=True
            )

    @app_commands.command(name="list_saved_drafts", description="List all saved draft states")
    @has_draft_staff_role()
    async def list_saved_drafts(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            saved_states = self.state_manager.list_saved_states()
            
            if not saved_states:
                await interaction.followup.send("No saved draft states found.", ephemeral=True)
                return

            embed = discord.Embed(
                title="Saved Draft States",
                color=discord.Color.blue()
            )

            for filename, timestamp in saved_states:
                dt = datetime.fromisoformat(timestamp)
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                embed.add_field(
                    name=filename,
                    value=f"Saved on: {formatted_time}",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing saved states: {e}")
            await interaction.followup.send(
                "An error occurred while listing saved draft states.",
                ephemeral=True
            )

    @app_commands.command(name="delete_saved_draft", description="Delete a saved draft state")
    @has_draft_staff_role()
    async def delete_saved_draft(self, interaction: discord.Interaction, filename: str):
        try:
            await interaction.response.defer(ephemeral=True)
            
            if self.state_manager.delete_state(filename):
                await interaction.followup.send(
                    f"✅ Draft state `{filename}` deleted successfully.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Could not delete draft state `{filename}`. File may not exist.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error deleting saved state: {e}")
            await interaction.followup.send(
                "An error occurred while deleting the saved draft state.",
                ephemeral=True
            )

    @load_draft.autocomplete('filename')
    async def load_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for the load_draft command"""
        saved_states = self.state_manager.list_saved_states()
        return [
            app_commands.Choice(name=filename, value=filename)
            for filename, _ in saved_states
            if current.lower() in filename.lower()
        ][:25]

    @delete_saved_draft.autocomplete('filename')
    async def delete_saved_draft_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for the delete_saved_draft command"""
        saved_states = self.state_manager.list_saved_states()
        return [
            app_commands.Choice(name=filename, value=filename)
            for filename, _ in saved_states
            if current.lower() in filename.lower()
        ][:25]
