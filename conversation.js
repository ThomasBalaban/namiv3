// Initialize the history with the system message
let history = [
  { role: 'system', content: 'You are PeepingNami...<system instructions>' }
];

// This function updates the conversation history
function updateHistory(userMessage, botResponse) {
  // Keep the system message, then add the user message and bot response
  history = [
    history[0],  // Keep the system message
    { role: 'user', content: userMessage },
    { role: 'assistant', content: botResponse }
  ];

  console.log('Updated history:', history); // Debug to see if it works
}

// This function handles the user's message and gets the bot's response
async function handleUserMessage(userMessage) {
  // Get the bot's response
  const botResponse = await getBotResponse(userMessage);

  // Save the updated history
  updateHistory(userMessage, botResponse);

  // Return the bot's response
  return botResponse;
}

// This function simulates getting the bot's response
async function getBotResponse(userMessage) {
  // Assuming you have a local function or some logic to get the bot's reply
  const botReply = await generateBotReply(userMessage);

  // Save both input and output together in the correct history
  await saveContext({ input: userMessage, output: botReply });

  return botReply;
}

// This function generates the bot's response (example)
function generateBotReply(userMessage) {
  // Simple example: return a message echoing the user's input
  return `You said: ${userMessage}`;
}

// This function saves the input and output to the history
function saveContext({ input, output }) {
  // Make sure we're modifying the correct `history` array
  history.push({ input, output });
  console.log("Updated Context History:", history); // Debug to see if it works
}

// Export the functions for use in other modules
export { handleUserMessage, updateHistory };
