#!/bin/bash

# Quick Start Script for RAG Document Analysis API
# This script helps you get started quickly with local development

echo "========================================="
echo "RAG Document Analysis API - Quick Start"
echo "========================================="
echo ""

# Check if Python 3.9+ is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Found Python $PYTHON_VERSION"

# Check if .env file exists
if [ ! -f .env ]; then
    echo ""
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Please edit the .env file with your Azure credentials before continuing."
    echo "   Required: DATABASE_URL, SECRET_KEY, and all Azure service credentials"
    echo ""
    read -p "Press Enter once you've configured the .env file..."
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo ""
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Check if database is configured
echo ""
echo "🔍 Checking database configuration..."
if grep -q "your-username" .env; then
    echo "⚠️  Database credentials not configured in .env file"
    echo "   Please update DATABASE_URL with your Azure PostgreSQL credentials"
    exit 1
fi

# Run database migrations
echo ""
echo "🗄️  Running database migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Database migrations completed"
else
    echo "❌ Database migrations failed"
    echo "   Please check your DATABASE_URL in .env and ensure the database is accessible"
    exit 1
fi

# All done
echo ""
echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "To start the development server, run:"
echo "  source venv/bin/activate  # (if not already activated)"
echo "  uvicorn app.main:app --reload"
echo ""
echo "The API will be available at:"
echo "  - API: http://localhost:8000"
echo "  - Swagger UI: http://localhost:8000/docs"
echo "  - ReDoc: http://localhost:8000/redoc"
echo ""
echo "Next steps:"
echo "  1. Review README.md for complete documentation"
echo "  2. Check SETUP_GUIDE.md for Azure setup instructions"
echo "  3. See API_REFERENCE.md for endpoint details"
echo ""
echo "Happy coding! 🚀"
echo ""
