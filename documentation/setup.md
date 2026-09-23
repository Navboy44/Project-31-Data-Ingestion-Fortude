# Setup
This document describes how to get started with development.
Refer to https://docs.google.com/document/d/1HHSTL8_dvFfBZY46qxhkSk_gw6rnYG-cDUmNmGnLFsg/edit?usp=sharing for the full Guide.

## Project 31: Data Ingestion Engine
Follow this link to join our repository:
https://github.com/rohith-chaps88/Project-31-Data-Ingestion-Fortude

This repository 'Project 31 Data Ingestion Fortude' contains the code for the Data Ingestion software.
The main branch reflects the most current state of the application.
New code will be pushed to a new feature branch, reviewed, tested, and merged to our main branch.

## Cloning the Repository
Please ensure you have the following:
- GIT
- GitHub account
- Visual Studio Code*

*This is the recommended IDE that will be used within this guide. Please replace it with your preferred IDE if necessary.

**To Clone**:
1. Open Visual Studio Code
2. Press ctrl/cmd + shift + P to open the Command Palette
3. Type and select 'Git Clone'
4. Paste the repository URL: https://github.com/rohith-chaps88/Project-31-Data-Ingestion-Fortude and click ‘Clone from URL’
5. Select the folder location you would like the project to be stored in and click the ‘Select as Repository Destination’ button

## Installing Extensions
1. Press ctrl/cmd + shift + X to open the Extensions tab
2. Search for and install the following extensions:
    - Ruff

## Creating Virtual Environment and Installing Requirements
1. Open a terminal and ensure you are at the project root (FIT4002-FORTUDE)
2. Type 'py -3.10 -m venv .venv' and press enter
3. Type ‘.venv\Scripts\Activate.ps1’ and press enter*
4. Test that your virtual environment is active and working correctly by typing 'Get-Command python'
5. Verify that your version of python is **Python 3.10.x** by typing 'python --version'
6. Upgrade pip by typing ‘python -m pip install --upgrade pip’ and press enter
7. Type 'pip install -r requirements.txt'

## Starting Kafka output

Set the broker and topic before starting the backend:

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_TOPIC=fortude.ingestion
```

## Starting Qdrant vector output

Start a Qdrant instance, then configure the backend before starting Uvicorn:

```bash
export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION=fortude_documents
# Optional for Qdrant Cloud:
export QDRANT_API_KEY=your-api-key
```

The backend uses the `BAAI/bge-small-en-v1.5` FastEmbed model by default. It
downloads the model on first use. Override it with `QDRANT_EMBEDDING_MODEL` if
required. Select `Vector Database` as the ingestion output to upsert each
canonical document into the configured collection.

For Jira ingestion, also configure:

```bash
export JIRA_BASE_URL=https://your-domain.atlassian.net
export JIRA_EMAIL=your-email@example.com
export JIRA_API_TOKEN=your-api-token
```

`JIRA_EMAIL` must be the exact email address of the Atlassian account that
created `JIRA_API_TOKEN`. Set these variables in the same terminal that starts
Uvicorn, then restart the backend.

Select Kafka in the ingestion request with `outputs: "Kafka"`:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/local-folder \
    -H 'Content-Type: application/json' \
    -d '{"connector":"SharePoint KB","rule":"Knowledge Base Rules","outputs":"Kafka"}'
```

Each processed canonical document is published as a JSON message to the
configured topic. Requests that omit `outputs` continue using local JSON output.

*you must do this every time you start a new terminal session to work on the project. Use 'deactivate' once you have finished working on the project.