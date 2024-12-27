import readline from "readline";
import ollama from "ollama";
import BOT_CONFIG, { setMood } from "./bot.js";
import { addMessage } from "./session.js";  // Import the session functions
import { loadConversation, appendMessageToConversation } from "./conversations.js";

const username = 'PeepingOtter';
const { name: BOTNAME, personality, creatorDetails, rules, } = BOT_CONFIG;
const rl = readline.createInterface({
	input: process.stdin,
	output: process.stdout,
});

const systemMessage = {
	role: "system",
	content: `${personality} ${creatorDetails} ${rules}`,
};

let historyArray = loadConversation(username, systemMessage);  // Start with the system message
let repetitionCount = 0;  // Track repeated inputs
let lastUserMessage = ""; // Store the last user message
let underage = false;  // Initialize underage flag

function detectUnderage(message) {
	const lowerMessage = message.toLowerCase();
	const underageIndicators = [
		"under 18", "under eighteen", "under 18 years old", "i am 17", "im 17", "i am 16", "im 16", "im under 18", "im a minor", "im not 18", "i am not 18", "i'm a minor", "i am a minor", "my age is 17", "my age is 16", "i'm too young", "too young", "not 18", "not eighteen", "teenager", "i'm still a kid", "i'm still young", "i am a teenager", "born in 2007", "born in 2008", "born in 2009", "i have not reached 18", "not of age", "not adult", "i am not an adult", "i'm not an adult", "still a kid", "still underage", "still 17", "still 16", "my birthday is coming up", "i turn 18 soon", "i will be 18 in", "i am not 18 yet", "i haven't turned 18", "i'm waiting to turn 18", "i haven't reached adulthood", "i am underage", "i'm a minor", "not legal", "under the legal age", "below legal age", "not of legal age", "not old enough", "too young to drink", "too young to drive", "too young to vote", "too young to be here", "my age is not 18", "i am not 18 years old", "i'm not old enough", "i'm just a kid", "i'm just a teenager"
	];
	

	// Check if the message contains any of the underage phrases
	for (let indicator of underageIndicators) {
		if (lowerMessage.includes(indicator)) {
			return true;  // Set underage flag if any indicator is found
		}
	}
	return false;  // Return false if no underage indicators are found
}

// Function to ask a question and process the bot's response
async function askQuestion(question) {
	// Check for repeated inputs
    if (question === lastUserMessage) {
        repetitionCount += 1; // Increment for repetitions
    } else {
        repetitionCount = 0; // Reset for new messages
    }
    lastUserMessage = question; // Update last message

	// Adjust max tokens dynamically based on repetition count
    let adjustedMaxTokens = BOT_CONFIG.max_tokens - (repetitionCount * 50);
	if (adjustedMaxTokens < 30) adjustedMaxTokens = 2; // Set a minimum token limit
	//console.log('adjustedMaxTokens', adjustedMaxTokens)

	console.log("historyArray = ", historyArray)

	// Push the user input into historyArray first
	historyArray.push({
		role: "user",
		content: `${username}: ${question}`
	});

	// Detect if the user is underage
	if (detectUnderage(question)) {
		underage = true;  // Set underage flag to true
		console.log("User is underage.");  // Optionally, log this to console
	}

	// Log the history array before adding to memory (for debugging)
	console.log("History array before adding user message:", historyArray);

	try {
		// Fetch the bot's response from Ollama using the history as context
		const response = await ollama.chat({
			model: BOT_CONFIG.model,
			messages: historyArray,
			stream: false,
			options: {
				repeat_penalty: 1.5,
				repeat_last_n: 2,
				num_predict: adjustedMaxTokens,
			}
		});

		//console.log('Response tokens:', response.options);  // Log the response
		//console.log('Response from Ollama:', response);  // Log the response

		if (response && response.message) {
			const botReply = response.message.content;
			console.log(`${botReply}`);  // Log bot reply

			// Save both the user's input and the bot's output together
			addMessage(question, botReply);

			historyArray.push({
				role: "assistant",
				content: `${botReply}`,
			});

			appendMessageToConversation(username, question, botReply); // Save the conversation before exiting
		} else {
			console.error("Unexpected response structure:", response);
		}
	} catch (error) {
		console.error("Error fetching response:", error);
	}
}

// Main function to start the conversation
function startConversation() {
	rl.question(`Say to ${BOTNAME}: `, async (question) => {
		if (question.toLowerCase() === "exit") {
			console.log("Goodbye!");
			rl.close();
			return;
		}

		if (question.toLowerCase().startsWith("set mood to ")) {
			const newMood = question.substring(12).trim();
			setMood(newMood);
			console.log(`Mood updated to: ${newMood}`);
			startConversation();
			return;
		}

		await askQuestion(question);  // Ask the bot the question
		startConversation();  // Recursively ask the next question
	});
}

startConversation();  // Start the conversation loop
