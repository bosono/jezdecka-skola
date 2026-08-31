import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1          # SQLite + jeden sdílený state → 1 worker stačí a nehrozí kolize zápisu
threads = 4
timeout = 60
accesslog = "-"
errorlog = "-"
# Bind-mount kódu + reload = rsync změny se projeví bez restartu kontejneru (jako melody-dashboard)
reload = os.environ.get("GUNICORN_RELOAD") == "1"
