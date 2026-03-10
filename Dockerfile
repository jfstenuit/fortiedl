FROM python:3.12-slim

# Non-root user
RUN useradd -r -s /bin/false -m -d /app appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser app/          ./app/
COPY --chown=appuser:appuser migrations/   ./migrations/
COPY --chown=appuser:appuser static/       ./static/
COPY --chown=appuser:appuser wsgi.py       .
COPY --chown=appuser:appuser gunicorn.conf.py .

USER appuser

EXPOSE 8080

CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
