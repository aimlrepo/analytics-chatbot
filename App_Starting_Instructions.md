# Application Starting Instructions

This guide provides the complete, step-by-step instructions to set up and run the **L2L Analytics Chatbot** on a new computer from scratch.

---

## 1. Prerequisites on the Target Machine

1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (Windows / macOS) or **Docker Engine + Docker Compose** (Linux).
   * Ensure Docker Desktop is installed and running before executing commands.
2. **LLM API Key**: An API key for either OpenAI (e.g. `gpt-4o`) or Google Gemini (e.g. `gemini-1.5-pro`).

---

## 2. Pre-Flight Checks Before Starting

### A. Adjust Host gcloud Path in `docker-compose.yml`
Open `docker-compose.yml` and look at line 33:
```yaml
- /c/Users/kumarma/AppData/Roaming/gcloud:/root/.config/gcloud:ro
```
* **If on Windows**: Change `kumarma` to the current Windows username (e.g. `C:/Users/<YourUsername>/AppData/Roaming/gcloud:/root/.config/gcloud:ro`).
* **If on Linux/macOS**: Change to `~/.config/gcloud:/root/.config/gcloud:ro`.
* **If you do not plan to pull data from BigQuery**: You can simply comment out this line by prefixing with `#`.

### B. Verify the Embedded Database Cache (`data/l2l_analytics.duckdb`)
* If the `data/l2l_analytics.duckdb` file is present in your folder, **the application will work immediately offline** without requiring Google Cloud / BigQuery access.
* The chatbot queries this local DuckDB file for all analytics and chart generation.

---

## 3. Step-by-Step Setup Instructions

### Step 1: Copy Project Folder
Copy the entire `l2l-analytics-chatbot` project folder to the target machine.

### Step 2: Configure Environment Variables (`.env`)
Ensure a `.env` file exists in the project root with the following parameters:

```ini
# Choose model provider: "openai" or "gemini"
MODEL_PROVIDER=openai

# Model Names
OPENAI_MODEL_NAME=gpt-4o
GEMINI_MODEL_NAME=gemini-1.5-pro

# API Keys
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_API_KEY=your_gemini_api_key_here

# GCP Configuration (for BigQuery sync)
GCP_PROJECT_ID=k-qualitytower-0001-p
```

### Step 3: Start Docker Desktop
Verify that the Docker engine is running on your computer.

### Step 4: Build and Start Containers
Open your terminal (PowerShell, Command Prompt, or terminal) in the project directory and run:

```bash
docker compose up --build -d
```
*(On older systems, use `docker-compose up --build -d`)*

> **Why `--build`?**
> The `--build` flag builds the Docker image defined in `Dockerfile`, installing Python 3.11, C/C++ compilation tools, and the Python packages listed in `requirements.txt`.
> Docker Compose will:
> 1. Start the PostgreSQL 16 container (`l2l_postgres_db`).
> 2. Wait until PostgreSQL passes its health check.
> 3. Start the FastAPI web application (`l2l_analytics_app`).

### Step 5: Verify Container Status
Check that both containers are running and healthy:
```bash
docker compose ps
```

To view live application logs:
```bash
docker compose logs -f web
```

### Step 6: Access the Application
Open your web browser and go to:
```
http://localhost:8000
```
You can now submit natural language queries to analyze dispatches, downtime, and generate Plotly charts.

---

## 4. Useful Operations & Maintenance

* **Stop the application:**
  ```bash
  docker compose down
  ```
* **Restart the containers:**
  ```bash
  docker compose restart
  ```
* **Refresh data from BigQuery:**
  If you have Google Cloud authentication configured, trigger the cache refresh endpoint:
  ```bash
  curl -X POST http://localhost:8000/sync-cache
  ```
  *(Neither a Docker rebuild nor a container restart is needed after syncing cache; the updated data is available instantly).*
