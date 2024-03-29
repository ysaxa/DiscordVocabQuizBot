import os
import re
import json
import yaml
import discord # type: ignore
import asyncio
import typing
from threading import RLock
from random import sample, shuffle, choice, choices, randint
from datetime import datetime

def notNone(data: dict[str, typing.Any], key: str):
	assert key in data
	ret = data[key]
	return ret

class Env:
	def __init__(self, data: dict[str, typing.Any]):
		self.token: str = notNone(data, 'TOKEN')
		self.question_delay_in_seconds: int = notNone(data, 'QUESTION_DELAY_IN_SECONDS')
		self.quizzes: list[Env.QuizDef] = [Env.QuizDef(quiz) for quiz in notNone(data, 'QUIZZES')]

	class QuizDef:
		channel: discord.TextChannel # set after the client starts

		def __init__(self, data: dict[str, typing.Any]):
			self.words: list[dict[str, str]] = self.loadWords(notNone(data, 'WORDS'))
			self.questions, self.substitutions = self.loadQuestions(notNone(data, 'QUESTIONS'))
			self.channelId: str = notNone(data, 'CHANNEL')

		@staticmethod
		def loadWords(filename: str) -> list[dict[str, str]]:
			with open(filename, encoding="utf-8") as f:
				words: list[dict[str, str]] = [{
					key: str(value)
					for key, value in wordDict.items()
				} for wordDict in yaml.safe_load(f)]

				return words

		@staticmethod
		def loadQuestions(filename: str) -> tuple[dict[str, str], dict[str, list[str]]]:
			with open(filename, encoding="utf-8") as f:
				questionsAndAnswersBase: dict[str, typing.Any] = yaml.safe_load(f)
				questionsAndAnswers: dict[str, str] = notNone(questionsAndAnswersBase, "questions")
				substitutions: dict[str, list[str]] = notNone(questionsAndAnswersBase, "substitutions")
				return questionsAndAnswers, substitutions


with open('.env.yaml', encoding="utf-8") as f:
	ENV: Env = Env(yaml.safe_load(f))

# stupid json file for now
class Scores:
	def __init__(self):
		self.scorepath: str = "appdata/scores.json"
		self.scoresLock: RLock = RLock()

	def add(self, userId: str, points: int) -> int:
		with self.scoresLock:
			data = self.readData()
			score = 0 if userId not in data else data[userId]
			data[userId] = score + points
			with open(self.scorepath, mode="w", encoding="utf-8") as f:
				json.dump(data, f)
			return data[userId]

	def readData(self) -> dict[str, int]:
		if os.path.exists(self.scorepath):
			with open(self.scorepath, encoding="utf-8") as f:
				data: dict[str, int] = json.load(f)
		else:
			data = {}

		return data

scores: Scores = Scores()

questionDataType = tuple[str, str, list[str], int] # what is necessary to post a question

# View with buttons
class Question(discord.ui.View):
	def __init__(self, words: list[dict[str, str]], questionsAndAnswers: dict[str, str], substitutions: dict[str, list[str]]):
		super().__init__(timeout=14400.0)
		self.msg: discord.Message

		def simpleVocabulary() -> questionDataType:
			wordgroup: dict[str, str] = choices(words, weights=[i+1 for i in range(len(words))])[0]
			if "" in wordgroup: del wordgroup[""]
			pick: list[str] = sample([*wordgroup.keys()], 4)
			answers: list[str] = [wordgroup[key] for key in pick]
			if choice([True, False]):
				pick, answers = answers, pick
			return "Traduction de vocabulaire simple", pick[0], answers, 0x00FF00

		def numbers() -> questionDataType:
			values: list[int] = [randint(0,9) for _ in range(8)]
			values.insert(0, randint(6,7))
			values.insert(0, 0)
			sinokorean: str = "공일이삼사오육칠팔구십"
			answer: list[str] = [sinokorean[i] for i in values]

			index: int = randint(2,10)
			replacements: list[str] = sample([c for c in sinokorean if c != answer[index]], 3)

			answers = [answer.copy(), answer.copy(), answer.copy()]
			for i in range(len(answers)):
				answers[i][index] = replacements[i]

			answers.insert(0, answer)

			return "Traduction de numéro de téléphone", ''.join([str(i) for i in values]), [''.join(a) for a in answers], 0xFFFF00

		def coherentAnswer() -> questionDataType:
			pick: list[str] = sample([*questionsAndAnswers.keys()], 4)
			prompt: str = pick[0]
			answers: list[str] = [questionsAndAnswers[key] for key in pick]

			def substitute(strings: list[str]):
				variableDict: dict[str, list[str]] = {
					key: list(set(re.findall(f"~{key}[0-9]*~", ''.join(strings))))
					for key in substitutions.keys()
				}

				#print(f"substitutions for {','.join(strings)}")
				#print(json.dumps(variableDict, sort_keys=True, indent=4))

				for key, variables in variableDict.items():
					if len(variables) == 0: continue
					subs: list[str] = sample(substitutions[key], len(variables))
					for i,_ in enumerate(strings):
						for j,__ in enumerate(subs):
							strings[i] = strings[i].replace(variables[j], subs[j])

				# replace 이에요 with 예요/이에요 according to rule
				def replace이에요(s:str):
					occurrences: list[str] = re.findall('.이에요', s)
					for occurrence in occurrences:
						print(occurrence)
						ch = occurrence[0]
						chOrd = ord(ch)
						if not (44032 <= chOrd <= 55203): s.replace(occurrence, f'{ch}이에요') # this should never happen
						if (chOrd-44032)%28 == 0: # no final
							s = s.replace(occurrence, f'{ch}예요')
						else:
							s = s.replace(occurrence, f'{ch}이에요')

					return s

				return [replace이에요(s) for s in strings]

			# substitute in question and real_answer with variable coherency
			prompt, answers[0] = substitute([prompt, answers[0]])

			# substitute in every answers without necessarily variable coherency (real_answer is already substituted so nothing will be done)
			answers = [substitute([answer])[0] for answer in answers]

			return "Trouver la réponse cohérente", prompt, answers, 0x0000FF

		title, question, answers, color = choice([
			*[simpleVocabulary]*sum([len(d) for d in words]),
			*[coherentAnswer]*len(questionsAndAnswers),
			*[numbers]*10,
		])()
		self.embed = discord.Embed(title=title, description=question, color=color)
		self.realAnswer: str = answers[0]
		shuffle(answers)

		# points people can earn from this question (decreases every wrong answer)
		triesLock: RLock = RLock()
		tries: dict[str, int] = {}

		def getCallback(localAnswer: str):
			async def callback(interaction: discord.Interaction):
				userId: str = str(interaction.user.id)

				with triesLock:
					if userId not in tries: tries[userId] = 0
					tries[userId] = tries[userId]+1
					userTries = tries[userId]

				if userTries >= 100: # magic
					await interaction.response.send_message(f'Tu as déjà répondu.', ephemeral=True)
				elif localAnswer == self.realAnswer:
					points: int = max(0, 5-userTries)
					total: int = scores.add(userId, points)
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
			button: discord.ui.Button[discord.ui.View] = discord.ui.Button(label=answer, style=discord.ButtonStyle.blurple)
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
		assert self.user is not None
		user: discord.ClientUser = self.user

		for quizDef in ENV.quizzes:
			print(f'Logged on as {self.user} ({user.id})')
			channel = discord.utils.get(list(self.get_all_channels()), id=quizDef.channelId)
			if channel is None or not isinstance(channel, discord.TextChannel) :
				print(f"invalid channel id {quizDef.channelId}")
				exit()

			quizDef.channel = channel
			print(f'Will send questions in channel {channel.name}')

			await channel.send(embed=discord.Embed(title="ATTENTION", description="⚠ Bot redéployé, les questions précédentes sont invalides.", color=0xFF0000))

		while True:
			try:
				for quizDef in ENV.quizzes:
					await self.sendQuestion(quizDef)
				await asyncio.sleep(ENV.question_delay_in_seconds)
			except:
				pass

	"""
	async def on_message_DISABLED(self, message: discord.Message) -> None:
		assert message.author is not None
		assert self.user is not None
		if message.author.id == self.user.id: return

		if True: # choice(range(5)) == 0:
			await self.sendQuestion()
	"""

	@staticmethod
	async def sendQuestion(quizDef: Env.QuizDef) -> None:
		question = Question(quizDef.words, quizDef.questions, quizDef.substitutions)
		msg: discord.Message = await quizDef.channel.send(embed=question.embed, view=question)
		await msg.add_reaction('✅')
		question.msg = msg

intents = discord.Intents.default()

client = MyClient(intents=intents)
client.run(ENV.token)
