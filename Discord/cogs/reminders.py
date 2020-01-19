
import discord
from discord.ext import commands, tasks

import asyncio
import datetime

import parsedatetime

from utilities import checks

def setup(bot):
	bot.add_cog(Reminders(bot))

class Reminders(commands.Cog):
	
	def __init__(self, bot):
		self.bot = bot

		self.calendar = parsedatetime.Calendar()
		# Patch https://github.com/bear/parsedatetime/commit/7a759c1f8ff7563f12ac2c1f2ea0b41452f61dec
		# until fix is released
		if "secss" in self.calendar.ptc.units["seconds"]:
			self.calendar.ptc.units["seconds"].append("secs")
			self.calendar.ptc.units["seconds"].remove("secss")
			self.calendar.ptc.units["seconds"].append('s')
		# Add mo as valid abbreviation for month
		self.calendar.ptc.units["months"].append("mo")

		self.current_timer = None
		self.new_reminder = asyncio.Event()
		self.restarting_timer = False
		self.timer.start().set_name("Reminders")
	
	def cog_unload(self):
		self.timer.cancel()
	
	async def initialize_database(self):
		await self.bot.connect_to_database()
		await self.bot.db.execute("CREATE SCHEMA IF NOT EXISTS reminders")
		await self.bot.db.execute(
			"""
			CREATE TABLE IF NOT EXISTS reminders.reminders (
				id				INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY, 
				user_id			BIGINT, 
				channel_id		BIGINT, 
				message_id		BIGINT, 
				created_time	TIMESTAMPTZ DEFAULT NOW(), 
				remind_time		TIMESTAMPTZ, 
				reminder		TEXT, 
				reminded		BOOL DEFAULT FALSE, 
				failed			BOOL DEFAULT FALSE
			)
			"""
		)
	
	async def cog_check(self, ctx):
		return await checks.not_forbidden().predicate(ctx)
	
	@commands.group(name = "reminder", aliases = ["remind", "timer"], 
					invoke_without_command = True, case_insensitive = True)
	async def reminder_command(self, ctx, *, reminder: commands.clean_content):
		'''Set reminders'''
		# TODO: Allow setting timezone (+ for time command as well)
		# Clean reminder input
		for prefix in ("me about ", "me to ", "me "):
			if reminder.startswith(prefix):
				reminder = reminder[len(prefix):]
		reminder = reminder.replace("from now", "")
		# Parse reminder
		now = datetime.datetime.now(datetime.timezone.utc)
		if not (matches := self.calendar.nlp(reminder, sourceTime = now)):
			raise commands.BadArgument("Time not specified")
		parsed_datetime, flags, start_pos, end_pos, matched_text = matches[0]
		parsed_datetime = parsed_datetime.replace(tzinfo = datetime.timezone.utc)
		if parsed_datetime < now:
			raise commands.BadArgument("Time is in the past")
		# Respond
		reminder = reminder[:start_pos] + reminder[end_pos + 1:]
		reminder = reminder.strip()
		response = await ctx.embed_reply(fields = (("Reminder", reminder or ctx.bot.ZWS),), 
											footer_text = f"Set for {parsed_datetime.isoformat()}", 
											timestamp = parsed_datetime)
		# Insert into database
		created_time = ctx.message.created_at.replace(tzinfo = datetime.timezone.utc)
		await self.bot.db.execute(
			"""
			INSERT INTO reminders.reminders (user_id, channel_id, message_id, created_time, remind_time, reminder)
			VALUES ($1, $2, $3, $4, $5, $6)
			""", 
			ctx.author.id, ctx.channel.id, response.id, created_time, parsed_datetime, reminder
		)
		# Update timer
		if self.current_timer and parsed_datetime < self.current_timer:
			self.restarting_timer = True
			self.timer.restart()
			self.timer.get_task().set_name("Reminders")
		else:
			self.new_reminder.set()
	
	# TODO: reminders command / list subcommand
	# TODO: delete/cancel/remove subcommand
	# TODO: clear subcommand
	
	# R/PT0S
	@tasks.loop()
	async def timer(self):
		record = await self.bot.db.fetchrow(
			"""
			SELECT * FROM reminders.reminders
			WHERE reminded = FALSE AND failed = FALSE
			ORDER BY remind_time
			LIMIT 1
			"""
		)
		if not record:
			self.new_reminder.clear()
			return await self.new_reminder.wait()
		self.current_timer = record["remind_time"]
		if record["remind_time"] > (now := datetime.datetime.now(datetime.timezone.utc)):
			await asyncio.sleep((record["remind_time"] - now).total_seconds())
		if not (channel := self.bot.get_channel(record["channel_id"])):
			# TODO: Attempt to fetch channel?
			return await self.bot.db.execute("UPDATE reminders.reminders SET failed = TRUE WHERE id = $1", record["id"])
		user = self.bot.get_user(record["user_id"]) or self.bot.fetch_user(record["user_id"])
		# TODO: Handle user not found?
		embed = discord.Embed(color = self.bot.bot_color)
		try:
			message = await channel.fetch_message(record["message_id"])
			embed.description = f"[{record['reminder'] or 'Reminder'}]({message.jump_url})"
		except discord.NotFound:
			embed.description = record["reminder"] or "Reminder"
		embed.set_footer(text = "Reminder set")
		embed.timestamp = record["created_time"]
		try:
			await channel.send(user.mention, embed = embed)
		except discord.Forbidden:
			# TODO: Attempt to send without embed
			# TODO: Fall back to DM
			await self.bot.db.execute("UPDATE reminders.reminders SET failed = TRUE WHERE id = $1", record["id"])
		else:
			await self.bot.db.execute("UPDATE reminders.reminders SET reminded = TRUE WHERE id = $1", record["id"])
	
	@timer.before_loop
	async def before_timer(self):
		await self.initialize_database()
		await self.bot.wait_until_ready()
	
	@timer.after_loop
	async def after_timer(self):
		if self.restarting_timer:
			self.restarting_timer = False
		else:
			print(f"{self.bot.console_message_prefix}Reminders task cancelled @ {datetime.datetime.now().isoformat()}")

