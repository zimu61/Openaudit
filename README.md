# OpenAudit - AI-Powered Code Security Audit Platform

An intelligent code security audit platform that combines **Joern** (static analysis) with **AI** (OpenAI GPT + Claude + others) for automated vulnerability detection.

## Architecture

- **Backend**: Python FastAPI (async) with SQLAlchemy + PostgreSQL
- **Task Queue**: Celery + Redis for background scan processing
- **Static Analysis**: Joern CPG-based code analysis
- **AI**: Configurable OpenAI GPT / Anthropic Claude / others for source identification and vulnerability analysis
- **Frontend**: Next.js with Tailwind CSS

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Joern installed locally (for scan execution)
- OpenAI or Anthropic API key or other API key
- Add your Joern path in docker-compose.yml

### Setup

1. **Configure environment**:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your API keys
   ```

2. **Start all services**:
   ```bash
   docker-compose up -d
   ```

3. **Run database migrations**:
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

4. **Access the app**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API docs: http://localhost:8000/docs


## How It Works

1. **Upload** a code package (.zip or .tar.gz)
2. **Joern** parses the code into a Code Property Graph (CPG)
3. **AI** identifies user-controlled input sources from function parameters and calls
4. **Joern** traces data flows from identified sources to dangerous sinks
5. **AI** analyzes each flow for real vulnerabilities
6. **Results** are displayed with severity, confidence, code context, and remediation
