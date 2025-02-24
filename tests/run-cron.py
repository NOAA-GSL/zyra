import subprocess
import time

# Path to the cron file
cron_file = "/etc/cron.d/real-time-video"

# Function to simulate running the crontab commands with retries
def run_cron_commands(file_path, max_retries=5, retry_delay=5):
    try:
        with open(file_path, "r") as file:
            for line in file:
                # Skip empty lines and comments
                if not line.strip() or line.startswith("#"):
                    continue

                # Print the original line for debugging
                print(f"Original line: {line.strip()}")

                # Strip the first 16 characters (assumed to be cron time and user fields)
                command = line[16:].strip()

                # Print the command for logging purposes
                print(f"Running: {command}")

                # Retry mechanism
                retries = 0
                while retries < max_retries:
                    try:
                        # Execute the command using subprocess
                        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        print(f"Command executed successfully: {result.stdout.decode('utf-8')}")
                        break  # If successful, exit the loop
                    except subprocess.CalledProcessError as e:
                        retries += 1
                        print(f"Error: Command failed (attempt {retries}) - {command}")
                        print(f"Error details: {e.stderr.decode('utf-8')}")
                        
                        if retries < max_retries:
                            print(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)  # Wait before retrying
                        else:
                            print(f"Max retries reached. Command failed permanently: {command}")
                            break

    except FileNotFoundError:
        print(f"Cron file {file_path} not found!")
    except Exception as e:
        print(f"An error occurred: {e}")

# Run the cron simulation with retry mechanism
run_cron_commands(cron_file, max_retries=5, retry_delay=5)
