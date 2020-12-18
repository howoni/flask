from flask import Flask, render_template, request, jsonify, _app_ctx_stack
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import session, redirect, url_for, escape
from werkzeug.utils import secure_filename
from datetime import timedelta
import sys, sqlite3, time, threading, os, hashlib, json

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] ='/static/picture'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

socketio = SocketIO(app)

DATABASE = './database.db'
THREAD_TIME_NEW = 10
worker = []
roomlist = []

def get_db():
	top = _app_ctx_stack.top
	if not hasattr(top, 'sqlite_db'):
		top.sqlite_db = sqlite3.connect(DATABASE)
	return top.sqlite_db

def query_db(query, args=(), one=False):
	cur = get_db().execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv

def encrypt_sid(data):
	return data

@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=5)

@app.route('/')
def main():
	if 'userid' in session:
		sql = 'select money from user_sender where id= ? limit 1'
		userid = escape(session['userid'])
		r = query_db(sql, (userid,))
		return render_template('donate.html',room=None,money=r[0][0])
	return render_template('index.html',room=None)

@app.route('/ineedmoney', methods=['POST'])
def ineedmoney():
	if 'userid' in session and request.method == 'POST':
		sql = 'update user_sender set money=money+1000 where id=?'
		userid = escape(session['userid'])
		r = query_db(sql, (userid,))
		return jsonify({'result':'good'})
	return jsonify({'result':'bad'})

@app.route('/login', methods=['POST'])
def login():
	if request.method == 'POST':
		data = request.get_json()
		userid = data['userid']
		userpw = hashlib.sha1((data['userpw']+'salt').encode('utf-8')).hexdigest()
		sql = 'select * from user_sender where id=? and password=? limit 1'
		r = query_db(sql, (userid, userpw))
		try:
			if r[0][0] == userid:
				session['userid'] = userid
				return jsonify({'result':'loginok'})
			else:
				return jsonify({'result':'fail'})
		except:
			return jsonify({'result':'fail'})

@app.route('/register', methods=['POST'])
def register():
	def do_reg(userid,userpw):
		sql = 'insert into user_sender(id, password) values(?, ?)'
		try:
			query_db(sql,(userid,userpw))
			return jsonify({'result':'success'})
		except:
			return jsonify({'result':'error'})

	if request.method == 'POST':
		data = request.get_json()
		userid = data['userid']
		userpw = hashlib.sha1((data['userpw']+'salt').encode('utf-8')).hexdigest()
		sql = 'select id from user_sender where id=? limit 1'
		r = query_db(sql, (userid,))
		try:
			if r[0][0] == userid:
				return jsonify({'result':'duplicate'})
		except:
			return do_reg(userid, userpw)
		return do_reg(userid, userpw)

@app.route('/donate', methods=['GET'])
def main_donate():
	if request.method == 'GET':
		if 'userid' in session:
			sql = 'select money from user_sender where id= ? limit 1'
			userid = escape(session['userid'])
			r = query_db(sql, (userid,))
			return render_template('donate.html', userid=userid,room=None,money=r[0][0])
		else:
			return render_template('index.html')

@app.route('/donate/<room>', methods=['GET','POST'])
def donate(room):
	if request.method == 'GET':
		if 'userid' in session:
			userid = escape(session['userid'])
			sql = 'select id, config from user_sender where id = ?'
			r = query_db(sql, (room,))
			sql = 'select money, id from user_sender where id= ? limit 1'
			r2 = query_db(sql, (userid,))
			try:
				if r[0][0] is not None:
					limit = json.loads(r[0][1])['limit']
					pass
				else:
					return render_template('donate.html', userid=userid,room=None,money=r2[0][0])
			except Exception as e:
				print(e)
				return render_template('donate.html', userid=userid,room=None,money=r2[0][0])

			return render_template('donate.html', userid=userid,room=room,money=r2[0][0], limit=limit)
		else:
			return render_template('index.html', roomid=room)

	elif request.method == 'POST':
		if 'userid' in session:
			sql = 'select config from user_sender where id=?'
			r = query_db(sql,(room,))
			try:
				limit = json.loads(r[0][0])['limit']
			except:
				limit = 100
			userid = escape(session['userid'])
			data = request.get_json()
			roomname = encrypt_sid(room)
			sender = data['sender']
			text = data['data']
			money = data['money']
			if money.isdigit() is False:
				return {'result':'bad'}
			if (int(money) % int(limit)) > 0 or int(money) < int(limit):
				return {'result':limit}
			sql = 'select money from user_sender where id= ? limit 1'
			r = query_db(sql, (userid,))
			try:
				if int(r[0][0]) < int(money):
					return {'result':'nomoney'}
			except Exception as e:
				print(e, file=sys.stdout)
				return {'result':'bad'}
			sql = 'insert into to_donate(senderid, receiverid, data, bool, money) values(?,?,?,?,?)'
			query_db(sql,(sender,room,text,0,money))
			sql = 'update user_sender set money=money-? where id=?'
			query_db(sql, (money, userid))
			return { 'result' : 'success' }

