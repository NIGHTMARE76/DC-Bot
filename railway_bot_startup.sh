#!/bin/bash

echo "Starting Radio FM Bot in Bot-Only Mode..."

# Set the Railway environment variable for our app to recognize
export RAILWAY_ENVIRONMENT=true

# Install ffmpeg (critical for audio playback)
echo "Installing ffmpeg for audio playback..."
apt-get update -y
apt-get install -y ffmpeg libopus0 libopusfile0 opus-tools

# Verify ffmpeg installation
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg installed successfully: $(ffmpeg -version | head -n 1)"
else
    echo "❌ ffmpeg installation failed, trying alternative approach..."
    # Try alternative installation approach without updating apt
    apt-get install -y --no-install-recommends ffmpeg
    
    if command -v ffmpeg &> /dev/null; then
        echo "✅ ffmpeg installed through alternative approach"
    else
        echo "❌ ffmpeg installation failed completely"
    fi
fi

# Print environment info
echo "Starting bot with Python $(python --version)"
echo "Working directory: $(pwd)"

# Try to copy the cookies file if it's in the repository
if [ -f "cookies.txt" ]; then
    echo "Found cookies.txt in main directory"
    # Make sure it has the right permissions
    chmod 644 cookies.txt
elif [ -f "attached_assets/cookies.txt" ]; then
    echo "Found cookies.txt in attached_assets, copying..."
    cp attached_assets/cookies.txt ./cookies.txt
    chmod 644 cookies.txt
fi

# Start the bot in standalone mode
echo "Starting Bot in standalone mode..."
python run_bot_only.py