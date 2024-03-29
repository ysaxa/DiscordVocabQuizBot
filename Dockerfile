FROM python:3.10
WORKDIR /bot
COPY requirements.txt /bot/
COPY .env.yaml /bot/
RUN pip install -r requirements.txt
COPY . /bot
CMD python bot.py
