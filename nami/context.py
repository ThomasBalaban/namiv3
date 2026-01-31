# nami/context.py
import httpx
from typing import List, Dict, Any, Union

# The port for the director_engine
DIRECTOR_URL = "http://localhost:8002"

def get_breadcrumbs_from_director(count: int = 3) -> Union[Dict[str, Any], List]:
    """
    Fetches the formatted context block from the director_engine (Brain 1).
    
    This is a SYNCHRONOUS call because Nami (Brain 2)
    needs this information *before* she can formulate a response.
    
    Returns:
        Dict with 'formatted_context' key if successful
        Empty list on failure
    """
    try:
        # Increased timeout since construct_context_block is async and may do Gemini calls
        response = httpx.get(f"{DIRECTOR_URL}/breadcrumbs?count={count}", timeout=10.0)
        
        if response.status_code == 200:
            data = response.json()
            # Debug: Show what we got
            if isinstance(data, dict) and "formatted_context" in data:
                ctx = data["formatted_context"]
                print(f"✅ [Context] Received {len(ctx)} chars from Director")
                if len(ctx) < 100:
                    print(f"   Content: {ctx}")
                else:
                    print(f"   Preview: {ctx[:150]}...")
            else:
                print(f"⚠️ [Context] Unexpected format: {type(data)} - {str(data)[:100]}")
            return data
        else:
            print(f"🔥 Director ERROR: Could not get breadcrumbs. Status {response.status_code}")
            print(f"   Response body: {response.text[:200]}")
            return []
            
    except httpx.ConnectError as e:
        print(f"🔥 DIRECTOR OFFLINE: Could not get breadcrumbs from {DIRECTOR_URL}")
        print(f"   Error: {e}")
        return []
    except httpx.TimeoutException as e:
        print(f"🔥 DIRECTOR TIMEOUT: Request to {DIRECTOR_URL}/breadcrumbs timed out after 10s")
        print(f"   This may happen if Gemini visual summarization is slow.")
        return []
    except Exception as e:
        print(f"🔥 Breadcrumb Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []