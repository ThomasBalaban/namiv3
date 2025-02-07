import tmi from 'tmi.js';
import readline from 'readline';
import path from "path";
import fs from "fs";
import { askQuestion } from './index.js';

const ACTIVE_CHANNEL = 'rabbithatplays';

// Directory to save the conversation file
const dir = './conversations/chat_logs';
if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir);
}

// Array to store chat messages
let conversationData = [];


// Twitch chat configuration
const client = new tmi.Client({
    options: { debug: true }, // Enable debugging
    connection: {
        reconnect: true, // Auto-reconnect if disconnected
        secure: true     // Use secure connection
    },
    identity: {
        username: 'peepingnami', // Replace with your Twitch username
        password: 'oauth:51ioccg8wrmo5m9dpb9kc039h5i6wc' // Replace with your OAuth token
    },
    channels: [ACTIVE_CHANNEL] // Replace with the Twitch channel you want to join
});

// Connect to Twitch
client.connect().catch(console.error);

// Set up console input
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// Prompt for input
function promptInput() {
    rl.question('Enter a message to send: ', (input) => {
        if (input.toLowerCase() === 'exit') {
            console.log('Exiting...');
            rl.close();
            process.exit();
        }

        // Send the message to Twitch chat
        client.say(ACTIVE_CHANNEL, input)
            .then(() => {
                promptInput(); // Prompt again
            })
            .catch((err) => {
                console.error('Error sending message:', err);
                promptInput(); // Prompt again
            });
    });
}

// Start the input loop once connected
client.on('connected', () => {
    console.log('Connected to Twitch chat.');
    console.log('Type your message and press Enter. Type "exit" to quit.');
    promptInput();
});

// Listen for chat messages
client.on('message', (channel, tags, message, self) => {
    const chatEntry = {
        role: "user",
        content: `${tags['display-name']}: ${message}`
    };

    console.log(`[${tags['display-name']}] ${message}`);
    conversationData.push(chatEntry);

    // Save the conversation every 10 messages
    if (conversationData.length % 5 === 0) {
        appendMessage(chatEntry);
    }
});

// Periodically save the conversation every 5 minutes
setInterval(saveConversation, 5 * 60 * 1000);

// Gracefully handle exit
process.on('SIGINT', () => {
    console.log('Saving conversation before exiting...');
    saveConversation();
    process.exit();
});

// Save conversation to JSON file
function saveConversation() {
    const channelName = ACTIVE_CHANNEL;
    const filename = `twitchchatConvervation_${channelName}.json`;
    const filePath = path.join(dir, filename);

    fs.writeFileSync(filePath, JSON.stringify(conversationData, null, 2), "utf8");
    console.log(`Conversation saved to ${filePath}`);
}

// Function to append a single message to the JSON file
function appendMessage(chatEntry) {
    const channelName = client.getChannels()[0].replace('#', ''); // Get channel name
    const filename = `twitchchatConvervation_${channelName}.json`;
    const filePath = path.join(dir, filename);

    try {
        if (!fs.existsSync(filePath)) {
            // If the file doesn't exist, create it with an empty array
            fs.writeFileSync(filePath, JSON.stringify([chatEntry], null, 2), "utf8");
            console.log(`New conversation file created at ${filePath}`);
        } else {
            // Read the current file contents
            const fileData = fs.readFileSync(filePath, "utf8");
            const jsonData = JSON.parse(fileData);

            // Append the new chat entry
            jsonData.push(chatEntry);

            // Write back the updated data to the file
            fs.writeFileSync(filePath, JSON.stringify(jsonData, null, 2), "utf8");
        }

        console.log(`Appended message: ${chatEntry.content}`);
    } catch (error) {
        console.error('Error appending message:', error);
    }
}