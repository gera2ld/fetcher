fetcher
===
requires: Python 3

Installation
---
Install the package:
``` sh
$ python3 setup.py install
```
or just copy the `fetcher` folder to your project.

Usage
---
``` python
import fetcher
fet = fetcher.Fetcher()
res = fet.fetch('http://www.google.com')
print(res.status)
print(res.reason)

# get binary
print(res.raw())

# get text
print(res.text())
# get text with specified charset
print(res.text(charset='utf-8'))

# get json
print(res.json())

# save response to a file
res.dump('response.html')
# or
fetcher.dump('response.html', res.raw())
```
