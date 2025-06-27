#!/bin/bash

# ==============================================================================
# AISavvy Deployment Script
# ==============================================================================

# --- Configuration: Define colors for user-friendly output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting the AISavvy deployment...${NC}"

# Step 1: Build and start the Docker containers in detached mode
echo -e "\n${YELLOW}[1/3] Building and starting all services (Postgres, Ollama, API, UI)...${NC}"
docker compose up --build -d

if [ $? -ne 0 ]; then
    echo -e "\n${RED}Error: Docker Compose failed to start the services. Please check logs.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Services started successfully!${NC}"

# Step 2: Pull the Llama 3 LLM model (the default powerful model)
echo -e "\n${YELLOW}[2/3] Downloading the Llama 3 LLM model. This may take several minutes...${NC}"
docker compose exec ollama ollama pull llama3
docker-compose exec ollama ollama pull phi3:mini

if [ $? -ne 0 ]; then
    echo -e "\n${RED}Error: Failed to download the Llama 3 model.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Llama 3 model downloaded successfully!${NC}"

# Step 3: Announce completion and provide the URL
echo -e "\n${YELLOW}[3/3] Deployment complete!${NC}"
echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}    🚀 Your AISavvy application is ready! 🚀    ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nAccess the web UI at the following URL:"
echo -e "${YELLOW}👉 http://localhost:8501 ${NC}\n"
