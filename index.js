import readline from "readline";
import ollama from "ollama";
import BOT_CONFIG, { setMood } from "./bot.js";
import { addMessage } from "./session.js";  // Import the session functions

const { name: BOTNAME, personality } = BOT_CONFIG;

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

const systemMessage = {
  role: "system",
  content: `${personality}`,
};

let historyArray = [systemMessage];  // Start with the system message

// Function to ask a question and process the bot's response
async function askQuestion(question) {
  // Push the user input into historyArray first
  historyArray.push({
    role: "user",
    content: question
  });

  // Log the history array before adding to memory (for debugging)
  console.log("History array before adding user message:", historyArray);

  try {
    // Fetch the bot's response from Ollama using the history as context
    const response = await ollama.chat({
      model: BOT_CONFIG.model,
      messages: historyArray,  // Provide the conversation history to Ollama
      stream: false,
      max_tokens: BOT_CONFIG.max_tokens
    });

    console.log('Response from Ollama:', response);  // Log the response

    // Check if response and message are valid
    if (response && response.message) {
      const botReply = response.message.content;
      console.log(`${BOTNAME}: ${botReply}`);  // Log bot reply

      // Save both the user's input and the bot's output together
      addMessage(question, botReply);  // Store in memory for context

      // Add the bot's reply to the conversation history for future context
      historyArray.push({
        role: "assistant",
        content: botReply
      });
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
