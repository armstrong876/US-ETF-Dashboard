from server import deploy_to_netlify
import os

# Change working directory to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Force deploying current code to Netlify...")
    success, msg = deploy_to_netlify()
    if success:
        print("Successfully deployed!")
    else:
        print(f"Deployment failed: {msg}")
