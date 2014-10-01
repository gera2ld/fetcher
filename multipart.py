#!python
# coding=utf-8
# Compatible with Python 2
import os,io,mimetypes,sys
from email.generator import Generator
if sys.version_info>(3,):
	from urllib import request,parse
else:
	import urllib as parse
	import urllib2 as request

def multipart_encode(params, files, boundary=None, buf=None, sep=b'\r\n'):
	if buf is None: buf=[]
	if boundary is None:
		boundary = Generator._make_boundary()
	for(key, value) in params:
		b=[]
		b.append('--'+boundary)
		b.append('Content-Disposition: form-data; name="%s"' % key)
		b.append('')
		b.append(str(value))
		buf.extend(map(str.encode,b))
	for(key, fd) in files:
		if isinstance(fd,tuple):
			filename,data=fd
			try: fd=open(filename,'rb')
			except: pass
		else:
			filename,data=os.path.basename(fd.name),None
		contenttype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
		b=[]
		b.append('--'+boundary)
		b.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
		b.append('Content-Type: '+contenttype)
		b.append('')
		buf.extend(map(str.encode,b))
		if data is None:
			try: data=fd.read()
			except: data=b''
		buf.append(data)
	buf.append(('--%s--' % boundary).encode())
	buf.append(sep)
	return boundary, sep.join(buf)

class MultipartPostHandler(request.BaseHandler):
	# needs to run first
	handler_order = request.HTTPHandler.handler_order - 10
	def http_request(self, req):
		if isinstance(req.data,dict):
			# key:value, key:fd, key:(filename, bindata)
			v_files = []
			v_vars = []
			for(key, value) in req.data.items():
				if isinstance(value,(tuple,io.BufferedReader)):
					v_files.append((key, value))
				else:
					v_vars.append((key, value))
			if v_files or req.get_header('Content-type')=='multipart/form-data':
				boundary, data = multipart_encode(v_vars, v_files)
				req.add_unredirected_header('Content-type','multipart/form-data; boundary='+boundary)
			else:
				data = parse.urlencode(v_vars, True).encode()
				req.add_unredirected_header('Content-type', 'application/x-www-form-urlencoded')
			req.data=data
		elif isinstance(req.data,str):
			req.add_unredirected_header('Content-type', 'text/plain')
			req.data=req.data.encode()
		# bytes will be ignored
		return req
	https_request = http_request

if __name__=="__main__":
	import tempfile
	validatorURL = "http://validator.w3.org/check"
	opener = request.build_opener(MultipartPostHandler)
	def validateFile(url):
		temp = tempfile.mkstemp(suffix=".html")
		os.write(temp[0], opener.open(url).read())
		params = { "ss" : "0",			# show source
				   "doctype" : "Inline",
				   "uploaded_file" : open(temp[1], "rb") }
		open('c:/users/gerald/1.html','wb').write(opener.open(validatorURL, params).read())
	if len(sys.argv)>1:
		for arg in sys.argv[1:]: validateFile(arg)
	else: validateFile("http://www.baidu.com")
