# Mac Disk Declutter

A local Mac application that identifies files/folders safe to delete, ranks them by ROI (space freed vs. risk), and provides a UI for selection and deletion with an AI chat co-pilot.

## Quick Start

```bash
cd disk-cleaner
pip install -r requirements.txt
python run.py
```

Opens browser to `http://localhost:5192`.

## Setup

### Claude API (default)
1. Click the gear icon in the UI
2. Enter your Claude API key
3. Save

### Ollama (local)
1. Install Ollama and pull a model: `ollama pull llama3`
2. Switch provider to "Ollama" in settings

## Features

- **Scan** predefined macOS locations (caches, logs, downloads, etc.)
- **LLM analysis** of each item's safety score, description, and deletion consequences
- **Ranked results** by ROI (size × safety), aggregated intelligently
- **Checkbox selection** with running total of space to free
- **Move to Trash** or **Delete Permanently** with confirmation
- **Chat co-pilot** for questions about files and safety
- All deletions logged to `~/.disk-cleaner/history.log`

## Safety

- Nothing is ever auto-deleted
- Permanent deletion requires explicit confirmation
- All actions are logged
