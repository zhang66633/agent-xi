#test/hello.py
#我的第一个程序：验证环境

print("="*40)
print("环境检查")
print("="*40)

from re import I
import sys
print(f"python版本：{sys.version}")

try:
    import httpx
    print(f"httpx版本：{httpx.__version__}")
except ImportError:
    print("httpx未安装")    

try:
    import pydantic
    print(f"pydantic版本：{pydantic.__version__}")
except ImportError:
    print("pydantic未安装")

try:
    import dotenv
    print(f"python-dotenv: 已安装")
except ImportError:
    print("dotenv未安装")

print("="*40)
print("环境检查完成")
print("="*40)