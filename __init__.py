#!python
# coding=utf-8
# Author: Gerald <gera2ld@163.com>
# Compatible with Python 2
from __future__ import unicode_literals
import json,logging,threading,io,sys,gzip
from . import multipart
from email import message
if sys.version_info>(3,):
	from urllib import request,parse
	from http import cookiejar,client,cookies
	from html import entities
else:
	import urlparse as parse
	import urllib
	parse.quote=lambda s:urllib.quote(s.encode('utf-8'))
	parse.unquote=urllib.unquote
	import urllib2 as request
	import Cookie as cookies
	import cookielib as cookiejar
	import httplib as client
	import htmlentitydefs as entities
	chr=unichr
if sys.version_info>(3,4):
	from html import unescape
else:
	import re
	def unescape(s):
		def sub(m):
			m=m.group(1)
			if m[0]=='#':
				if m[1]=='x':	# hex
					n=int(m[2:],16)
				elif m[1]=='0':	# oct
					n=int(m[2:],8)
				else:			# dec
					n=int(m[1:])
				return chr(n)
			else:
				c=entities.entitydefs.get(m)
				if c is None:
					c='&'+m+';'
				elif isinstance(c,bytes):	# compatible with Python 2
					c=unescape(c.decode('latin-1'))
				return c
		return re.sub(r'&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);',sub,s)

class HostRequired(Exception): pass
class SameHostRequired(Exception): pass
class HTTPError(Exception): pass
class InvalidJSON(Exception): pass
class FetcherError(Exception): pass

class SimpleCookieJar(cookies.SimpleCookie):
	encoding='utf-8'
	def __init__(self, filename=None):
		self.filename=filename
		if filename:
			try: self.load(open(filename,encoding=self.encoding).read())
			except: pass
	def toHeader(self):
		ck=[]
		for i in self:
			# TODO validate cookie
			ck.append('%s=%s' % (i,self[i].value))
		return '; '.join(ck)
	def save(self):
		if self.filename:
			open(self.filename,'w',encoding=self.encoding).write(self.output())

def initLogger(level=logging.NOTSET):
	logging.basicConfig(level=level,format='%(asctime)s - %(levelname)s: %(message)s')

class BaseFetcher:
	encoding='utf-8'
	scheme='http'
	user=None
	bufsize=8192
	host=None
	timeout=10.0
	cookiejar=None
	def __init__(self,host=None,timeout=None):
		self.addheaders=[('Accept-Encoding','gzip')]
		if host: self.host=host
		if timeout is not None: self.timeout=timeout
	def __str__(self):
		return '%s:%s' % (type(self).__name__,self.user)
	def addHeader(self,key,val):
		self.addheaders.append((key,val))
	def addUA_Opera(self,ver=None):
		if ver: ver=ver.lower()
		if ver in ('p','presto'):
			ua='Opera/9.80 (Windows NT 6.1) Presto/2.12.388 Version/12.17'
		else:
			ua='Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.153 Safari/537.36 OPR/22.0.1471.70'
		self.addHeader('User-Agent',ua)
	def save(self, fd, data, charset=None):
		if isinstance(fd,str):
			import os
			f=open(os.path.expanduser(fd),'wb')
		else: f=fd
		if isinstance(data,str): data=data.encode(charset or self.encoding)
		if isinstance(data,bytes): f.write(data)
		else:
			while True:
				buf=data.read(self.bufsize)
				if not buf: break
				f.write(buf)
		if f is not fd: f.close()
	def loadRawBinary(self, *k, **kw):
		r=self.open(*k, **kw)
		g=r.read()
		return r,g
	def loadBinary(self,*k,**kw):
		r,g=self.loadRawBinary(*k,**kw)
		if r.getheader('Content-Encoding')=='gzip':
			b=io.BytesIO(g)
			gz=gzip.GzipFile(fileobj=b)
			g=gz.read()
		return g
	def load(self, *k, **kw):
		charset=kw.pop('charset',None)
		g=self.loadBinary(*k, **kw)
		return g.decode(charset or self.encoding,'replace')
	def loadJSON(self, *k, **kw):
		g=self.load(*k, **kw)
		try:
			g=json.loads(g)
		except:
			raise InvalidJSON(g)
		else:
			return g

