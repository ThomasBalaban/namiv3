import fs from "fs";
import path from "path";
import BOT_CONFIG from "./bot.js";

const { name: BOTNAME, personality, creatorDetails, rules, } = BOT_CONFIG;

const systemMessage = {
	role: "system",
	content: `${personality} ${creatorDetails} ${rules}`,
};

let historyArray = [systemMessage];  // Start with the system message

export function loadTwitchChatConversation(usernameOfStreamer) {    
    const filePath = path.join("./conversations/chat_logs/", `twitchchatconvervation_${usernameOfStreamer}.json`);

    if (fs.existsSync(filePath)) {
        try {
            // Read and parse the JSON content from the file
            const conversationData = JSON.parse(fs.readFileSync(filePath, "utf8"));

            // If the data is an array (as expected), return it
            if (Array.isArray(conversationData)) {
                if (conversationData.length > 40) {
                    conversationData.splice(0, conversationData.length - 20);  // Remove earliest entries
                    fs.writeFileSync(filePath, JSON.stringify(conversationData, null, 2), "utf8");
                }
                return conversationData; // Return the entire conversation array
            } else {
                return []; // Return an empty array if the structure is not as expected
            }
        } catch (error) {
            console.error("Error reading or parsing the Twitch chat file:", error);
            throw new Error(`Failed to load Twitch chat conversation: ${error.message}`);
        }
    } else {
        // If the file doesn't exist, create a new empty file
        console.log("No Twitch chat history found, initializing new conversation file.");
        saveConversation("twitchChat", false, []); // Save an empty file to initialize
        return []; // Return an empty conversation array
    }
}

export function loadConversation(username) {
    const filePath = path.join("./conversations", `conversation_${username}.json`);

    if (fs.existsSync(filePath)) {
        try {
            // Read the file and parse the JSON content
            const conversationData = JSON.parse(fs.readFileSync(filePath, "utf8"));
            let pastConversation = [];

            if (Array.isArray(conversationData.conversation)) {
                conversationData.conversation.forEach(item => {
                    pastConversation.push(item);
                });
            }

            let convoData = [...pastConversation]; // Only include past conversation, no system message

            console.log(convoData);

            return convoData;
        } catch (error) {
            console.error("Error reading or parsing the file:", error);
            throw new Error(`something broke bad ${error}`);
        }
    } else {
        saveConversation(username, false, historyArray);
        const conversationData = JSON.parse(fs.readFileSync(filePath, "utf8"));
        console.log(`No conversation history found for user: ${username}`);
        
        let convoData = []; // No system message to return here
        
        return convoData;
    }
}

// Function to append a new message to an existing conversation
export async function appendMessageToConversation(username, question, botReply) {
    const filename = `./conversations/user_profiles/conversation_${username}.json`;
    const filePath = path.join("./conversations", filename);

    // Check if the conversation file exists
    if (!fs.existsSync(filename)) {
        console.log(`Error: The conversation file for ${username} does not exist.`);
        await saveConversation(username, false, historyArray)
    }

    try {
        // Read the existing conversation file
        const fileContent = fs.readFileSync(filename, "utf8");
        const conversationData = JSON.parse(fileContent);

        // Append the new message to the existing conversation history
        conversationData.conversation.push(
            {
                role: 'user',
                content: question
            },
            {
                role: 'assistant',
                content: botReply
            }
        );
        // Write the updated conversation back to the file (no overwrite of the entire file)
        fs.writeFileSync(filename, JSON.stringify(conversationData, null, 2), "utf8");

        console.log(`New message appended to ${username}'s conversation.`);
    } catch (error) {
        console.error("Error appending the message:", error);
    }
}

function saveConversation(username, underage = false, historyArray) {
    console.log('reached save convo')
    const filename = `conversation_${username}.json`;

    const conversationData = {
        username,
        underage,
        conversation: [], // Leave out system message
    };

    // Add only user and assistant messages (skip system message)
    historyArray.forEach(item => {
        if (item.role !== 'system') {
            conversationData.conversation.push(item);
        }
    });

    // Ensure the directory exists
    const dir = "./conversations/user_profiles/";
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir);
    }

    // Write the file
    const filePath = path.join(dir, filename);
    fs.writeFileSync(filePath, JSON.stringify(conversationData, null, 2), "utf8");
    console.log(`Conversation saved to ${filePath}`);
}

