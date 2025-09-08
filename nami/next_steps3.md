# Phase 3: Unleash the Real Nami

Once your model has finished tuning, you will get a unique model ID.

## Step 1: Get Your Tuned Model ID

1. In Google AI Studio, go back to the "**Tuned models**" section
2. Find your completed model and click on it
3. Find the API ID. It will look something like `tunedModels/nami-v1-tuned-abcd123`. Copy this ID

## Step 2: Final Update to `nami/bot_core.py`

Make one final, simple change to your `nami/bot_core.py` file.

### Find this line in the `__init__` method:

```python
model_to_use = 'gemini-1.5-flash-latest'
```

### Replace with your tuned model ID:

Replace `'gemini-1.5-flash-latest'` with your tuned model ID. It's a string, so keep the quotes:

```python
# Example Change
model_to_use = 'tunedModels/nami-v1-tuned-abcd123'  # <-- PASTE YOUR MODEL ID HERE
```

## Step 3: Relaunch and Celebrate!

That's it! Restart your bot. Nami is now running on a super-fast, cloud-hosted model that has been specifically trained on her personality, humor, and adult nature. You now have the best of both worlds: extreme performance and deep personality customization, without the hardware headaches.