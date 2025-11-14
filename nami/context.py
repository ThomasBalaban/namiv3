# Replace the entire contents of nami/context.py with this:
import httpx
from typing import List, Dict, Any

# The port for the director_engine
DIRECTOR_URL = "http://localhost:8002"

def get_breadcrumbs_from_director(count: int = 3) -> List[Dict[str, Any]]:
    """
    Fetches the "Top N" most interesting events (breadcrumbs)
    from the director_engine (Brain 1).
    
    This is a SYNCHRONOUS call because Nami (Brain 2)
    needs this information *before* she can formulate a response.
    """
    try:
        response = httpx.get(f"{DIRECTOR_URL}/breadcrumbs?count={count}", timeout=1.0)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"🔥 Director ERROR: Could not get breadcrumbs. Status {response.status_code}")
            return []
            
    except httpx.ConnectError:
        print(f"🔥 DIRECTOR OFFLINE: Could not get breadcrumbs from {DIRECTOR_URL}")
        return []
    except Exception as e:
        print(f"🔥 Breadcrumb Error: {e}")
        return []