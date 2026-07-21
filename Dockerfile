FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching
COPY webapp/requirements.txt webapp/requirements.txt
RUN pip install --no-cache-dir -r webapp/requirements.txt

# Copy the whole repo (webapp needs parent-child-skill/scripts/lib.py)
COPY . .

ENV PORT=8080
EXPOSE 8080

# --chdir webapp so `app:app` resolves; imports of the skill scripts use
# absolute paths derived from __file__, so they work regardless of cwd.
# Long timeout: a single upload may trigger several live web-search lookups.
CMD ["sh", "-c", "gunicorn --chdir webapp --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 300 app:app"]