class UrllibFetcher(BaseFetcher):
	'''Keep-alive connection not supported.'''
	handlers=[]
	def initCookieJar(self,user,domain):
		self.cookiejar=cookiejar.LWPCookieJar('%s@%s.lwp' % (parse.quote(user),domain))
		try: self.cookiejar.load(ignore_discard=True)
		except: pass
	def open(self, url, data=None, headers={}, params=None, timeout=None):
		if self.host: url=parse.urljoin(self.scheme+'://'+self.host,url)
		# Response object
		if params:
			if not isinstance(params,str):
				params=parse.urlencode(params)
			url='%s?%s' % (url, params)
		req=request.Request(url,None,headers)
		# Build opener
		handlers=[multipart.MultipartPostHandler]
		if self.cookiejar is None:
			self.cookiejar=cookiejar.CookieJar()
		handlers.append(request.HTTPCookieProcessor(self.cookiejar))
		handlers.extend(self.handlers)
		opener=request.build_opener(*handlers)
		if self.addheaders: opener.addheaders=self.addheaders
		if timeout is None: timeout=self.timeout
		try: r=opener.open(req,data,timeout=timeout)
		except Exception as e:
			logging.debug(e)
			raise e
		else:
			if isinstance(self.cookiejar,cookiejar.LWPCookieJar):
				self.cookiejar.save(ignore_discard=True)
			return r

class HttpFetcher(BaseFetcher):
	'''Keep-alive connection supported.'''
	local=threading.local()
	def __init__(self,host=None,timeout=None):
		super().__init__(host,timeout)
		if self.host is None: raise HostRequired
	def initCookieJar(self,user,domain):
		self.cookiejar=SimpleCookieJar('%s@%s.cookie' % (parse.quote(user),domain))
	def open(self, url, data=None, headers={'Connection':'Keep-alive'},
			params=None, timeout=None, ignore_error=False):
		loop=getattr(self.local,'loop',0)
		if loop>200: raise FetcherError('Too many loops.')
		# Response object
		if not url.startswith('/'):
			pref=self.scheme+'://'+self.host
			if url.startswith(pref): url=url[len(pref):]
			else: raise SameHostRequired(url)
		if params:
			if not isinstance(params,str):
				params=parse.urlencode(params)
			url='%s?%s' % (url, params)
		_headers=message.Message()
		# add default headers
		for i in self.addheaders:
			_headers[i[0]]=i[1]
		# add user headers
		for i in headers:
			_headers[i]=headers[i]
		# add cookies
		if self.cookiejar is None:
			self.cookiejar=SimpleCookieJar()
		ck=self.cookiejar.toHeader()
		if ck: _headers['Cookie']=ck
		ct=_headers.get('Content-type')
		del _headers['Content-type']
		if isinstance(data,dict):
			# key:value, key:fd, key:(filename, bindata)
			v_files = []
			v_vars = []
			for(key, value) in data.items():
				if isinstance(value,(tuple,io.BufferedReader)):
					v_files.append((key, value))
				else:
					v_vars.append((key, value))
			if v_files or _headers.get('Content-type')=='multipart/form-data':
				boundary, data = multipart.multipart_encode(v_vars, v_files)
				subtype='form-data' if len(v_files)==1 else 'mixed'
				ct='multipart/%s; boundary=%s' % (subtype,boundary)
			else:
				data = parse.urlencode(v_vars, True).encode()
				ct='application/x-www-form-urlencoded'
		elif isinstance(data,str):
			ct='text/plain'
			data=data.encode()
		if ct: _headers['Content-type']=ct
		method='GET' if data is None else 'POST'
		try:
			self.local.con.request(method,url,data,_headers)
			r=self.local.con.getresponse()
		except:
			c=client.HTTPSConnection if self.scheme=='https' else client.HTTPConnection
			self.local.con=c(self.host,timeout=timeout)
			self.local.con.request(method,url,data,_headers)
			r=self.local.con.getresponse()
		for c in r.getheader('Set-Cookie','').split(','):
			self.cookiejar.load(c)
		if isinstance(self.cookiejar,SimpleCookieJar):
			self.cookiejar.save()
		if r.status>300 and r.status<304:	# redirect
			l=r.getheader('Location','')
			self.local.loop=loop+1
			return self.open(l,timeout=timeout,ignore_error=ignore_error)
		elif not ignore_error and r.status>300:	# error
			raise HTTPError(r.status)
		return r
	def loadRawBinary(self,*k,**kw):
		r,g=super().loadRawBinary(*k,**kw)
		if r.closed or r.getheader('Connection')=='close':
			try: self.local.con.close()
			except: pass
			self.local.con=None
		return r,g

# Set default fetcher
Fetcher=UrllibFetcher
