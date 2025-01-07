import fs from "fs";
import path from "path";

export function detectUnderage(message) {
	const lowerMessage = message.toLowerCase();
	const underageIndicators = [
		"im underage", "under 18", "under eighteen", "under 18 years old", "i am 17", "im 17", "i am 16", "im 16", "im under 18", "im a minor", "im not 18", "i am not 18", "i'm a minor", "i am a minor", "my age is 17", "my age is 16", "i'm too young", "too young", "not 18", "not eighteen", "teenager", "i'm still a kid", "i'm still young", "i am a teenager", "born in 2007", "born in 2008", "born in 2009", "i have not reached 18", "not of age", "not adult", "i am not an adult", "i'm not an adult", "still a kid", "still underage", "still 17", "still 16", "my birthday is coming up", "i turn 18 soon", "i will be 18 in", "i am not 18 yet", "i haven't turned 18", "i'm waiting to turn 18", "i haven't reached adulthood", "i am underage", "i'm a minor", "not legal", "under the legal age", "below legal age", "not of legal age", "not old enough", "too young to drink", "too young to drive", "too young to vote", "too young to be here", "my age is not 18", "i am not 18 years old", "i'm not old enough", "i'm just a kid", "i'm just a teenager"
	];
	
	// Check if the message contains any of the underage phrases
	for (let indicator of underageIndicators) {
		if (lowerMessage.includes(indicator)) {
			return true;  // Set underage flag if any indicator is found
		}
	}
	return false;  // Return false if no underage indicators are found
}

export function setUnderAgeToTrue(username, underage = false) {
    const filePath = path.join("./conversations", `conversation_${username}.json`);
    console.log(`${username} is underage.`);

    if (fs.existsSync(filePath)) {
        try {
            // Read the file and parse the JSON content
            const conversationData = JSON.parse(fs.readFileSync(filePath, "utf8"));
            conversationData.underage = true;
            fs.writeFileSync(filePath, JSON.stringify(conversationData, null, 2), "utf8");
            console.log("The underage field has been updated successfully.");
        } catch (error) {
            console.error("Error reading or parsing the file:", error);
            throw new Error(`something broke bad ${error}`)
        }
    }
}