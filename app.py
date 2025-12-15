import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
import uuid
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-this-with-a-secure-random-string"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

sessions = {}

def new_session(name):
    sid = str(uuid.uuid4())[:8]
    sessions[sid] = {
        "name": name or f"Session {sid}",
        "host": None,
        "items": [],
        "clients": {},
        "reveal": False,
        "created": time.time(),
    }
    return sid

def new_item(title, description=""):
    return {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "created": time.time(),
        "votes": {},
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/host", methods=["GET", "POST"])
def host():
    if request.method == "POST":
        name = request.form.get("session_name") or "Planning Poker"
        sid = new_session(name)
        return redirect(url_for("host_room", session_id=sid))
    return render_template("host.html")

@app.route("/host/<session_id>")
def host_room(session_id):
    s = sessions.get(session_id)
    if not s:
        return "Session not found", 404
    return render_template("host.html", session_id=session_id, session=s)

@app.route("/join", methods=["GET", "POST"])
def join():
    if request.method == "POST":
        session_id = request.form.get("session_id")
        name = request.form.get("name") or "Guest"
        return redirect(url_for("join_room_page", session_id=session_id, name=name))
    return render_template("join.html")

@app.route("/join/<session_id>")
def join_room_page(session_id):
    name = request.args.get("name") or "Guest"
    s = sessions.get(session_id)
    if not s:
        return "Session not found", 404
    return render_template("join.html", session_id=session_id, name=name)

@socketio.on("create_or_join")
def on_create_or_join(data):
    name = data.get("name") or "Guest"
    requested = data.get("session_id")
    as_host = bool(data.get("as_host"))

    if requested:
        sid = requested
        s = sessions.get(sid)
        if not s:
            emit("error", {"message": "Session not found"})
            return
    else:
        sid = new_session(name)
        s = sessions[sid]

    client_id = str(uuid.uuid4())[:8]
    s["clients"][client_id] = {"name": name}
    if as_host:
        s["host"] = client_id

    join_room(sid)
    emit("joined", {"session_id": sid, "client_id": client_id, "session": s})
    emit("client_list", {"clients": s["clients"]}, room=sid)

@socketio.on("add_item")
def on_add_item(data):
    s = sessions.get(data.get("session_id"))
    if not s:
        return
    item = new_item(data.get("title"), data.get("description"))
    s["items"].append(item)
    emit("item_added", {"item": item}, room=data.get("session_id"))

@socketio.on("vote")
def on_vote(data):
    s = sessions.get(data.get("session_id"))
    if not s:
        return
    item = next((i for i in s["items"] if i["id"] == data.get("item_id")), None)
    if not item:
        return
    item["votes"][data.get("client_id")] = data.get("vote")
    emit("vote_update", {"item_id": item["id"], "votes": item["votes"]}, room=data.get("session_id"))

if __name__ == "__main__":
    socketio.run(app, debug=True)
