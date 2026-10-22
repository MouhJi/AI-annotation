FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchvision==0.20.1
RUN pip install --no-cache-dir -r requirements.txt && pip uninstall -y opencv-python && pip install --no-cache-dir --no-deps --force-reinstall "opencv-python-headless>=4.8,<5"
COPY app ./app
COPY tests ./tests
COPY seed.py ./seed.py
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
