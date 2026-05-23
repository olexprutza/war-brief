from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic()

message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=100,
    messages=[{"role": "user", "content": "In one sentence, tell me what a BD analyst at a defense tech company does."}]
)

print(message.content[0].text)

