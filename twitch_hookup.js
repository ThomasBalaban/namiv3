import tmi from 'tmi.js';
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { askQuestion } from './index.js'; // Import bot logic

const ACTIVE_CHANNEL = 'peepingotter';
let chatters = [];

// Array to store chat messages
let conversationData = [];

// Twitch chat configuration
const client = new tmi.Client({
    options: { debug: true },
    connection: {
        reconnect: true,
        secure: true,
    },
    identity: {
        username: 'peepingnami', // Replace with your Twitch bot username
        password: 'oauth:51ioccg8wrmo5m9dpb9kc039h5i6wc', // Replace with your OAuth token
    },
    channels: [ACTIVE_CHANNEL], // Channel to join
});

// Connect to Twitch
client.connect().catch(console.error);

// Set up console input
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// Start the input loop once connected
client.on('connected', () => {
    console.log('Connected to Twitch chat.');
});

// Listen for chat messages
client.on('message', async (channel, tags, message, self) => {
    if (self) return;

    const username = tags['display-name'];

    // Add the username to the array if it's not already there
    if (!chatters.includes(username)) {
        chatters.push(username);
        console.log(`New user added: ${username}`);
    }
    
    const chatEntry = {
        role: "user",
        content: `${tags['display-name']}: ${message}`
    };

    appendMessage(chatEntry);

    // Send the message to the bot and get a response
    try {
        const botReply = await askQuestion(message, tags['display-name']);
        conversationData.push(chatEntry);

        if (botReply) {
            const botReplyEntry = {
                role: "assistant",
                content: `${botReply}`
            };

            conversationData.push(botReplyEntry);
            appendMessage(botReplyEntry);            
            client.say(channel, `@${tags['display-name']} ${botReply}`); // Reply to the user in Twitch chat
        } 
    } catch (error) {
        console.error('Error processing Twitch message:', error);
    }
});

// Gracefully handle disconnect
process.on('SIGINT', () => {
    console.log('Disconnecting from Twitch...');
    saveConversations(); // Save the full conversation before exit   
});

// Save conversation to JSON file
function saveConversations() {
    console.log(chatters); // This will log all chatters who have chatted
    console.log('Reached save conversation function');
    
    // Iterate through each username in the chatters array
    for (const username of chatters) {
        console.log('Found username:', username);

        // Define the file path for the user profile conversation JSON
        const filename = path.join('/conversations/user_profiles/', `conversation_${username}.json`);

        // Check if the file exists
        if (fs.existsSync(filename)) {
            console.log('Found username\'s file:', filename);
            // You can proceed with further processing here (e.g., reading the file, summarizing it, etc.)
        } else {
            console.log('No file found for username:', username);
            console.log(filename)
        }
    }

    // Disconnect the Twitch client and exit the process after checking all files
    client.disconnect();
    process.exit();
}

// Function to append a single message to the JSON file

export function appendMessage(chatEntry) {
    // Directory to save the conversation file
    const dir = './conversations/chat_logs';
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir);
    }

    const filename = `twitchchatconvervation_${ACTIVE_CHANNEL}.json`;
    const filePath = path.join(dir, filename);

    try {
        if (!fs.existsSync(filePath)) {
            // If the file doesn't exist, create it with an empty array
            fs.writeFileSync(filePath, JSON.stringify([chatEntry], null, 2), "utf8");
        } else {
            // Read the current file contents
            const fileData = fs.readFileSync(filePath, "utf8");
            const jsonData = JSON.parse(fileData);

            // Append the new chat entry
            jsonData.push(chatEntry);

            // If there are more than 80 entries, remove the earliest 40
            if (jsonData.length > 80) {
                jsonData.splice(0, 40);  // Remove the first 40 entries
            }

            // Write back the updated data to the file
            fs.writeFileSync(filePath, JSON.stringify(jsonData, null, 2), "utf8");
        }
    } catch (error) {
        console.error('Error appending message:', error);
    }
}
