from datetime import datetime
from pyowm import OWM
from swarm import Swarm, Agent
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import json
import os
import readline
import uuid

owm_api_key = os.getenv("OWM_API_KEY")
if owm_api_key is None:
    raise ValueError("Please set the OWM_API_KEY environment variable")

owm = OWM(api_key=owm_api_key)
mgr = owm.weather_manager()

slack_token = os.getenv("SLACK_BOT_TOKEN")
if slack_token is None:
    raise ValueError("Please set the SLACK_BOT_TOKEN environment variable")

slack_client = WebClient(token=slack_token)


def instructions(context_variables: dict) -> str:
    name = context_variables["name"]
    user_id = context_variables["user_id"]
    today = context_variables["today"]
    location = context_variables["location"]

    return f"""
        You are a customer service bot.
        Introduce yourself. Always be very brief.
        If a external tool fails to return a result, return a error message stating why.
        After each successful tool call, print a message to the console and ask the user if they want to continue.
        If they say no, ask the user if they want to start over, do not continue with the tool.

        Today's date is {today}.
        Here is some information about the current user:
        name is {name}
        user id is {user_id}
        current location is {location}
    """


def get_weather_for_location_and_date(
    location: str,
    date: str,
) -> str:
    """
    Get the current weather in a given location.
    The location must be a city and the date must be given in the format "YYYY-MM-DD".
    """

    print(f"Fetching forecast for {location} at {date} ☀️")
    try:
        daily_forecaster = mgr.forecast_at_place(location, "daily")
        print("daily_forecaster", daily_forecaster)
        if daily_forecaster is None:
            return json.dumps({"error": "Location not found"})
        weather = daily_forecaster.get_weather_at(date)
        print("weather", weather)
        return json.dumps(
            {
                "location": location,
                "temperature": 0,
                "date": date,
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


def send_slack_message(message: str) -> str:
    """
    Send a message to a Slack channel.
    """
    print(f"Sending message to Slack 📤: {message}")
    try:
        slack_client.chat_postMessage(channel="#customer-support-agent", text=message)
        return json.dumps({"message": "sent message to slack"})
    except SlackApiError as e:
        return json.dumps({"error": str(e)})


def pretty_print_messages(messages) -> None:
    for message in messages:
        if message["role"] != "assistant":
            continue

        print(f"\033[94m{message['sender']}\033[0m:", end=" ")

        if message["content"]:
            print(message["content"])

        tool_calls = message.get("tool_calls") or []
        if len(tool_calls) > 1:
            print()
        for tool_call in tool_calls:
            f = tool_call["function"]
            name, args = f["name"], f["arguments"]
            arg_str = json.dumps(json.loads(args)).replace(":", "=")
            print(f"\033[95m{name}\033[0m({arg_str[1:-1]})")


def run_repl_loop(context_variables={}):
    print("Welcome to Customer Service Bot! 😊")

    HISTORY_FILE = os.path.expanduser("~/.repl_history")
    if os.path.exists(HISTORY_FILE):
        readline.read_history_file(HISTORY_FILE)

    client = Swarm()
    context_variables = {
        "name": "Christopher Lillthors",
        "user_id": uuid.uuid4(),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "location": "Stockholm",
    }

    customer_center_agent = Agent(
        name="Customer Service Agent",
        model="llama3.1",
        instructions=instructions,  # pyright: ignore
        functions=[
            get_weather_for_location_and_date,
            send_slack_message,
        ],  # pyright: ignore
    )

    messages = []
    while True:
        try:
            user_input = input("> ")
            readline.write_history_file(HISTORY_FILE)
            messages.append({"role": "user", "content": user_input})

            response = client.run(
                agent=customer_center_agent,
                messages=messages,
                context_variables=context_variables,
            )

            pretty_print_messages(response.messages)
            messages.extend(response.messages)

            if response.agent:
                customer_center_agent = response.agent
        except (KeyboardInterrupt, EOFError):
            break

    print("Goodbye! 👋")
