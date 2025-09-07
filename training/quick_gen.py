#!/usr/bin/env python3
from mlx_lm import load, generate

MODEL = "./nami-trained"
SYSTEM = "You are Nami—playful, witty, mischievous, but helpful. Stay in character."

def build(history):
    # You trained on "User: ...\nNami:" pairs; stick to that format.
    lines = [SYSTEM, ""]
    for role, text in history:
        lines.append(f"{'User' if role=='user' else 'Nami'}: {text}")
    lines.append("Nami:")  # cue the model to speak next
    return "\n".join(lines)

def main():
    model, tok = load(MODEL)
    history = []
    print("Loaded Nami. Type 'exit' to quit.\n")
    while True:
        try:
            u = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if u.lower() in {"exit", "quit"}:
            break

        history.append(("user", u))
        prompt = build(history)

        # Call generate() with ONLY the safest args for your version.
        out = generate(
            model=model,
            tokenizer=tok,
            prompt=prompt,
            max_tokens=200,  # keep small if it rambles
        )

        # Trim everything before the last "Nami:" so you only print her reply
        reply = out.split("Nami:", 1)[-1].strip()
        print("Nami:", reply, "\n")
        history.append(("nami", reply))

if __name__ == "__main__":
    main()
