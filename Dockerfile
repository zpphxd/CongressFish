FROM python:3.11

# Install Node.js (18+) and build tools
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files for layer caching
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY requirements.txt ./

# Install dependencies
RUN npm ci --prefix frontend \
  && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 3000 8000

# Start FastAPI backend (port 8000) and React frontend (port 3000)
CMD ["sh", "-c", "python -m uvicorn backend.api.simulation_api:app --host 0.0.0.0 --port 8000 & cd frontend && npm run dev"]
