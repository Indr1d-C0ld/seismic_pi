#!/bin/bash

# Replace with your bot token
TOKEN=""

# Replace with the message you want to send
MESSAGE="*** TEST ***"

# Send a message to the bot
curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendMessage?chat_id=$CHAT_ID&text=$MESSAGE" > /dev/null 2>&1

# Fetch the chat ID from the bot's response
CHAT_ID=$(curl -s "https://api.telegram.org/bot$TOKEN/getUpdates" | jq -r '.result[-1].message.chat.id')

# Print the chat ID
echo "Chat ID: $CHAT_ID"
