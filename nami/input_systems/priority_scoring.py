import time

def calculate_input_score(item, source_weights, recent_inputs, last_response_time):
    """Calculate priority score for an input"""
    # Start with base score from source weight
    score = source_weights[item.source]
    
    # Apply recency boost (more recent is higher priority)
    time_factor = max(0, 1 - min(1, (time.time() - item.timestamp) / 30))  # Effect decays over 30 seconds
    score += time_factor * 0.2
    
    # Apply content relevance factors if available
    if 'relevance' in item.metadata:
        score += item.metadata['relevance'] * 0.3
    
    # Apply urgency factor if available
    if 'urgency' in item.metadata:
        score += item.metadata['urgency'] * 0.2
    
    # Apply conversation continuity bonus
    if recent_inputs and _is_continuation(item, recent_inputs):
        score += 0.2
    
    # Apply cadence penalty if we just responded
    time_since_response = time.time() - last_response_time
    if time_since_response < 5:  # If less than 5 seconds since last response
        score -= 0.3 * max(0, 1 - time_since_response/5)
    
    return score

def _is_continuation(item, recent_inputs) -> bool:
    """Check if this input is related to recent conversation"""
    # Very simple implementation - could be improved with NLP
    if not recent_inputs:
        return False
        
    # Check if this input contains words from recent inputs
    recent_words = set()
    for recent in recent_inputs[-3:]:  # Look at last 3 inputs
        for word in recent.text.lower().split():
            if len(word) > 4:  # Only consider substantial words
                recent_words.add(word)
    
    # Count matching words
    matches = 0
    for word in item.text.lower().split():
        if len(word) > 4 and word in recent_words:
            matches += 1
    
    return matches >= 1  # At least one significant word match