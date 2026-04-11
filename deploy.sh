#!/bin/bash

# RAG System Automated Deployment & Run Script
# ══════════════════════════════════════════════════════════════

set -e # Exit immediately if a command exits with a non-zero status

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}  RAG Document Intelligence - Deployment & Setup Script${NC}"
echo -e "${BLUE}============================================================${NC}"

# 1. System Dependencies
echo -e "\n${YELLOW}[1/5] Checking system dependencies...${NC}"
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
    echo -e "${RED}python3.12-venv is not installed. Requesting sudo to install...${NC}"
    sudo apt-get update
    sudo apt-get install -y python3.12-venv python3-pip
else
    echo -e "${GREEN}✓ Python venv package is installed.${NC}"
fi

if ! dpkg -s zstd >/dev/null 2>&1; then
    echo -e "${RED}zstd is not installed (required for Ollama extraction). Requesting sudo to install...${NC}"
    sudo apt-get install -y zstd
else
    echo -e "${GREEN}✓ zstd package is installed.${NC}"
fi

# 2. Virtual Environment
echo -e "\n${YELLOW}[2/5] Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Created new virtual environment 'venv'.${NC}"
else
    echo -e "${GREEN}✓ Virtual environment 'venv' already exists.${NC}"
fi

echo -e "Activating virtual environment..."
source venv/bin/activate
pip install --upgrade pip > /dev/null

# 3. Python Dependencies
echo -e "\n${YELLOW}[3/5] Installing Python dependencies...${NC}"
echo -e "Running pip install (this might take a minute)..."
pip install -r backend/requirements.txt
echo -e "${GREEN}✓ Python dependencies installed.${NC}"

# 4. Ollama & Models
echo -e "\n${YELLOW}[4/5] Checking Ollama installation and models...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}Ollama is not installed. Installing now...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo -e "${GREEN}✓ Ollama is already installed.${NC}"
fi

echo -e "Ensuring Ollama server is running..."
# Function to check if Ollama API is reachable
check_ollama_api() {
    curl -s -o /dev/null http://127.0.0.1:11434/api/version
}

if ! check_ollama_api; then
    echo -e "${YELLOW}Ollama server is not running. Starting it...${NC}"
    
    # Check if we are using systemd (WSL often does not use it by default)
    if [ -d "/run/systemd/system" ]; then
        echo -e "Using systemd to start Ollama..."
        sudo systemctl start ollama
    else
        echo -e "systemd not detected (likely WSL). Starting Ollama in the background..."
        nohup ollama serve > ollama_setup.log 2>&1 &
        disown
    fi
    
    # Wait for the API to become available
    echo -e "Waiting for Ollama API to become available..."
    for i in {1..15}; do
        if check_ollama_api; then
            echo -e "${GREEN}✓ Ollama server is running.${NC}"
            break
        fi
        sleep 1
    done
    
    if ! check_ollama_api; then
        echo -e "${RED}Warning: Failed to verify Ollama server is running. Proceeding anyway, but models may fail to pull.${NC}"
    fi
else
    echo -e "${GREEN}✓ Ollama server is already running.${NC}"
fi

# Determine Models to pull
# Note: For the client machine with an RTX 4070 (8GB VRAM) and 64GB RAM,
# we can use gemma3:12b or keep gemma3:1b if configured that way.
# The server will pick up models automatically based on environment vars or defaults in config.py
CHAT_MODEL=${RAG_CHAT_MODEL:-"gemma3:1b"}
EMBED_MODEL=${RAG_EMBED_MODEL:-"nomic-embed-text"}

echo -e "Pulling chat model: ${CHAT_MODEL}..."
ollama pull $CHAT_MODEL

echo -e "Pulling embed model: ${EMBED_MODEL}..."
ollama pull $EMBED_MODEL
echo -e "${GREEN}✓ Models are downloaded and ready.${NC}"

# 5. Directories Creation
echo -e "\n${YELLOW}[5/5] Ensuring data directories exist...${NC}"
mkdir -p data/clients data/vendors data/customers
echo -e "${GREEN}✓ Data directories are ready.${NC}"

# Start System
echo -e "\n${BLUE}============================================================${NC}"
echo -e "${GREEN}  System Setup Complete! Starting RAG Server...${NC}"
echo -e "${BLUE}============================================================${NC}"
echo -e "The server will start on ${YELLOW}http://0.0.0.0:8000${NC}"
echo -e "Press ${RED}Ctrl+C${NC} to stop the server."
echo -e "${BLUE}============================================================\n${NC}"

# Standard uvicorn run command
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
