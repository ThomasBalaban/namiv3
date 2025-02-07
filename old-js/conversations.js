import fs from "fs";
import path from "path";
import BOT_CONFIG from "./bot.js";

const { name: BOTNAME, personality, creatorDetails, rules, } = BOT_CONFIG;

const systemMessage = {
	role: "system",
	content: `${personality} ${creatorDetails} ${rules}`,
};

let historyArray = [systemMessage];  // Start with the system message

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

            let convoData = [
                {
                    role: 'system',
                    content: conversationData.content
                },
                ...pastConversation
            ]

            console.log(convoData)

            return convoData;
        } catch (error) {
            console.error("Error reading or parsing the file:", error);
            throw new Error(`something broke bad ${error}`)
        }
    } else {
        saveConversation(username, false, systemMessage.content)
        const conversationData = JSON.parse(fs.readFileSync(filePath, "utf8"));
        console.log(`No conversation history found for user: ${username}`);
        
        let convoData = [
            {
                role: 'system',
                content: conversationData.content
            },
        ]
        
        return convoData
        //return { underage: false, historyArray };  // Return empty history if the file doesn't exist
    }
}

// Function to append a new message to an existing conversation
export async function appendMessageToConversation(username, question, botReply) {
    const filename = `conversation_${username}.json`;
    const filePath = path.join("./conversations", filename);

    // Check if the conversation file exists
    if (!fs.existsSync(filePath)) {
        console.log(`Error: The conversation file for ${username} does not exist.`);
        await saveConversation(username, false, historyArray)
    }

    try {
        // Read the existing conversation file
        const fileContent = fs.readFileSync(filePath, "utf8");
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
        fs.writeFileSync(filePath, JSON.stringify(conversationData, null, 2), "utf8");

        console.log(`New message appended to ${username}'s conversation.`);
    } catch (error) {
        console.error("Error appending the message:", error);
    }
}

// Function to save conversation to a JSON file
function saveConversation(username, underage = false, historyArray) {
    console.log('reached save convo')
    const filename = `conversation_${username}.json`;

    const conversationData = {
        username,
        underage,
        role: "system",
        content: historyArray,
        conversation: [],
    };

    console.log(conversationData)

    // Ensure the directory exists
    const dir = "./conversations";
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir);
    }

    // Write the file
    const filePath = path.join(dir, filename);
    fs.writeFileSync(filePath, JSON.stringify(conversationData, null, 2), "utf8");
    console.log(`Conversation saved to ${filePath}`);
}

