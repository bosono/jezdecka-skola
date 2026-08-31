FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Prague

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kód se za běhu bind-mountuje z /home/jarda/jezdecka-skola (rsync workflow),
# tahle kopie je jen fallback když se mount nepoužije.
COPY . .

EXPOSE 8000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
