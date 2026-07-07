import json

api_response = '''
{
    "choices":[
        {
            "message": {
                "role" : "assistant",
                "content": "hello,world!"
            }
        }
    ]
}
'''
data = json.loads(api_response)
content = data["choices"][0]["message"]["content"]
print(content)