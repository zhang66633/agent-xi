#我的第一个Agent:调用Deepseek，单论对话
#目标：理解“发HTTP请求”和“读JSON响应“这两件事

import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY= os.getenv("DEEPSEEK_API_KEY")

if not API_KEY:
    print("❌  错误：没找到DEEPSEEK_API_KEY")
    print("    请在.env文件中设置DEEPSEEK_API_KEY")
    print("    DEEPSEEK_API_KEY=sk-××xxxx")
    exit(1)

async def chat(message: str) -> str:
    """发一条消息给Deepseek，返回它的回复"""

    #异步HTTP客户端（async with 确保连接会关闭）
    async with httpx.AsyncClient() as client:

        #发POST请求到Deepseek API
        response = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization" : f"Bearer {API_KEY}", #鉴权
                "Content-Type" : "application/json" ,  #告诉服务器发的是JSON
            },
            json={
                "model": "deepseek-v4-pro",
                "messages":[
                    {"role": "user", "content": message}
                ],
            },
            timeout=30.0,
        )

        if response.status_code !=200:
            return f"❌  错误：{response.status_code}\n{response.text}"

        #解析 JSON 响应
        data = response.json()

        #从JSON里提取回复内容
        #data结构：{"choices":[{"message":{"content":"回复内容}]}
        return data["choices"][0]["message"]["content"]

async def main():
    print("="*50)
    print("   我的第一个agent(单论对话)")
    print("="*50)
    print()

    # 固定的测试问题
    user_input = "今天南京天气怎么样？"
    print(f"我：{user_input}")
    print()
    print("XI：",end="",flush=True)

    # 调用Agent
    reply = await chat(user_input)

    # 打印回复
    print(reply)
    print()
    print("="*50)
    print("恭喜！你的第一个agent成功了！")
    

# 程序的入口
if __name__ == "__main__":
    # asyncio.run(0) 会运行异步函数并等待它完成
    asyncio.run(main())
