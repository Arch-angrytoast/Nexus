import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
from .ui_music import MusicView, EffectSelect

# yt-dlp setup tailored for streaming and low-memory usage
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # ipv6 issues sometimes
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn' # no video
}

EFFECT_FILTERS = {
    'none': '',
    'bassboost': 'bass=g=15',
    'nightcore': 'asetrate=44100*1.25,aresample=44100',
    'vaporwave': 'asetrate=44100*0.8,aresample=44100,aecho=0.8:0.8:250:0.5'
}

class MusicPlayer:
    def __init__(self, guild):
        self.guild = guild
        self.queue = []
        self.current_song = None
        self.bound_message = None
        self.loop_mode = False
        self.current_effect = 'none'
        self.bot_loop = asyncio.get_event_loop()

    def generate_embed(self):
        embed = discord.Embed(color=discord.Color.from_str("#2B2D31"))

        if self.current_song:
            title = self.current_song.get('title', 'Unknown Title')
            uploader = self.current_song.get('uploader', 'Unknown Artist')
            duration = self.current_song.get('duration', 0)
            mins, secs = divmod(duration, 60)

            embed.title = f"Now Playing"

            effect_str = f" | Effect: **{self.current_effect.capitalize()}**" if self.current_effect != 'none' else ""
            loop_str = " | **🔁 Looping**" if self.loop_mode else ""
            embed.description = f"**{title}**\n*by {uploader}*\n⏱ {mins}:{secs:02d}{effect_str}{loop_str}"

            thumbnail = self.current_song.get('thumbnail')
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
        else:
            embed.title = "Not Playing Anything"
            embed.description = "Queue up some songs!"

        if self.queue:
            q_list = ""
            for i, song in enumerate(self.queue[:5]):
                q_list += f"`{i+1}.` {song.get('title', 'Unknown')}\n"
            if len(self.queue) > 5:
                q_list += f"*...and {len(self.queue)-5} more*"
            embed.add_field(name="Up Next", value=q_list, inline=False)

        return embed

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, guild):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(guild)
        return self.players[guild.id]

    async def extract_info(self, search: str):
        loop = asyncio.get_event_loop()
        # Ensure search uses ytsearch if it's not a url
        if not search.startswith('http'):
            search = f"ytsearch:{search}"

        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))

        if 'entries' in data:
            data = data['entries'][0]
        return data

    def play_next(self, guild_id, error=None):
        if error:
            print(f"Player error: {error}")

        player = self.players.get(guild_id)
        if not player:
            return

        vc = player.guild.voice_client
        if not vc or not vc.is_connected():
            return

        if player.loop_mode and player.current_song:
            player.queue.insert(0, player.current_song)

        if len(player.queue) == 0:
            player.current_song = None
            asyncio.run_coroutine_threadsafe(self.update_ui(player), player.bot_loop)
            return

        player.current_song = player.queue.pop(0)
        url = player.current_song['url']

        # Build ffmpeg options with effects
        ffmpeg_opts = dict(FFMPEG_OPTIONS)
        filter_str = EFFECT_FILTERS.get(player.current_effect, '')
        if filter_str:
            ffmpeg_opts['options'] = f"-vn -af {filter_str}"

        try:
            source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source, after=lambda e: self.play_next(guild_id, e))
        except Exception as e:
            print(f"Failed to play stream: {e}")
            self.play_next(guild_id)

        asyncio.run_coroutine_threadsafe(self.update_ui(player), player.bot_loop)

    async def update_ui(self, player):
        view = MusicView(player)
        view.add_item(EffectSelect(player))
        await view.update_ui()

    @commands.hybrid_command(name="play", description="Play a song from YouTube or Soundcloud")
    @app_commands.describe(query="The song name or URL")
    async def play(self, ctx: commands.Context, *, query: str):
        if not ctx.author.voice:
            await ctx.send("You must be in a voice channel to use this.", ephemeral=True)
            return

        await ctx.defer()

        vc = ctx.guild.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect()

        player = self.get_player(ctx.guild)

        try:
            song_data = await self.extract_info(query)
            player.queue.append(song_data)
        except Exception as e:
            await ctx.send(f"Failed to find song: {e}", ephemeral=True)
            return

        # If a bound message exists, update it or create a new one
        embed = player.generate_embed()
        view = MusicView(player)
        view.add_item(EffectSelect(player))

        if not player.bound_message:
            msg = await ctx.send(embed=embed, view=view)
            player.bound_message = msg
        else:
            await ctx.send(f"Added **{song_data.get('title')}** to the queue!", delete_after=5)
            await player.bound_message.edit(embed=embed, view=view)

        if not vc.is_playing() and not vc.is_paused():
            self.play_next(ctx.guild.id)

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
