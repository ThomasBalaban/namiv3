import { HumanMessage, AIMessage } from "@langchain/core/messages";

// In-memory storage to simulate a "history"
let conversationHistory = [];

// Function to add a message to the conversation history
export function addMessage(userMessage, botMessage) {
    if (!userMessage || !botMessage) {
        throw new Error("Both user message and bot message are required.");
    }

    // Add the user message and bot response to the conversation history
    conversationHistory.push(new HumanMessage(userMessage));
    conversationHistory.push(new AIMessage(botMessage));
}

// Function to retrieve the conversation history as structured messages
export function getConversationHistory() {
    return conversationHistory;
}
