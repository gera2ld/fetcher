#!python
# coding=utf-8
import os, sys
sys.path.append(os.path.dirname(__file__))

import fetcher
fet = fetcher.Fetcher()
res = fet.fetch('http://www.baidu.com')
print(res.status)
print(res.reason)
print(res.encoding)
print(len(res.content))
print(len(res.text))
