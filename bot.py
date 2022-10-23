import os
import json
import discord # type: ignore
import asyncio
from threading import RLock
from random import sample, shuffle, choice
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

temp = os.getenv("TOKEN")
assert temp is not None
TOKEN: str = temp

temp = os.getenv("CHANNEL")
assert temp is not None
CHANNELID: int = int(temp)

with open('words.json', encoding="utf-8") as f:
	words: dict = json.load(f)
	del words[""]

# stupid json file for now
class Scores:
	def __init__(self):
		self.scorepath: str = "scores.json"
		self.scoresLock: RLock = RLock()

	def add(self, userIdInt: int, points: int) -> int:
		userId: str = str(userIdInt)

		with self.scoresLock:
			data = self.readData()
			score = 0 if userId not in data else data[userId]
			data[userId] = score + points
			with open(self.scorepath, mode="w", encoding="utf-8") as f:
				json.dump(data, f)
			return data[userId]

	def readData(self) -> dict:
		if os.path.exists(self.scorepath):
			with open(self.scorepath, encoding="utf-8") as f:
				data: dict = json.load(f)
		else:
			data = {}

		return data

scores: Scores = Scores()

# View with buttons
class Question(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=3600.0)
		self.msg: discord.Message

		pick: list[str] = sample([*words.keys()], 4)
		answers: list[str] = [words[key] for key in pick]
		if choice([True, False]):
			pick, answers = answers, pick
		self.question = pick[0]
		self.realAnswer: str = answers[0]
		shuffle(answers)

		# points people can earn from this question (decreases every wrong answer)
		triesLock: RLock = RLock()
		tries: dict = {}

		def getCallback(localAnswer: str):
			async def callback(interaction: discord.Interaction):
				userId: int = interaction.user.id

				with triesLock:
					if userId not in tries: tries[userId] = 0
					tries[userId] = tries[userId]+1
					userTries = tries[userId]

				if userTries >= 100: # magic
					await interaction.response.send_message(f'Tu as déjà répondu.', ephemeral=True)
				elif localAnswer == self.realAnswer:
					points: int = max(0, 5-userTries)
					total:int = scores.add(userId, points)
					with triesLock:
						tries[userId] = 100 # magic
					await interaction.response.send_message('\n'.join([
						f"Bonne réponse ! Tu gagnes {points} points pour avoir trouvé en {userTries} essai{'s' if userTries > 1 else ''}.",
						f"Total des points: {total}",
					]), ephemeral=True)
				else:
					await interaction.response.send_message(f"Mauvaise réponse 🤔 (essai {userTries}).", ephemeral=True)

			return callback

		for answer in answers:
			button: discord.ui.Button = discord.ui.Button(label=answer, style=discord.ButtonStyle.blurple)
			button.callback = getCallback(answer)
			self.add_item(button)

	async def on_timeout(self):
		for item in self.children:
			if isinstance(item, discord.ui.Button):
				item.style = discord.ButtonStyle.grey
				item.disabled = True
		await self.msg.edit(view=self)

class MyClient(discord.Client):
	async def on_ready(self):
		print(f'Logged on as {self.user} ({self.user.id})')
		self.channel = discord.utils.get(self.get_all_channels(), id=CHANNELID)
		print(f'Will send questions in channel {self.channel.name}')

		while True:
			await asyncio.sleep(600)
			await self.sendQuestion()

	async def on_message(self, message: discord.Message):
		assert message.author is not None
		assert self.user is not None
		if message.author.id == self.user.id: return

		if True: # choice(range(5)) == 0:
			await self.sendQuestion()

	async def sendQuestion(self):
		question = Question()
		msg: discord.Message = await self.channel.send(question.question, view=question)
		await msg.add_reaction('✅')
		question.msg = msg

intents = discord.Intents.default()

client = MyClient(intents=intents)
client.run(TOKEN)
