FROM python:3.9-slim

WORKDIR /app

COPY . .

RUN pip install requests beautifulsoup4 voluptuous plotly

CMD ["python", "main.py"]
