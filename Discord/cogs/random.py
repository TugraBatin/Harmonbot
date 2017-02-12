
import discord
from discord.ext import commands

import asyncio
from bs4 import BeautifulSoup
import calendar
import concurrent.futures
import datetime
import dice
import inspect
import multiprocessing
import pydealer
import pyparsing
import random
import string
import xml.etree.ElementTree

from utilities import checks
import clients
import credentials
from modules import utilities

def setup(bot):
	bot.add_cog(Random(bot))

class Random:
	
	def __init__(self, bot):
		self.bot = bot
		# Add commands as random subcommands
		for name, command in inspect.getmembers(self):
			if isinstance(command, commands.Command) and command.parent is None and name != "random":
				self.bot.add_command(command)
				self.random.add_command(command)
		# Add fact subcommands as subcommands of corresponding commands
		for command, parent in ((self.fact_cat, self.cat), (self.fact_date, self.date), (self.fact_number, self.number)):
			utilities.add_as_subcommand(self, command, parent, "fact")
	
	@commands.group(invoke_without_command = True)
	@checks.not_forbidden()
	async def random(self):
		'''
		Random things
		All random subcommands are also commands
		'''
		await self.bot.embed_reply(":grey_question: Random what?")
	
	@commands.command()
	@checks.not_forbidden()
	async def card(self):
		'''Random playing card'''
		await self.bot.embed_reply(":{}: {}".format(random.choice(pydealer.const.SUITS).lower(), random.choice(pydealer.const.VALUES)))
	
	@commands.group(pass_context = True, invoke_without_command = True)
	@checks.not_forbidden()
	async def cat(self, ctx, *, category : str = ""):
		'''
		Random image of a cat
		cat categories (cats) for different categories you can choose from
		cat <category> for a random image of a cat from that category
		'''
		if category and category in ("categories", "cats"):
			async with clients.aiohttp_session.get("http://thecatapi.com/api/categories/list") as resp:
				data = await resp.text()
			categories = xml.etree.ElementTree.fromstring(data).findall(".//name")
			await self.bot.embed_reply('\n'.join(sorted(category.text for category in categories)))
		elif category:
			async with clients.aiohttp_session.get("http://thecatapi.com/api/images/get?format=xml&results_per_page=1&category={}".format(category)) as resp:
				data = await resp.text()
			url = xml.etree.ElementTree.fromstring(data).find(".//url")
			if url is not None:
				await self.bot.embed_reply("[:cat:]({})".format(url.text), image_url = url.text)
			else:
				await self.bot.embed_reply(":no_entry: Error: Category not found")
		else:
			async with clients.aiohttp_session.get("http://thecatapi.com/api/images/get?format=xml&results_per_page=1") as resp:
				data = await resp.text()
			url = xml.etree.ElementTree.fromstring(data).find(".//url").text
			await self.bot.embed_reply("[:cat:]({})".format(url), image_url = url)
	
	@commands.command(aliases = ["die", "roll"])
	@checks.not_forbidden()
	async def dice(self, *, input : str = '6'):
		'''
		Roll dice
		Inputs:                                      Examples:
		S     |  S - number of sides (default is 6)  [6      | 12]
		AdS   |  A - amount (default is 1)           [5d6    | 2d10]
		AdSt  |  t - return total                    [2d6t   | 20d5t]
		AdSs  |  s - return sorted                   [4d6s   | 5d8s]
		AdS^H | ^H - return highest H rolls          [10d6^4 | 2d7^1]
		AdSvL | vL - return lowest L rolls           [15d7v2 | 8d9v2]
		'''
		if 'd' not in input:
			input = 'd' + input
		with multiprocessing.Pool(1) as pool:
			async_result = pool.apply_async(dice.roll, (input,))
			future = self.bot.loop.run_in_executor(None, async_result.get, 10.0)
			try:
				result = await asyncio.wait_for(future, 10.0, loop = self.bot.loop)
				await self.bot.embed_reply(", ".join(str(roll) for roll in result))
			except discord.errors.HTTPException:
				await self.bot.embed_reply(":no_entry: Output too long")
			except pyparsing.ParseException:
				await self.bot.embed_reply(":no_entry: Invalid input")
			except concurrent.futures.TimeoutError:
				await self.bot.embed_reply(":no_entry: Execution exceeded time limit")
	
	@commands.command(pass_context = True)
	@checks.not_forbidden()
	async def command(self, ctx):
		'''Random command'''
		await self.bot.embed_reply("{}{}".format(ctx.prefix, random.choice(tuple(set(command.name for command in self.bot.commands.values())))))
	
	@commands.group(invoke_without_command = True)
	@checks.not_forbidden()
	async def date(self):
		'''Random date'''
		await self.bot.embed_reply(datetime.date.fromordinal(random.randint(1, 365)).strftime("%B %d"))
	
	@commands.command()
	@checks.not_forbidden()
	async def day(self):
		'''Random day of week'''
		await self.bot.embed_reply(random.choice(calendar.day_name))
	
	@commands.group(invoke_without_command = True)
	@checks.not_forbidden()
	async def fact(self):
		'''Random fact'''
		async with clients.aiohttp_session.get("http://mentalfloss.com/api/1.0/views/amazing_facts.json?limit=1&bypass=1") as resp:
			data = await resp.json()
		await self.bot.embed_reply(BeautifulSoup(data[0]["nid"]).text)
	
	@fact.command(name = "cat", aliases = ["cats"], pass_context = True)
	@checks.not_forbidden()
	async def fact_cat(self, ctx):
		'''Random fact about cats'''
		async with clients.aiohttp_session.get("http://catfacts-api.appspot.com/api/facts") as resp:
			data = await resp.json()
		if data["success"]:
			await self.bot.embed_reply(data["facts"][0])
		else:
			await self.bot.embed_reply(":no_entry: Error")
	
	@fact.command(name = "date")
	@checks.not_forbidden()
	async def fact_date(self, date : str):
		'''
		Random fact about a date
		Format: month/date
		Example: 1/1
		'''
		async with clients.aiohttp_session.get("http://numbersapi.com/{}/date".format(date)) as resp:
			if resp.status == 404:
				await self.bot.embed_reply(":no_entry: Error")
				return
			data = await resp.text()
		await self.bot.embed_reply(data)
	
	@fact.command(name = "math")
	@checks.not_forbidden()
	async def fact_math(self, number : int):
		'''Random math fact about a number'''
		async with clients.aiohttp_session.get("http://numbersapi.com/{}/math".format(number)) as resp:
			data = await resp.text()
		await self.bot.embed_reply(data)
	
	@fact.command(name = "number")
	@checks.not_forbidden()
	async def fact_number(self, number : int):
		'''Random fact about a number'''
		async with clients.aiohttp_session.get("http://numbersapi.com/{}".format(number)) as resp:
			data = await resp.text()
		await self.bot.embed_reply(data)
	
	@fact.command(name = "year")
	@checks.not_forbidden()
	async def fact_year(self, year : int):
		'''Random fact about a year'''
		async with clients.aiohttp_session.get("http://numbersapi.com/{}/year".format(year)) as resp:
			data = await resp.text()
		await self.bot.embed_reply(data)
	
	@commands.command()
	@checks.not_forbidden()
	async def idea(self):
		'''Random idea'''
		async with clients.aiohttp_session.get("http://itsthisforthat.com/api.php?json") as resp:
			data = await resp.json()
		await self.bot.embed_reply("{0[this]} for {0[that]}".format(data))
	
	@commands.command()
	@checks.not_forbidden()
	async def insult(self):
		'''Random insult'''
		async with clients.aiohttp_session.get("http://quandyfactory.com/insult/json") as resp:
			data = await resp.json()
		await self.bot.embed_say(data["insult"])
	
	@commands.command()
	@checks.not_forbidden()
	async def joke(self):
		'''Random joke'''
		async with clients.aiohttp_session.get("http://tambal.azurewebsites.net/joke/random") as resp:
			data = await resp.json()
		await self.bot.embed_reply(data["joke"])
	
	@commands.command()
	@checks.not_forbidden()
	async def letter(self):
		'''Random letter'''
		await self.bot.embed_reply(random.choice(string.ascii_uppercase))
	
	@commands.command()
	@checks.not_forbidden()
	async def location(self):
		'''Random location'''
		await self.bot.embed_reply("{}, {}".format(random.uniform(-90, 90), random.uniform(-180, 180)))
	
	@commands.group(aliases = ["rng"], invoke_without_command = True)
	@checks.not_forbidden()
	async def number(self, number : int = 10):
		'''
		Random number
		Default range is 1 to 10
		'''
		await self.bot.embed_reply(random.randint(1, number))
	
	@commands.command(aliases = ["why"])
	@checks.not_forbidden()
	async def question(self):
		'''Random question'''
		async with clients.aiohttp_session.get("http://xkcd.com/why.txt") as resp:
			data = await resp.text()
		questions = data.split('\n')
		await self.bot.embed_reply("{}?".format(random.choice(questions).capitalize()))
	
	@commands.command()
	@checks.not_forbidden()
	async def quote(self):
		'''Random quote'''
		async with clients.aiohttp_session.get("http://api.forismatic.com/api/1.0/?method=getQuote&format=json&lang=en") as resp:
			try:
				data = await resp.json()
			except:
				await self.bot.embed_reply(":no_entry: Error")
				return
		await self.bot.embed_reply(data["quoteText"], footer_text = data["quoteAuthor"]) # quoteLink?
	
	@commands.command()
	@checks.not_forbidden()
	async def time(self):
		'''Random time'''
		await self.bot.embed_reply("{:02d}:{:02d}".format(random.randint(0, 23), random.randint(0, 59)))
	
	@commands.command()
	@checks.not_forbidden()
	async def word(self):
		'''Random word'''
		await self.bot.embed_reply(clients.wordnik_words_api.getRandomWord().word.capitalize())

