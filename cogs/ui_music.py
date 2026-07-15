import discord

class MusicView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    async def update_ui(self, interaction=None):
        embed = self.player.generate_embed()
        if interaction:
            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except discord.NotFound:
                pass
        elif self.player.bound_message:
            try:
                await self.player.bound_message.edit(embed=embed, view=self)
            except discord.NotFound:
                self.player.bound_message = None

    @discord.ui.button(label="⏯", style=discord.ButtonStyle.primary, custom_id="music_play_pause")
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.player.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
            elif vc.is_paused():
                vc.resume()
        await self.update_ui(interaction)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.player.guild.voice_client
        if vc and vc.is_playing():
            vc.stop() # Triggers the next song in the callback
        await interaction.response.defer()

    @discord.ui.button(label="⏹", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear()
        vc = self.player.guild.voice_client
        if vc:
            await vc.disconnect()
        if self.player.bound_message:
            try:
                await self.player.bound_message.delete()
            except Exception:
                pass
            self.player.bound_message = None
        # Clean up player mapping in the cog happens in the disconnect event or manually
        await interaction.response.defer()

    @discord.ui.button(label="🔀", style=discord.ButtonStyle.secondary, custom_id="music_shuffle")
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        import random
        random.shuffle(self.player.queue)
        await self.update_ui(interaction)

    @discord.ui.button(label="🔁", style=discord.ButtonStyle.secondary, custom_id="music_loop")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop_mode = not self.player.loop_mode
        button.style = discord.ButtonStyle.success if self.player.loop_mode else discord.ButtonStyle.secondary
        await self.update_ui(interaction)

class EffectSelect(discord.ui.Select):
    def __init__(self, player):
        self.player = player
        options = [
            discord.SelectOption(label="None", value="none", description="Standard Audio"),
            discord.SelectOption(label="Bassboost", value="bassboost", description="Boosts low frequencies"),
            discord.SelectOption(label="Nightcore", value="nightcore", description="Speed up and higher pitch"),
            discord.SelectOption(label="Vaporwave", value="vaporwave", description="Slowed and reverb")
        ]
        super().__init__(placeholder="Audio Effects", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        effect = self.values[0]
        self.player.current_effect = effect
        # Restart the current song with the new effect if playing
        vc = self.player.guild.voice_client
        if vc and vc.is_playing() and self.player.current_song:
            # We must stop the current playing and re-insert the current song at index 0
            self.player.queue.insert(0, self.player.current_song)
            self.player.current_song = None
            vc.stop()

        # update UI
        view = self.view
        if isinstance(view, MusicView):
            await view.update_ui(interaction)
        else:
            await interaction.response.defer()
