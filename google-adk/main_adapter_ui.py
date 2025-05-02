# main_adapter.py
"""
Adapter to ensure main.py can be easily called from the Streamlit UI.
This file is optional but helps with proper integration.
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path

# Ensure your main.py can be loaded in tests 
def prepare_environment():
    """Set up the environment before loading main.py"""
    # Add current directory to Python path if not already present
    current_dir = str(Path(__file__).parent)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        
    # Ensure required environment variables are set with defaults if not present
    defaults = {
        "USER_PROFILE_PATH": "knowledge/user_preference.txt",
        "OUTPUT_DIR": "results/",
        "GRANTS_COUNT": "3",
    }
    
    for key, default_value in defaults.items():
        if key not in os.environ:
            os.environ[key] = default_value

# Create a command-line parser for main.py
def create_parser():
    """Create a command-line argument parser for main.py"""
    parser = argparse.ArgumentParser(description="Run grant search")
    parser.add_argument(
        "--profile", 
        dest="user_profile_path",
        help="Path to user profile file",
        default=os.environ.get("USER_PROFILE_PATH", "knowledge/user_preference.txt")
    )
    parser.add_argument(
        "--output", 
        dest="output_dir",
        help="Output directory",
        default=os.environ.get("OUTPUT_DIR", "results/")
    )
    parser.add_argument(
        "--grants", 
        dest="grants_to_process",
        type=int,
        help="Number of grants to process",
        default=int(os.environ.get("GRANTS_COUNT", "3"))
    )
    return parser

# Main entry point that can be called from other Python files
def run_main():
    """Run the main.py script with command-line arguments"""
    # Prepare environment
    prepare_environment()
    
    # Import main.py
    try:
        import main
    except ImportError as e:
        print(f"Error importing main.py: {e}")
        return {"status": "error", "message": f"Error importing main.py: {e}"}
    
    # Parse arguments
    parser = create_parser()
    args = parser.parse_args()
    
    # Run main.main() with arguments from command line
    try:
        # Create an event loop
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(main.main(
            user_profile_path=args.user_profile_path,
            output_dir=args.output_dir,
            grants_to_process=args.grants_to_process
        ))
        return result
    except Exception as e:
        print(f"Error running main.main(): {e}")
        return {"status": "error", "message": f"Error running main.main(): {e}"}

# Command-line execution
if __name__ == "__main__":
    # Run main.py with command-line arguments
    result = run_main()
    
    # Print result
    if isinstance(result, dict) and "status" in result:
        status = result["status"]
        message = result.get("message", "")
        print(f"Status: {status}")
        if message:
            print(f"Message: {message}")
    else:
        print("Main script completed successfully")