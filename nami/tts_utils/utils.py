def check_dependencies():
    """
    Check if recommended libraries are installed
    Returns list of missing but recommended libraries
    """
    missing_libs = []
    
    try:
        import soundfile
    except ImportError:
        missing_libs.append("soundfile")
        
    try:
        import scipy
    except ImportError:
        missing_libs.append("scipy")
    
    return missing_libs