@app.route('/view/<viewid>', methods=['GET','POST'])
def view(viewid):
	roomname = encrypt_sid(viewid)
	sql = 'select config from user_sender where id=?'
	r = query_db(sql,(viewid,))
	try:
		data = json.loads(r[0][0])
		img = data['img']
		content = data['content']
		return render_template('view.html',viewid=roomname,realid=viewid,img=img,content=content)
	except:
		return render_template('view.html',viewid=roomname,realid=viewid)

@app.route('/user', methods=['GET','POST'])
def user():
	if 'userid' in session:
		userid = escape(session['userid'])
		sql = 'select money,config from user_sender where id= ? limit 1'
		r = query_db(sql, (userid,))
		try:
			config = json.loads(r[0][1])
			print(config, file=sys.stdout)
			return render_template('user.html', money=r[0][0], user_id=userid, img=config['img'], content=config['content'] , limit=config['limit'])
		except:
			return render_template('user.html', money=r[0][0], user_id=userid)
	else:
		return redirect('/')

@app.route('/user/uploadconfig', methods=['POST'])
def uploadconfig():
	if 'userid' in session:
		data = request.get_json()
		userid = escape(session['userid'])
		user_id = data['user_id']
		if user_id != userid:
			return jsonify({"result":"bad"})
		imgdata = data['img']
		contentdata = data['content']
		limit = data['limit']
		if limit.isalpha():
			return jsonify({"result":"bad"})
		r = json.dumps({'img':imgdata,'content':contentdata,'limit':limit})
		sql = 'update user_sender set config=? where id=?'	
		query_db(sql, (r, userid))
		return jsonify({"result":"good"})
	else:
		return redirect('/')

@socketio.on('alive')
def oooalive(data):
	roomlist.append(data['room'])
	print(data['room'] + ' is alive' ,file=sys.stdout)
	print("alive roomlist", roomlist)

@socketio.on('join')
def ooojoin(data):
	def chk_room_duplicate(roomname):
		tg = 0
		if worker == []:
			return 1
		for i in worker:
			if i[0] == roomname:
				tg = 1
		if tg == 1:
			return 0
		else:
			return 1

	roomname = encrypt_sid(data['room'])
	join_room(roomname)
	emit('welcome', roomname + ' is active', room=roomname)
	if chk_room_duplicate(roomname) == 1:
		donate_que = thread_donate(roomname)
		donate_que.daemon = True
		donate_que.start()
		worker.append([roomname,donate_que,0])
		print(str(roomname) + ' is start', file=sys.stdout)
	else:
		print(str(roomname) + ' is duplicate', file=sys.stdout)

@socketio.on('leave')
def oooleave(data):
	roomname = encrypt_sid(data['room'])
	leave_room(roomname)
	emit(roomname + ' is deactive', room=roomname)
	print(roomname + ' is deactive',file=sys.stdout)

@socketio.on('que')
def ooonew(data):
	data = request.get_json()
	room = data['room']
	return render_template('index.html')

@app.teardown_appcontext
def close_connection(exception):
	top = _app_ctx_stack.top
	if hasattr(top, 'sqlite_db'):
		top.sqlite_db.commit()
		top.sqlite_db.close()

class thread_donate(threading.Thread):
	def query_db2(self,query, args=(), one=False):
		conn = sqlite3.connect('./database.db')
		cur = conn.cursor()
		cur.execute(query, (args,))
		rv = cur.fetchall()
		conn.commit()
		conn.close()
		return (list(rv[0]) if rv else None) if one else rv

	def chkdonate(self,roomname):
		try:
			sql = 'select no, senderid, data, money from to_donate where receiverid = ? and bool = 0 order by no asc limit 1'
			r = self.query_db2(sql,(self.roomname))
			sql = 'update to_donate set bool=1 where no = ?'
			self.query_db2(sql,(r[0][0]))
			return r[0]
		except:
			return None

	def __init__(self, roomname):
		super().__init__()
		self.flag = threading.Event()
		self.roomname = roomname

	def run(self):
		while not self.flag.is_set():
			donate_data = self.chkdonate(self.roomname)
			if donate_data is not None:
				socketio.emit('new', {'images': '', 'sender':donate_data[1], 'data':donate_data[2], 'images':'smile.jpg', 'money':donate_data[3]}, room=self.roomname)
			else:
				socketio.emit('clear', room=self.roomname)
			time.sleep(THREAD_TIME_NEW)

	def terminate(self):
		self.flag.set()

class thread_heartbeat(threading.Thread):
	def clean_room(self):
		tg = 0
		if len(worker) < 1:
			return 1
		print("roomlist : ",roomlist,file=sys.stdout)
		print("heartbeat : ",worker,file=sys.stdout)
		for idx, i in enumerate(worker):
			for j in roomlist:
				if i[0] == j:
					tg = 1
			if tg == 0:
				worker[idx][2] += 1
				if worker[idx][2] > 3:
					worker[idx][1].terminate()
					worker.pop(idx)
			tg = 0

	def __init__(self):
		super().__init__()
		self.flag = threading.Event()

	def run(self):
		print("heart beat XD")
		while not self.flag.is_set():
			if worker != []:
				del roomlist[:]
				for i in worker:
					socketio.emit('heart','r u alive?', room=i[0])
			time.sleep(20)
			self.clean_room()

	def terminate(self):
		self.flag.set()

heartbeat = thread_heartbeat()
heartbeat.daemon = True
heartbeat.start()

socketio.run(app, debug=True, port=8888)

