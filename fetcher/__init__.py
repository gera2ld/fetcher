#!python
# coding=utf-8
# Author: Gerald <gera2ld@163.com>
import json, logging, threading, io, sys, gzip, time, queue, re
from . import multipart
from urllib import request, parse, error
from http import cookiejar, client
if sys.version_info > (3, 4):
	from html import unescape
else:
	from html import entities
	def unescape(s):
		def sub(m):
			m=m.group(1)
			if m[0] == '#':
				if m[1] == 'x':	# hex
					n = int(m[2:], 16)
				elif m[1] == '0':	# oct
					n = int(m[2:], 8)
				else:			# dec
					n = int(m[1:])
				return chr(n)
			else:
				c = entities.entitydefs.get(m)
				if c is None:
					c='&' + m + ';'
				return c
		return re.sub(r'&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);', sub, s)

__all__ = ['unescape', 'InvalidJSON', 'KeepAliveHandler', 'Fetcher']
logger = logging.getLogger(__package__)
ENC = 'utf-8'

def dump(fd, data, charset=None):
	if isinstance(fd, str):
		import os
		f=open(os.path.expanduser(fd), 'wb')
	else:
		f=fd
	if isinstance(data, str):
		data=data.encode(charset or ENC)
	if isinstance(data, bytes):
		f.write(data)
	else:
		while True:
			buf = data.read(self.bufsize)
			if not buf: break
			f.write(buf)
	if f is not fd:
		f.close()

class InvalidJSON(Exception): pass

class Response:
	encoding = ENC
	def __init__(self, response):
		'''
		response is a http.client.HTTPResponse object
		'''
		self.__response = response
		content = response.read()
		if response.getheader('Content-Encoding') == 'gzip':
			b = io.BytesIO(content)
			gz = gzip.GzipFile(fileobj=b)
			content = gz.read()
		contenttype = response.getheader('Content-Type')
		m = re.search(';\s*charset\s*=\s*(\S+)', contenttype, re.I)
		if m:
			self.encoding = m.group(1)
		self.__content = content
		self.status = response.status
		self.reason = response.reason

	@property
	def raw(self):
		return self.__response

	@property
	def url(self):
		return self.__response.full_url

	@property
	def content(self):
		return self.__content

	@property
	def text(self):
		return self.__content.decode(self.encoding, 'replace')

	def json(self):
		text = self.text
		try:
			return json.loads(text)
		except:
			raise InvalidJSON(text)

	def dump(self, fd):
		dump(fd, self.__content)

class KeepAliveHandler(request.HTTPHandler):
	timeout = 10

	def __init__(self, timeout=None):
		if timeout is not None:
			self.timeout = timeout
		self.cache = {}

	def get_connection(self, host, http_class, req):
		cons = self.cache.get(host)
		if cons is None:
			cons = self.cache[host] = queue.Queue()
		now = time.time()
		try:
			while True:
				con, ts = cons.get_nowait()
				if ts < now:
					con.close()
				else:
					break
			logger.debug('reused connection')
		except queue.Empty:
			con = http_class(host, timeout = req.timeout)
			logger.debug('new connection')
		return con

	def cache_connection(self, host, con):
		logger.debug('cached connection')
		self.cache[host].put_nowait((con, time.time() + self.timeout))

	def do_open(self, http_class, req, **http_conn_args):
		host = req.host
		if not host:
			raise error.URLError('no host given')
		con = self.get_connection(host, client.HTTPConnection, req)
		headers = dict(req.headers)
		headers.update(req.unredirected_hdrs)
		headers['Connection'] = 'keep-alive'
		headers = dict((name.title(), val) for name, val in headers.items())

		if req._tunnel_host:
			tunnel_headers = {}
			proxy_auth_hdr = "Proxy-Authorization"
			if proxy_auth_hdr in headers:
				tunnel_headers[proxy_auth_hdr] = headers[proxy_auth_hdr]
				# Proxy-Authorization should not be sent to origin
				# server.
				del headers[proxy_auth_hdr]
			con.set_tunnel(req._tunnel_host, headers = tunnel_headers)

		try:
			try:
				con.request(req.get_method(), req.selector, req.data, headers)
			except OSError as err: # timeout error
				raise error.URLError(err)
			r = con.getresponse()
		except:
			con.close()
			raise

		if con.sock:
			self.cache_connection(host, con)

		r.url = req.get_full_url()
		r.msg = r.reason
		return r

class Fetcher:
	scheme = 'http'
	user = None
	bufsize = 8192
	host = None
	timeout = 10.0
	cookiejar = None

	def __init__(self, host = None, scheme = None, timeout = None, keepAliveTimeout = None):
		'''
		host is the default host to use when no host is assigned.
		>>> fet = Fetcher('www.baidu.com')
		>>> res = fet.fetch('/')
		'''
		self.addheaders = [('Accept-Encoding', 'gzip,deflate')]
		self.handlers = [
			KeepAliveHandler(keepAliveTimeout),
			multipart.MultipartPostHandler,
		]
		self.host = host
		if scheme:
			self.scheme = scheme
		if timeout is not None:
			self.timeout = timeout

	def __str__(self):
		return '%s:%s' % (type(self).__name__, self.user)

	def initCookieJar(self, user, domain):
		'''
		Initiate a LWPCookieJar saved in {user}@{domain}.lwp
		'''
		self.cookiejar = cookiejar.LWPCookieJar(
				'%s@%s.lwp' % (parse.quote_plus(user), domain))
		try:
			self.cookiejar.load(ignore_discard = True)
		except:
			pass
		self.handlers.append(request.HTTPCookieProcessor(self.cookiejar))

	def addHeader(self, key, val):
		self.addheaders.append((key, val))

	def addUA_Opera(self, ver = None):
		if ver and ver.lower() in ('p', 'presto'):
			ua = 'Opera/9.80 (Windows NT 6.1) Presto/2.12.388 Version/12.17'
		else:
			ua = 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36 OPR/26.0.1656.60'
		self.addHeader('User-Agent', ua)

	def fetch(self, url, data=None, headers={}, params=None, timeout=None):
		if self.host:
			url = parse.urljoin(self.scheme + '://' + self.host, url)
		# Response object
		if params:
			if not isinstance(params, str):
				params = parse.urlencode(params)
			url += '?' + params
		req = request.Request(url, data, headers)
		# Build opener
		if self.cookiejar is None:
			self.cookiejar = cookiejar.CookieJar()
			self.handlers.append(request.HTTPCookieProcessor(self.cookiejar))
		opener = request.build_opener(*self.handlers)
		if self.addheaders:
			opener.addheaders = self.addheaders
		if timeout is None:
			timeout = self.timeout
		try:
			res = opener.open(req, timeout = timeout)
		except Exception as e:
			logger.debug(e)
			raise e
		if isinstance(self.cookiejar, cookiejar.LWPCookieJar):
			self.cookiejar.save(ignore_discard = True)
		return Response(res)

	def getCookie(self, name, default = None):
		if self.cookiejar:
			for cookie in self.cookiejar:
				if cookie.name == name:
					return cookie.value
		return default
