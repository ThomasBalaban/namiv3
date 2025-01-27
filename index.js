import readline from "readline";
import ollama from "ollama";
import BOT_CONFIG, { setMood } from "./bot.js";
import { addMessage } from "./session.js";  // Import the session functions
import { loadTwitchChatConversation, appendMessageToConversation } from "./conversations.js";
import { detectUnderage, setUnderAgeToTrue } from "./safety-checks/underage.js";

const ACTIVE_CHANNEL = 'peepingotter';
const username = 'PeepingOtter';
const { name: BOTNAME, personality, creatorDetails, rules, } = BOT_CONFIG;
const rl = readline.createInterface({
	input: process.stdin,
	output: process.stdout,
});

let historyArray = loadTwitchChatConversation(ACTIVE_CHANNEL);
 // Ensure the system message is always at the top
 const systemMessage = {
	role: "system",
	content: `${personality} ${creatorDetails} ${rules}`,
};

// Combine the system message with the full chat history
const conversationHistory = [systemMessage, ...historyArray];

export async function askQuestion(question, username = "anonymous") {
    conversationHistory.push({
        role: "user",
        content: `${username}: ${question}`, // Include the username in the message
    });

    try {       
        console.log("Conversation history:", conversationHistory);

		if (conversationHistory.length > 30) {
			const messagesToDelete = conversationHistory.slice(1); // Skip the system message
			const messagesToKeep = messagesToDelete.filter(message =>
				message.content.toLowerCase().includes("nami") || 
				message.content.toLowerCase().includes("peepingnami") ||
				message.role === "assistant"
			);

			// Limit the number of messages to keep to 20
			const messagesToKeepLimited = messagesToKeep.slice(0, 7);

			// Limit the number of messages to 20 to remove
			const messagesToRemove = messagesToDelete.slice(0, 15 - messagesToKeepLimited.length);
			
			// Combine the system message with the messages we want to keep
			conversationHistory.length = 1; // Reset to just the system message
			conversationHistory.push(...messagesToKeep, ...messagesToRemove);

			console.log('Updated conversation history after trimming:', conversationHistory);
		}

		if (!question.toLowerCase().includes("nami") && !question.toLowerCase().includes("peepingnami")) {
            // Skip processing if the trigger words are not present
            return null;
        }

        // Send the full history to the bot
        const response = await ollama.chat({
            model: BOT_CONFIG.model,
            messages: conversationHistory,
            stream: false,
            max_tokens: BOT_CONFIG.max_tokens,  // Adjusted max token limit
            temperature: BOT_CONFIG.temperature,  // Creativity level
            top_k: BOT_CONFIG.top_k,  // Token choice range
            top_p: BOT_CONFIG.top_p,  // Probability cutoff
            repeat_penalty: BOT_CONFIG.repeat_penalty,  // Penalize repeated tokens
            repeat_last_n: BOT_CONFIG.repeat_last_n,  // Memory window for repetition penalty
            num_predict: BOT_CONFIG.num_predict,  // Number of response candidates
        });

        if (response && response.message) {
            const botReply = response.message.content;

            // Save the response to the history
            conversationHistory.push({
                role: "assistant",
                content: botReply,
            });

            // Save the interaction for persistent storage
            appendMessageToConversation(username, question, botReply);			

            return botReply; // Return the bot's response
        } else {
            console.error("Unexpected response structure:", response);
            return "I couldn't process that, sorry!";
        }
    } catch (error) {
        console.error("Error fetching response:", error);
        return "Something went wrong, please try again later.";
    }
}


// Main function to start the conversation
function startConversation() {
    rl.on('line', async (question) => {
        if (question.toLowerCase() === "exit") {
            console.log("Goodbye!");
            rl.close();
            return;
        }

        if (question.toLowerCase().startsWith("set mood to ")) {
            const newMood = question.substring(12).trim();
            setMood(newMood);
            console.log(`Mood updated to: ${newMood}`);
            return; // Skip further processing to prevent looping
        }

        await askQuestion(question);  // Ask the bot the question
    });
}

startConversation();  // Start the conversation loop
